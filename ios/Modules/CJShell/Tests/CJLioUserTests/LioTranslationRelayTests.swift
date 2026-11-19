import Foundation
import Testing
@testable import CJLioUser

struct LioTranslationRelayTests {
    let id = UUID(uuid: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1))

    @Test func textUsesTheRelaySchemaAndSendsNoMedia() throws {
        let request = LioRelayTranslationRequest(id: id, source: .chinese, target: .english, payload: .text("茶"))
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: String])
        #expect(json == ["version": "TRANSLATION.1", "request_id": id.uuidString.lowercased(),
                         "kind": "text", "source_lang": "zh", "target_lang": "en", "text": "茶"])
    }

    @Test func imageUsesBase64AndKeepsEveryReturnedLine() throws {
        let request = LioRelayTranslationRequest(id: id, source: .chinese, target: .english, payload: .png(Data([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3])))
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: String])
        #expect(json["kind"] == "image")
        #expect(json["media"] == "iVBORw0KGgoBAgM=")
        #expect(json["media_type"] == nil)
        #expect(json["text"] == nil)
        let result = try LioRelayTranslationResponse.decode(status: 200, body: Data(#"{"version":"TRANSLATION.1","kind":"image","items":[{"source_text":"茶","translated_text":"Tea"},{"source_text":"咖啡","translated_text":"Coffee"}]}"#.utf8), expecting: .image)
        #expect(result.items.map(\.sourceText) == ["茶", "咖啡"])
        #expect(result.items.map(\.translatedText) == ["Tea", "Coffee"])
    }

    @Test func rejectsAccessAndDistinguishesQuotaFromAvailability() {
        #expect(throws: LioRelayTranslationFailure.accessDenied) {
            try LioRelayTranslationResponse.decode(status: 403, body: Data(), expecting: .text)
        }
        #expect(throws: LioTranslationFailure.quota) {
            try LioRelayTranslationResponse.decode(status: 429, body: Data(#"{"version":"TRANSLATION.1","error":"quota_exceeded"}"#.utf8), expecting: .text)
        }
        #expect(throws: LioTranslationFailure.service) {
            try LioRelayTranslationResponse.decode(status: 503, body: Data(#"{"version":"TRANSLATION.1","error":"unavailable"}"#.utf8), expecting: .text)
        }
    }

    @Test @MainActor func relayQuotaResponseFallsBackThroughTheTranslationRouter() async throws {
        let relay = LioRelayTranslationClient { route, body in
            #expect(route == "/v1/tools/translate")
            let json = try #require(JSONSerialization.jsonObject(with: body) as? [String: String])
            #expect(json["text"] == "Hello")
            return (429, Data(#"{"version":"TRANSLATION.1","error":"quota_exceeded"}"#.utf8))
        }
        let translator = LioTranslator(remote: { request in
            let response = try await relay.translate(.init(id: id, source: request.source,
                                                           target: request.target, payload: .text(request.text[0])))
            return response.items.map(\.translatedText)
        }, local: { _ in ["你好"] })
        let result = try await translator.translate(.init(source: .english, target: .chinese, text: ["Hello"]))
        #expect(result == LioTranslationResult(text: ["你好"], offline: true))
    }

    @Test func distinguishesEmptyImageFromAnAlreadyAcceptedRequest() throws {
        let empty = Data(#"{"version":"TRANSLATION.1","kind":"image","items":[]}"#.utf8)
        #expect(try LioRelayTranslationResponse.decode(status: 200, body: empty, expecting: .image).items.isEmpty)
        #expect(throws: LioTranslationFailure.service) {
            try LioRelayTranslationResponse.decode(status: 200, body: empty, expecting: .text)
        }
        #expect(throws: LioRelayTranslationFailure.alreadyAccepted) {
            try LioRelayTranslationResponse.decode(status: 409, body: Data(), expecting: .image)
        }
    }

    @Test func rejectsTextOutsideTheAgreedRequestBounds() {
        let request = LioRelayTranslationRequest(id: id, source: .english, target: .chinese,
                                                  payload: .text(String(repeating: "a", count: 4001)))
        #expect(throws: LioRelayTranslationFailure.invalidInput) { try JSONEncoder().encode(request) }
    }

    @Test func wavUsesMonoSixteenKilohertzPCM() throws {
        let wav = try LioTranslationWAV.encode(pcm: Data([1, 0, 2, 0]))
        #expect(wav.prefix(4) == Data("RIFF".utf8))
        #expect(wav[8..<16] == Data("WAVEfmt ".utf8))
        #expect(wav[20..<24] == Data([1, 0, 1, 0]))
        #expect(wav[24..<28] == Data([0x80, 0x3e, 0, 0]))
        #expect(wav[34..<36] == Data([16, 0]))
        #expect(wav[36..<40] == Data("data".utf8))
        #expect(wav[44...] == Data([1, 0, 2, 0]))
        let request = LioRelayTranslationRequest(id: id, source: .english, target: .chinese, payload: .wav(wav))
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: String])
        #expect(json["kind"] == "speech")
        #expect(Data(base64Encoded: try #require(json["media"])) == wav)
        let reply = try LioRelayTranslationResponse.decode(status: 200, body: Data(
            #"{"version":"TRANSLATION.1","kind":"speech","items":[{"source_text":"Hello","translated_text":"你好"}]}"#.utf8),
            expecting: .speech)
        #expect(reply.items.first?.sourceText == "Hello")
        #expect(reply.items.first?.translatedText == "你好")

        #expect(throws: LioRelayTranslationFailure.invalidAudio) {
            try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 1_920_002))
        }
    }
}
