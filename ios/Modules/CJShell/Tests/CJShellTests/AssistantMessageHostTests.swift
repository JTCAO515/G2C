import Foundation
import Testing
import CJAuth
import CJSession
import CJMessageClient
@testable import CJShell

@MainActor private final class SyntheticMessages: SecureMessageStorage {
    let environment = "synthetic-" + UUID().uuidString
    var snapshot: Snapshot?
    var failSave = false
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {
        if failSave { throw RecoveryError.persistenceUnknown }
        self.snapshot = snapshot
    }
}
@MainActor private final class QueryControl {
    var calls = 0
    var continuation: CheckedContinuation<Void, any Error>?
    var operation: CJMessageClient.Operation?
    let recovery: MessageRecovery
    init(_ recovery: MessageRecovery) { self.recovery = recovery }
    func query(_ id: String, _ lease: Lease) async throws {
        calls += 1
        operation = try recovery.beginQuery(messageID: id, lease: lease)
        try await withCheckedThrowingContinuation { continuation = $0 }
    }
    func finish() { let c = continuation; continuation = nil; c?.resume() }
    func fail() { let c = continuation; continuation = nil; c?.resume(throwing: RecoveryError.persistenceUnknown) }
}
@MainActor private final class FailingSession: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws { throw SessionFailure.storageUnavailable }
}

