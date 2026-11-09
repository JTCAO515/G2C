#if DEBUG && os(iOS) && targetEnvironment(simulator)
import CryptoKit
import SwiftUI
import Observation
import CJMessageHTTP

/// Simulator-only fixture for the actual signed Beta assistant controller.
public struct DemoV2LiveFixture: View {
    let shell: ShellState
    @State private var fixture: LocalDialogue
    @State private var model: DemoV2LiveAssistantModel

    @MainActor public init(shell: ShellState) {
        self.shell = shell
        let fixture = LocalDialogue()
        _fixture = State(initialValue: fixture)
        _model = State(initialValue: DemoV2LiveAssistantModel(shell: shell, services: .init(
            submit: fixture.submit, reconcile: fixture.reconcile, unresolved: fixture.unresolved,
            originalText: fixture.originalText, read: fixture.read), isCurrentSession: { true }))
    }

    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Text(shell.language.text("Local live-controller fixture", "本地助手控制器夹具"))
                    .font(.caption.weight(.semibold))
                Text("POST \(fixture.submissions) · GET \(fixture.queries)")
                    .font(.caption)
                    .accessibilityIdentifier("demo.v2.fixture.counts")
                DemoV2LiveAssistant(model: model, language: shell.language)
            }
        }
    }
}

@MainActor @Observable private final class LocalDialogue {
    private struct Stored {
        let receipt: DemoDialogueMessageReceipt
        let text: String
    }

    private var original: Stored?
    private var queryRequired = false
    private(set) var submissions = 0
    private(set) var queries = 0

    func submit(_ bytes: Data) async throws -> DemoDialogueMessageOutcome {
        guard let request = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let messageID = request["message_id"] as? String, let text = request["text"] as? String,
              request["version"] as? String == "DEMO-dialogue-message.1" else { throw DemoV2Dialogue.Failure.invalidMessage }
        let conversation = request["conversation_id"] as? String
            ?? "demo-dialogue-" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        let receipt = try JSONDecoder().decode(DemoDialogueMessageReceipt.self, from: JSONSerialization.data(withJSONObject: [
            "message_id": messageID, "conversation_id": conversation, "run_id": UUID().uuidString.lowercased(),
            "input_sha256": SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        ]))
        original = .init(receipt: receipt, text: text)
        submissions += 1
        queryRequired = submissions == 1
        return queryRequired ? .unknown : .accepted(receipt)
    }

    func reconcile(_ messageID: String) async throws -> DemoDialogueMessageOutcome {
        guard let original, original.receipt.messageID == messageID, queryRequired
        else { throw DemoV2Dialogue.Failure.mismatchedOriginal }
        queries += 1
        queryRequired = false
        return .accepted(original.receipt)
    }

    func unresolved() throws -> [String] {
        if queryRequired, let original { return [original.receipt.messageID] }
        return []
    }

    func originalText(_ messageID: String) throws -> String {
        guard let original, original.receipt.messageID == messageID else { throw DemoV2Dialogue.Failure.mismatchedOriginal }
        return original.text
    }

    func read(_ messageID: String, _ cursor: String?, _ consume: @MainActor (Data) throws -> Void) async throws {
        guard let original, original.receipt.messageID == messageID else { throw DemoV2Dialogue.Failure.mismatchedOriginal }
        let receipt = original.receipt
        let after = cursor.flatMap(Int.init) ?? 0
        for (sequence, kind, payload) in [
            (1, "status", ["status": "queued", "stage": "queued"]),
            (64, "answer_delta", ["text": "Use the station map · 查看站内线路图"]),
            (128, "status", ["status": "completed", "stage": "completed"])
        ] where sequence > after {
            let raw = try JSONSerialization.data(withJSONObject: [
                "version": "DEMO-dialogue-event.1", "event_id": String(sequence), "kind": kind, "payload": payload,
                "message_id": receipt.messageID, "conversation_id": receipt.conversationID, "run_id": receipt.runID
            ])
            guard let json = String(data: raw, encoding: .utf8) else { throw DemoV2Dialogue.Failure.invalidEvent }
            try consume(Data("id: \(sequence)\nevent: \(kind)\ndata: \(json)\n\n".utf8))
        }
    }
}
#endif
