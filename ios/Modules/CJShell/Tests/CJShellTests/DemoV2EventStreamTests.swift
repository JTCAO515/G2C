import Foundation
import Testing
@testable import CJShell

struct DemoV2EventStreamTests {
    private let receipt = DemoV2Dialogue.Receipt(message_id: "m", conversation_id: "demo-dialogue-" + String(repeating: "a", count: 32),
                                                run_id: "r", input_sha256: String(repeating: "f", count: 64))

    @Test func fragmentedUTF8AndKeepaliveOnlyAdvanceOnCompleteEvents() throws {
        var stream = try DemoV2EventStream(receipt: receipt, maximumWireBytes: 2048)
        let raw = Data((": keepalive\r\n\r\n" + frame(1, text: "北京 🧳") + frame(2, text: " 继续")).utf8)
        var events: [DemoV2Dialogue.Event] = []
        for byte in raw { events += try stream.append(Data([byte])) }
        #expect(events.map(\.eventID) == ["event-1", "event-2"])
        #expect(stream.lastEventID == "2")
        guard case .answer(let first) = events[0].payload else { Issue.record("Expected an answer delta"); return }
        #expect(first.text == "北京 🧳")
        try stream.finish()
    }

    @Test func malformedOrForeignFrameNeverSkipsAnUndisplayedEvent() throws {
        var stream = try DemoV2EventStream(receipt: receipt, maximumWireBytes: 2048, resumingAfter: 2)
        let mixed = frame(3, text: "next") + frame(4, text: "foreign", run: "wrong")
        #expect(throws: DemoV2Dialogue.Failure.mismatchedOriginal) { try stream.append(Data(mixed.utf8)) }
        #expect(stream.lastEventID == "2")
        #expect(throws: DemoV2EventStream.Failure.invalidSequence) {
            try stream.append(Data(frame(4, text: "skip").utf8))
        }
        let original = try stream.append(Data(frame(3, text: "next").utf8))
        #expect(original.count == 1 && stream.lastEventID == "3")
        #expect(throws: DemoV2EventStream.Failure.invalidSequence) {
            try stream.append(Data(frame(3, text: "repeat").utf8))
        }
    }

    @Test func incompleteFrameIsNotAConfirmedEvent() throws {
        var stream = try DemoV2EventStream(receipt: receipt, maximumWireBytes: 2048)
        #expect(try stream.append(Data(frame(1, text: "truncated").dropLast().utf8)).isEmpty)
        #expect(stream.lastEventID == nil)
        #expect(throws: DemoV2EventStream.Failure.incompleteFrame) { try stream.finish() }
    }

    private func frame(_ seq: Int, text: String, run: String = "r") -> String {
        """
        id: \(seq)
        event: dialogue
        data: {"version":"DEMO-dialogue-event.1","event_id":"event-\(seq)","conversation_id":"\(receipt.conversation_id)","message_id":"m","run_id":"\(run)","kind":"answer_delta","payload":{"text":"\(text)"}}


        """
    }
}