@Suite @MainActor struct AssistantMessageHostTests {
    private func shell() throws -> ShellState {
        ShellState(preferences: try #require(UserDefaults(suiteName: "cj006.message.tests.\(UUID().uuidString)")))
    }
    private func wait(_ predicate: () -> Bool) async {
        for _ in 0..<1000 { if predicate() { return }; await Task.yield() }
        #expect(predicate(), "Synthetic query did not reach expected state")
    }
    private func fixture(_ shell: ShellState, queryRequired: Bool = false) throws -> (AssistantMessageHost, MessageRecovery, Lease, QueryControl, SyntheticMessages) {
        let store = SyntheticMessages(); let recovery = MessageRecovery(storage: store)
        let scope = try StorageScope(environment: store.environment, account: "synthetic-A")
        let lease = try recovery.activate(scope)
        try recovery.stage(messageID: "original-1", originalUTF8: Data("{\"synthetic\":\"原字节\"}".utf8), lease: lease)
        if queryRequired { let submission = try recovery.beginSubmission(messageID: "original-1", lease: lease); try recovery.observeUnknown(submission.operation) }
        let control = QueryControl(recovery)
        let host = AssistantMessageHost(shell: shell)
        #expect(host.bind(AssistantMessageBinding(recovery: recovery, scope: scope, lease: lease, generation: shell.generation,
                                                conversationID: "conversation-1", messageID: "original-1", synthetic: true,
                                                isCurrent: { true }, invalidateResources: {}, queryOriginal: control.query)))
        return (host, recovery, lease, control, store)
    }
    @Test func defaultHasNoSendOrStorage() throws {
        let host = AssistantMessageHost(shell: try shell())
        #expect(!host.canSend && !host.canQuery && !host.canSaveDraft && host.visibleRecord == nil)
    }
    @Test func stagedAndLanguagePreserveOriginalBytesIDAndDraft() throws {
        let shell = try shell(); let (host, recovery, lease, _, _) = try fixture(shell)
        let before = try #require(host.visibleRecord)
        shell.draft = "去北京 / Beijing 🧳"; host.saveDraft()
        #expect(host.draftStored && !host.canSend && !host.canQuery)
        let generation = shell.generation
        shell.selectLanguage(.chinese)
        let after = try #require(host.visibleRecord)
        #expect(after.phase == .staged && after.messageID == before.messageID && after.originalUTF8 == before.originalUTF8)
        #expect(shell.generation == generation && host.draftStored)
        #expect(try recovery.draft(conversationID: "conversation-1", lease: lease) == Data(shell.draft.utf8))
        shell.draft += " changed"; #expect(!host.draftStored)
    }
    @Test func queryNullRemainsNotObservedAndCannotSend() async throws {
        let shell = try shell(); let (host, recovery, _, control, _) = try fixture(shell, queryRequired: true)
        #expect(host.visibleRecord?.phase == .queryRequired)
        host.queryOriginal(); host.queryOriginal()
        await wait { control.continuation != nil }
        #expect(control.calls == 1)
        try recovery.observeNotObserved(try #require(control.operation))
        control.finish(); await wait { host.activity == .ready }
        #expect(host.visibleRecord?.phase == .notObserved && !host.canSend && host.canQuery)
    }
    @Test func unknownAndReceiptAreDistinctWithoutAssistantReply() async throws {
        let shell = try shell(); let (host, recovery, _, control, _) = try fixture(shell, queryRequired: true)
        host.queryOriginal(); await wait { control.continuation != nil }
        try recovery.observeUnknown(try #require(control.operation)); control.fail()
        await wait { host.activity == .unknown }
        #expect(!host.canSend && host.visibleRecord?.phase == .queryRequired)
        host.queryOriginal(); await wait { control.continuation != nil }
        let record = try #require(host.visibleRecord)
        try recovery.observeReceipt(try #require(control.operation), messageID: record.messageID, inputSHA256: record.inputSHA256, receipt: Data("synthetic-receipt".utf8))
        control.finish(); await wait { host.activity == .ready }
        #expect(host.visibleRecord?.phase == .accepted && !host.canSend && !host.canQuery)
        #expect(shell.assistantBody == nil && host.isSynthetic)
    }
    @Test func cleanupFailureImmediatelyFencesClientAndLateQuery() async throws {
        let shell = try shell(); let (host, recovery, lease, control, _) = try fixture(shell, queryRequired: true)
        host.queryOriginal(); await wait { control.continuation != nil }
        let account = AccountHost(shell: shell, session: SessionLifecycle(persistence: FailingSession(), restorePolicy: .userInitiatedOnly)) { _, _ in UnconfiguredSDKAdapter() }
        account.clearLocalSession()
        #expect(account.localSessionStatus == .blocked(.storageUnavailable))
        #expect(host.visibleRecord == nil && !host.isConfigured && host.activity == .invalidated)
        #expect(throws: (any Error).self) { try recovery.action(messageID: "original-1", lease: lease) }
        let scope = try StorageScope(environment: "synthetic-env", account: "synthetic-B")
        let fresh = MessageRecovery(storage: SyntheticMessages())
        let freshLease = try fresh.activate(scope)
        #expect(!host.bind(AssistantMessageBinding(recovery: fresh, scope: scope, lease: freshLease,
            generation: shell.generation, conversationID: "new", messageID: nil, synthetic: true,
            isCurrent: { true }, invalidateResources: {})))
        control.finish(); for _ in 0..<10 { await Task.yield() }
        #expect(host.visibleRecord == nil && shell.assistantBody == nil && host.activity == .invalidated)
    }
    @Test func storageUnknownNeverKeepsAVisibleReceiptOrSavedDraft() throws {
        let shell = try shell(); let (host, _, _, _, store) = try fixture(shell)
        store.failSave = true; shell.draft = "draft"; host.saveDraft()
        #expect(host.activity == .storageBlocked && host.visibleRecord == nil && !host.draftStored && !host.canQuery)
    }
    @Test func wrongScopeAndSameGenerationRebindAreRejected() throws {
        let shell = try shell(); let (host, recovery, lease, _, _) = try fixture(shell)
        let wrong = try StorageScope(environment: "synthetic-env", account: "synthetic-B")
        #expect(!host.bind(AssistantMessageBinding(recovery: recovery, scope: wrong, lease: lease, generation: shell.generation,
                                                 conversationID: "conversation-1", messageID: "original-1", synthetic: true, isCurrent: { true }, invalidateResources: {})))
        shell.invalidateIdentity()
        #expect(host.visibleRecord == nil)
        #expect(!host.bind(AssistantMessageBinding(recovery: recovery, scope: wrong, lease: lease, generation: shell.generation,
                                                 conversationID: "conversation-1", messageID: "original-1", synthetic: true, isCurrent: { true }, invalidateResources: {})))
        let anotherShell = try self.shell()
        let another = MessageRecovery(storage: SyntheticMessages())
        let correct = try StorageScope(environment: "synthetic-env", account: "synthetic-A")
        let anotherLease = try another.activate(correct)
        let freshHost = AssistantMessageHost(shell: anotherShell)
        var invalidations = 0
        #expect(!freshHost.bind(AssistantMessageBinding(recovery: another, scope: wrong, lease: anotherLease,
            generation: anotherShell.generation, conversationID: "conversation-1", messageID: nil,
            synthetic: true, isCurrent: { true }, invalidateResources: { invalidations += 1 })))
        #expect(freshHost.activity == .storageBlocked && invalidations == 0)
    }
    @Test func reopenedStagedRecordDisplaysQueryOnlyWithIdenticalBytes() throws {
        let shell = try shell(); let (old, _, _, _, store) = try fixture(shell)
        let original = try #require(old.visibleRecord)
        old.invalidate() // previous lifetime stopped before the new single writer opens
        let recovered = MessageRecovery(storage: store)
        let scope = try StorageScope(environment: store.environment, account: "synthetic-A")
        let lease = try recovered.activate(scope)
        let freshShell = try self.shell()
        let host = AssistantMessageHost(shell: freshShell)
        #expect(host.bind(AssistantMessageBinding(recovery: recovered, scope: scope, lease: lease,
            generation: freshShell.generation, conversationID: "conversation-1", messageID: "original-1",
            synthetic: true, isCurrent: { true }, invalidateResources: {})))
        #expect(host.visibleRecord?.phase == .queryRequired)
        #expect(host.visibleRecord?.originalUTF8 == original.originalUTF8 && host.visibleRecord?.messageID == original.messageID)
        #expect(!host.canSend)
    }

}
