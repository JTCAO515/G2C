import CryptoKit
import Foundation

@MainActor struct LioSpokenLedgerStorage {
    static let maximumEncodedBytes = 14 * 1024 * 1024
    let load: () throws -> Data?
    let save: (Data) throws -> Void
}

@MainActor public final class LioSpokenClip {
    struct Phrase: Hashable {
        let language: LioTranslationLanguage
        let text: String

        var bytes: Data { Data(text.utf8) }

        var fingerprint: String {
            let message = Data(language.rawValue.utf8) + Data([0]) + bytes
            return SHA256.hash(data: message).map { String(format: "%02x", $0) }.joined()
        }

        static func == (lhs: Phrase, rhs: Phrase) -> Bool {
            lhs.language == rhs.language && lhs.bytes == rhs.bytes
        }

        func hash(into hasher: inout Hasher) {
            hasher.combine(language)
            hasher.combine(bytes)
        }
    }

    enum Failure: Error { case alreadyLoading }

    private struct Ledger: Codable {
        struct Record: Codable {
            let fingerprint: String
            let id: UUID
            var settled: Bool
            var audio: Data?
        }

        var schema = 1
        var records: [Record] = []

        var audioBytes: Int {
            records.compactMap { $0.audio?.count }.reduce(0, +)
        }
    }

    typealias Load = @MainActor (Phrase, UUID) async throws -> Data
    private static let maximumSavedAudioBytes = 8 * 1024 * 1024
    private static let maximumRecords = 8192
    private let isCurrent: @MainActor () -> Bool
    private let storage: LioSpokenLedgerStorage?
    private let load: Load
    private var loadedLedger: Ledger?
    private var inFlight: Set<String> = []

    init(isCurrent: @escaping @MainActor () -> Bool = { true },
         storage: LioSpokenLedgerStorage? = nil, load: @escaping Load) {
        self.isCurrent = isCurrent
        self.storage = storage
        self.load = load
    }

    func audio(for phrase: Phrase) async throws -> Data {
        try requireCurrentSession()
        let key = phrase.fingerprint
        var ledger = try currentLedger()
        let id: UUID
        if let record = ledger.records.first(where: { $0.fingerprint == key }) {
            if record.settled {
                guard let audio = record.audio else { throw LioSpokenRelayFailure.alreadyUsed }
                return audio
            }
            id = record.id
        } else {
            guard ledger.records.count < Self.maximumRecords else { throw LioSpokenRelayFailure.unavailable }
            id = UUID()
            ledger.records.append(.init(fingerprint: key, id: id, settled: false))
            try persist(ledger)
        }

        guard inFlight.insert(key).inserted else { throw Failure.alreadyLoading }
        defer { inFlight.remove(key) }

        do {
            let data = try await load(phrase, id)
            try requireCurrentSession()
            try validateWAV(data)
            try settle(key, audio: data)
            return data
        } catch LioSpokenRelayFailure.alreadyUsed {
            try requireCurrentSession()
            try settle(key, audio: nil)
            throw LioSpokenRelayFailure.alreadyUsed
        }
    }

    var canPlayCurrentAudio: Bool { isCurrent() }

    func requireCurrentSession() throws {
        try Task.checkCancellation()
        guard isCurrent() else { throw CancellationError() }
    }

    private func currentLedger() throws -> Ledger {
        if let loadedLedger { return loadedLedger }
        let ledger: Ledger
        if let encoded = try storage?.load() {
            guard encoded.count <= LioSpokenLedgerStorage.maximumEncodedBytes else {
                throw CocoaError(.fileReadCorruptFile)
            }
            ledger = try JSONDecoder().decode(Ledger.self, from: encoded)
            guard ledger.schema == 1, ledger.records.count <= Self.maximumRecords,
                  Set(ledger.records.map(\.fingerprint)).count == ledger.records.count,
                  ledger.records.allSatisfy({
                      $0.fingerprint.utf8.count == 64 && ($0.settled || $0.audio == nil)
                  }),
                  ledger.audioBytes <= Self.maximumSavedAudioBytes else {
                throw CocoaError(.fileReadCorruptFile)
            }
            for audio in ledger.records.compactMap(\.audio) { try validateWAV(audio) }
        } else {
            ledger = Ledger()
        }
        loadedLedger = ledger
        return ledger
    }

    private func persist(_ ledger: Ledger) throws {
        do {
            if let storage { try storage.save(JSONEncoder().encode(ledger)) }
            loadedLedger = ledger
        } catch {
            loadedLedger = nil
            throw error
        }
    }

    private func settle(_ key: String, audio: Data?) throws {
        var ledger = try currentLedger()
        guard let index = ledger.records.firstIndex(where: { $0.fingerprint == key }) else {
            throw CocoaError(.fileReadCorruptFile)
        }
        var record = ledger.records.remove(at: index)
        record.settled = true
        record.audio = audio
        ledger.records.append(record)

        var used = ledger.audioBytes
        for entry in ledger.records.indices where used > Self.maximumSavedAudioBytes {
            if let old = ledger.records[entry].audio {
                used -= old.count
                ledger.records[entry].audio = nil
            }
        }
        try persist(ledger)
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
