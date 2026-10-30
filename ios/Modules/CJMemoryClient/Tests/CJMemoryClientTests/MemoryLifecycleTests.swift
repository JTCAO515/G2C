import Foundation
import Testing
import CJAPI
import OpenAPIRuntime
import HTTPTypes
@testable import CJMemoryClient

// In-process wire tests only. Actual App/API/PG acceptance is a separate matrix.
actor LifecycleWire: ClientTransport {
    let id = "synthetic-lifecycle"
    var kind: String
    var state: String
    var version = 1
    var text = "original"
    var source = "source-test"
    var sourceVersion = 1
    var failure: String?
    var loseReply = false
    var queryNull = false
    var badHash = false
    var calls: [(String, Data)] = []
    var receipts: [String: [String: Any]] = [:]
    init(kind: String = "preference", state: String = "active") { self.kind = kind; self.state = state }
    func configure(failure: String? = nil, loseReply: Bool = false, queryNull: Bool = false, badHash: Bool = false) {
        self.failure = failure; self.loseReply = loseReply; self.queryNull = queryNull; self.badHash = badHash
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data
        if let body { bytes = try await Data(collecting: body, upTo: 32768) } else { bytes = Data() }
        calls.append((operationID, bytes))
        var object: [String: Any] = ["request_id": trace]
        var status = HTTPResponse.Status.ok
        if operationID == "getMemoryItem" {
            var item = try JSONSerialization.jsonObject(with: Data(itemJSON(id: id, timestamp: "2026-10-30T01:00:00Z").utf8)) as! [String: Any]
            var command = item["command"] as! [String: Any]
            command["kind"] = kind; command["text"] = text; command["source_id"] = source; command["source_version"] = sourceVersion
            item["command"] = command; item["version"] = version; item["status"] = state
            object["item"] = item
        } else if operationID == "applyMemoryEditAction" || operationID == "applyMemoryStopUseAction" {
            let a = try JSONSerialization.jsonObject(with: bytes) as! [String: Any]
            if let failure {
                status = .conflict
                object["error"] = ["code": "MEMORY_MANAGEMENT_CONFLICT", "category": "conflict", "message_en": "Conflict", "message_zh": "冲突", "outcome": failure, "recovery": "do_not_retry"]
            } else {
                let expectedVersion = a["expected_version"] as! Int
                let expectedSourceVersion = a["expected_source_version"] as! Int
                let matchesVersion = expectedVersion == version && expectedSourceVersion == sourceVersion
                #expect(matchesVersion)
                if operationID == "applyMemoryEditAction" {
                    text = a["text"] as! String; source = "edit-v1:" + digest(bytes); sourceVersion = 1
                } else { let matchesSource = a["source_id"] as? String == source; #expect(matchesSource); state = "withdrawn" }
                version += 1
                let receipt: [String: Any] = ["action_id": a["action_id"]!, "item_id": id, "version": version, "status": state,
                    "input_sha256": badHash ? String(repeating: "0", count: 64) : digest(bytes)]
                receipts[a["action_id"] as! String] = receipt; object["receipt"] = receipt
                if loseReply { throw MemoryFailure.exchangeUnknown }
            }
        } else if operationID == "queryMemoryManagementReceipt" || operationID == "getMemoryStopUseReceipt" {
            let receipt = receipts.first { request.path!.contains($0.key) }?.value
            object["receipt"] = queryNull ? NSNull() : receipt.map { $0 as Any } ?? NSNull()
        } else { throw MemoryFailure.invalidInput }
        var response = HTTPResponse(status: status)
        response.headerFields[.contentType] = "application/json"; response.headerFields[.cacheControl] = "no-store"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        return (response, HTTPBody(try JSONSerialization.data(withJSONObject: object)))
    }
}

@MainActor struct MemoryLifecycleTests {
    @Test(arguments: ["fact", "experience", "preference"], ["active", "disabled"])
    func editKeepsExactTextAndSealedState(kind: String, state: String) async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let wire = LifecycleWire(kind: kind, state: state)
        let client = try f.client(wire); let selected = try await f.selection(client, id: wire.id)
        let input = "  新输入 e\u{301}\nOriginal spacing retained\t"
        guard case .historicalReceipt(let receipt) = try await client.editMemory(text: input, selection: selected, binding: f.base.binding) else { Issue.record("missing edit receipt"); return }
        #expect(receipt.status.rawValue == state && receipt.version == 2)
        let original = try #require(f.store().pending().first)
        let decoded = try JSONDecoder().decode(Components.Schemas.MemoryManagementEditAction.self, from: original.originalUTF8)
        #expect(Data(decoded.text.utf8) == Data(input.utf8))
        #expect(original.originalStatus?.rawValue == state && original.expectedSHA256 == digest(original.originalUTF8))
        let reopened = try f.client(wire)
        guard case .historicalReceipt = try await reopened.queryManagement(actionID: original.actionID, binding: f.base.binding) else { Issue.record("missing original receipt"); return }
        #expect(try f.store().pending().first?.originalUTF8 == original.originalUTF8)
        #expect(await wire.calls.filter { $0.0 == "applyMemoryEditAction" }.count == 1)
    }
    @Test func stopUseRecoversThroughItsOwnReceiptWithoutRewritingOriginal() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let wire = LifecycleWire(); let client = try f.client(wire)
        let selected = try await f.selection(client, id: wire.id)
        guard case .historicalStopUseReceipt(let receipt) = try await client.stopUsingMemory(selection: selected, binding: f.base.binding) else { Issue.record("missing stop-use receipt"); return }
        #expect(receipt.status == .withdrawn && receipt.version == 2)
        let original = try #require(f.store().pending().first); let before = original.originalUTF8
        let reopened = try f.client(wire)
        guard case .historicalStopUseReceipt = try await reopened.queryManagement(actionID: original.actionID, binding: f.base.binding) else { Issue.record("wrong receipt route"); return }
        #expect(await wire.calls.filter { $0.0 == "getMemoryStopUseReceipt" }.count == 1)
        #expect(await wire.calls.filter { $0.0 == "queryMemoryManagementReceipt" }.isEmpty)
        #expect(try f.store().pending().first?.originalUTF8 == before)
    }
    @Test func explicitEditFailureSurvivesReopenAndAllowsOnlyFreshReview() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let wire = LifecycleWire(); let client = try f.client(wire)
        await wire.configure(failure: "failed")
        let selected = try await f.selection(client, id: wire.id)
        guard case .rejected(409, "MEMORY_MANAGEMENT_CONFLICT") = try await client.editMemory(text: "keep this input", selection: selected, binding: f.base.binding) else { Issue.record("not explicit failure"); return }
        let original = try #require(f.store().pending().first)
        let reopened = try f.client(wire)
        guard case .rejected = try await reopened.queryManagement(actionID: original.actionID, binding: f.base.binding) else { Issue.record("failure lost"); return }
        await #expect(throws: MemoryFailure.staleBinding) { try await client.editMemory(text: "new", selection: selected, binding: f.base.binding) }
        await wire.configure()
        let fresh = try await f.selection(reopened, id: wire.id)
        guard case .historicalReceipt = try await reopened.editMemory(text: "explicit fresh review", selection: fresh, binding: f.base.binding) else { Issue.record("fresh action blocked"); return }
        let records = try f.store().pending(); #expect(records.count == 2)
        #expect(records.contains { $0.originalUTF8 == original.originalUTF8 && $0.actionID == original.actionID })
    }
    @Test func unknownEditAndNullReceiptStillForbidNewActions() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let wire = LifecycleWire(); let client = try f.client(wire)
        let selected = try await f.selection(client, id: wire.id); await wire.configure(loseReply: true)
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await client.editMemory(text: "retain unknown", selection: selected, binding: f.base.binding) }
        let original = try #require(f.store().pending().first); let reopened = try f.client(wire)
        await wire.configure(queryNull: true)
        guard case .notObserved = try await reopened.queryManagement(actionID: original.actionID, binding: f.base.binding) else { Issue.record("null granted authority"); return }
        let fresh = try await f.selection(reopened, id: wire.id)
        await #expect(throws: MemoryFailure.pendingRequiresQuery) { try await reopened.stopUsingMemory(selection: fresh, binding: f.base.binding) }
        #expect(await wire.calls.filter { $0.0 == "applyMemoryEditAction" }.count == 1)
        #expect(try f.store().pending().first?.originalUTF8 == original.originalUTF8)
    }
    @Test(arguments: ["candidate", "withdrawn"], ["fact", "inference"])
    func editNeverPromotesCandidatesOrInference(state: String, kind: String) async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let wire = LifecycleWire(kind: kind, state: state); let client = try f.client(wire)
        let selected = try await f.selection(client, id: wire.id)
        await #expect(throws: MemoryFailure.invalidInput) { try await client.editMemory(text: "not authorized", selection: selected, binding: f.base.binding) }
        #expect(try f.store().pending().isEmpty)
        #expect(await wire.calls.filter { $0.0 == "applyMemoryEditAction" }.isEmpty)
    }
}
