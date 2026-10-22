import Foundation
import Testing
import CJMessageClient
@testable import CJShell

@MainActor private final class ProjectionMemoryStore: SecureMessageStorage {
    var value: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { value }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { value = snapshot }
}

@Suite @MainActor struct LocalRecoveryListHostTests {
    private func shell() throws -> ShellState {
        ShellState(preferences: try #require(UserDefaults(suiteName: "cj006.list.tests.\(UUID().uuidString)")))
    }
    private func setup(_ shell: ShellState, query: (@MainActor (MessageRecovery, String, Lease) async throws -> Void)? = nil) throws -> AssistantMessageHost {
        let recovery = MessageRecovery(storage: ProjectionMemoryStore())
        let scope = try StorageScope(environment: "synthetic-" + UUID().uuidString, account: "A")
        let lease = try recovery.activate(scope)
        try recovery.saveDraft(Data("private draft body".utf8), conversationID: "draft-A", lease: lease)
        for id in ["é", "e\u{301}"] {
            try recovery.stage(messageID: id, originalUTF8: Data(("private-original-" + id).utf8), lease: lease)
            let submission = try recovery.beginSubmission(messageID: id, lease: lease)
            try recovery.observeUnknown(submission.operation)
        }
        let host = AssistantMessageHost(shell: shell)
        #expect(host.bind(AssistantMessageBinding(recovery: recovery, scope: scope, lease: lease, generation: shell.generation,
            synthetic: true, isCurrent: { true }, invalidateResources: {}, queryOriginal: { id, lease in
                if let query { try await query(recovery, id, lease) }
            })))
        return host
    }
    @Test func listsReferencesWithoutManualIDOrBodyRead() throws {
        let shell = try shell(); let host = try setup(shell)
        let projection = try #require(host.visibleProjection)
        #expect(projection.actions.count == 2 && projection.drafts.count == 1)
        #expect(Set(projection.actions.map { Data($0.messageID.utf8) }).count == 2)
        #expect(host.visibleRecord == nil && shell.draft.isEmpty && !host.canQuery && !host.canSend)
    }
    @Test func explicitDraftSelectionAndLanguageKeepExactContent() throws {
        let shell = try shell(); let host = try setup(shell)
        let projection = try #require(host.visibleProjection)
        #expect(host.selectDraft(try #require(projection.drafts.first), from: projection))
        #expect(shell.draft == "private draft body")
        let original = Data(shell.draft.utf8); let generation = shell.generation
        shell.selectLanguage(.chinese)
        #expect(Data(shell.draft.utf8) == original && shell.generation == generation)
        #expect(host.visibleProjection?.actions.count == 2)
    }
    @Test func selectedExactUTF8IDIsTheOnlyQueriedID() async throws {
        let shell = try shell(); var queried: [Data] = []
        let host = try setup(shell) { recovery, id, lease in
            queried.append(Data(id.utf8))
            try recovery.observeNotObserved(recovery.beginQuery(messageID: id, lease: lease))
        }
        host.queryOriginal(); #expect(queried.isEmpty)
        let projection = try #require(host.visibleProjection)
        let target = try #require(projection.actions.first { Data($0.messageID.utf8) == Data("e\u{301}".utf8) })
        #expect(host.selectAction(target, from: projection))
        host.queryOriginal()
        for _ in 0..<1000 { if host.activity != .querying { break }; await Task.yield() }
        #expect(queried == [Data(target.messageID.utf8)])
        #expect(host.visibleRecord?.phase == .notObserved && !host.canSend)
        #expect(host.visibleProjection?.actions.first { Data($0.messageID.utf8) == Data(target.messageID.utf8) }?.phase == .notObserved)
    }
    @Test func oldProjectionCannotLoadAfterIdentityChange() throws {
        let shell = try shell(); let host = try setup(shell)
        let old = try #require(host.visibleProjection)
        shell.invalidateIdentity()
        #expect(host.visibleProjection == nil)
        #expect(!host.selectDraft(try #require(old.drafts.first), from: old))
        #expect(!host.selectAction(try #require(old.actions.first), from: old))
        #expect(shell.draft.isEmpty && host.visibleRecord == nil)
    }
    @Test func switchingSelectionWhileQueryWaitsIsRejected() async throws {
        let shell = try shell(); var resume: CheckedContinuation<Void, Never>?
        let host = try setup(shell) { _, _, _ in await withCheckedContinuation { resume = $0 } }
        let projection = try #require(host.visibleProjection)
        let original = projection.actions[0]
        #expect(host.selectAction(original, from: projection))
        host.queryOriginal()
        for _ in 0..<1000 { if resume != nil { break }; await Task.yield() }
        #expect(!host.selectAction(projection.actions[1], from: projection))
        #expect(!host.selectDraft(try #require(projection.drafts.first), from: projection))
        shell.invalidateIdentity()
        resume?.resume()
        for _ in 0..<10 { await Task.yield() }
        #expect(host.visibleProjection == nil && host.visibleRecord == nil && host.activity == .invalidated)
    }
}
