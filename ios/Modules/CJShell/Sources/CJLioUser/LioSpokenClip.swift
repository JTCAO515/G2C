import Foundation

@MainActor public final class LioSpokenClip {
    struct Phrase: Hashable {
        let language: LioTranslationLanguage
        let text: String

        var bytes: Data { Data(text.utf8) }

        static func == (lhs: Phrase, rhs: Phrase) -> Bool {
            lhs.language == rhs.language && lhs.bytes == rhs.bytes
        }

        func hash(into hasher: inout Hasher) {
            hasher.combine(language)
            hasher.combine(bytes)
        }
    }

    enum Failure: Error { case alreadyLoading }

    typealias Load = @MainActor (Phrase, UUID) async throws -> Data
    private let isCurrent: @MainActor () -> Bool
    private let load: Load
    private let cached = NSCache<NSString, NSData>()
    private var originalIDs: [Phrase: UUID] = [:]
    private var inFlight: Set<Phrase> = []

    init(isCurrent: @escaping @MainActor () -> Bool = { true }, load: @escaping Load) {
        self.isCurrent = isCurrent
        self.load = load
        cached.countLimit = 12
        cached.totalCostLimit = 8 * 1024 * 1024
    }

    func audio(for phrase: Phrase) async throws -> Data {
        try requireCurrentSession()
        let key = (phrase.language.rawValue + ":" + phrase.bytes.base64EncodedString()) as NSString
        if let audio = cached.object(forKey: key) { return audio as Data }

        guard inFlight.insert(phrase).inserted else { throw Failure.alreadyLoading }
        defer { inFlight.remove(phrase) }
        let originalID = originalIDs[phrase] ?? UUID()
        originalIDs[phrase] = originalID

        let data = try await load(phrase, originalID)
        try requireCurrentSession()
        try validateWAV(data)
        cached.setObject(data as NSData, forKey: key, cost: data.count)
        return data
    }

    private func requireCurrentSession() throws {
        try Task.checkCancellation()
        guard isCurrent() else { throw CancellationError() }
    }

    private func validateWAV(_ data: Data) throws {
        guard data.count >= 44, data.count <= LioSpokenRelayClient.maximumAudioBytes,
              data.prefix(4) == Data("RIFF".utf8), data.dropFirst(8).prefix(4) == Data("WAVE".utf8)
        else { throw CocoaError(.fileReadCorruptFile) }

        var declaredSize: UInt32 = 0
        for (index, byte) in data.dropFirst(4).prefix(4).enumerated() {
            declaredSize |= UInt32(byte) << (index * 8)
        }
        guard declaredSize == UInt32(data.count - 8) else { throw CocoaError(.fileReadCorruptFile) }
    }
}
