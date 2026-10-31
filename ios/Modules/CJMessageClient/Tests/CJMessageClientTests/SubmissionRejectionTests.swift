import Foundation
import CryptoKit
import Testing
@testable import CJMessageClient

@MainActor private final class RejectionStore: SecureMessageStorage {
    var values: [Data: Snapshot] = [:]
    var afterSave: (() throws -> Void)?
    var failBeforeSave = false
    func load(scope: StorageScope) throws -> Snapshot? { values[scope.binding] }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {
        if failBeforeSave { throw RecoveryError.persistenceUnknown }
        values[scope.binding] = snapshot
        let callback = afterSave; afterSave = nil; try callback?()
    }
}
@MainActor private final class RejectionKey: MessageEncryptionKeyProvider {
    let material=MessageStorageKey(id:UUID(),key:SymmetricKey(size:.bits256))
    func existing(for scope:StorageScope,expectedID:UUID?) throws -> MessageStorageKey? {
        guard expectedID == nil || expectedID == material.id else { throw RecoveryError.keyMismatch }
        return material
    }
}

@MainActor struct SubmissionRejectionTests {
    let raw = Data("SYNTHETIC original action bytes".utf8)
    let proof = Data("SYNTHETIC opaque proof verified by transport".utf8)
    private func scope(_ account: String = "A") throws -> StorageScope { try .init(environment: UUID().uuidString, account: account) }
    @Test func rejectionAndOriginalAreOneDurableVersionThreeRecord() throws {
        let storage = RejectionStore(), scope = try scope(), state = MessageRecovery(storage: storage), lease = try state.activate(scope)
        try state.stage(messageID: "original", originalUTF8: raw, lease: lease)
        try state.saveDraft(Data("old draft".utf8), conversationID: "old-chat", lease: lease)
        let submit = try state.beginSubmission(messageID: "original", lease: lease)
        try state.observeSubmissionRejection(submit.operation, httpStatus: 409, responseUTF8: proof)
        #expect(try state.action(messageID: "original", lease: lease)?.phase == .notAccepted)
        #expect(storage.values[scope.binding]?.version == 3)
        #expect(try state.submissionRejection(messageID: "original", lease: lease)?.responseUTF8 == proof)
        #expect(throws: RecoveryError.queryOnly) { try state.beginSubmission(messageID: "original", lease: lease) }
        let reopened = MessageRecovery(storage: storage), next = try reopened.activate(scope)
        #expect(try reopened.action(messageID: "original", lease: next)?.originalUTF8 == raw)
        #expect(try reopened.submissionRejection(messageID: "original", lease: next)?.httpStatus == 409)
        #expect(try reopened.draft(conversationID: "old-chat", lease: next) == Data("old draft".utf8))
        try reopened.stage(messageID: "new-original", originalUTF8: Data("different explicit action".utf8), lease: next)
        #expect(try reopened.action(messageID: "original", lease: next)?.originalUTF8 == raw)
        _ = try reopened.stageConversationOpening(conversationID: "discussion." + UUID().uuidString, lease: next)
        #expect(storage.values[scope.binding]?.version == 3)
        #expect(try reopened.submissionRejection(messageID: "original", lease: next)?.responseUTF8 == proof)
    }
    @Test func nullQueryCannotManufactureDefiniteSubmissionRejection() throws {
        let storage = RejectionStore(), scope = try scope(), state = MessageRecovery(storage: storage), lease = try state.activate(scope)
        try state.stage(messageID: "original", originalUTF8: raw, lease: lease)
        let submit = try state.beginSubmission(messageID: "original", lease: lease)
        try state.observeUnknown(submit.operation)
        let query = try state.beginQuery(messageID: "original", lease: lease)
        #expect(throws: RecoveryError.invalidInput) { try state.observeSubmissionRejection(query, httpStatus: 409, responseUTF8: proof) }
        try state.observeNotObserved(query)
        #expect(try state.submissionRejection(messageID: "original", lease: lease) == nil)
        #expect(try state.action(messageID: "original", lease: lease)?.phase == .notObserved)
        #expect(throws: RecoveryError.queryOnly) { try state.beginSubmission(messageID: "original", lease: lease) }
    }
    @Test func failedProofSaveKeepsUnknownAndOriginalBytes() throws {
        let storage = RejectionStore(), scope = try scope(), state = MessageRecovery(storage: storage), lease = try state.activate(scope)
        try state.stage(messageID: "original", originalUTF8: raw, lease: lease)
        let submit = try state.beginSubmission(messageID: "original", lease: lease)
        storage.failBeforeSave = true
        #expect(throws: RecoveryError.persistenceUnknown) { try state.observeSubmissionRejection(submit.operation, httpStatus: 409, responseUTF8: proof) }
        storage.failBeforeSave = false
        let reopened = MessageRecovery(storage: storage), next = try reopened.activate(scope)
        #expect(try reopened.action(messageID: "original", lease: next)?.originalUTF8 == raw)
        #expect(try reopened.action(messageID: "original", lease: next)?.phase == .queryRequired)
        #expect(try reopened.submissionRejection(messageID: "original", lease: next) == nil)
        #expect(throws: RecoveryError.queryOnly) { try reopened.beginSubmission(messageID: "original", lease: next) }
    }
    @Test func proofSaveAccountReentryCannotPublishIntoReplacementOwner() throws {
        let storage = RejectionStore(), a = try scope(), b = try scope("B"), state = MessageRecovery(storage: storage), lease = try state.activate(a)
        try state.stage(messageID: "original", originalUTF8: raw, lease: lease)
        let submit = try state.beginSubmission(messageID: "original", lease: lease)
        var current: Lease?
        storage.afterSave = { current = try state.activate(b) }
        #expect(throws: RecoveryError.inactive) { try state.observeSubmissionRejection(submit.operation, httpStatus: 409, responseUTF8: proof) }
        let active = try #require(current)
        #expect(try state.action(messageID: "original", lease: active) == nil)
        #expect(try state.submissionRejection(messageID: "original", lease: active) == nil)
        #expect(storage.values[a.binding]?.submissionRejections.count == 1)
    }
    @Test func unsupportedOrOrphanedProofCannotBeSilentlyDiscarded() throws {
        let storage = RejectionStore(), scope = try scope(), state = MessageRecovery(storage: storage), lease = try state.activate(scope)
        try state.stage(messageID: "original", originalUTF8: raw, lease: lease)
        let submit = try state.beginSubmission(messageID: "original", lease: lease)
        try state.observeSubmissionRejection(submit.operation, httpStatus: 409, responseUTF8: proof)
        let valid = try #require(storage.values[scope.binding])
        for version in [1, 2, 4] {
            var changed = valid; changed.version = version; storage.values[scope.binding] = changed
            #expect(throws: RecoveryError.invalidSnapshot) { try MessageRecovery(storage: storage).activate(scope) }
        }
        var orphan = valid; orphan.actions = [:]; storage.values[scope.binding] = orphan
        #expect(throws: RecoveryError.invalidSnapshot) { try MessageRecovery(storage: storage).activate(scope) }
        var missing = valid; missing.submissionRejections = [:]; storage.values[scope.binding] = missing
        #expect(throws: RecoveryError.invalidSnapshot) { try MessageRecovery(storage: storage).activate(scope) }
    }
    @Test func encryptedRebuildRetainsFailureWithoutPlaintextOrNewWritePermit() throws {
        let directory=FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        defer { do { try FileManager.default.removeItem(at:directory) } catch { Issue.record(error) } }
        let keys=RejectionKey(),scope=try scope(),storage=try EncryptedFileStorage(directory:directory,keys:keys)
        let state=MessageRecovery(storage:storage),lease=try state.activate(scope)
        try state.stage(messageID:"original",originalUTF8:raw,lease:lease)
        let submit=try state.beginSubmission(messageID:"original",lease:lease)
        try state.observeSubmissionRejection(submit.operation,httpStatus:409,responseUTF8:proof)
        let reopened=MessageRecovery(storage:try EncryptedFileStorage(directory:directory,keys:keys)),next=try reopened.activate(scope)
        #expect(try reopened.action(messageID:"original",lease:next)?.originalUTF8 == raw)
        #expect(try reopened.submissionRejection(messageID:"original",lease:next)?.responseUTF8 == proof)
        #expect(throws:RecoveryError.queryOnly) { try reopened.beginSubmission(messageID:"original",lease:next) }
        for file in try FileManager.default.contentsOfDirectory(at:directory,includingPropertiesForKeys:nil) {
            let bytes=try Data(contentsOf:file)
            #expect(bytes.range(of:raw) == nil && bytes.range(of:proof) == nil)
        }
    }
}
