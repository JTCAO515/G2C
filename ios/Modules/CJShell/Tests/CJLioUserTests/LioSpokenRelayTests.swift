import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LioSpokenRelayTests {
    private let host = URL(string: "https://api-beta.go2china.space")!
    private let route = URL(string: "https://api-beta.go2china.space/v1/tools/tts")!

    @Test func retriesUseTheSameOriginalBodyAndBoundRoute() async throws {
        let example = try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 32))
        let phrase = LioSpokenClip.Phrase(language: .chinese, text: "不加糖")
        let id = UUID()
        var requests: [URLRequest] = []
        let relay = LioSpokenRelayClient(baseURL: host, isCurrent: { true }, bearer: { "synthetic-owner" }) { request in
            requests.append(request)
            if requests.count == 1 { throw URLError(.timedOut) }
            return (example, response(route, status: 200))
        }
        await #expect(throws: LioSpokenRelayFailure.timedOut) { try await relay.audio(for: phrase, requestID: id) }
        #expect(try await relay.audio(for: phrase, requestID: id) == example)
        #expect(requests.count == 2)
        let request = try #require(requests.first)
        let bytes = try #require(request.httpBody)
        #expect(request.url == route)
        #expect(request.httpMethod == "POST")
        #expect(request.value(forHTTPHeaderField: "Accept") == "audio/wav")
        #expect(requests.last?.httpBody == bytes)
        let decoded = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: String])
        #expect(decoded == ["version":"TTS.1", "request_id":id.uuidString, "language":"zh", "text":"不加糖"])
    }

    @Test func invalidInputOrMissingCredentialNeverSends() async {
        var sends = 0
        let capture: LioSpokenRelayClient.Exchange = { _ in
            sends += 1
            return (Data(), response(route, status: 500))
        }
        let relay = LioSpokenRelayClient(baseURL: host, isCurrent: { true }, bearer: { "synthetic-owner" }, exchange: capture)
        let excessive = LioSpokenClip.Phrase(language: .english, text: String(repeating: "e\u{0301}", count: 141))
        await #expect(throws: LioSpokenRelayFailure.invalidText) { try await relay.audio(for: excessive, requestID: UUID()) }
        let missing = LioSpokenRelayClient(baseURL: host, isCurrent: { true }, bearer: { nil }, exchange: capture)
        await #expect(throws: LioSpokenRelayFailure.signInRequired) {
            try await missing.audio(for: .init(language: .english, text: "Tea"), requestID: UUID())
        }
        #expect(sends == 0)
    }

    @Test func rejectsStaleAndNonAudioResponses() async throws {
        let wav = try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 32))
        let phrase = LioSpokenClip.Phrase(language: .english, text: "Tea")
        let foreign = URL(string: "https://example.invalid/v1/tools/tts")!
        for http in [response(foreign, status: 200), response(route, status: 302),
                     response(route, status: 200, type: "application/json")] {
            let relay = LioSpokenRelayClient(baseURL: host, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
                (wav, http)
            }
            await #expect(throws: LioSpokenRelayFailure.unavailable) { try await relay.audio(for: phrase, requestID: UUID()) }
        }
        var active = true
        let retired = LioSpokenRelayClient(baseURL: host, isCurrent: { active }, bearer: { "synthetic-owner" }) { _ in
            active = false
            return (wav, response(route, status: 200))
        }
        await #expect(throws: CancellationError.self) { try await retired.audio(for: phrase, requestID: UUID()) }
    }

    private func response(_ url: URL, status: Int, type: String = "audio/wav") -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": type])!
    }
}
