import AVFoundation
import Foundation
import Testing
@testable import CJLioUser

struct LioTranslationRelayTests {
    let id = UUID(uuid: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1))

    @Test func microphonePCMConvertsToWireWAVAndBackToARecognitionBufferInMemory() throws {
        let inputFormat = try #require(AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 1))
        let input = try #require(AVAudioPCMBuffer(pcmFormat: inputFormat, frameCapacity: 4800))
        input.frameLength = 4800
        let samples = try #require(input.floatChannelData?.pointee)
        for frame in 0..<Int(input.frameLength) {
            samples[frame] = Float(sin(Double(frame) * 0.07) * 0.5)
        }

        let collector = try LioTranslationPCMCollector(inputFormat: inputFormat)
        collector.append(input)
        let recording = try collector.finish()
        let wav = try recording.wireWAV()
        let native = try recording.recognitionBuffer()
        #expect(wav.prefix(4) == Data("RIFF".utf8))
        #expect(native.format.sampleRate == 16_000 && native.format.channelCount == 1)
        #expect(native.format.commonFormat == .pcmFormatInt16)
        #expect(native.frameLength > 0)
        #expect(wav.count == 44 + Int(native.frameLength) * 2)
        let pcm = try #require(native.int16ChannelData?.pointee)
        #expect((0..<Int(native.frameLength)).contains { pcm[$0] != 0 })
    }

    @Test func textUsesTheRelaySchemaAndSendsNoMedia() throws {
        let request = LioRelayTranslationRequest(id: id, source: .chinese, target: .english, payload: .text("茶"))
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: String])
        #expect(json == ["version": "TRANSLATION.1", "request_id": id.uuidString.lowercased(),
                         "kind": "text", "source_lang": "zh", "target_lang": "en", "text": "茶"])
    }

    @Test @MainActor func unknownRelayOutcomeKeepsTheIDForTheSameBytesAndLanguages() throws {
        var originals = LioRelayOriginalRequests()
        let original = try originals.request(source: .english, target: .chinese, payload: .text("Cafe\u{301}"))
        let differentBytes = try originals.request(source: .english, target: .chinese, payload: .text("Café"))
        #expect(differentBytes.id != original.id)
        let retry = try originals.request(source: .english, target: .chinese, payload: .text("Cafe\u{301}"))
        #expect(retry.id == original.id)
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        #expect(try encoder.encode(retry) == encoder.encode(original))
        let reversed = try originals.request(source: .chinese, target: .english, payload: .text("Cafe\u{301}"))
        #expect(reversed.id != original.id)
        let result = LioRecentTranslation(source: .english, target: .chinese, input: "Cafe\u{301}",
                                         output: "咖啡", offline: false)
        _ = try originals.deliver(original, entry: result)
        let next = try originals.request(source: .english, target: .chinese, payload: .text("Cafe\u{301}"))
        #expect(next.id != original.id)
    }

    @Test @MainActor func paidOriginalSurvivesReopeningAndAcceptedStateStopsAnotherDispatch() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let history = LioTranslationHistory(directory: root.appendingPathComponent("first-account"), isCurrent: { true })
        let otherHistory = LioTranslationHistory(directory: root.appendingPathComponent("second-account"), isCurrent: { true })
        var first = LioRelayOriginalRequests()
        let original = try first.request(source: .english, target: .chinese, payload: .text("Same private sentence"), storage: history)
        var reopened = LioRelayOriginalRequests()
        let retry = try reopened.request(source: .english, target: .chinese, payload: .text("Same private sentence"), storage: history)
        #expect(retry.id == original.id)
        try reopened.accept(retry, storage: history)
        var afterReopening = LioRelayOriginalRequests()
        #expect(throws: LioRelayTranslationFailure.alreadyAccepted) {
            try afterReopening.request(source: .english, target: .chinese, payload: .text("Same private sentence"), storage: history)
        }
        var other = LioRelayOriginalRequests()
        let otherRequest = try other.request(source: .english, target: .chinese, payload: .text("Same private sentence"), storage: otherHistory)
        #expect(otherRequest.id != original.id)
        let persisted = try Data(contentsOf: root.appendingPathComponent("first-account").appendingPathComponent(LioTranslationHistory.relayOriginalsFileName))
        #expect(!String(decoding: persisted, as: UTF8.self).contains("Same private sentence"))
    }

    @Test @MainActor func completedRelayResultCanBeRecoveredBeforeTheOriginalIDIsReleased() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let history = LioTranslationHistory(directory: directory, isCurrent: { true })
        var originals = LioRelayOriginalRequests()
        let response = LioRecentTranslation(source: .english, target: .chinese, input: "Hello",
                                            output: "你好", offline: false)
        let original = try originals.request(source: .english, target: .chinese, payload: .text("Hello"), storage: history)
        #expect(try originals.deliver(original, entry: response, storage: history) == [response])
        #expect(try history.load() == [response])
        var reopened = LioRelayOriginalRequests()
        let later = try reopened.request(source: .english, target: .chinese, payload: .text("Hello"), storage: history)
        #expect(later.id != original.id)
    }

    @Test @MainActor func failedHistoryWriteLeavesTheAcceptedOriginalProtectedAfterReopening() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let history = LioTranslationHistory(directory: directory, isCurrent: { true })
        var originals = LioRelayOriginalRequests()
        let original = try originals.request(source: .english, target: .chinese, payload: .text("Hello"), storage: history)
        let recent = directory.appendingPathComponent(LioTranslationHistory.fileName)
        let corrupt = Data("existing unreadable history".utf8)
        try corrupt.write(to: recent)
        let response = LioRecentTranslation(source: .english, target: .chinese, input: "Hello",
                                            output: "你好", offline: false)
        #expect(throws: DecodingError.self) {
            try originals.deliver(original, entry: response, storage: history)
        }
        var reopened = LioRelayOriginalRequests()
        #expect(throws: LioRelayTranslationFailure.alreadyAccepted) {
            try reopened.request(source: .english, target: .chinese, payload: .text("Hello"), storage: history)
        }
        #expect(try Data(contentsOf: recent) == corrupt)
    }

    @Test @MainActor func recreatedRequestNeverSendsAnOldIDWithDifferentWireBytes() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let history = LioTranslationHistory(directory: directory, isCurrent: { true })
        var originals = LioRelayOriginalRequests()
        _ = try originals.request(source: .english, target: .chinese, payload: .text("Hello"), storage: history)
        let stored = try history.loadRelayOriginals()
        let bytes = try #require(stored)
        let decoded = try JSONSerialization.jsonObject(with: bytes)
        var entries = try #require(decoded as? [[String: Any]])
        #expect(entries.count == 2)
        entries[1]["wireFingerprint"] = Data(repeating: 0, count: 32).base64EncodedString()
        let unsupportedWireVersion = try JSONSerialization.data(withJSONObject: entries)
        try history.saveRelayOriginals(unsupportedWireVersion)
        var reopened = LioRelayOriginalRequests()
        #expect(throws: LioRelayTranslationFailure.originalUnavailable) {
            try reopened.request(source: .english, target: .chinese, payload: .text("Hello"), storage: history)
        }
        #expect(try history.loadRelayOriginals() == unsupportedWireVersion)
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

    @Test(arguments: [500, 502, 503, 504])
    func gatewayFailureWithoutTheServiceEnvelopeStillAllowsOfflineTranslation(_ status: Int) {
        #expect(throws: LioTranslationFailure.service) {
            try LioRelayTranslationResponse.decode(status: status, body: Data("gateway unavailable".utf8),
                                                   expecting: .text)
        }
    }

    @Test func rejectsAccessAndDistinguishesQuotaFromAvailability() {
        #expect(throws: LioRelayTranslationFailure.signInRequired) {
            try LioRelayTranslationResponse.decode(status: 401, body: Data(), expecting: .text)
        }
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
