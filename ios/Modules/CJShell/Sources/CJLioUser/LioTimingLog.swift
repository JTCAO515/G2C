import Foundation
import os

/// Records, on this device only, how long each reply took to show progress, its first visible
/// character and its end (#913). Only durations and the interface language are kept: no message
/// text, IDs or account data. Line C reads the newest entries from the app's user defaults key
/// `lio.timing.v1`; each entry is also logged under subsystem `space.go2china.lio`, category `timing`.
@MainActor
final class LioTimingLog {
    struct Entry: Codable, Equatable {
        /// Seconds since 1970 when the message was sent.
        let sentAt: Double
        let language: String
        var indicatorMs: Int?
        var firstTextMs: Int?
        var finishedMs: Int?

        enum CodingKeys: String, CodingKey {
            case sentAt = "sent_at", language
            case indicatorMs = "indicator_ms", firstTextMs = "first_text_ms", finishedMs = "finished_ms"
        }
    }

    enum Milestone { case indicator, firstText, finished }

    static let defaultsKey = "lio.timing.v1"
    static let capacity = 50
    private static let logger = Logger(subsystem: "space.go2china.lio", category: "timing")

    private let defaults: UserDefaults
    private var open: [Data: (start: Date, entry: Entry)] = [:]
    private var unrecorded: [Data: Date] = [:]

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    func start(_ turn: Data, language: String, at now: Date = .now) {
        open[turn] = (now, Entry(sentAt: now.timeIntervalSince1970, language: language))
    }

    func sentAt(_ turn: Data) -> Date? { open[turn]?.start }

    /// When the indicator for `turn` should count from: its send time, or for a restored pending turn
    /// the first time it was seen. Restored turns are not recorded.
    func indicatorStart(_ turn: Data, now: Date = .now) -> Date {
        if let start = open[turn]?.start ?? unrecorded[turn] { return start }
        unrecorded[turn] = now
        return now
    }

    /// Marks the first time a milestone is reached; later repeats are ignored. `finished` stores the entry.
    func mark(_ milestone: Milestone, _ turn: Data, at now: Date = .now) {
        guard var record = open[turn] else { return }
        let elapsed = Int((now.timeIntervalSince(record.start) * 1000).rounded())
        switch milestone {
        case .indicator where record.entry.indicatorMs == nil: record.entry.indicatorMs = elapsed
        case .firstText where record.entry.firstTextMs == nil: record.entry.firstTextMs = elapsed
        case .finished:
            record.entry.finishedMs = elapsed
            open[turn] = nil
            store(record.entry)
            return
        default: return
        }
        open[turn] = record
    }

    /// Stored entries, oldest first.
    func entries() -> [Entry] {
        guard let data = defaults.data(forKey: Self.defaultsKey) else { return [] }
        return (try? JSONDecoder().decode([Entry].self, from: data)) ?? []
    }

    private func store(_ entry: Entry) {
        let kept = Array((entries() + [entry]).suffix(Self.capacity))
        if let data = try? JSONEncoder().encode(kept) { defaults.set(data, forKey: Self.defaultsKey) }
        Self.logger.info("""
            reply timing language=\(entry.language, privacy: .public) \
            indicator_ms=\(entry.indicatorMs ?? -1, privacy: .public) \
            first_text_ms=\(entry.firstTextMs ?? -1, privacy: .public) \
            finished_ms=\(entry.finishedMs ?? -1, privacy: .public)
            """)
    }
}
