import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJMessageHTTP

/// #1999: the App's side of `LIO-memory-consent.1` (`contracts/message/LIO-MEMORY-CONSENT-V1.md`).
@MainActor
struct LioMemoryConsentWireTests {
    private func request(_ state: LioMemoryConsentWire.State = .granted, id: String = "mc-7f3a") throws -> LioMemoryConsentWire.Request {
        try #require(LioMemoryConsentWire.Request(state: state, textVersion: "memory-2026-11", requestID: id))
    }

    @Test func theBodyHasExactlyTheContractsFields() throws {
        let object = try #require(JSONSerialization.jsonObject(with: request().originalUTF8) as? [String: String])
        #expect(object == ["version": "LIO-memory-consent.1", "state": "granted",
                           "consent_text_version": "memory-2026-11", "request_id": "mc-7f3a"])
        let withdrawn = try #require(JSONSerialization.jsonObject(with: request(.withdrawn).originalUTF8) as? [String: String])
        #expect(withdrawn["state"] == "withdrawn")
    }

    @Test func aRetryIsTheSameBytes() throws {
        #expect(try request().originalUTF8 == request().originalUTF8)
    }

    @Test func idsAndVersionsFollowTheContractsCharacterSetAndLengths() {
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: "consent-2026-11", requestID: "c-7f3a") != nil)
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: "a.b:c_d-1", requestID: "A") != nil)
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: "", requestID: "x") == nil)
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: "v", requestID: "") == nil)
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: "has space", requestID: "x") == nil)
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: "v", requestID: "a/b") == nil)
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: "v", requestID: "é") == nil)
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: String(repeating: "a", count: 64), requestID: "x") != nil)
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: String(repeating: "a", count: 65), requestID: "x") == nil)
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: "v", requestID: String(repeating: "a", count: 128)) != nil)
        #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: "v", requestID: String(repeating: "a", count: 129)) == nil)
    }

    @Test func aReceiptIsReadForBothAnswersAndNeverChoosesForTheTraveller() throws {
        let granted = try LioMemoryConsentWire.decodeReceipt(Data("""
            {"version":"LIO-memory-consent.1","state":"granted","recorded":true,
             "consent_text_version":"memory-2026-11","changed_at":"2026-11-27T01:02:03.456+00:00"}
            """.utf8))
        #expect(granted == .init(state: .granted, recorded: true))
        // An account that has never chosen reads as withdrawn and not recorded.
        let never = try LioMemoryConsentWire.decodeReceipt(Data("""
            {"version":"LIO-memory-consent.1","state":"withdrawn","recorded":false,"consent_text_version":null,"changed_at":null}
            """.utf8))
        #expect(never == .init(state: .withdrawn, recorded: false))
        // A PUT answer without `recorded` is a state that was just written.
        let put = try LioMemoryConsentWire.decodeReceipt(Data(#"{"version":"LIO-memory-consent.1","state":"withdrawn"}"#.utf8))
        #expect(put == .init(state: .withdrawn, recorded: true))
    }

    @Test(arguments: [
        #"{"version":"LIO-memory-consent.2","state":"granted"}"#,
        #"{"version":"LIO-memory-consent.1","state":"maybe"}"#,
        #"{"version":"LIO-memory-consent.1"}"#,
        #"{"state":"granted"}"#,
        #"{"version":"LIO-memory-consent.1","state":"granted","state":"withdrawn"}"#,
        "not json", "[]"
    ]) func aReceiptThatIsNotTheContractsIsRejected(body: String) {
        #expect(throws: (any Error).self) { try LioMemoryConsentWire.decodeReceipt(Data(body.utf8)) }
    }

    @Test func putAndGetUseTheirOneRouteWithNoQueryAndTheSameBodyOnRetry() async throws {
        let exit = ConsentExit()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16_384, maximumResponseBytes: 4_500_000)
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint,
                                                validateMessage: {}, lio: true)
        let action = try request()
        _ = try await transport.sendLioMemoryConsent(action, bearer: "fixture")
        _ = try await transport.sendLioMemoryConsent(action, bearer: "fixture")
        _ = try await transport.readLioMemoryConsent(bearer: "fixture")
        let calls = await exit.calls
        #expect(calls.map(\.method) == [.put, .put, .get])
        #expect(calls.map(\.path) == ["/v1/lio/memory/consent", "/v1/lio/memory/consent", "/v1/lio/memory/consent"])
        let bytes = try action.originalUTF8
        #expect(calls.map(\.body) == [bytes, bytes, nil], "\(calls.map { $0.body.map { String(decoding: $0, as: UTF8.self) } ?? "nil" })")
        #expect(calls.map(\.contentType) == ["application/octet-stream", "application/octet-stream", nil])
    }
}

