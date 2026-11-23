import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LioSpokenClipTests {
    @Test func samePhraseReusesValidatedAudio() async throws {
        let fixture = try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 32))
        var calls = 0
        let clip = LioSpokenClip { _, _ in calls += 1; return fixture }
        let phrase = LioSpokenClip.Phrase(language: .chinese, text: "茶")
        #expect(try await clip.audio(for: phrase) == fixture)
        #expect(try await clip.audio(for: phrase) == fixture)
        #expect(calls == 1)
    }

    @Test func timeoutOrCancellationRetainsTheRequestIdentifier() async throws {
        let fixture = try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 32))
        var requests: [UUID] = []
        let clip = LioSpokenClip { _, request in
            requests.append(request)
            if requests.count == 1 { throw URLError(.timedOut) }
            if requests.count == 2 { throw CancellationError() }
            return fixture
        }
        let phrase = LioSpokenClip.Phrase(language: .english, text: "Tea")
        await #expect(throws: URLError.self) { try await clip.audio(for: phrase) }
        await #expect(throws: CancellationError.self) { try await clip.audio(for: phrase) }
        #expect(try await clip.audio(for: phrase) == fixture)
        #expect(requests.count == 3)
        #expect(Set(requests).count == 1)
    }
}
