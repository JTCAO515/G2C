import Foundation
import CryptoKit
import Testing
import CJMessageKeys
@testable import CJMemoryClient

@MainActor struct TypedMemoryStoreTests {
    @Test func typedJournalReopensExactBytesButV1CannotReadItAndOldBytesRemain() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        defer { try? FileManager.default.removeItem(at:root) }
        let binding = MemoryBinding(environment:UUID(),account:UUID(),generation:UUID(),selection:UUID())
        let namespace = MessageKeyNamespace(environment:binding.environment,account:binding.account,purpose:.localMemoryPendingV1)
        let key = SymmetricKey(size:.bits256),keyID = UUID()
        let store = try TypedMemoryPendingStore(directory:root,maximumBytes:100_000,maximumRecords:100,namespace:namespace,keyID:keyID,key:{ key })
        let command = try TypedMemoryCommand(operationID:"same-original",itemID:"item-original",subject:"traveller",slot:"preference",text:"原文",occurredAt:"约去年",kind:.preference,travelContext:nil)
        let original = TypedMemoryPending(command)
        try store.append(original,validateBinding:{ try store.validate(binding) })
        let file = try #require(FileManager.default.contentsOfDirectory(at:root,includingPropertiesForKeys:nil).first)
        let bytes = try Data(contentsOf:file)
        let reopened = try TypedMemoryPendingStore(directory:root,maximumBytes:100_000,maximumRecords:100,namespace:namespace,keyID:keyID,key:{ key })
        #expect(try reopened.pending().map(\.originalUTF8) == [command.originalUTF8])
        #expect(throws:(any Error).self) { try reopened.append(original,validateBinding:{}) }
        let old = try MemoryPendingStore(directory:root,maximumBytes:100_000,maximumRecords:100,namespace:namespace,keyID:keyID,key:{ key })
        #expect(throws:(any Error).self) { try old.pending() }
        let other = MemoryBinding(environment:binding.environment,account:UUID(),generation:binding.generation,selection:binding.selection)
        #expect(throws:MemoryFailure.staleBinding) { try reopened.validate(other) }
        #expect(try Data(contentsOf:file) == bytes)
    }
    @Test func durableTypedRejectionDoesNotChangeOriginalOrOtherJournals() throws {
        let parent = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let root = parent.appendingPathComponent("typed")
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        defer { try? FileManager.default.removeItem(at:parent) }
        let namespace = MessageKeyNamespace(environment:UUID(),account:UUID(),purpose:.localMemoryPendingV1)
        let key = SymmetricKey(size:.bits256),keyID = UUID()
        let store = try TypedMemoryPendingStore(directory:root,maximumBytes:100_000,maximumRecords:100,namespace:namespace,keyID:keyID,key:{ key })
        let original = TypedMemoryPending(try TypedMemoryCommand(operationID:"original",itemID:"item",subject:"traveller",slot:"preference",text:"原文",occurredAt:"去年",kind:.preference,travelContext:nil))
        try store.append(original,validateBinding:{})
        try store.recordRejection(original,status:409,code:"INPUT_CONFLICT",validateBinding:{})
        let reopened = try TypedMemoryPendingStore(directory:root,maximumBytes:100_000,maximumRecords:100,namespace:namespace,keyID:keyID,key:{ key })
        let observed = try reopened.rejection(for:original)
        let rejection = try #require(observed)
        #expect(rejection.status == 409 && rejection.code == "INPUT_CONFLICT")
        #expect(rejection.originalUTF8 == original.originalUTF8)
        #expect(try reopened.pending().map(\.originalUTF8) == [original.originalUTF8])
        #expect(!FileManager.default.fileExists(atPath:root.appendingPathExtension("CJMemoryRejections").path))
    }
}
