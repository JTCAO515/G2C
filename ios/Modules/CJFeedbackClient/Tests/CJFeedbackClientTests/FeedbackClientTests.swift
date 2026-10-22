import Testing
import Foundation
import CryptoKit
import CJAPI
import CJMessageKeys
import CJSession
import CJMessageHTTP
@testable import CJFeedbackClient

@MainActor struct FeedbackClientTests {
    @Test(arguments: [false, true]) func officialExactBodyAndOriginalQuery(linked: Bool) async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(linked: linked)
        let body = try receiptJSON(original)
        let wire = Interceptor { _, _, _ in Reply(text: body) }
        let client = try h.client(wire); let op = try client.begin(binding: h.binding)
        guard case .submitted(let receipt) = try await client.submit(original, operation: op) else { Issue.record("missing receipt"); return }
        #expect(receipt.input_sha256 == digest(original.originalUTF8))
        #expect(receipt.submitted_at.timeIntervalSince1970 == 1792663200)
        guard case .submitted(let replay) = try await client.queryOriginal(actionID: original.actionID, operation: op) else { Issue.record("missing original"); return }
        #expect(replay == receipt)
        let calls = await wire.calls
        #expect(calls.count == 2); #expect(calls[0].bytes == original.originalUTF8)
        #expect(calls[0].operation == "submitFeedback"); #expect(calls[1].operation == "queryFeedbackAction")
        #expect(calls[1].bytes.isEmpty); #expect(calls[1].path?.contains(original.actionID) == true)
        #expect(calls[0].authorization == "Bearer synthetic-test-token")
        let object = try #require(JSONSerialization.jsonObject(with: calls[0].bytes) as? [String: Any])
        #expect(Set(object.keys) == ["action_id", "problem", "expectation", "references"])
        #expect(try client.pending(operation: op).count == 1)
    }
    @Test(arguments: ["2026-10-22T10:00:00Z", "2026-10-22T10:00:00.125Z"]) func officialUTC(date: String) async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending()
        let body = try receiptJSON(original, date: date)
        let client = try h.client(Interceptor { _, _, _ in Reply(text: body) })
        guard case .submitted(let receipt) = try await client.submit(original, operation: client.begin(binding: h.binding)) else { Issue.record("missing"); return }
        #expect(receipt.submitted_at.timeIntervalSince1970 == (date.contains(".125") ? 1792663200.125 : 1792663200))
    }
    @Test func lostACKReopenQueryOnly() async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending(linked: true)
        let first = Interceptor { _, _, _ in throw URLError(.networkConnectionLost) }
        let client = try h.client(first); let op = try client.begin(binding: h.binding)
        await #expect(throws: FeedbackFailure.exchangeUnknown) { try await client.submit(original, operation: op) }
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.submit(original, operation: op) }
        #expect(await first.calls.count == 1)
        let replay = try receiptJSON(original)
        let second = Interceptor { _, _, _ in Reply(text: replay) }
        let reopened = try h.client(second); let next = try reopened.begin(binding: h.binding)
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await reopened.submit(pending(actionID: "new"), operation: next) }
        guard case .submitted(let receipt) = try await reopened.queryOriginal(actionID: original.actionID, operation: next) else { Issue.record("missing"); return }
        if case .FeedbackSourceObservation(let source) = receipt.source { #expect(source.run_status_at_read == .running); #expect(source.event_highwater_at_read == 4) }
        else { Issue.record("source lost") }
        #expect(await second.calls.map(\.operation) == ["queryFeedbackAction"])
    }
    @Test(arguments: ["null", "{}", "false", "42", "\"invalid\""]) func nullAndMalformedLookupNeverAllowResend(value: String) async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending(); let store = try h.store(); try store.append(original)
        let response = "{\"request_id\":\"\(trace)\",\"receipt\":\(value)}"
        let wire = Interceptor { _, _, _ in Reply(text: response) }; let client = try h.client(wire, store: store); let op = try client.begin(binding: h.binding)
        if value == "null" {
            guard case .notObserved = try await client.queryOriginal(actionID: original.actionID, operation: op) else { Issue.record("null became success"); return }
        } else { await #expect(throws: (any Error).self) { try await client.queryOriginal(actionID: original.actionID, operation: op) } }
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.submit(pending(actionID: "replacement"), operation: op) }
        #expect(await wire.calls.count == 1)
    }
    @Test(arguments: ["{}", "false", "null"]) func badLinkedSourceRejected(source: String) async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending(linked: true)
        let response = try receiptJSON(original, source: source)
        let client = try h.client(Interceptor { _, _, _ in Reply(text: response) })
        await #expect(throws: (any Error).self) { try await client.submit(original, operation: client.begin(binding: h.binding)) }
    }
    @Test(arguments: ["action", "feedbackHash", "messageHash", "message", "run", "missingSource", "extra", "duplicate", "generalLinked"]) func malformedReceiptRejected(kind: String) async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending(linked: kind != "generalLinked")
        var body = try receiptJSON(original)
        switch kind {
        case "action": body = body.replacingOccurrences(of: original.actionID, with: "different")
        case "feedbackHash": body = body.replacingOccurrences(of: original.inputSHA256, with: String(repeating: "0", count: 64))
        case "messageHash": body = body.replacingOccurrences(of: original.inputSHA256, with: String(repeating: "b", count: 64))
        case "message": body = body.replacingOccurrences(of: "消息e\\u0301", with: "消息é")
        case "run": body = body.replacingOccurrences(of: "运行", with: "foreign")
        case "missingSource":
            let data = try #require(body.data(using: .utf8)); var object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
            var receipt = try #require(object["receipt"] as? [String: Any]); receipt.removeValue(forKey: "source"); object["receipt"] = receipt
            body = String(decoding: try JSONSerialization.data(withJSONObject: object), as: UTF8.self)
        case "extra": body = body.replacingOccurrences(of: "\"status\":", with: "\"owner\":\"invented\",\"status\":")
        case "duplicate": body = body.replacingOccurrences(of: "\"status\":", with: "\"status\":\"submitted\",\"status\":")
        default:
            let linked = try receiptJSON(pending(linked: true))
            let object = try #require(JSONSerialization.jsonObject(with: Data(linked.utf8)) as? [String: Any])
            let record = try #require(object["receipt"] as? [String: Any])
            let source = try #require(record["source"] as? [String: Any])
            body = try receiptJSON(original, source: String(decoding: JSONSerialization.data(withJSONObject: source), as: UTF8.self))
        }
        let final = body
        let client = try h.client(Interceptor { _, _, _ in Reply(text: final) })
        await #expect(throws: (any Error).self) { try await client.submit(original, operation: client.begin(binding: h.binding)) }
    }
    @Test func invalidInputAndExactUnicode() throws {
        #expect(throws: (any Error).self) { try FeedbackPending(problem: " ", expectation: "", context: nil) }
        #expect(throws: (any Error).self) { try FeedbackPending(problem: String(repeating: "界", count: 2001), expectation: "", context: nil) }
        #expect(throws: (any Error).self) { try FeedbackPending(problem: "a\0", expectation: "", context: nil) }
        #expect(throws: (any Error).self) { try FeedbackContext(messageID: "") }
        #expect(throws: (any Error).self) { try FeedbackContext(messageID: "message", runID: " ") }
        #expect(throws: (any Error).self) { try FeedbackPending(problem: "p", expectation: "", context: nil, actionID: "not.allowed") }
        let original = try pending(linked: true)
        #expect(Data(try original.action().references[0].id.utf8) == Data("消息e\u{301}".utf8))
        #expect(!same(try original.action().references[0].id, "消息é"))
        #expect(!original.description.contains("自愿"))
    }
    @Test func malformedStoredOriginalShapes() throws {
        let shapes = ["[{\"kind\":\"run\",\"id\":\"r\"}]", "[{\"kind\":\"memory\",\"id\":\"m\"}]", "[{\"kind\":\"trip\",\"id\":\"t\"}]", "[{\"kind\":\"proposal\",\"id\":\"p\"}]", "[{\"kind\":\"message\",\"id\":\"m\"},{\"kind\":\"message\",\"id\":\"m2\"}]"]
        for shape in shapes {
            let raw = Data("{\"action_id\":\"a\",\"problem\":\"p\",\"expectation\":\"\",\"references\":\(shape)}".utf8)
            let stored = try JSONSerialization.data(withJSONObject: ["actionID":"a", "originalUTF8":raw.base64EncodedString(), "inputSHA256":digest(raw)])
            let value = try JSONDecoder().decode(FeedbackPending.self, from: stored)
            #expect(throws: (any Error).self) { try value.validate() }
        }
    }
}
