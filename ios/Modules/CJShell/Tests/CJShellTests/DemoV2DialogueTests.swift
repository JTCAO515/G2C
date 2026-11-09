import Foundation
import Testing
@testable import CJShell

struct DemoV2DialogueTests {
    private let id = UUID(uuidString: "f0a58744-d9cc-4b11-a5fa-9a1a0a4d02a1")!
    private let conversation = "demo-dialogue-0123456789abcdef0123456789abcdef"

    @Test func firstMessageKeepsOriginalTextWithoutHiddenSelections() throws {
        let original = "  北京 / Beijing 🧳\n"
        let command = try DemoV2Dialogue.Message(id: id, text: original, language: .chinese, destination: .initial)
        let json = try #require(JSONSerialization.jsonObject(with: command.encoded()) as? [String: String])
        #expect(json == [
            "version": "DEMO-dialogue-message.1",
            "message_id": id.uuidString.lowercased(),
            "text": original,
            "locale": "zh"
        ])
        #expect(try command.encoded() == command.encoded())
    }

    @Test func conversationContinuationAndCreationAreExclusive() throws {
        let next = try DemoV2Dialogue.Message(id: id, text: "Next", language: .english, destination: .conversation(conversation))
        let fresh = try DemoV2Dialogue.Message(id: id, text: "New", language: .english, destination: .newConversation)
        #expect(next.conversation_id == conversation && next.new_conversation == nil)
        #expect(fresh.conversation_id == nil && fresh.new_conversation == true)
        #expect(throws: DemoV2Dialogue.Failure.invalidMessage) {
            try DemoV2Dialogue.Message(id: id, text: " \n", language: .english, destination: .initial)
        }
    }

    @Test func receiptAndEventStayOnTheSameOriginal() throws {
        let command = try DemoV2Dialogue.Message(id: id, text: "Hello", language: .english, destination: .initial)
        let original = try DemoV2Dialogue.OriginalMessage(command)
        let receipt = DemoV2Dialogue.Receipt(message_id: command.message_id, conversation_id: conversation, run_id: "run",
                                             input_sha256: original.sha256)
        try receipt.checkOriginal(original)
        let accepted = try event(kind: "answer_delta", messageID: command.message_id, runID: "run", payload: ["text": "Hello"])
        try accepted.checkOriginal(receipt)
        let foreign = try event(kind: "answer_delta", messageID: command.message_id, runID: "other", payload: ["text": "Hello"])
        #expect(throws: DemoV2Dialogue.Failure.mismatchedOriginal) { try foreign.checkOriginal(receipt) }
        let later = try DemoV2Dialogue.Message(id: UUID(), text: "Hello", language: .english, destination: .initial)
        #expect(throws: DemoV2Dialogue.Failure.mismatchedOriginal) {
            try receipt.checkOriginal(DemoV2Dialogue.OriginalMessage(later))
        }
    }

    @Test func unknownAndUnsafeSourcesCannotOpen() throws {
        let unknown = try event(kind: "source", payload: ["source_id": "1", "label": "Unknown", "state": "unknown"])
        guard case .source(let source) = unknown.payload else { Issue.record("Expected a source"); return }
        #expect(source.openableURL == nil)
        #expect(throws: DemoV2Dialogue.Failure.invalidSource) {
            try event(kind: "source", payload: [
                "source_id": "1", "label": "Unknown", "state": "unknown", "url": "https://example.test/"
            ])
        }
        let unsafe = try event(kind: "source", payload: [
            "source_id": "2", "label": "Unsafe", "state": "verified", "url": "https://user@example.test/"
        ])
        guard case .source(let other) = unsafe.payload else { Issue.record("Expected a source"); return }
        #expect(other.openableURL == nil)
    }

    @Test func reconciliationUsesOriginalIDAndNeverAttachesTheWriteBody() throws {
        let origin = try #require(URL(string: "https://example.test"))
        let command = try DemoV2Dialogue.Message(id: id, text: "  原文  ", language: .chinese, destination: .initial)
        let original = try DemoV2Dialogue.OriginalMessage(command)
        let submission = original.submission(to: origin)
        #expect(submission.httpMethod == "POST")
        #expect(submission.httpBody == original.bytes)
        #expect(submission.value(forHTTPHeaderField: "Content-Type") == "application/octet-stream")
        let read = original.reconciliation(at: origin)
        #expect(read.httpMethod == "GET")
        #expect(read.httpBody == nil)
        #expect(read.url == DemoV2Dialogue.Route.originalMessage(command.message_id).url(origin: origin))
    }

    @Test func unknownReadsQueryTheExactOriginal() throws {
        let origin = try #require(URL(string: "https://example.test"))
        let message = DemoV2Dialogue.Route.originalMessage("id+a/b").url(origin: origin)
        let action = DemoV2Dialogue.Route.originalAction("action+1").url(origin: origin)
        #expect(message.path == "/v1/demo-dialogue/messages")
        #expect(message.absoluteString.contains("id%2Ba/b"))
        #expect(action.path == "/v1/demo-dialogue/actions")
        #expect(URLComponents(url: message, resolvingAgainstBaseURL: false)?.queryItems == [
            URLQueryItem(name: "message_id", value: "id+a/b")
        ])
        #expect(URLComponents(url: action, resolvingAgainstBaseURL: false)?.queryItems == [
            URLQueryItem(name: "action_id", value: "action+1")
        ])
    }

    @Test func frozenEnvelopeRequiresExactOriginalDigestAndSeparatesNullRead() throws {
        let original = try DemoV2Dialogue.OriginalMessage(.init(id: id, text: "  原文  ", language: .chinese, destination: .initial))
        func response(_ fields: [String: Any], operation: DemoV2Dialogue.MessageOperation) throws -> DemoV2Dialogue.MessageResult {
            let data = try JSONSerialization.data(withJSONObject: fields.merging([
                "version": "DEMO-dialogue-receipt.1", "request_id": "fixture"
            ]) { field, _ in field })
            return try DemoV2Dialogue.response(data, status: 200, contentType: "application/json",
                                               original: original, operation: operation)
        }
        var receipt = [
            "message_id": original.command.message_id, "conversation_id": conversation, "run_id": "run",
            "input_sha256": original.sha256
        ]
        guard case .accepted = try response(["receipt": receipt], operation: .submit) else {
            Issue.record("Expected the original write receipt")
            return
        }
        receipt["input_sha256"] = String(repeating: "f", count: 64)
        #expect(throws: DemoV2Dialogue.Failure.mismatchedOriginal) { try response(["receipt": receipt], operation: .reconcile) }
        guard case .notObserved = try response(["receipt": NSNull()], operation: .reconcile) else {
            Issue.record("A null read must keep the outcome unresolved")
            return
        }
        #expect(throws: DemoV2Dialogue.Failure.invalidResponse) { try response(["receipt": NSNull()], operation: .submit) }
        #expect(throws: DemoV2Dialogue.Failure.invalidResponse) { try response([:], operation: .reconcile) }
    }

    @Test func dailyLimitAndUncertainWriteRemainDifferentOutcomes() throws {
        let original = try DemoV2Dialogue.OriginalMessage(.init(id: id, text: "Hello", language: .english, destination: .initial))
        func failure(_ status: Int, code: String, outcome: String, recovery: String) throws -> DemoV2Dialogue.MessageResult {
            let data = try JSONSerialization.data(withJSONObject: [
                "request_id": "fixture", "error": ["code": code, "outcome": outcome, "recovery": recovery]
            ])
            return try DemoV2Dialogue.response(data, status: status, contentType: "application/json",
                                               original: original, operation: .submit)
        }
        guard case .dailyLimit = try failure(429, code: "DEMO_DAILY_LIMIT", outcome: "failed", recovery: "do_not_retry"),
              case .unknown = try failure(503, code: "MESSAGE_OUTCOME_UNKNOWN", outcome: "unknown", recovery: "reconcile_original")
        else { Issue.record("Daily limit and uncertain write must render distinct states"); return }
    }

    private func event(kind: String, messageID: String = "message", runID: String = "run",
                       payload: [String: Any]) throws -> DemoV2Dialogue.Event {
        let body: [String: Any] = [
            "version": "DEMO-dialogue-event.1",
            "event_id": "event",
            "conversation_id": conversation,
            "message_id": messageID,
            "run_id": runID,
            "kind": kind,
            "payload": payload
        ]
        return try JSONDecoder().decode(DemoV2Dialogue.Event.self, from: JSONSerialization.data(withJSONObject: body))
    }
}
