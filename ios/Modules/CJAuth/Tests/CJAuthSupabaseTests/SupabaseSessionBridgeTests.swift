import Foundation
import Auth
import CJAuth
import CJSession
import Testing
@testable import CJAuthSupabase

@MainActor private final class SessionMemory: SessionPersistence {
    var material: SessionMaterial?
    var saves = 0
    var clears = 0
    var failClear = false
    func load() throws -> SessionMaterial? { material }
    func save(_ material: SessionMaterial) throws { self.material = material; saves += 1 }
    func clearAndBlock() throws {
        if failClear { throw SessionFailure.storageUnavailable }
        material = nil; clears += 1
    }
}
@Suite @MainActor struct SupabaseSessionBridgeTests {
    func session(_ id: UUID, refresh: String = "SYNTHETIC-REFRESH-NOT-A-TOKEN") -> Session {
        Session(accessToken: "SYNTHETIC-ACCESS-NOT-A-TOKEN", tokenType: "bearer", expiresIn: 3600,
                expiresAt: Date().timeIntervalSince1970+3600, refreshToken: refresh,
                user: User(id: id, appMetadata: [:], userMetadata: [:], aud: "synthetic",
                           createdAt: Date(), updatedAt: Date()))
    }
    private func seeded(_ id: UUID) throws -> (SessionMemory, SessionLifecycle, SessionOperation, SessionMaterial) {
        let memory = SessionMemory(); let lifecycle = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let op = try lifecycle.beginTrustedSDKSave()
        #expect(SupabaseSessionBridge.saveTrustedSDKSession(session(id), lifecycle: lifecycle,
                operation: op, expectedUserID: id, uiIsCurrent: { true }) == .stored)
        let load = try lifecycle.beginUserRestore()
        let bytes = try lifecycle.load(for: load)
        return (memory, lifecycle, load, try #require(bytes))
    }
    @Test func officialSessionRoundTripAndRefreshUsesTwoPhaseCommit() async throws {
        let id = UUID(); let (memory, life, op, material) = try seeded(id); var calls = 0
        let bridge = SupabaseSessionBridge(lifecycle: life, operation: op, expectedUserID: id, uiIsCurrent: { true }, verify: { original, reason in
            calls += 1
            #expect(original.refreshToken == "SYNTHETIC-REFRESH-NOT-A-TOKEN")
            #expect(reason == .refresh)
            return .verified(session(id, refresh: "SYNTHETIC-ROTATED-NOT-A-TOKEN"))
        })
        #expect(await bridge.revalidate(material, reason: .refresh) == .readyToSave)
        #expect(life.isCurrent(op) && memory.saves == 1)
        #expect(await bridge.revalidate(material, reason: .refresh) == .readyToSave)
        #expect(calls == 1 && bridge.persistVerified() == .stored)
        #expect(memory.saves == 2 && bridge.persistVerified() == .stale)
        let saved = try #require(memory.material)
        let decoded = try saved.withBytes { try AuthClient.Configuration.jsonDecoder.decode(Session.self, from: $0) }
        #expect(decoded.refreshToken == "SYNTHETIC-ROTATED-NOT-A-TOKEN")
        #expect(!bridge.canUseRestrictedBusiness)
    }
    @Test func unknownPreservesSessionAndDoesNotRepeatSDK() async throws {
        let id = UUID(); let (memory, life, op, material) = try seeded(id); var calls = 0
        let bridge = SupabaseSessionBridge(lifecycle: life, operation: op, expectedUserID: id, uiIsCurrent: { true }, verify: { _,_ in calls += 1; return .unknown })
        #expect(await bridge.revalidate(material, reason: .backgroundRevalidation) == .networkUnknown)
        #expect(await bridge.revalidate(material, reason: .backgroundRevalidation) == .networkUnknown)
        #expect(memory.saves == 1 && memory.clears == 0 && life.isCurrent(op) && calls == 1)
        #expect(bridge.clearAuthoritativelyInvalid() == .stale)
    }
    @Test func explicitInvalidIsNotDeletionUntilHostCommits() async throws {
        let id = UUID(); let (memory, life, op, material) = try seeded(id)
        let bridge = SupabaseSessionBridge(lifecycle: life, operation: op, expectedUserID: id, uiIsCurrent: { true }, verify: { _,_ in .invalid })
        #expect(await bridge.revalidate(material, reason: .explicitRestore) == .identityInvalid)
        #expect(memory.clears == 0 && life.isCurrent(op))
        memory.failClear = true
        #expect(bridge.clearAuthoritativelyInvalid() == .storageFailure(.storageUnavailable))
        #expect(life.state == .blocked(.storageUnavailable))
    }
    @Test func lateOldScopeAndUIResultsCannotClearOrSave() async throws {
        let id = UUID(); let (memory, life, op, material) = try seeded(id)
        var gate: CheckedContinuation<SDKSessionCheck,Never>?
        var ui = true
        let bridge = SupabaseSessionBridge(lifecycle: life, operation: op, expectedUserID: id, uiIsCurrent: { ui }, verify: { _,_ in await withCheckedContinuation { gate = $0 } })
        let task = Task { await bridge.revalidate(material, reason: .refresh) }
        for _ in 0..<10000 { if gate != nil { break }; await Task.yield() }
        let completion = try #require(gate)
        ui = false; try life.clear()
        completion.resume(returning: .verified(session(UUID())))
        #expect(await task.value == .stale)
        #expect(bridge.persistVerified() == .stale && bridge.clearAuthoritativelyInvalid() == .stale)
        #expect(memory.saves == 1 && memory.clears == 1)
    }
    @Test func absentHookMalformedDataAndWrongUserCannotActivate() async throws {
        let id = UUID(); let (memory, life, op, material) = try seeded(id)
        let disabled = SupabaseSessionBridge(lifecycle: life, operation: op, expectedUserID: id, uiIsCurrent: { true })
        #expect(await disabled.revalidate(material, reason: .explicitRestore) == .unavailable)
        var calls = 0
        let malformed = SupabaseSessionBridge(lifecycle: life, operation: op, expectedUserID: id, uiIsCurrent: { true }, verify: { _,_ in calls += 1; return .unknown })
        let bytes = try SessionMaterial(trustedSDKBytes: Data([1,2,3]))
        #expect(await malformed.revalidate(bytes, reason: .explicitRestore) == .malformedMaterial)
        let wrongOperation = try life.beginUserRestore()
        let wrong = SupabaseSessionBridge(lifecycle: life, operation: wrongOperation, expectedUserID: UUID(), uiIsCurrent: { true }, verify: { _,_ in calls += 1; return .unknown })
        #expect(await wrong.revalidate(material, reason: .explicitRestore) == .identityMismatch)
        #expect(calls == 0 && memory.saves == 1 && memory.clears == 0)
    }
    @Test func originalOperationCannotBeRevalidatedBySecondBridge() async throws {
        let id = UUID(); let (_, life, op, material) = try seeded(id); var calls = 0
        let first = SupabaseSessionBridge(lifecycle: life, operation: op, expectedUserID: id, uiIsCurrent: { true }, verify: { _,_ in calls += 1; return .unknown })
        let second = SupabaseSessionBridge(lifecycle: life, operation: op, expectedUserID: id, uiIsCurrent: { true }, verify: { _,_ in calls += 1; return .unknown })
        #expect(await first.revalidate(material, reason: .refresh) == .networkUnknown)
        #expect(await second.revalidate(material, reason: .refresh) == .operationConflict)
        #expect(calls == 1)
    }
    @Test func uiPredicateReentryCannotRebindOldVerifiedSessionToNewOperation() async throws {
        let id = UUID(); let (memory, life, op, material) = try seeded(id); var reenter = false
        let bridge = SupabaseSessionBridge(lifecycle: life, operation: op, expectedUserID: id,
            uiIsCurrent: { if reenter { try? life.clear() }; return true },
            verify: { _,_ in .verified(session(id)) })
        #expect(await bridge.revalidate(material, reason: .refresh) == .readyToSave)
        reenter = true
        #expect(bridge.persistVerified() == .stale)
        #expect(memory.saves == 1 && memory.clears == 1)
    }
    @Test func actualSDKDecodedSyntheticSessionReachesBoundStorageOnce() async throws {
        let id = UUID(); let synthetic = session(id)
        let payload = try AuthClient.Configuration.jsonEncoder.encode(synthetic)
        let memory = SessionMemory(); let lifecycle = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let save = try lifecycle.beginTrustedSDKSave(); let flow = AuthFlow()
        var callbacks = 0; var stored: SessionBridgeResult?
        let adapter = SupabaseSDKAdapter(configuration: .init(authURL: URL(string: "https://synthetic.invalid/auth/v1"), publicKey: "sb_publishable_SYNTHETIC_NOT_A_KEY"),
            fetch: { request in (payload, HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type":"application/json"])!) },
            isCurrent: { flow.pending == $0 },
            onSessionForSecureStorage: { sdkSession, attempt in
                callbacks += 1
                stored = SupabaseSessionBridge.saveTrustedSDKSession(sdkSession, lifecycle: lifecycle, operation: save,
                    expectedUserID: id, uiIsCurrent: { flow.pending == attempt })
            }, material: { .email(attempt: $0, address: "synthetic@example.invalid", password: "synthetic-not-a-password") })
        let attempt = try #require(flow.begin(.emailSignIn, using: adapter))
        #expect(await adapter.perform(attempt) == .identityNeedsServerCheck)
        #expect(await adapter.perform(attempt) == .identityNeedsServerCheck)
        #expect(callbacks == 1 && memory.saves == 1 && stored == .stored)
        #expect(!flow.canUseRestrictedBusiness)
    }
    @Test func existingTrailingMaterialClosureStillCompilesAndStaysDisabled() {
        let adapter = SupabaseSDKAdapter(configuration: .init(), isCurrent: { _ in false }) { _ in nil }
        #expect(adapter.unavailableReason(for: .emailSignIn) == .missingConfiguration)
    }
    @Test func staleInitialSDKSaveAndChangedDuplicateAreRejected() async throws {
        let id = UUID(); let (memory, life, op, material) = try seeded(id)
        let bridge = SupabaseSessionBridge(lifecycle: life, operation: op, expectedUserID: id, uiIsCurrent: { true }, verify: { _,_ in .unknown })
        #expect(await bridge.revalidate(material, reason: .refresh) == .networkUnknown)
        #expect(await bridge.revalidate(material, reason: .backgroundRevalidation) == .operationConflict)
        let old = try life.beginTrustedSDKSave(); try life.clear()
        #expect(SupabaseSessionBridge.saveTrustedSDKSession(session(id), lifecycle: life, operation: old,
                expectedUserID: id, uiIsCurrent: { true }) == .stale)
        #expect(memory.saves == 1)
    }
}
