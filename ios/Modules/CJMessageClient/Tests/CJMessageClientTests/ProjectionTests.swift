import Foundation
import CryptoKit
import Testing
@testable import CJMessageClient

@MainActor private final class ProjectionStore: SecureMessageStorage {
    var records: [Data:Snapshot] = [:]
    var onLoad: (() throws -> Void)?
    var saves = 0
    func load(scope: StorageScope) throws -> Snapshot? {
        let captured = records[scope.binding]
        let hook = onLoad; onLoad = nil; try hook?()
        return captured
    }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { saves += 1; records[scope.binding] = snapshot }
}
@MainActor private final class NoProjectionKey: MessageEncryptionKeyProvider {
    func existing(for scope: StorageScope, expectedID: UUID?) throws -> MessageStorageKey? { nil }
}
@Suite @MainActor struct ProjectionTests {
    private func scope(_ account: String = "a") throws -> StorageScope { try StorageScope(environment:UUID().uuidString,account:account) }
    @Test func reopenEnumeratesOnlyReferencesWithoutGrantingSend() throws {
        let store=ProjectionStore(); let s=try scope(); let original=MessageRecovery(storage:store)
        let lease=try original.activate(s)
        try original.stage(messageID:"original-id",originalUTF8:Data("PRIVATE BODY".utf8),lease:lease)
        try original.saveDraft(Data("PRIVATE DRAFT".utf8),conversationID:"draft-chat",lease:lease)
        let reopened=MessageRecovery(storage:store); let next=try reopened.activate(s)
        let saves=store.saves
        let projection=try reopened.localProjection(scope:s,lease:next)
        #expect(projection.actions.count == 1)
        #expect(projection.actions[0].messageID == "original-id")
        #expect(projection.actions[0].phase == .queryRequired)
        #expect(projection.drafts.map(\.conversationID) == ["draft-chat"])
        #expect(!String(reflecting:projection).contains("PRIVATE"))
        #expect(store.saves == saves)
        #expect(throws:RecoveryError.self) { try reopened.beginSubmission(messageID:projection.actions[0].messageID,lease:next) }
        #expect(try reopened.draft(conversationID:projection.drafts[0].conversationID,lease:next) == Data("PRIVATE DRAFT".utf8))
    }
    @Test func oldProjectionAndWrongScopeRejectedAfterSwitchOrReopen() throws {
        let store=ProjectionStore(); let state=MessageRecovery(storage:store)
        let a=try scope(), b=try scope("b")
        let lease=try state.activate(a)
        try state.saveDraft(Data("a".utf8),conversationID:"a-draft",lease:lease)
        let projection=try state.localProjection(scope:a,lease:lease)
        #expect(throws:RecoveryError.self) { try state.localProjection(scope:b,lease:lease) }
        let bLease=try state.activate(b)
        #expect(try state.localProjection(scope:b,lease:bLease).drafts.isEmpty)
        #expect(throws:RecoveryError.self) { try state.validateProjection(projection,scope:b,lease:bLease) }
        #expect(throws:RecoveryError.self) { try state.localProjection(scope:a,lease:lease) }
        let again=try state.activate(a)
        #expect(throws:RecoveryError.self) { try state.validateProjection(projection,scope:a,lease:again) }
    }
    @Test func loadCallbackCannotExposeOldAccountProjection() throws {
        let store=ProjectionStore(); let state=MessageRecovery(storage:store)
        let a=try scope(), b=try scope("b")
        let first=try state.activate(a)
        try state.saveDraft(Data("a".utf8),conversationID:"a-draft",lease:first)
        let second=try state.activate(b)
        try state.saveDraft(Data("b".utf8),conversationID:"b-draft",lease:second)
        var current: Lease?
        store.onLoad = { current = try state.activate(b) }
        #expect(throws:RecoveryError.self) { try state.activate(a) }
        let lease=try #require(current)
        let projection=try state.localProjection(scope:b,lease:lease)
        #expect(projection.drafts.map(\.conversationID) == ["b-draft"])
        #expect(throws:RecoveryError.self) { try state.localProjection(scope:a,lease:first) }
    }
    @Test func malformedDraftReferenceIsExplicitFailureNotEmpty() throws {
        let store=ProjectionStore(); let s=try scope()
        var snapshot=Snapshot(); snapshot.drafts["not base64!"]=Data("private".utf8)
        store.records[s.binding]=snapshot
        let state=MessageRecovery(storage:store); let lease=try state.activate(s)
        #expect(throws:RecoveryError.self) { try state.localProjection(scope:s,lease:lease) }
    }
    @Test func missingKeyCannotActivateOrReadProjection() throws {
        let dir=FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cj009-projection-"+UUID().uuidString)
        let storage=try EncryptedFileStorage(directory:dir,keys:NoProjectionKey())
        let state=MessageRecovery(storage:storage); let s=try scope()
        #expect(throws:RecoveryError.self) { try state.activate(s) }
        // No lease is returned; no projection read can be authorized.
    }
    @Test func emptyLocalProjectionIsNotServerHistory() throws {
        let state=MessageRecovery(storage:ProjectionStore()); let s=try scope(); let lease=try state.activate(s)
        let projection=try state.localProjection(scope:s,lease:lease)
        #expect(projection.actions.isEmpty && projection.drafts.isEmpty)
        try state.validateProjection(projection,scope:s,lease:lease)
        state.invalidate()
        #expect(throws:RecoveryError.self) { try state.validateProjection(projection,scope:s,lease:lease) }
    }
}
