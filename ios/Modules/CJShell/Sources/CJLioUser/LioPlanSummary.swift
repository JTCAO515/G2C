import CJMessageHTTP
import CryptoKit
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

/// Plans the user saved on this device (#1453), newest first; one file per trip, replaced by a newer version.
struct LioSavedPlans: Sendable {
    let directory: URL

    static func appDefault() throws -> LioSavedPlans {
        let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                  appropriateFor: nil, create: true)
        return LioSavedPlans(directory: support.appendingPathComponent("lio-saved-plans", isDirectory: true))
    }

    private struct Record: Codable {
        let version: Int
        let savedAt: Date
        let plan: LioPlanSummary
    }

    func save(_ plan: LioPlanSummary, at date: Date = Date()) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let data = try JSONEncoder().encode(Record(version: 1, savedAt: date, plan: plan))
        try data.write(to: file(for: plan.tripID), options: [.atomic, .completeFileProtection])
    }

    func load() -> [LioPlanSummary] {
        guard let files = try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) else {
            return []
        }
        return files.compactMap { file -> Record? in
            guard file.pathExtension == "json", let data = try? Data(contentsOf: file),
                  let record = try? JSONDecoder().decode(Record.self, from: data), record.version == 1 else { return nil }
            return record
        }
        .sorted { $0.savedAt > $1.savedAt }
        .map(\.plan)
    }

    func remove(_ tripID: String) throws {
        let file = file(for: tripID)
        guard FileManager.default.fileExists(atPath: file.path) else { return }
        try FileManager.default.removeItem(at: file)
    }

    private func file(for tripID: String) -> URL {
        // Trip IDs are server values; hash them so any character set makes a safe file name.
        let name = SHA256.hash(data: Data(tripID.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(name + ".json")
    }
}

/// Saved plans for this device (#1453). A failed write keeps the previous list; nothing is reported as saved.
@MainActor @Observable
final class LioSavedPlansModel {
    private let store: LioSavedPlans?
    private(set) var plans: [LioPlanSummary]

    init(store: LioSavedPlans?) {
        self.store = store
        plans = store?.load() ?? []
    }

    static func appDefault() -> LioSavedPlansModel { LioSavedPlansModel(store: try? LioSavedPlans.appDefault()) }

    var available: Bool { store != nil }

    /// Saved means a plan with the same trip; a newer version of it is saved again.
    func isSaved(_ plan: LioPlanSummary) -> Bool { plans.contains(plan) }

    func save(_ plan: LioPlanSummary) {
        guard let store else { return }
        do {
            try store.save(plan)
            plans = store.load()
        } catch {}
    }

    func remove(_ plan: LioPlanSummary) {
        guard let store else { return }
        do {
            try store.remove(plan.tripID)
            plans = store.load()
        } catch {}
    }
}
