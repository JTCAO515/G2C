import Foundation

@MainActor final class LioSpokenClip {
    struct Phrase: Hashable {
        let language: LioTranslationLanguage
        let text: String
    }

    typealias Load = @MainActor (Phrase, UUID) async throws -> Data
    private let load: Load
    private var cached: (Phrase, Data)?
    private var pending: [Phrase: UUID] = [:]

    init(load: @escaping Load) {
        self.load = load
    }

    func audio(for phrase: Phrase) async throws -> Data {
        try Task.checkCancellation()
        if let cached, cached.0 == phrase { return cached.1 }
        let id = pending[phrase] ?? UUID()
        pending[phrase] = id

        let data = try await load(phrase, id)
        try Task.checkCancellation()
        guard pending[phrase] == id else { throw CancellationError() }
        guard data.count >= 44, data.count <= LioTranslationWAV.maximumPCMBytes + 44,
              data.prefix(4) == Data("RIFF".utf8), data.dropFirst(8).prefix(4) == Data("WAVE".utf8)
        else { throw CocoaError(.fileReadCorruptFile) }
        cached = (phrase, data)
        pending.removeValue(forKey: phrase)
        return data
    }
}
