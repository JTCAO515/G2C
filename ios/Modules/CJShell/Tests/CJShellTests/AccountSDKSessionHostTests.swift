import Foundation
import Testing
import Auth
import CJAuth
import CJAuthSupabase
import CJSession
@testable import CJShell

@MainActor private final class HostSessionMemory: SessionPersistence {
    var material: SessionMaterial?
    var loads = 0, saves = 0, clears = 0
    var failSave = false, failClear = false
    var onSave: (() -> Void)?
    func load() throws -> SessionMaterial? { loads += 1; return material }
    func save(_ value: SessionMaterial) throws {
        saves += 1
        let callback = onSave; onSave = nil; callback?()
        if failSave { throw SessionFailure.storageUnavailable }
        material = value
    }
    func clearAndBlock() throws {
        clears += 1
        if failClear { throw SessionFailure.storageUnavailable }
        material = nil
    }
}
/// This simulates one trusted service verification flow; it is NOT production JWT verification.
@MainActor private final class SyntheticVerificationFlow: AccountSessionVerification {
    var generation = UUID()
    var verifiedUserID: UUID?
    var initialCalls = 0, restoreCalls = 0
    var initialHook: ((Session, AuthAttempt) async -> SDKSessionCheck)?
    var restoreHook: ((Session, SessionRevalidationReason) async -> SDKSessionCheck)?
    init(_ id: UUID?) { verifiedUserID = id }
    func verifyInitialSession(_ candidate: Session, attempt: AuthAttempt) async -> SDKSessionCheck {
        initialCalls += 1
        return await initialHook?(candidate, attempt) ?? .verified(candidate)
    }
    func revalidateSession(_ candidate: Session, reason: SessionRevalidationReason) async -> SDKSessionCheck {
        restoreCalls += 1
        return await restoreHook?(candidate, reason) ?? .verified(candidate)
    }
}
private actor SDKFetchCounter {
    var calls = 0
    func called() { calls += 1 }
}

