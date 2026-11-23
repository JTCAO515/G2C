import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LioSpokenClipTests {
    @Test func revisitingTheFirstPhraseUsesItsCachedAudio() async throws {
        let wav = try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 32))
        var calls = 0
        let audio = LioSpokenClip { _, _ in
            calls += 1
            return wav
        }
        let tea = LioSpokenClip.Phrase(language: .english, text: "Tea")
        let coffee = LioSpokenClip.Phrase(language: .english, text: "Coffee")
        _ = try await audio.audio(for: tea)
        _ = try await audio.audio(for: coffee)
        #expect(try await audio.audio(for: tea) == wav)
        #expect(calls == 2)
    }

    @Test func keepsByteDistinctInputsAndTheSameOriginalRetryApart() async throws {
        let wav = try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 32))
        var sent: [(Data, UUID)] = []
        let audio = LioSpokenClip { phrase, id in
            sent.append((Data(phrase.text.utf8), id))
            if sent.count == 1 { throw URLError(.timedOut) }
            return wav
        }
        let first = LioSpokenClip.Phrase(language: .english, text: "\u{00E9}")
        let second = LioSpokenClip.Phrase(language: .english, text: "e\u{0301}")
        await #expect(throws: URLError.self) { try await audio.audio(for: first) }
        _ = try await audio.audio(for: second)
        _ = try await audio.audio(for: first)
        #expect(sent.count == 3)
        if sent.count == 3 {
            #expect(sent[0].0 == sent[2].0)
            #expect(sent[0].1 == sent[2].1)
            #expect(sent[0].0 != sent[1].0)
            #expect(sent[0].1 != sent[1].1)
        }
    }

    @Test func retiredScopeCannotReadPreviouslyCachedAudio() async throws {
        let wav = try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 32))
        var live = true
        let clip = LioSpokenClip(isCurrent: { live }) { _, _ in wav }
        let phrase = LioSpokenClip.Phrase(language: .chinese, text: "茶")
        _ = try await clip.audio(for: phrase)
        live = false
        await #expect(throws: CancellationError.self) { try await clip.audio(for: phrase) }
    }

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
