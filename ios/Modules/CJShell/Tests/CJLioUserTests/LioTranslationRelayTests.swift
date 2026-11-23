import AVFoundation
import Foundation
import Testing
@testable import CJLioUser

struct LioTranslationRelayTests {
    let id = UUID(uuid: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1))

    @Test @MainActor func microphoneTapCollectsAudioWhenInvokedOffMainThread() async throws {
        let tap = try #require(AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1))
        let collector = try LioTranslationPCMCollector(inputFormat: tap)
        let callback = LioTranslationPCMCollector.tap(for: collector)
        try await withCheckedThrowingContinuation { (done: CheckedContinuation<Void, any Error>) in
            DispatchQueue.global().async {
                done.resume(with: Result {
                    #expect(!Thread.isMainThread)
                    let format = try #require(AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1))
                    let buffer = try #require(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 128))
                    buffer.frameLength = 128
                    let samples = try #require(buffer.floatChannelData?.pointee)
                    for index in 0..<128 { samples[index] = 0.25 }
                    callback(buffer, AVAudioTime(sampleTime: 0, atRate: format.sampleRate))
                })
            }
        }
        let wav = try collector.finish().wireWAV()
        #expect(wav.prefix(4) == Data("RIFF".utf8))
        #expect(wav.dropFirst(44).contains { $0 != 0 })
        let relay = LioRelayTranslationClient { path, body in
            #expect(path == "/v1/tools/translate")
            let fields = try #require(JSONSerialization.jsonObject(with: body) as? [String: String])
            #expect(fields["kind"] == "speech")
            #expect(fields["media"].flatMap { Data(base64Encoded: $0) } == wav)
            return (200, Data(#"{"version":"TRANSLATION.1","kind":"speech","items":[{"source_text":"Tea, please.","translated_text":"请给我一杯茶。"}]}"#.utf8))
        }
        let response = try await relay.translate(.init(id: id, source: .english, target: .chinese, payload: .wav(wav)))
        #expect(response.items.map(\.sourceText) == ["Tea, please."])
        #expect(response.items.map(\.translatedText) == ["请给我一杯茶。"])
    }

    @Test @MainActor func sendsAllThreeKindsToTheSameEndpoint() async throws {
        let wav = try LioTranslationWAV.encode(pcm: Data([1, 0, 2, 0]))
        let jpeg = Data([0xff, 0xd8, 0xff, 0xd9])
        let cases: [(LioRelayTranslationRequest.Payload, String, String, String)] = [
            (.text("Tea"), "text", "text", "Tea"),
            (.wav(wav), "speech", "media", wav.base64EncodedString()),
            (.jpeg(jpeg), "image", "media", jpeg.base64EncodedString()),
        ]
        for (payload, kind, key, expectedValue) in cases {
            let relay = LioRelayTranslationClient { path, body in
                #expect(path == "/v1/tools/translate")
                let fields = try #require(JSONSerialization.jsonObject(with: body) as? [String: String])
                #expect(fields["kind"] == kind)
                #expect(fields[key] == expectedValue)
                let reply = """
                {"version":"TRANSLATION.1","kind":"\(kind)","items":[{"source_text":"Tea","translated_text":"茶"}]}
                """
                return (200, Data(reply.utf8))
            }
            let reply = try await relay.translate(.init(id: id, source: .english, target: .chinese, payload: payload))
            #expect(reply.items.map(\.sourceText) == ["Tea"])
            #expect(reply.items.map(\.translatedText) == ["茶"])
        }
    }

    @Test @MainActor func forwardsUploadCompletionBeforeTheVoiceResult() async throws {
        var bodySent = false
        let relay = LioRelayTranslationClient(requiresOriginalStore: false) { path, _, uploadFinished in
            #expect(path == "/v1/tools/translate")
            #expect(!bodySent)
            uploadFinished?()
            #expect(bodySent)
            return (200, Data(#"{"version":"TRANSLATION.1","kind":"speech","items":[{"source_text":"Tea","translated_text":"茶"}]}"#.utf8))
        }
        let wav = try LioTranslationWAV.encode(pcm: Data([1, 0, 2, 0]))
        let speech = LioRelayTranslationRequest(id: id, source: .english, target: .chinese, payload: .wav(wav))
        let result = try await relay.translate(speech, uploadFinished: { bodySent = true })
        #expect(result.items.first?.translatedText == "茶")
        #expect(bodySent)
    }

    @Test func microphonePCMConvertsToWireWAVInMemory() throws {
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
        #expect(wav.prefix(4) == Data("RIFF".utf8))
        #expect(wav.count > 44)
        #expect(wav.dropFirst(44).contains { $0 != 0 })
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

    @Test @MainActor func previousPhotoRequestKeepsItsOriginalProtocolAndIDAcrossRollout() throws {
        let photo: LioRelayTranslationRequest.Payload = .jpeg(Data([0xff, 0xd8, 0xff, 7]))
        var originals = LioRelayOriginalRequests()
        let prior = try originals.request(source: .chinese, target: .english, payload: photo)
        let resumed = try originals.request(source: .chinese, target: .english, payload: photo, prefersImageLayout: true)
        #expect(resumed.id == prior.id)
        #expect(resumed.route == LioRelayTranslationRequest.route)
        #expect(try resumed.wireBody() == prior.wireBody())

        var enabled = LioRelayOriginalRequests()
        let layout = try enabled.request(source: .chinese, target: .english, payload: photo, prefersImageLayout: true)
        let afterRollback = try enabled.request(source: .chinese, target: .english, payload: photo)
        #expect(afterRollback.id == layout.id)
        #expect(afterRollback.route == LioRelayTranslationRequest.imageLayoutRoute)
        #expect(try afterRollback.wireBody() == layout.wireBody())
    }

    @Test @MainActor func layoutUsesItsDedicatedRouteAndMatchingVersion() async throws {
        let request = LioRelayTranslationRequest(id: id, source: .chinese, target: .english,
                                                 payload: .jpeg(Data([0xff, 0xd8, 0xff, 7])), usesImageLayout: true)
        let client = LioRelayTranslationClient(requiresOriginalStore: false, supportsImageLayout: true) { path, body, _ in
            #expect(path == "/v1/tools/translate/image-layout")
            let fields = try #require(JSONSerialization.jsonObject(with: body) as? [String: String])
            #expect(fields["version"] == "IMAGE-LAYOUT.1")
            #expect(fields["request_id"] == id.uuidString.lowercased())
            return (200, Data(#"{"version":"IMAGE-LAYOUT.1","image_width":32,"image_height":16,"items":[]}"#.utf8))
        }
        let reply = try await client.translate(request)
        #expect(reply.imageWidth == 32)
        #expect(reply.kind == .image)
        let disabled = LioRelayTranslationClient { _, _ in
            Issue.record("Disabled coordinate translation must not send a request.")
            return (500, Data())
        }
        await #expect(throws: LioRelayTranslationFailure.accessDenied) { try await disabled.translate(request) }
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

    @Test @MainActor func relayQuotaResponseIsReportedWithoutAnAnswer() async throws {
        let relay = LioRelayTranslationClient { route, body in
            #expect(route == "/v1/tools/translate")
            let json = try #require(JSONSerialization.jsonObject(with: body) as? [String: String])
            #expect(json["text"] == "Hello")
            return (429, Data(#"{"version":"TRANSLATION.1","error":"quota_exceeded"}"#.utf8))
        }
        await #expect(throws: LioTranslationFailure.quota) {
            try await relay.translate(.init(id: id, source: .english, target: .chinese, payload: .text("Hello")))
        }
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

    @Test func emptySpeechAndPhotoResultsHaveDifferentRecoveryActions() throws {
        let speech = Data(#"{"version":"TRANSLATION.1","kind":"speech","items":[]}"#.utf8)
        let photo = Data(#"{"version":"TRANSLATION.1","kind":"image","items":[]}"#.utf8)
        let speechResult = try LioRelayTranslationResponse.decode(status: 200, body: speech, expecting: .speech)
        let photoResult = try LioRelayTranslationResponse.decode(status: 200, body: photo, expecting: .image)
        #expect(speechResult.items.isEmpty && photoResult.items.isEmpty)
        let speechGuidance = LioEmptyTranslationMedia(kind: speechResult.kind)
        let photoGuidance = LioEmptyTranslationMedia(kind: photoResult.kind)
        #expect(speechGuidance.recoveryText(.chinese) == "没有听清，请再说一遍")
        #expect(speechGuidance.recoveryText(.english) == "Didn't catch that. Please try again.")
        #expect(photoGuidance.recoveryText(.chinese) == "没有识别到文字，请换个角度重拍")
        #expect(photoGuidance.recoveryText(.english) == "No text found. Try another angle.")
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