@Suite @MainActor struct AccountSDKSessionHostTests {
    private func shell() throws -> ShellState {
        ShellState(preferences: try #require(UserDefaults(suiteName: "cj006.sdkhost." + UUID().uuidString)))
    }
    private func sdkSession(_ id: UUID, version: String = "A") -> Session {
        Session(accessToken: "SYNTHETIC-ACCESS-"+version, tokenType: "bearer", expiresIn: 3600,
            expiresAt: Date().timeIntervalSince1970+3600, refreshToken: "SYNTHETIC-REFRESH-"+version,
            user: User(id: id, appMetadata: [:], userMetadata: [:], aud: "synthetic",
                createdAt: Date(), updatedAt: Date()))
    }
    private func config() -> SupabaseAdapterConfiguration {
        .init(authURL: URL(string:"https://synthetic.invalid/auth/v1"), publicKey:"sb_publishable_SYNTHETIC_NOT_A_KEY")
    }
    private func material(_ value: Session) throws -> SessionMaterial {
        try SessionMaterial(trustedSDKBytes: AuthClient.Configuration.jsonEncoder.encode(value))
    }
    private func sameBytes(_ a: SessionMaterial?, _ b: SessionMaterial?) -> Bool {
        guard let a, let b else { return a == nil && b == nil }
        return a.withBytes { first in b.withBytes { first == $0 } }
    }
    private func wait(_ condition: () -> Bool) async {
        for _ in 0..<5000 { if condition() { return }; await Task.yield() }
        #expect(condition(), "Synthetic SDK/host operation did not reach expected state")
    }
    private func response(_ payload: Data, _ counter: SDKFetchCounter) -> AuthFetch {
        { request in
            await counter.called()
            return (payload, HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type":"application/json"])!)
        }
    }
    @Test func actualSDKLoginVerifiesThenStoresOnlyOnceWithoutGrant() async throws {
        let id = UUID(), flow = SyntheticVerificationFlow(nil), memory = HostSessionMemory(), counter = SDKFetchCounter()
        flow.verifiedUserID = id // explicitly supplied by synthetic trusted service flow, not candidate/cache
        let lifecycle = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let ui = try shell(), payload = try AuthClient.Configuration.jsonEncoder.encode(sdkSession(id))
        var duplicateCallbacks = 0
        let host = AccountHost(shell: ui, session: lifecycle, sessionVerification: flow) { channel, current in
            SupabaseSDKAdapter(configuration: config(), fetch: response(payload, counter), isCurrent: current,
                onSessionForSecureStorage: { value, attempt in
                    duplicateCallbacks += 2
                    channel.receiveSDKSession(value, for: attempt)
                    channel.receiveSDKSession(value, for: attempt)
                }, material: { attempt in
                    guard let input = channel.take(for: attempt) else { return nil }
                    return .email(attempt: attempt, address: input.address, password: input.password)
                })
        }
        flow.initialHook = { candidate, _ in
            #expect(memory.saves == 0 && host.committedSessionOperation == nil)
            return .verified(candidate)
        }
        var password = "SYNTHETIC-NOT-A-PASSWORD"
        host.submit(.emailSignIn, email:"synthetic@example.invalid", password:&password)
        host.submit(.emailSignIn, email:"synthetic@example.invalid", password:&password)
        await wait { !host.isWaiting }
        #expect(password.isEmpty && duplicateCallbacks == 2 && flow.initialCalls == 1)
        #expect(await counter.calls == 1)
        #expect(memory.saves == 1 && host.sessionBridgeResult == .stored)
        let published = try #require(host.committedSessionOperation)
        #expect(lifecycle.isCurrent(published) && host.localSessionStatus == .needsVerification)
        #expect(host.state == .identityNeedsServerCheck && !host.canUseRestrictedBusiness)
    }
    @Test func missingTrustedIdentityRejectsBeforeSDKOrStore() async throws {
        let ui = try shell(), memory = HostSessionMemory(), flow = SyntheticVerificationFlow(nil), counter = SDKFetchCounter()
        let lifecycle = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let payload = try AuthClient.Configuration.jsonEncoder.encode(sdkSession(UUID()))
        let host = AccountHost(shell: ui, session: lifecycle, sdkConfiguration: config(), verification: flow, fetch: response(payload,counter))
        var password = "SYNTHETIC-NOT-A-PASSWORD"
        host.submit(.emailSignIn,email:"synthetic@example.invalid",password:&password); host.restoreSession()
        #expect(host.state == .unavailable(.hostCapabilityRequired) && !host.canRestoreSession)
        #expect(await counter.calls == 0)
        #expect(memory.loads == 0 && memory.saves == 0 && memory.clears == 0 && flow.initialCalls == 0)
    }
    @Test func restorationCommitsAfterVerificationAndAdoptsCommittedOperation() async throws {
        let id = UUID(), memory = HostSessionMemory(), flow = SyntheticVerificationFlow(nil)
        flow.verifiedUserID = id; memory.material = try material(sdkSession(id))
        let life = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let host = AccountHost(shell: try shell(), session: life, sdkConfiguration: .init(), verification: flow)
        var gate: CheckedContinuation<SDKSessionCheck,Never>?
        flow.restoreHook = { _, reason in
            #expect(reason == .explicitRestore && memory.saves == 0)
            return await withCheckedContinuation { gate = $0 }
        }
        host.restoreSession(); await wait { gate != nil }; host.restoreSession()
        #expect(memory.loads == 1 && memory.saves == 0 && host.isRestoring)
        memory.onSave = { #expect(host.isRestoring && host.sessionBridgeResult != .stored) }
        gate?.resume(returning: .verified(sdkSession(id,version:"ROTATED")))
        await wait { !host.isRestoring }
        #expect(memory.saves == 1 && memory.clears == 0 && flow.restoreCalls == 1)
        #expect(host.sessionBridgeResult == .stored && host.localSessionStatus == .needsVerification)
        let operation = try #require(host.committedSessionOperation)
        #expect(life.isCurrent(operation) && !host.canUseRestrictedBusiness)
        // Compare only the rotated marker through SDK decoding, not timestamp-sensitive encoding.
        let stored = try #require(memory.material)
        let matches = try stored.withBytes { try AuthClient.Configuration.jsonDecoder.decode(Session.self,from:$0).refreshToken == "SYNTHETIC-REFRESH-ROTATED" }
        #expect(matches)
        host.restoreSession(); #expect(memory.loads == 1 && memory.saves == 1)
    }
    @Test func restoreUnknownPreservesSessionAndNeverStartsReplacementOperation() async throws {
        let id = UUID(), memory = HostSessionMemory(), flow = SyntheticVerificationFlow(nil)
        flow.verifiedUserID = id; memory.material = try material(sdkSession(id)); let original = memory.material
        flow.restoreHook = { _, _ in .unknown }
        let life = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let host = AccountHost(shell: try shell(), session: life, sdkConfiguration: .init(), verification: flow)
        host.restoreSession(); await wait { !host.isRestoring }
        #expect(host.sessionBridgeResult == .networkUnknown && host.requiresReconciliation && host.localSessionStatus == .unknown)
        #expect(memory.clears == 0 && memory.saves == 0 && sameBytes(memory.material, original))
        host.restoreSession(); #expect(memory.loads == 1 && flow.restoreCalls == 1)
        #expect(host.committedSessionOperation == nil)
    }
    @Test(arguments:[false,true]) func authoritativeInvalidClearsOnlyAfterCurrentCheckAndFailureBlocks(fails:Bool) async throws {
        let id = UUID(), memory = HostSessionMemory(), flow = SyntheticVerificationFlow(nil)
        flow.verifiedUserID = id; memory.material = try material(sdkSession(id)); let original = memory.material
        memory.failClear = fails
        flow.restoreHook = { _, _ in #expect(memory.clears == 0); return .invalid }
        let life = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let host = AccountHost(shell: try shell(), session: life, sdkConfiguration: .init(), verification: flow)
        host.restoreSession(); await wait { !host.isRestoring }
        #expect(memory.clears == 1 && memory.saves == 0 && !host.canRestoreSession)
        if fails {
            #expect(host.sessionBridgeResult == .storageFailure(.storageUnavailable) && host.localSessionStatus == .blocked(.storageUnavailable))
            #expect(sameBytes(memory.material, original))
        } else { #expect(host.sessionBridgeResult == .invalidated && memory.material == nil && host.localSessionStatus == .cleared) }
    }
    @Test func lateVerifiedRestoreCannotPublishAfterAccountChange() async throws {
        let id = UUID(), memory = HostSessionMemory(), flow = SyntheticVerificationFlow(nil), ui = try shell()
        flow.verifiedUserID = id; memory.material = try material(sdkSession(id))
        let life = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let host = AccountHost(shell: ui, session: life, sdkConfiguration: .init(), verification: flow)
        var gate: CheckedContinuation<SDKSessionCheck,Never>?
        flow.restoreHook = { _, _ in await withCheckedContinuation { gate = $0 } }
        host.restoreSession(); await wait { gate != nil }
        host.clearLocalSession(); flow.generation = UUID(); flow.verifiedUserID = UUID()
        ui.draft = "new account editor"
        gate?.resume(returning: .verified(sdkSession(id,version:"LATE")))
        for _ in 0..<100 { await Task.yield() }
        #expect(memory.saves == 0 && ui.draft == "new account editor" && !host.isRestoring)
        #expect(host.committedSessionOperation == nil && host.sessionBridgeResult != .stored)
    }
    @Test func storageFailureIsNotPublishedAsStoredOrSignedIn() async throws {
        let id = UUID(), memory = HostSessionMemory(), flow = SyntheticVerificationFlow(nil)
        flow.verifiedUserID = id; memory.material = try material(sdkSession(id)); let original = memory.material; memory.failSave = true
        let host = AccountHost(shell: try shell(), session: SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly), sdkConfiguration: .init(), verification: flow)
        host.restoreSession(); await wait { !host.isRestoring }
        #expect(host.sessionBridgeResult == .storageFailure(.storageUnavailable) && host.localSessionStatus == .blocked(.storageUnavailable))
        #expect(host.committedSessionOperation == nil && !host.canUseRestrictedBusiness && sameBytes(memory.material,original))
    }
    @Test func verifiedDifferentUserCannotReplaceTrustedIdentity() async throws {
        let id = UUID(), memory = HostSessionMemory(), flow = SyntheticVerificationFlow(nil)
        flow.verifiedUserID = id; memory.material = try material(sdkSession(id)); let original = memory.material
        flow.restoreHook = { _, _ in .verified(sdkSession(UUID())) }
        let host = AccountHost(shell: try shell(), session: SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly), sdkConfiguration: .init(), verification: flow)
        host.restoreSession(); await wait { !host.isRestoring }
        #expect(host.sessionBridgeResult == .identityMismatch && memory.saves == 0 && memory.clears == 0)
        #expect(sameBytes(memory.material, original) && !host.canUseRestrictedBusiness)
    }
    @Test func oldInitialVerificationCannotPublishAfterTrustedFlowChanges() async throws {
        let id = UUID(), memory = HostSessionMemory(), flow = SyntheticVerificationFlow(nil), counter = SDKFetchCounter()
        flow.verifiedUserID = id
        let payload = try AuthClient.Configuration.jsonEncoder.encode(sdkSession(id))
        let host = AccountHost(shell: try shell(), session: SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly),
            sdkConfiguration: config(), verification: flow, fetch: response(payload,counter))
        var gate: CheckedContinuation<SDKSessionCheck,Never>?
        flow.initialHook = { _, _ in await withCheckedContinuation { gate = $0 } }
        var password = "SYNTHETIC-NOT-A-PASSWORD"
        host.submit(.emailSignIn,email:"synthetic@example.invalid",password:&password)
        await wait { gate != nil }
        flow.generation = UUID(); flow.verifiedUserID = UUID()
        gate?.resume(returning: .verified(sdkSession(id)))
        await wait { !host.isWaiting }
        #expect(memory.saves == 0 && host.committedSessionOperation == nil)
        #expect(host.sessionBridgeResult == .stale && host.requiresReconciliation && host.state == .networkUnknown)
    }
    @Test func stalePersistErrorCannotDamageReplacementSession() async throws {
        let id = UUID(), replacementID = UUID(), memory = HostSessionMemory(), flow = SyntheticVerificationFlow(nil), ui = try shell()
        flow.verifiedUserID = id; memory.material = try material(sdkSession(id))
        let life = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let host = AccountHost(shell: ui, session: life, sdkConfiguration: .init(), verification: flow)
        let replacement = sdkSession(replacementID,version:"REPLACEMENT")
        var replacementOperation: SessionOperation?
        var replacementStored = false
        var replacementMaterial: SessionMaterial?
        memory.onSave = {
            host.clearLocalSession()
            flow.generation = UUID(); flow.verifiedUserID = replacementID
            do {
                let op = try life.beginTrustedSDKSave(); replacementOperation = op
                replacementStored = SupabaseSessionBridge.saveTrustedSDKSession(replacement, lifecycle: life,
                    operation: op, expectedUserID: replacementID, uiIsCurrent: { true }) == .stored
                replacementMaterial = memory.material
            } catch { Issue.record("Synthetic replacement setup failed") }
            memory.failSave = true // only the outer A save throws after replacement B committed
            ui.draft = "replacement editor"
        }
        host.restoreSession()
        await wait { replacementOperation != nil && !host.isRestoring }
        for _ in 0..<100 { await Task.yield() }
        let op = try #require(replacementOperation)
        #expect(replacementStored && life.isCurrent(op) && life.state == .saved)
        #expect(sameBytes(memory.material, replacementMaterial))
        #expect(ui.draft == "replacement editor" && host.sessionBridgeResult != .storageFailure(.storageUnavailable))
    }

    @Test func emailCompositionDoesNotPretendNativeProviderMaterialExists() async throws {
        let id = UUID(), memory = HostSessionMemory(), flow = SyntheticVerificationFlow(nil), counter = SDKFetchCounter()
        flow.verifiedUserID = id
        let payload = try AuthClient.Configuration.jsonEncoder.encode(sdkSession(id))
        let configuration = SupabaseAdapterConfiguration(authURL: URL(string:"https://synthetic.invalid/auth/v1"),
            publicKey:"sb_publishable_SYNTHETIC_NOT_A_KEY", googleClientID:"synthetic-google", appleClientID:"synthetic-apple")
        let host = AccountHost(shell: try shell(), session: SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly),
            sdkConfiguration: configuration, verification: flow, fetch: response(payload,counter))
        var password = ""
        host.submit(.googleSignIn,password:&password)
        #expect(host.state == .unavailable(.hostCapabilityRequired))
        host.submit(.appleSignIn,password:&password)
        #expect(host.state == .unavailable(.hostCapabilityRequired))
        #expect(await counter.calls == 0)
        #expect(memory.clears == 0 && memory.saves == 0)
    }

}
