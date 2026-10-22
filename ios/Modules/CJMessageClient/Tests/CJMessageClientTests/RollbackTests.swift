import Foundation
import CryptoKit
import Testing
@testable import CJMessageClient

@MainActor private final class RollbackKeys: MessageEncryptionKeyProvider {
    let material = MessageStorageKey(id: UUID(), key: SymmetricKey(size:.bits256))
    func existing(for scope: StorageScope, expectedID: UUID?) throws -> MessageStorageKey? { material }
}
@Suite @MainActor struct RollbackTests {
    @Test func restoredLegitimateStagedSnapshotCannotSubmitAgain() throws {
        let dir = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cj009-rollback-"+UUID().uuidString)
        let keys = RollbackKeys(); let storage = try EncryptedFileStorage(directory:dir,keys:keys)
        let scope = try StorageScope(environment:"synthetic",account:"a")
        let state = MessageRecovery(storage:storage); let first = try state.activate(scope)
        try state.stage(messageID:"m1",originalUTF8:Data("original fixture".utf8),lease:first)
        let file = try #require(FileManager.default.contentsOfDirectory(at:dir,includingPropertiesForKeys:nil).first)
        let oldValidCiphertext = try Data(contentsOf:file)
        _ = try state.beginSubmission(messageID:"m1",lease:first)
        // Test-only replay of an older authentic ciphertext, not a bit-flip/tamper test.
        try oldValidCiphertext.write(to:file,options:.atomic)
        let reopened = MessageRecovery(storage:storage); let current = try reopened.activate(scope)
        #expect(try reopened.action(messageID:"m1",lease:current)?.phase == .queryRequired)
        #expect(throws:RecoveryError.self) { try reopened.beginSubmission(messageID:"m1",lease:current) }
        #expect(try reopened.action(messageID:"m1",lease:current)?.originalUTF8 == Data("original fixture".utf8))
    }
}
