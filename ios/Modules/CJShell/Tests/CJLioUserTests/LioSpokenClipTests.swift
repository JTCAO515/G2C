import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LioSpokenClipTests {
    @Test func settledButUnavailableAudioDoesNotSubmitAgain() async {
        var saved: Data?
        var sent = 0
        let storage = LioSpokenLedgerStorage(load: { saved }, save: { saved = $0 })
        let load: LioSpokenClip.Load = { _, _ in
            sent += 1
            throw LioSpokenRelayFailure.alreadyUsed
        }
        let phrase = LioSpokenClip.Phrase(language: .english, text: "Tea")
        let first = LioSpokenClip(storage: storage, load: load)
        await #expect(throws: LioSpokenRelayFailure.alreadyUsed) { try await first.audio(for: phrase) }
        let restored = LioSpokenClip(storage: storage, load: load)
        await #expect(throws: LioSpokenRelayFailure.alreadyUsed) { try await restored.audio(for: phrase) }
        #expect(sent == 1)
    }

    @Test func onDiskLedgerIsOwnerScopedAndDoesNotFollowASymlink() throws {
        let parent = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: parent) }
        var isCurrent = true
        let directory = parent.appendingPathComponent(LioTranslationHistory.directoryName)
        let history = LioTranslationHistory(directory: directory, isCurrent: { isCurrent })
        let store = history.spokenLedgerStorage()
        #expect(try store.load() == nil)
        let fixture = Data("synthetic".utf8)
        try store.save(fixture)
        #expect(try store.load() == fixture)
        isCurrent = false
        #expect(throws: CancellationError.self) { try store.load() }
        isCurrent = true

        let ledger = directory.appendingPathComponent(LioTranslationHistory.spokenLedgerFileName)
        let otherFile = parent.appendingPathComponent("other.json")
        try fixture.write(to: otherFile)
        try FileManager.default.removeItem(at: ledger)
        try FileManager.default.createSymbolicLink(at: ledger, withDestinationURL: otherFile)
        #expect(throws: CocoaError.self) { try store.load() }
    }

    @Test func recreatingTheSessionKeepsPreviouslyReturnedAudio() async throws {
        let wav = try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 32))
        var stored: Data?
        var calls = 0
        let storage = LioSpokenLedgerStorage(load: { stored }, save: { stored = $0 })
        let load: LioSpokenClip.Load = { _, _ in
            calls += 1
            return wav
        }
        let phrase = LioSpokenClip.Phrase(language: .chinese, text: "茶")
        let first = LioSpokenClip(storage: storage, load: load)
        _ = try await first.audio(for: phrase)
        let restored = LioSpokenClip(storage: storage, load: load)
        #expect(try await restored.audio(for: phrase) == wav)
        #expect(calls == 1)
        #expect(stored?.range(of: Data("茶".utf8)) == nil)
    }

    @Test func restoredAttemptKeepsTheOriginalIdentifier() async throws {
        let wav = try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 32))
        var stored: Data?
        var sent: [UUID] = []
        let storage = LioSpokenLedgerStorage(load: { stored }, save: { stored = $0 })
        let load: LioSpokenClip.Load = { _, id in
            sent.append(id)
            if sent.count == 1 { throw URLError(.timedOut) }
            return wav
        }
        let phrase = LioSpokenClip.Phrase(language: .english, text: "Tea")
        let first = LioSpokenClip(storage: storage, load: load)
        await #expect(throws: URLError.self) { try await first.audio(for: phrase) }
        let restored = LioSpokenClip(storage: storage, load: load)
        #expect(try await restored.audio(for: phrase) == wav)
        #expect(sent.count == 2)
        #expect(Set(sent).count == 1)
    }

    @Test func noRequestLeavesWhenTheOriginalIdentifierCannotBeSaved() async throws {
        let wav = try LioTranslationWAV.encode(pcm: Data(repeating: 0, count: 32))
        var sent = false
        let storage = LioSpokenLedgerStorage(load: { nil }, save: { _ in throw CocoaError(.fileWriteUnknown) })
        let clip = LioSpokenClip(storage: storage) { _, _ in
            sent = true
            return wav
        }
        await #expect(throws: CocoaError.self) { try await clip.audio(for: .init(language: .english, text: "Tea")) }
        #expect(!sent)
    }

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
