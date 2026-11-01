import Foundation
import Testing
import CryptoKit
import CJMessageKeys
@testable import CJTripClient

@Suite @MainActor struct ManualTripJournalTests {
    let inputCases = ManualTripInputTests()
    func original(_ name: String = "text") throws -> ManualTripOriginal { try .init(prepare: inputCases.frozen(inputCases.fixture(name))) }
    func records(_ store: TripPendingStore, create: Bool = true) throws -> TripEncryptedRecords<ManualTripOriginal> {
        let result: TripEncryptedRecords<ManualTripOriginal>? = try store.manualRecords(maximumBytes: 4_000_000, maximumRecords: 100, create: create)
        return try #require(result)
    }
    @Test func prepareAndLinkedSaveReopenWithExactOriginalBytes() throws {
        let h = try Harness(); defer { h.clean() }
        let store = try h.store(), storage = try records(store)
        for f in try inputCases.fixtures() {
            let input = try inputCases.frozen(f)
            // Fixture business IDs intentionally repeat, so use independent
            // owned test directories for each positive variant.
            let local = try Harness(); defer { local.clean() }
            let journal = try records(local.store()), prepare = ManualTripOriginal(prepare: input)
            try journal.append(prepare)
            let bytes = Data(base64Encoded: f.preparation_utf8_base64)!
            let result = try ManualTripReplies.preparation(bytes, original: input, requestID: "B35279D6-8B42-466D-A55D-8A16B64BB270")
            let reply = try #require(result), save = try ManualTripSaveInput(actionID: "journal-save", preparation: reply, original: input)
            let saved = ManualTripOriginal(save: save, responseUTF8: bytes)
            try journal.append(saved)
            let reopened = try records(local.store(), create: false), all = try reopened.pending()
            let p = try #require(all.first { $0.stage == .prepare }), s = try #require(all.first { $0.stage == .save })
            #expect(try p.prepareInput().originalUTF8 == input.originalUTF8)
            #expect(try s.saveInput(preparation: p).originalUTF8 == save.originalUTF8)
            let proof = try reopened.requireOriginal(p); try reopened.validateDurability(proof)
        }
        #expect(try storage.pending().isEmpty)
    }
    @Test func newNamespacePreventsLegacyWritesButPreservesLegacyQueries() throws {
        let h = try Harness(); defer { h.clean() }
        let store = try h.store(), old = try pending()
        try store.append(old)
        let before = try Data(contentsOf: h.root.appendingPathComponent(digest(Data(old.actionID.utf8))+".trip"))
        let storage = try records(store), new = try original()
        try storage.append(new)
        #expect(throws: TripFailure.pendingRequiresQuery) { try store.requireLegacyWritesAllowed() }
        #expect(try store.pending().first?.originalUTF8 == old.originalUTF8)
        #expect(try Data(contentsOf: h.root.appendingPathComponent(digest(Data(old.actionID.utf8))+".trip")) == before)
        #expect(throws: TripFailure.keyUnavailable) { try TripPendingStore.requireEmptyNamespace(directory: h.root) }
    }
    @Test func noReplacementKeyWhenOnlyAnAdjacentJournalRetainsData() throws {
        let h = try Harness(); defer { h.clean() }
        let storage = try records(h.store()); try storage.append(original())
        #expect(try FileManager.default.contentsOfDirectory(atPath: h.root.path).isEmpty)
        #expect(throws: TripFailure.keyUnavailable) { try TripPendingStore.requireEmptyNamespace(directory: h.root) }
    }
    @Test func duplicateAppendAndCiphertextReplacementFailClosed() throws {
        let h = try Harness(); defer { h.clean() }
        let storage = try records(h.store()), record = try original()
        try storage.append(record)
        let url = h.root.appendingPathExtension("CJTripManual").appendingPathComponent(digest(Data(record.storageID.utf8))+".trip")
        let first = try Data(contentsOf: url), proof = try storage.requireOriginal(record)
        #expect(throws: TripFailure.storageUnavailable) { try storage.append(record) }
        #expect(try Data(contentsOf: url) == first)
        var corrupt = first; corrupt[corrupt.startIndex] ^= 1; try corrupt.write(to: url)
        #expect(throws: TripFailure.storageUnavailable) { try storage.validateDurability(proof) }
        #expect(throws: (any Error).self) { try storage.pending() }
    }
    @Test func inventoryAndOwnerCannotBeSubstitutedDuringResourceCallbacks() throws {
        let h = try Harness(); defer { h.clean() }
        let storage = try records(h.store()), record = try original(); try storage.append(record)
        try storage.validateInventory([record.storageID])
        let foreign = MessageKeyNamespace(environment: h.binding.environment, account: UUID(), purpose: .localTripPendingV1)
        let wrong = try TripPendingStore(directory: h.root, maximumBytes: 100_000, maximumRecords: 20, namespace: foreign,
            keyID: h.keyID, key: { h.key })
        #expect(throws: (any Error).self) { try records(wrong, create: false).pending() }
        let extra = h.root.appendingPathExtension("CJTripManual").appendingPathComponent("unexpected")
        try Data("unexpected".utf8).write(to: extra)
        #expect(throws: TripFailure.storageUnavailable) { try storage.validateInventory([record.storageID]) }
    }
    @Test func persistedSchemaAndSelectionDoNotCoerceOrAcquireScope() throws {
        let record = try original(), encoder = JSONEncoder(), bytes = try encoder.encode(record)
        var value = try JSONSerialization.jsonObject(with: bytes) as! [String: Any]
        value["sourceVersion"] = 2.0
        #expect(throws: (any Error).self) { try JSONDecoder().decode(ManualTripOriginal.self, from: JSONSerialization.data(withJSONObject: value)) }
        value = try JSONSerialization.jsonObject(with: bytes) as! [String: Any]; value["owner"] = "caller"
        #expect(throws: (any Error).self) { try JSONDecoder().decode(ManualTripOriginal.self, from: JSONSerialization.data(withJSONObject: value)) }
        value = try JSONSerialization.jsonObject(with: bytes) as! [String: Any]; value["selectedIDs"] = []
        let invalid = try JSONDecoder().decode(ManualTripOriginal.self, from: JSONSerialization.data(withJSONObject: value))
        #expect(throws: (any Error).self) { try invalid.validate() }
    }
}
