import Foundation
import CryptoKit
import CJAPI
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
        let verified = try event(kind: "source", payload: [
            "source_id": "3", "label": "Original", "state": "verified", "url": "https://example.test/original"
        ])
        guard case .source(let valid) = verified.payload else { Issue.record("Expected a source"); return }
        #expect(valid.openableURL?.absoluteString == "https://example.test/original")
        let pending = try event(kind: "source", payload: [
            "source_id": "4", "label": "Pending", "state": "pending", "url": "https://example.test/original"
        ])
        guard case .source(let unverified) = pending.payload else { Issue.record("Expected a source"); return }
        #expect(unverified.openableURL == nil)
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

    @Test func tripProjectionKeepsOriginalLocalTimesAndUnknownFacts() throws {
        let parsed = try event(kind: "trip_candidate", payload: [
            "card_id": "trip-card", "version": 1, "status": "pending",
            "proposal_id": "proposal", "trip_id": NSNull(), "expected_trip_version": NSNull(),
            "candidate_hash": String(repeating: "1", count: 64),
            "days": [
                ["date": "2026-11-10", "items": [
                    ["item_id": "fixed", "label": "集合", "place": "酒店大堂", "starts_at": "2026-11-10T09:00",
                     "ends_at": "2026-11-10T10:00", "time_zone": "Asia/Shanghai", "source_ids": ["needs"], "fixed": true]
                ]],
                ["date": NSNull(), "items": [
                    ["item_id": "unknown", "label": "Walk", "place": NSNull(), "starts_at": NSNull(),
                     "ends_at": NSNull(), "time_zone": NSNull(), "source_ids": [String](), "fixed": NSNull()]
                ]]
            ]
        ])
        guard case .trip(let card) = parsed.payload else { Issue.record("Expected an itinerary candidate"); return }
        let fixed = try #require(card.days.first?.items.first)
        let unknown = try #require(card.days.last?.items.first)
        #expect(fixed.starts_at == "2026-11-10T09:00")
        #expect(fixed.ends_at == "2026-11-10T10:00")
        #expect(fixed.fixed == true && fixed.source_ids == ["needs"])
        #expect(card.days.last?.date == nil)
        #expect(unknown.place == nil && unknown.starts_at == nil && unknown.fixed == nil)
        #expect(card.trip_id == nil && card.expected_trip_version == nil)
    }

    @Test func memoryCandidateKeepsProposalTextAndIdentity() throws {
        let parsed = try event(kind: "memory_candidate", payload: [
            "card_id": "memory-card", "version": 3, "status": "pending", "candidate_id": "original-candidate",
            "kind": "preference", "text": " 每天两个景点 / two sights 🧳 "
        ])
        guard case .memory(let card) = parsed.payload else { Issue.record("Expected a memory candidate"); return }
        #expect(card.text == " 每天两个景点 / two sights 🧳 ")
        #expect(card.candidate_id == "original-candidate")
        #expect(card.version == 3 && card.status == "pending")
    }

    @Test func explicitActionKeepsTheOriginalCardVersionAndRejectsOtherKinds() throws {
        let original = try DemoV2Dialogue.OriginalMessage(.init(id: id, text: "Preference", language: .english, destination: .initial))
        let receipt = DemoV2Dialogue.Receipt(message_id: original.command.message_id, conversation_id: conversation,
                                             run_id: "run", input_sha256: original.sha256)
        let card = try event(kind: "memory_candidate", messageID: receipt.message_id, payload: [
            "card_id": "card", "version": 3, "status": "pending", "candidate_id": "candidate",
            "kind": "preference", "text": "Slow pace"
        ])
        let action = try DemoV2Dialogue.Action(id: id, operation: .remember, event: card, receipt: receipt)
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(action)) as? [String: Any])
        #expect(json["version"] as? String == "DEMO-dialogue-action.1")
        #expect(json["action_id"] as? String == id.uuidString.lowercased())
        #expect(json["conversation_id"] as? String == conversation)
        #expect(json["card_id"] as? String == "card")
        #expect(json["expected_version"] as? Int == 3)
        #expect(json["operation"] as? String == "remember")
        #expect(json.count == 6)
        #expect(throws: DemoV2Dialogue.Failure.invalidAction) {
            try DemoV2Dialogue.Action(id: id, operation: .acceptTrip, event: card, receipt: receipt)
        }
    }

    @Test func planningV2UsesSameSelectorsAndManualCorrectionPatch() throws {
        let message = try DemoV2Dialogue.Message(id: id, text: "计划 / Plan", language: .chinese,
                                                destination: .initial, version: .planning)
        let original = try DemoV2Dialogue.OriginalMessage(message)
        let body = try #require(JSONSerialization.jsonObject(with: original.bytes) as? [String: Any])
        #expect(body["version"] as? String == "DEMO-dialogue-message.2")
        #expect(Set(body.keys) == ["version", "message_id", "text", "locale"])
        let receipt = DemoV2Dialogue.Receipt(message_id: message.message_id, conversation_id: conversation,
                                             run_id: "run", input_sha256: original.sha256)
        let card = try event(kind: "needs_card", messageID: message.message_id, payload: [
            "card_id": "needs", "version": 1, "status": "pending", "dates": ["start": "2026-11-10", "end": NSNull()],
            "city": "北京", "party_size": NSNull(), "pace": "轻松", "fixed_items": NSNull()
        ])
        guard case .needs(let needs) = card.payload else { Issue.record("Expected a typed needs card"); return }
        #expect(needs.dates?.start == "2026-11-10" && needs.dates?.end == nil)
        #expect(needs.party_size == nil && needs.fixed_items == nil)
        let changes = try JSONDecoder().decode(Components.Schemas.NeedsChanges.self,
            from: Data(#"{"party_size":{"state":"known","value":2}}"#.utf8))
        let correction = try DemoV2Dialogue.Action(id: id, operation: .correctNeeds, event: card, receipt: receipt, changes: changes)
        let encoded = try JSONEncoder().encode(correction)
        let payload = try #require(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        let patch = try #require(payload["changes"] as? [String: Any])
        let party = try #require(patch["party_size"] as? [String: Any])
        #expect(party["state"] as? String == "known" && party["value"] as? Int == 2)
        #expect(throws: DemoV2Dialogue.Failure.invalidAction) {
            try DemoV2Dialogue.Action(id: id, operation: .confirmNeeds, event: card, receipt: receipt, changes: changes)
        }
        #expect(throws: DemoV2Dialogue.Failure.invalidAction) {
            try DemoV2Dialogue.Action(id: id, operation: .correctNeeds, event: card, receipt: receipt)
        }

        let digest = SHA256.hash(data: encoded).map { String(format: "%02x", $0) }.joined()
        var reply: [String: Any] = [
            "action_id": correction.action_id, "conversation_id": conversation, "card_id": "needs",
            "version": 2, "operation": "correct_needs", "input_sha256": digest,
            "message_id": NSNull(), "run_id": NSNull(), "card": NSNull()
        ]
        let corrected = try JSONDecoder().decode(DemoV2Dialogue.ActionReceipt.self, from: JSONSerialization.data(withJSONObject: reply))
        try corrected.checkOriginal(correction, bytes: encoded)
        reply["message_id"] = "unexpected"
        reply["run_id"] = "unexpected"
        let spuriousRun = try JSONDecoder().decode(DemoV2Dialogue.ActionReceipt.self, from: JSONSerialization.data(withJSONObject: reply))
        #expect(throws: DemoV2Dialogue.Failure.invalidResponse) { try spuriousRun.checkOriginal(correction, bytes: encoded) }
    }

    @Test func confirmationReceiptBindsTheNewRunWithoutSubstitutingTheOldMessage() throws {
        let original = try DemoV2Dialogue.OriginalMessage(.init(id: id, text: "Plan", language: .english,
                                                                destination: .initial, version: .planning))
        let receipt = DemoV2Dialogue.Receipt(message_id: original.command.message_id, conversation_id: conversation,
                                             run_id: "run", input_sha256: original.sha256)
        let needs = try event(kind: "needs_card", messageID: receipt.message_id, payload: [
            "card_id": "needs", "version": 1, "status": "pending", "dates": NSNull(), "city": "Beijing",
            "party_size": 2, "pace": "Relaxed", "fixed_items": NSNull()
        ])
        let confirmation = try DemoV2Dialogue.Action(id: id, operation: .confirmNeeds, event: needs, receipt: receipt)
        let bytes = try JSONEncoder().encode(confirmation)
        let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        let payload: [String: Any] = [
            "action_id": confirmation.action_id, "conversation_id": conversation, "card_id": "needs",
            "version": 2, "operation": "confirm_needs", "input_sha256": digest, "message_id": "planned", "run_id": "next-run",
            "card": ["card_id": "needs", "version": 2, "status": "confirmed"]
        ]
        let response = try JSONDecoder().decode(DemoV2Dialogue.ActionReceipt.self, from: JSONSerialization.data(withJSONObject: payload))
        let newRun = try #require(try response.checkOriginal(confirmation, bytes: bytes))
        let planned = try event(kind: "answer_delta", messageID: "planned", runID: "next-run", payload: ["text": "Plan"])
        try planned.checkBinding(newRun)
        #expect(throws: DemoV2Dialogue.Failure.mismatchedOriginal) { try planned.checkOriginal(receipt) }
        #expect(throws: DemoV2Dialogue.Failure.mismatchedOriginal) { try needs.checkBinding(newRun) }
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