private actor ConsentExit: ClientTransport {
    struct Call: Sendable {
        let method: HTTPRequest.Method
        let path: String?
        let body: Data?
        let contentType: String?
    }

    private(set) var calls: [Call] = []

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes = if let body { try await Data(collecting: body, upTo: 16_384) } else { nil as Data? }
        calls.append(Call(method: request.method, path: request.path, body: bytes,
                          contentType: request.headerFields[.contentType]))
        return (HTTPResponse(status: .ok), HTTPBody("{}"))
    }
}

/// #1999: `rich.memory.prompt` (LIO-answer-rich.1): "this answer holds a preference and the account has never chosen".
@MainActor
struct LioMemoryPromptWireTests {
    private let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"

    private func decoded(_ rich: String, status: String = "completed", answer: String = "我喜欢慢节奏。") throws -> LioTimelineWire.Message {
        let body = """
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[{"message_id":"m1","text":"Q","answer":"\(answer)","status":"\(status)","sources":[],"rich":\(rich)}],"next_before":null}
            """
        return try #require(try LioTimelineWire.decodePage(Data(body.utf8), for: conversation, version: .v2).messages.first)
    }

    @Test func thePromptAloneIsEnoughForRichAndNothingElseIsMadeUp() throws {
        let message = try decoded(#"{"version":"LIO-answer-rich.1","memory":{"prompt":"consent"}}"#)
        #expect(message.rich == .init(entities: [], memoryPrompt: true))
        #expect(message.memoryTags.isEmpty, "the prompt prepares no suggestion")
    }

    @Test func thePromptAndPlacesLiveSideBySideAndAnOverlongPlaceListDoesNotTakeThePromptWithIt() throws {
        let place = #"{"type":"place","start":2,"end":4,"place_id":"pl_bj_gugong"}"#
        let both = try decoded(#"{"version":"LIO-answer-rich.1","entities":[\#(place)],"memory":{"prompt":"consent"}}"#)
        #expect(both.rich?.entities.count == 1 && both.rich?.memoryPrompt == true)
        let many = Array(repeating: place, count: 21).joined(separator: ",")
        let over = try decoded(#"{"version":"LIO-answer-rich.1","entities":[\#(many)],"memory":{"prompt":"consent"}}"#)
        #expect(over.rich == .init(entities: [], memoryPrompt: true))
    }

    @Test(arguments: [
        #"{"version":"LIO-answer-rich.1","memory":{"prompt":"other"}}"#,
        #"{"version":"LIO-answer-rich.1","memory":{"prompt":"Consent"}}"#,
        #"{"version":"LIO-answer-rich.1","memory":{"prompt":null}}"#,
        #"{"version":"LIO-answer-rich.1","memory":{"prompt":7}}"#,
        #"{"version":"LIO-answer-rich.1","memory":{}}"#,
        #"{"version":"LIO-answer-rich.1","memory":"consent"}"#,
        #"{"version":"LIO-answer-rich.1","memory":[]}"#,
        #"{"version":"LIO-answer-rich.2","memory":{"prompt":"consent"}}"#,
        #"{"memory":{"prompt":"consent"}}"#,
    ]) func anythingButTheExactPromptReadsAsNoPromptAndNeverFailsThePage(value: String) throws {
        let message = try decoded(value)
        #expect(message.rich?.memoryPrompt != true)
        #expect(message.answer == "我喜欢慢节奏。")
    }

    @Test func thePromptOnlyRidesOnACompletedRowWithAnAnswer() throws {
        let body = #"{"version":"LIO-answer-rich.1","memory":{"prompt":"consent"}}"#
        #expect(try decoded(body, status: "answering").rich == nil)
        #expect(try decoded(body, status: "sending").rich == nil)
        #expect(try decoded(body, answer: "").rich == nil)
    }
}
