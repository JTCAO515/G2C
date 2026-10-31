import Foundation
import CryptoKit
import Testing
@testable import CJMessageClient

@MainActor private final class OpeningStore:SecureMessageStorage {
    var values:[Data:Snapshot]=[:]
    var afterSave:(()->Void)?
    func load(scope:StorageScope) throws -> Snapshot? { values[scope.binding] }
    func save(_ snapshot:Snapshot,scope:StorageScope) throws {
        values[scope.binding]=snapshot
        let callback=afterSave;afterSave=nil;callback?()
    }
}
@MainActor private final class OpeningKey:MessageEncryptionKeyProvider {
    let material=MessageStorageKey(id:UUID(),key:SymmetricKey(size:.bits256))
    func existing(for scope:StorageScope,expectedID:UUID?) throws -> MessageStorageKey? {
        guard expectedID==nil || expectedID==material.id else { throw RecoveryError.keyMismatch }
        return material
    }
}
@MainActor struct ConversationOpeningTests {
    private func scope(_ account:String="A") throws -> StorageScope { try .init(environment:UUID().uuidString,account:account) }
    private func id() -> String { "discussion."+UUID().uuidString }
    @Test func oldSnapshotKeepsItsOriginalFieldSet() throws {
        let object=try #require(JSONSerialization.jsonObject(with:JSONEncoder().encode(Snapshot())) as? [String:Any])
        #expect(Set(object.keys)==["version","actions","drafts","draftEdits","draftSaves"])
    }
    @Test func journalUpgradePreservesOldUnknownAndDraftAndNeverRestoresPUTPermission() throws {
        let storage=OpeningStore(),scope=try scope(),state=MessageRecovery(storage:storage),lease=try state.activate(scope)
        try state.stage(messageID:"original",originalUTF8:Data("SYNTHETIC old message".utf8),lease:lease)
        try state.saveDraft(Data("SYNTHETIC old draft".utf8),conversationID:"old-chat",lease:lease)
        let cid=id(),create=try state.stageConversationOpening(conversationID:cid,lease:lease)
        try state.consumeConversationCreation(create)
        #expect(throws:RecoveryError.queryOnly) { try state.consumeConversationCreation(create) }
        #expect(storage.values[scope.binding]?.version==2)
        let reopened=MessageRecovery(storage:storage),next=try reopened.activate(scope)
        #expect(try reopened.action(messageID:"original",lease:next)?.originalUTF8==Data("SYNTHETIC old message".utf8))
        #expect(try reopened.action(messageID:"original",lease:next)?.phase == .queryRequired)
        #expect(try reopened.draft(conversationID:"old-chat",lease:next)==Data("SYNTHETIC old draft".utf8))
        #expect(try reopened.conversationOpenings(lease:next).first?.conversationID==cid)
        #expect(throws:RecoveryError.queryOnly) { try reopened.stageConversationOpening(conversationID:id(),lease:next) }
        let query=try reopened.beginConversationOpeningQuery(conversationID:cid,lease:next)
        #expect(throws:RecoveryError.queryOnly) { try reopened.consumeConversationCreation(query) }
    }
    @Test func onlyCurrentOriginalQueryCanSettleAndOriginalProofIsRetained() throws {
        let storage=OpeningStore(),scope=try scope(),state=MessageRecovery(storage:storage),lease=try state.activate(scope),cid=id()
        _=try state.stageConversationOpening(conversationID:cid,lease:lease)
        let first=try state.beginConversationOpeningQuery(conversationID:cid,lease:lease)
        let second=try state.beginConversationOpeningQuery(conversationID:cid,lease:lease)
        let proof=Data("SYNTHETIC transport-validated proof".utf8)
        #expect(throws:RecoveryError.staleOperation) { try state.observeConversationOpening(first,phase:.available,httpStatus:200,responseUTF8:proof) }
        try state.observeConversationOpening(second,phase:.available,httpStatus:200,responseUTF8:proof)
        let third=try state.beginConversationOpeningQuery(conversationID:cid,lease:lease)
        try state.observeConversationOpening(third,phase:.available,httpStatus:200,responseUTF8:Data("later read".utf8))
        #expect(try state.conversationOpenings(lease:lease).first?.responseUTF8==proof)
        _=try state.stageConversationOpening(conversationID:id(),lease:lease)
    }
    @Test func saveCallbackAccountSwitchCannotGrantAnOldOpeningPermit() throws {
        let storage=OpeningStore(),a=try scope(),b=try scope("B"),state=MessageRecovery(storage:storage),lease=try state.activate(a)
        var current:Lease?
        storage.afterSave={ do { current=try state.activate(b) } catch { Issue.record(error) } }
        #expect(throws:RecoveryError.inactive) { try state.stageConversationOpening(conversationID:id(),lease:lease) }
        let active=try #require(current)
        #expect(try state.conversationOpenings(lease:active).isEmpty)
        #expect(try state.localProjection(scope:b,lease:active).drafts.isEmpty)
    }
    @Test func malformedVersionOrOriginalIdentityCannotHideAnOpeningInV1() throws {
        let storage=OpeningStore(),scope=try scope(),state=MessageRecovery(storage:storage),lease=try state.activate(scope)
        _=try state.stageConversationOpening(conversationID:id(),lease:lease)
        var bad=try #require(storage.values[scope.binding]);bad.version=1;storage.values[scope.binding]=bad
        #expect(throws:RecoveryError.invalidSnapshot) { try MessageRecovery(storage:storage).activate(scope) }
        bad.version=2;let entry=try #require(bad.conversationOpens.first);bad.conversationOpens=["wrong-key":entry.value];storage.values[scope.binding]=bad
        #expect(throws:RecoveryError.invalidSnapshot) { try MessageRecovery(storage:storage).activate(scope) }
    }
    @Test func resultSaveCallbackCannotRetireANewerOriginalQuery() throws {
        let storage=OpeningStore(),scope=try scope(),state=MessageRecovery(storage:storage),lease=try state.activate(scope),cid=id()
        let create=try state.stageConversationOpening(conversationID:cid,lease:lease);try state.consumeConversationCreation(create)
        var newer:ConversationOpeningOperation?
        storage.afterSave={ do { newer=try state.beginConversationOpeningQuery(conversationID:cid,lease:lease) } catch { Issue.record(error) } }
        #expect(throws:RecoveryError.staleOperation) { try state.observeConversationOpening(create,phase:.available,httpStatus:200,responseUTF8:Data("verified original result".utf8)) }
        try state.validateConversationOpening(#require(newer))
    }
    @Test func encryptedReopenRetainsOpeningIDAndDoesNotExposeOldPlaintext() throws {
        let directory=FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:directory) }
        let storage=try EncryptedFileStorage(directory:directory,keys:OpeningKey()),scope=try scope(),state=MessageRecovery(storage:storage),lease=try state.activate(scope)
        let text=Data("SYNTHETIC_PRIVATE_OLD_DRAFT".utf8),cid=id()
        try state.saveDraft(text,conversationID:"old-chat",lease:lease)
        _=try state.stageConversationOpening(conversationID:cid,lease:lease)
        let reopened=MessageRecovery(storage:storage),next=try reopened.activate(scope)
        #expect(try reopened.conversationOpenings(lease:next).first?.conversationID==cid)
        #expect(try reopened.draft(conversationID:"old-chat",lease:next)==text)
        for file in try FileManager.default.contentsOfDirectory(at:directory,includingPropertiesForKeys:nil) {
            let bytes=try Data(contentsOf:file)
            #expect(bytes.range(of:text)==nil && bytes.range(of:Data(cid.utf8))==nil)
        }
    }
}
