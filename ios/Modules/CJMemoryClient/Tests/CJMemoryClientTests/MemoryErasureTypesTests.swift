import Foundation
import CryptoKit
import Testing
import CJMessageKeys
@testable import CJMemoryClient

private let erasureTrace = "11111111-1111-4111-8111-111111111468"
private let erasureOperation = "memory-erasure-v1:" + String(repeating: "a", count: 64)
private func erasureOriginal(_ item: String = "条目-e\u{301}", version: Int64 = 3) throws -> MemoryErasureAction {
    try .init(itemID: item, expectedVersion: version, acknowledgement: .ownedTripDerivedScope)
}

@MainActor private final class ErasureJournalFixture {
    let parent = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("erasure-" + UUID().uuidString)
    let key = SymmetricKey(size: .bits256), keyID = UUID()
    let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localMemoryPendingV1)
    var root: URL { parent.appendingPathComponent("account-A") }
    init() throws { try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700]) }
    func dispose() { try? FileManager.default.removeItem(at: parent) }
    func store(at root: URL? = nil, namespace: MessageKeyNamespace? = nil, key: (() throws -> SymmetricKey)? = nil) throws -> MemoryErasurePendingStore {
        let material = self.key
        return try MemoryErasurePendingStore(directory: root ?? self.root, maximumBytes: 100000, maximumRecords: 100,
            namespace: namespace ?? self.namespace, keyID: keyID, key: key ?? { material })
    }
}
@MainActor struct MemoryErasureJournalTests {
    @Test func reopenPreservesOriginalAndFirstServerIdentityWhileProgressCanAdvance() throws {
        let f = try ErasureJournalFixture(); defer { f.dispose() }
        let action = try erasureOriginal(), original = MemoryErasurePending(action), store = try f.store()
        try store.append(original, validate: {})
        let initial = try MemoryErasureProgress(response: erasureBytes(erasureResponse(action, post: true)), trace: erasureTrace, original: action, post: true)
        try store.record(initial, original: original, validate: {})
        let restored = try f.store(), record = try #require(try restored.records().first)
        #expect(record.originalUTF8 == action.originalUTF8 && record.expectedSHA256 == action.inputSHA256)
        let first = try #require(try restored.observation(for: record))
        let stable = first.value.originalUTF8
        let finished = try MemoryErasureProgress(response: erasureBytes(erasureResponse(action, post: false, phase: "complete")), trace: erasureTrace, original: action, post: false)
        try restored.record(finished, original: record, validate: {})
        #expect(try restored.observation(for: record)?.value.originalUTF8 == stable)
        var changed = erasureResponse(action, post: false), fields = changed["result"] as! [String: Any]
        fields["operation_id"] = "memory-erasure-v1:" + String(repeating: "b", count: 64); changed["result"] = fields
        let retargeted = try MemoryErasureProgress(response: erasureBytes(changed), trace: erasureTrace, original: action, post: false)
        #expect(throws: MemoryFailure.invalidResponse) { try restored.record(retargeted, original: record, validate: {}) }
        #expect(try restored.observation(for: record)?.value.originalUTF8 == stable)
        for directory in [f.root, f.root.appendingPathExtension("CJMemoryErasureObservationsV1")] {
            for file in try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) {
                let raw = try Data(contentsOf: file)
                #expect(!raw.contains(Data(action.itemID.utf8)) && !raw.contains(Data(erasureOperation.utf8)))
            }
        }
    }
    @Test func exactFamilyErasureNeedsNoKeyAndKeepsOtherAccountBytes() throws {
        let f = try ErasureJournalFixture(); defer { f.dispose() }
        var available = true, keyCalls = 0
        let store = try f.store(key: { keyCalls += 1; guard available else { throw MemoryFailure.keyUnavailable }; return f.key })
        let action = try erasureOriginal(), original = MemoryErasurePending(action)
        try store.append(original, validate: {})
        let progress = try MemoryErasureProgress(response: erasureBytes(erasureResponse(action, post: true)), trace: erasureTrace, original: action, post: true)
        try store.record(progress, original: original, validate: {})
        let other = f.parent.appendingPathComponent("account-B")
        try FileManager.default.createDirectory(at: other, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let otherNamespace = MessageKeyNamespace(environment: f.namespace.environment, account: UUID(), purpose: .localMemoryPendingV1)
        let otherStore = try f.store(at: other, namespace: otherNamespace); try otherStore.append(original, validate: {})
        let file = try #require(FileManager.default.contentsOfDirectory(at: other, includingPropertiesForKeys: nil).first)
        let before = try Data(contentsOf: file)
        let binding = MemoryBinding(environment: f.namespace.environment, account: otherNamespace.account, generation: UUID(), selection: UUID())
        #expect(throws: MemoryFailure.staleBinding) { try store.validate(binding) }
        available = false; let priorCalls = keyCalls
        try store.clearLocalFiles()
        #expect(keyCalls == priorCalls)
        for directory in [f.root, f.root.appendingPathExtension("CJMemoryErasureObservationsV1")] {
            #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path).isEmpty)
        }
        #expect(try Data(contentsOf: file) == before)
        #expect(throws: MemoryFailure.storageUnavailable) { try store.records() }
    }
    @Test func unexpectedObservationFileRefusesAllUnlinksAndRetainsOriginalRetryTargets() throws {
        let f = try ErasureJournalFixture(); defer { f.dispose() }
        let store = try f.store(), action = try erasureOriginal(), original = MemoryErasurePending(action)
        try store.append(original, validate: {})
        let progress = try MemoryErasureProgress(response: erasureBytes(erasureResponse(action, post: true)), trace: erasureTrace, original: action, post: true)
        try store.record(progress, original: original, validate: {})
        let file = try #require(FileManager.default.contentsOfDirectory(at: f.root, includingPropertiesForKeys: nil).first)
        let originalBytes = try Data(contentsOf: file)
        let unknown = f.root.appendingPathExtension("CJMemoryErasureObservationsV1").appendingPathComponent("unexpected")
        try Data("unrecognized".utf8).write(to: unknown)
        #expect(throws: MemoryFailure.storageUnavailable) { try store.clearLocalFiles() }
        #expect(try Data(contentsOf: file) == originalBytes)
        try FileManager.default.removeItem(at: unknown)
        try store.clearLocalFiles()
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
}
private func erasureResponse(_ original: MemoryErasureAction, post: Bool, phase: String = "unknown", empty: Bool = false) -> [String: Any] {
    var result: [String: Any] = ["action_id": original.actionID, "operation_id": erasureOperation,
        "item_version": original.expectedVersion == Int64.max ? Int64.max : original.expectedVersion + 1,
        "scope_epoch": 5, "stop_use": "stopped", "online_status": phase,
        "steps": empty ? [] : MemoryErasureTarget.allCases.map { ["target": $0.rawValue, "state": phase == "complete" ? "confirmed" : "pending"] }]
    if post {
        result.merge(["item_id": original.itemID, "derived_range": "owned_trip_derived_scope", "precise_item_match": false,
            "retained": ["original_chat", "accepted_formal_trip", "minimum_hashed_barriers"],
            "limits": ["already_sent_model_requests", "already_displayed_history", "external_provider_retention"]]) { _, new in new }
    }
    return ["version": "MEMORY-ERASURE-response@1", "request_id": erasureTrace, "result": result]
}
private func erasureBytes(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes]) }

