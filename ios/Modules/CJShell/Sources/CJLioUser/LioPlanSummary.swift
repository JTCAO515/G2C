import CJMessageHTTP
import Foundation
import Observation

/// #1453: a planned trip as the summary card carries it (LIO-trip-card.2/.3): title, calendar state and each
/// day's places and times. It has no place kind, address, coordinate, travel leg or lodging; those come from the
/// rich detail read, which is not available yet. The summary maps to `LioRichItinerary` without inventing them.
struct LioPlanSummary: Codable, Equatable, Identifiable, Sendable {
    struct Item: Codable, Equatable, Sendable {
        let id: String
        let label: String
        let startTime: String?
        let endTime: String?
        let fixed: Bool?
    }
    struct Day: Codable, Equatable, Sendable {
        let number: Int
        let date: String?
        let items: [Item]
    }

    let tripID: String
    let tripVersion: Int64
    let title: String
    /// Nil for an undated plan.
    let startDate: String?
    let undated: Bool
    let days: [Day]

    var id: String { tripID }
    var stopCount: Int { days.reduce(0) { $0 + $1.items.count } }

    init(tripID: String, tripVersion: Int64, title: String, startDate: String?, undated: Bool, days: [Day]) {
        self.tripID = tripID; self.tripVersion = tripVersion; self.title = title
        self.startDate = startDate; self.undated = undated; self.days = days
    }

    init(_ trip: LioExplorationWire.Trip) {
        switch trip {
        case .calendar(let card):
            self.init(id: card.id, version: card.tripVersion, title: card.title, calendar: card.calendar, days: card.days)
        case .rich(let card):
            self.init(id: card.id, version: card.tripVersion, title: card.title, calendar: card.calendar, days: card.days)
        }
    }

    private init(id: String, version: Int64, title: String, calendar: LioCalendarTripCard.CalendarState?,
                 days: [LioCalendarTripCard.Day]) {
        let start: String?
        switch calendar { case .dated(let date): start = date; case .undated, nil: start = nil }
        self.init(tripID: id, tripVersion: version, title: title, startDate: start, undated: start == nil,
                  days: days.enumerated().map { position, day in
            Day(number: day.index.map(Int.init) ?? position + 1, date: day.date, items: day.items.map {
                Item(id: $0.id, label: $0.label, startTime: $0.startTime, endTime: $0.endTime, fixed: $0.fixed)
            })
        })
    }

    /// Display values only: summary places are unconfirmed, so no map marker, taxi or driver card is offered.
    var itinerary: LioRichItinerary {
        LioRichItinerary(title: title, undated: undated, days: days.map { day in
            LioRichItinerary.Day(number: day.number, date: day.date, theme: "", area: "", stops: day.items.map { item in
                LioRichItinerary.Stop(id: item.id, kind: .unspecified, text: "", time: item.startTime,
                                      place: .init(nameZH: item.label, nameEN: item.label, address: nil, matched: false, point: nil),
                                      note: nil, tip: nil, fixed: item.fixed)
            }, legs: [])
        }, lodgingArea: "", hotels: [])
    }
}

extension LioRichItinerary {
    /// Plain text for the system share sheet: title, then each day's times and places.
    func shareText(_ language: LioLanguage) -> String {
        var lines = [title]
        for day in days {
            lines.append("")
            var heading = language.text("Day \(day.number)", "第 \(day.number) 天")
            if let date = day.date { heading += " · " + date }
            if !day.area.isEmpty { heading += " · " + day.area }
            lines.append(heading)
            for stop in day.stops {
                let name = stop.place.displayName(language)
                lines.append(stop.time.map { "\($0) \(name)" } ?? name)
            }
        }
        return lines.joined(separator: "\n")
    }
}

/// Plans the user saved on this device (#1453), newest first, in the signed-in account's message folder.
/// One file per account; account cleanup removes it. A newer version of a trip replaces the older copy.
@MainActor public struct LioSavedPlans {
    public static let directoryName = "saved-plans"
    public static let fileName = "saved-plans.json"
    static let maximumCount = 50

    public static func storageDirectory(inMessageDirectory directory: URL) -> URL {
        directory.appendingPathComponent(directoryName, isDirectory: true)
    }

    let directory: URL
    private let isCurrent: @MainActor () -> Bool
    private var file: URL { directory.appendingPathComponent(Self.fileName) }

    public init(directory: URL, isCurrent: @escaping @MainActor () -> Bool) {
        self.directory = directory
        self.isCurrent = isCurrent
    }

    var current: Bool { isCurrent() }

    private struct Record: Codable {
        let savedAt: Date
        let plan: LioPlanSummary
    }
    private struct Archive: Codable {
        let version: Int
        let records: [Record]
    }

    func load() throws -> [LioPlanSummary] { try records().map(\.plan) }

    func save(_ plan: LioPlanSummary, at date: Date = Date()) throws {
        let others = try records().filter { $0.plan.tripID != plan.tripID }
        try write(Array(([Record(savedAt: date, plan: plan)] + others).prefix(Self.maximumCount)))
    }

    func remove(_ tripID: String) throws {
        let all = try records()
        guard all.contains(where: { $0.plan.tripID == tripID }) else { return }
        try write(all.filter { $0.plan.tripID != tripID })
    }

    private func records() throws -> [Record] {
        guard isCurrent() else { throw CancellationError() }
        do {
            let archive = try JSONDecoder().decode(Archive.self, from: Data(contentsOf: file))
            guard archive.version == 1 else { return [] }
            return archive.records.sorted { $0.savedAt > $1.savedAt }
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return []
        }
    }

    private func write(_ records: [Record]) throws {
        guard isCurrent() else { throw CancellationError() }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var storedDirectory = directory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try storedDirectory.setResourceValues(attributes)
        let data = try JSONEncoder().encode(Archive(version: 1, records: records))
        #if os(iOS)
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file, options: .atomic)
        #endif
    }
}

/// Saved plans for the current account (#1453). Nothing shows once the account is no longer current, and a
/// failed write keeps the previous list; nothing is reported as saved.
@MainActor @Observable
final class LioSavedPlansModel {
    private let store: LioSavedPlans?
    private var cached: [LioPlanSummary]

    init(store: LioSavedPlans?) {
        self.store = store
        cached = (try? store?.load()) ?? []
    }

    var storeDirectory: URL? { store?.directory }
    var available: Bool { store?.current == true }
    var plans: [LioPlanSummary] { available ? cached : [] }

    /// The same version of the same trip; a newer version of a saved trip can be saved again.
    func isSaved(_ plan: LioPlanSummary) -> Bool { plans.contains(plan) }

    func save(_ plan: LioPlanSummary) {
        guard let store else { return }
        do {
            try store.save(plan)
            cached = try store.load()
        } catch {}
    }

    func remove(_ plan: LioPlanSummary) {
        guard let store else { return }
        do {
            try store.remove(plan.tripID)
            cached = try store.load()
        } catch {}
    }
}
