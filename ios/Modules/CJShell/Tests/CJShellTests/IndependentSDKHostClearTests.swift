import Foundation
import Testing
import Auth
import CJAuth
import CJAuthSupabase
import CJSession
@testable import CJShell

@MainActor private final class ClearMemory: SessionPersistence {
    var material: SessionMaterial?
    var onClear: (() throws -> Void)?
    var failure: SessionFailure?
    var saveFailure: SessionFailure?
    var clears = 0
    func load() throws -> SessionMaterial? { material }
    func save(_ value: SessionMaterial) throws {
        if let saveFailure { throw saveFailure }
        material = value
    }
    func clearAndBlock() throws {
        clears += 1
        if let failure { throw failure }
        material = nil
        let callback = onClear; onClear = nil
        try callback?()
    }
}
@MainActor private final class ClearVerifier: AccountSessionVerification {
    var generation = UUID()
    var verifiedUserID: UUID?
    init(_ id: UUID) { verifiedUserID = id }
    func verifyInitialSession(_ candidate: Session, attempt: AuthAttempt) async -> SDKSessionCheck { .verified(candidate) }
    func revalidateSession(_ candidate: Session, reason: SessionRevalidationReason) async -> SDKSessionCheck { .verified(candidate) }
}
@Suite @MainActor struct IndependentSDKHostClearTests {
    private func value(_ id: UUID, marker: String = "B") -> Session {
        Session(accessToken: "SYNTHETIC-CLEAR-" + marker, tokenType: "bearer", expiresIn: 3600,
                expiresAt: Date().timeIntervalSince1970 + 3600, refreshToken: "SYNTHETIC-CLEAR-REFRESH-" + marker,
                user: User(id: id, appMetadata: [:], userMetadata: [:], aud: "synthetic", createdAt: Date(), updatedAt: Date()))
    }
    @Test(arguments: [false, true], [false, true]) func oldClearCannotBlockSuccessfullySavedReplacement(changesVerification: Bool, outerThrows: Bool) throws {
        let a = UUID(), b = changesVerification ? UUID() : a, memory = ClearMemory(), verifier = ClearVerifier(a)
        memory.material = try SessionMaterial(trustedSDKBytes: AuthClient.Configuration.jsonEncoder.encode(value(a, marker: "A")))
        let lifecycle = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString)))
        let host = AccountHost(shell: shell, session: lifecycle, sdkConfiguration: .init(), verification: verifier)
        var replacement: SessionOperation?
        var exactBytes: Data?
        memory.onClear = {
            try lifecycle.clear()
            if changesVerification { verifier.generation = UUID(); verifier.verifiedUserID = b }
            let operation = try lifecycle.beginTrustedSDKSave(); replacement = operation
            #expect(SupabaseSessionBridge.saveTrustedSDKSession(value(b), lifecycle: lifecycle, operation: operation,
                    expectedUserID: b, uiIsCurrent: { true }) == .stored)
            exactBytes = memory.material?.withBytes { $0 }
            if outerThrows { throw SessionFailure.staleOperation }
        }
        host.clearLocalSession()
        let operation = try #require(replacement)
        #expect(lifecycle.state == .saved && lifecycle.isCurrent(operation))
        #expect(memory.material?.withBytes { $0 } == exactBytes && exactBytes != nil)
        #expect(host.localSessionStatus == .idle && host.sessionBridgeResult == .stale)
        #expect(host.canRestoreSession && host.canSubmitAccount && !host.canUseRestrictedBusiness)
        #expect(host.committedSessionOperation == nil && !host.isRestoring && !host.isWaiting)
    }
    @Test(arguments: [SessionFailure.storageUnavailable, .staleOperation], [false, true])
    func failedReplacementIsNotTheOldClearFailure(failure: SessionFailure, outerThrows: Bool) throws {
        let id = UUID(), memory = ClearMemory(), verifier = ClearVerifier(id)
        let lifecycle = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString)))
        let host = AccountHost(shell: shell, session: lifecycle, sdkConfiguration: .init(), verification: verifier)
        var replacement: SessionOperation?
        memory.onClear = {
            try lifecycle.clear()
            let operation = try lifecycle.beginTrustedSDKSave(); replacement = operation
            memory.saveFailure = failure
            #expect(SupabaseSessionBridge.saveTrustedSDKSession(value(id), lifecycle: lifecycle, operation: operation,
                    expectedUserID: id, uiIsCurrent: { true }) == .storageFailure(failure))
            if outerThrows { throw SessionFailure.staleOperation }
        }
        host.clearLocalSession()
        let operation = try #require(replacement)
        #expect(lifecycle.ownsOperation(operation) && !lifecycle.isCurrent(operation))
        #expect(lifecycle.state == .blocked(failure) && memory.material == nil && memory.clears == 2)
        #expect(host.localSessionStatus == .idle && host.sessionBridgeResult == .stale)
        #expect(host.committedSessionOperation == nil && !host.canUseRestrictedBusiness)
        #expect(shell.messageBindingBlocked) // retired UI result does not authorize replacement business binding
    }
    @Test(arguments: [SessionFailure.storageUnavailable, .staleOperation])
    func sameOriginalClearFailureStillBlocks(_ failure: SessionFailure) throws {
        let memory = ClearMemory(), verifier = ClearVerifier(UUID())
        memory.failure = failure
        let lifecycle = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString)))
        let host = AccountHost(shell: shell, session: lifecycle, sdkConfiguration: .init(), verification: verifier)
        host.clearLocalSession()
        #expect(lifecycle.state == .blocked(failure) && host.localSessionStatus == .blocked(failure))
        #expect(!host.canRestoreSession && !host.canSubmitAccount && !host.canUseRestrictedBusiness)
    }
    @Test func successfulClearRetiresTokenAndStaysCleared() throws {
        let memory = ClearMemory(), verifier = ClearVerifier(UUID())
        let lifecycle = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let operation = try lifecycle.beginTrustedSDKSave()
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString)))
        let host = AccountHost(shell: shell, session: lifecycle, sdkConfiguration: .init(), verification: verifier)
        host.clearLocalSession()
        #expect(!lifecycle.ownsOperation(operation) && lifecycle.state == .cleared)
        #expect(host.localSessionStatus == .cleared && !host.canRestoreSession && host.canSubmitAccount)
    }
}