struct MemoryErasureTypesTests {
    @Test func explicitRangeAndOriginalUTF8ArePreservedWithoutOperationIDCreation() throws {
        let item = "  条目-e\u{301}  ", original = try erasureOriginal(item)
        let fields = try #require(JSONSerialization.jsonObject(with: original.originalUTF8) as? [String: Any])
        #expect(Set(fields.keys) == ["version", "action_id", "item_id", "expected_version", "derived_range"])
        #expect(Data((fields["item_id"] as! String).utf8) == Data(item.utf8))
        #expect(fields["derived_range"] as? String == "owned_trip_derived_scope")
        #expect(fields["operation_id"] == nil)
        let raw = Data(" {\"version\":\"MEMORY-ERASURE@1\",\"action_id\":\"original\",\"item_id\":\"e\\u0301\",\"expected_version\":3,\"derived_range\":\"owned_trip_derived_scope\"}\n".utf8)
        let restored = try MemoryErasureAction(originalUTF8: raw)
        #expect(restored.originalUTF8 == raw && restored.inputSHA256 == digest(raw))
        #expect(Data(restored.itemID.utf8) == Data("e\u{301}".utf8))
    }
    @Test func identifierBoundsUseUnicodeScalarsRatherThanGraphemeClusters() throws {
        let maximum = String(repeating: "😀", count: 4096)
        let accepted = try erasureOriginal(maximum)
        #expect(try MemoryErasureAction(originalUTF8: accepted.originalUTF8).itemID.utf8.count == 16384)
        let tooMany = String(repeating: "e\u{301}", count: 2049)
        #expect(tooMany.count == 2049 && tooMany.unicodeScalars.count == 4098)
        for invalid in [tooMany, " ", "x\0y"] {
            #expect(throws: MemoryFailure.invalidInput) { try erasureOriginal(invalid) }
        }
        let composed = try erasureOriginal("é"), decomposed = try erasureOriginal("e\u{301}")
        #expect(Data(composed.itemID.utf8) != Data(decomposed.itemID.utf8))
    }
    @Test func untrustedOriginalRejectsExtraAuthorityAliasesAndInvalidVersions() throws {
        let base = try #require(JSONSerialization.jsonObject(with: erasureOriginal().originalUTF8) as? [String: Any])
        for (field, value) in [("owner", "other" as Any), ("derived_range", "precise_item" as Any),
            ("version", "MEMORY-ERASURE@2" as Any), ("expected_version", true as Any),
            ("expected_version", 0 as Any), ("expected_version", -1 as Any)] {
            var fields = base; fields[field] = value
            #expect(throws: (any Error).self) { try MemoryErasureAction(originalUTF8: erasureBytes(fields)) }
        }
        let source = String(decoding: try erasureBytes(base), as: UTF8.self)
        for token in ["3.0", "3e0", "9223372036854775808"] {
            let raw = source.replacingOccurrences(of: "\"expected_version\":3", with: "\"expected_version\":" + token)
            #expect(throws: (any Error).self) { try MemoryErasureAction(originalUTF8: Data(raw.utf8)) }
        }
        let duplicate = source.replacingOccurrences(of: "\"expected_version\":3", with: "\"expected_version\":3,\"expected_version\":3")
        #expect(throws: (any Error).self) { try MemoryErasureAction(originalUTF8: Data(duplicate.utf8)) }
    }
    @Test func stopUseAndPhysicalProgressRemainDistinct() throws {
        let original = try erasureOriginal()
        for phase in ["in_progress", "unknown", "blocked", "failed"] {
            let value = try MemoryErasureProgress(response: erasureBytes(erasureResponse(original, post: true, phase: phase)), trace: erasureTrace, original: original, post: true)
            #expect(value.stopped && !value.onlineComplete && value.steps.count == 8)
        }
        let complete = try MemoryErasureProgress(response: erasureBytes(erasureResponse(original, post: true, phase: "complete")), trace: erasureTrace, original: original, post: true)
        #expect(complete.stopped && complete.onlineComplete)
        let queried = try MemoryErasureProgress(response: erasureBytes(erasureResponse(original, post: false, empty: true)), trace: erasureTrace, original: original, post: false)
        #expect(queried.stopped && !queried.onlineComplete && queried.steps.isEmpty)
    }
    @Test func responseCannotClaimAnotherOriginalOrExpandAcknowledgedScope() throws {
        let original = try erasureOriginal()
        let base = erasureResponse(original, post: true)
        for (field, value) in [("action_id", "other" as Any), ("item_id", "é" as Any),
            ("item_version", 5 as Any), ("scope_epoch", true as Any), ("stop_use", "pending" as Any),
            ("precise_item_match", true as Any), ("derived_range", "account" as Any),
            ("online_status", "confirmed" as Any), ("operation_id", "invented" as Any)] {
            var envelope = base, result = base["result"] as! [String: Any]
            result[field] = value; envelope["result"] = result
            #expect(throws: (any Error).self) { try MemoryErasureProgress(response: erasureBytes(envelope), trace: erasureTrace, original: original, post: true) }
        }
        let overflowing = try erasureOriginal(version: Int64.max)
        #expect(throws: (any Error).self) { try MemoryErasureProgress(response: erasureBytes(erasureResponse(overflowing, post: true)), trace: erasureTrace, original: overflowing, post: true) }
    }
    @Test func completionRequiresAllOriginalTargetsAndKnownStepStates() throws {
        let original = try erasureOriginal()
        let targets = MemoryErasureTarget.allCases
        var cases: [[[String: String]]] = [[], [["target": targets[0].rawValue, "state": "confirmed"]],
            targets.map { ["target": $0.rawValue, "state": "pending"] },
            targets.map { ["target": $0.rawValue, "state": "available"] }]
        cases.append(targets.map { ["target": $0.rawValue, "state": "confirmed"] } + [["target": targets[0].rawValue, "state": "confirmed"]])
        cases.append(targets.map { ["target": $0 == .message ? "external/other" : $0.rawValue, "state": "confirmed"] })
        for steps in cases {
            var envelope = erasureResponse(original, post: false, phase: "complete"), result = envelope["result"] as! [String: Any]
            result["steps"] = steps; envelope["result"] = result
            #expect(throws: (any Error).self) { try MemoryErasureProgress(response: erasureBytes(envelope), trace: erasureTrace, original: original, post: false) }
        }
    }
    @Test func missingResponseIsNotAnEmptySuccessfulDeleteAndPrivateValuesAreRedacted() throws {
        let original = try erasureOriginal()
        let empty: [String: Any] = ["version": "MEMORY-ERASURE-response@1", "request_id": erasureTrace, "result": NSNull()]
        #expect(throws: (any Error).self) { try MemoryErasureProgress(response: erasureBytes(empty), trace: erasureTrace, original: original, post: false) }
        let value = try MemoryErasureProgress(response: erasureBytes(erasureResponse(original, post: true)), trace: erasureTrace, original: original, post: true)
        #expect(!String(reflecting: value).contains(value.operationID))
        #expect(!String(describing: value).contains(value.actionID))
        #expect(Mirror(reflecting: value).children.isEmpty)
    }
}
