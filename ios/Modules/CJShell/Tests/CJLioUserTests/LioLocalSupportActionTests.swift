import Foundation
import Testing
@testable import CJLioUser

struct LioLocalSupportActionTests {
    @Test func onlyTheMatchingResponseCanOpenLocalSupport() throws {
        let action = try decode(action: #""open_local_support""#)
        #expect(try action.opensSupport(conversationID: "sample-chat", messageID: "sample-answer"))
        #expect(throws: LioLocalSupportAction.Failure.differentMessage) {
            try action.opensSupport(conversationID: "other-chat", messageID: "sample-answer")
        }
        #expect(throws: LioLocalSupportAction.Failure.differentMessage) {
            try action.opensSupport(conversationID: "sample-chat", messageID: "other-answer")
        }
        let regular = try decode(action: "null")
        #expect(try !regular.opensSupport(conversationID: "sample-chat", messageID: "sample-answer"))
    }

    @Test func rejectsUnexpectedFormatsOrInstructions() {
        #expect(throws: DecodingError.self) { try decode(action: #""call_now""#) }
        #expect(throws: DecodingError.self) { try decode(version: "LIO-local-support-action.2", action: "null") }
        #expect(throws: DecodingError.self) {
            try JSONDecoder().decode(LioLocalSupportAction.self, from: Data("""
            {"version":"LIO-local-support-action.1","conversation_id":"sample-chat","message_id":"sample-answer"}
            """.utf8))
        }
    }

    private func decode(version: String = "LIO-local-support-action.1", action: String) throws -> LioLocalSupportAction {
        try JSONDecoder().decode(LioLocalSupportAction.self, from: Data("""
        {"version":"\(version)","conversation_id":"sample-chat","message_id":"sample-answer","action":\(action)}
        """.utf8))
    }
}
