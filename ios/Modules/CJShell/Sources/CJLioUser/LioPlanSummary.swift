import CJMessageHTTP
import Foundation
import Observation

/// #1453 / #1723: the one trip object a saved plan is. The day-by-day page, the roadbook and the trip home all
/// read its stored `itinerary`; `days` is only a view of that itinerary for the trip home's rules.
/// A chat card (LIO-trip-card.2/.3) carries names and times only, so its places are unconfirmed (`matched=false`:
/// no map marker, taxi or driver card). A popular-route template (#1725) carries checked addresses and GCJ-02 points.
struct LioPlanSummary: Equatable, Identifiable, Sendable {
    /// Where the trip came from: the chat (the server's trip, by id and version) or a popular-route template.
    enum Source: String, Codable, Sendable { case chat, template }

    struct Item: Codable, Equatable, Sendable {
        let id: String
        let label: String
        let startTime: String?
        let endTime: String?
        let fixed: Bool?
        /// The English name, for a template's checked places only; nil for a chat plan, whose one name is
        /// shown in both languages.
        var labelEN: String? = nil

        func label(_ language: LioLanguage) -> String { language == .chinese ? label : (labelEN ?? label) }
    }
    struct Day: Codable, Equatable, Sendable {
        let number: Int
        let date: String?
        let items: [Item]
    }

    let tripID: String
    let tripVersion: Int64
    let source: Source
    /// Nil for an undated plan.
    let startDate: String?
    let itinerary: LioRichItinerary

    var id: String { tripID }
    var title: String { itinerary.title }
    var undated: Bool { itinerary.undated }
    /// The itinerary's days as names and times (Chinese names, as the booking rules match them; a template's
    /// English names ride along for the English trip home).
    var days: [Day] {
        itinerary.days.map { day in
            Day(number: day.number, date: day.date, items: day.stops.map {
                Item(id: $0.id, label: $0.place.nameZH, startTime: $0.time, endTime: nil, fixed: $0.fixed,
                     labelEN: source == .template ? $0.place.nameEN : nil)
            })
        }
    }
    var stopCount: Int { itinerary.days.reduce(0) { $0 + $1.stops.count } }

    init(tripID: String, tripVersion: Int64, source: Source, startDate: String?, itinerary: LioRichItinerary) {
        self.tripID = tripID; self.tripVersion = tripVersion; self.source = source
        self.startDate = startDate; self.itinerary = itinerary
    }

    /// A chat plan: names and times only, every place unconfirmed.
    init(tripID: String, tripVersion: Int64, title: String, startDate: String?, undated: Bool, days: [Day]) {
        self.init(tripID: tripID, tripVersion: tripVersion, source: .chat, startDate: startDate,
                  itinerary: LioRichItinerary(title: title, undated: undated, days: days.map { day in
            LioRichItinerary.Day(number: day.number, date: day.date, theme: "", area: "", stops: day.items.map { item in
                LioRichItinerary.Stop(id: item.id, kind: .unspecified, text: "", time: item.startTime,
                                      place: .init(nameZH: item.label, nameEN: item.label, address: nil, matched: false, point: nil),
                                      note: nil, tip: nil, fixed: item.fixed)
            }, legs: [])
        }, lodgingArea: "", hotels: []))
    }

    init(_ trip: LioExplorationWire.Trip) {
        switch trip {
        case .calendar(let card):
            self.init(id: card.id, version: card.tripVersion, title: card.title, calendar: card.calendar, days: card.days)
        case .rich(let card):
            self.init(id: card.id, version: card.tripVersion, title: card.title, calendar: card.calendar, days: card.days)
        }
    }

    /// #1723 / #1725: a popular route saved as the traveller's trip, with its checked places (taxi and the
    /// driver card work). Id `template:<route>`, version 0; it stays on this phone only.
    init(template roadbook: LioRoadbook) {
        let route = roadbook.id.hasPrefix("template.") ? String(roadbook.id.dropFirst("template.".count)) : roadbook.id
        self.init(tripID: Self.templatePrefix + route, tripVersion: 0, source: .template, startDate: nil,
                  itinerary: roadbook.itinerary)
    }

    static let templatePrefix = "template:"

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
    /// Distinguishes stores made for different host sessions, even for the same folder.
    let id = UUID()
    private let isCurrent: @MainActor () -> Bool
    private var file: URL { directory.appendingPathComponent(Self.fileName) }

    public init(directory: URL, isCurrent: @escaping @MainActor () -> Bool) {
        self.directory = directory
        self.isCurrent = isCurrent
    }

    var current: Bool { isCurrent() }

    /// v1 (#1453): the summary only. Read so nothing saved earlier is lost; its places are unconfirmed.
    private struct RecordV1: Codable {
        struct Plan: Codable {
            let tripID: String
            let tripVersion: Int64
            let title: String
            let startDate: String?
            let undated: Bool
            let days: [LioPlanSummary.Day]
        }
        let savedAt: Date
        let plan: Plan
    }
    /// v2 (#1723): the whole trip, in the roadbook copy's place, stop and day encoding.
    private struct Record: Codable {
        struct Trip: Codable {
            let title: String
            let undated: Bool
            let days: [LioRoadbookArchive.Day]
            let lodgingArea: String
            let hotels: [LioRoadbookArchive.Hotel]
        }
        let savedAt: Date
        let tripID: String
        let tripVersion: Int64
        let source: LioPlanSummary.Source
        let startDate: String?
        let trip: Trip

        init(savedAt: Date, plan: LioPlanSummary) {
            self.savedAt = savedAt
            tripID = plan.tripID; tripVersion = plan.tripVersion; source = plan.source; startDate = plan.startDate
            let itinerary = plan.itinerary
            trip = Trip(title: itinerary.title, undated: itinerary.undated, days: LioRoadbookArchive.days(itinerary),
                        lodgingArea: itinerary.lodgingArea, hotels: LioRoadbookArchive.hotels(itinerary))
        }

        func plan() throws -> LioPlanSummary {
            guard !tripID.isEmpty else { throw LioRoadbookArchive.Failure.invalidValue }
            return LioPlanSummary(tripID: tripID, tripVersion: tripVersion, source: source, startDate: startDate,
                                  itinerary: try LioRoadbookArchive.itinerary(title: trip.title, undated: trip.undated,
                                                                              days: trip.days, lodgingArea: trip.lodgingArea,
                                                                              hotels: trip.hotels))
        }
    }
    private struct Header: Codable { let version: Int }
    private struct ArchiveV1: Codable { let version: Int; let records: [RecordV1] }
    /// A record that cannot be read is skipped rather than hiding every other saved trip.
    private struct Lenient<Value: Decodable>: Decodable {
        let value: Value?
        init(from decoder: Decoder) throws { value = try? Value(from: decoder) }
    }
    private struct ArchiveV2Read: Decodable { let version: Int; let records: [Lenient<Record>] }
    private struct Archive: Encodable { let version: Int; let records: [Record] }
    static let currentVersion = 2

    /// The file was written by a newer app (a version this build does not know). It is never rewritten:
    /// reading throws this, so saving and removing stop before they write, and the newer trips stay on disk.
    struct UnsupportedVersion: Error, Equatable { let version: Int }

    func load() throws -> [LioPlanSummary] { try records().map(\.plan) }

    /// Keeps one copy per trip, the highest version; an older version never replaces a newer one.
    func save(_ plan: LioPlanSummary, at date: Date = Date()) throws {
        let all = try records()
        if let kept = all.first(where: { $0.plan.tripID == plan.tripID }), kept.plan.tripVersion > plan.tripVersion { return }
        let others = all.filter { $0.plan.tripID != plan.tripID }
        try write(Array(([(savedAt: date, plan: plan)] + others).prefix(Self.maximumCount)))
    }

    /// #1725: saves a popular route as the traveller's trip (`template:<route>`, version 0, checked places).
    @discardableResult
    func saveTemplate(_ roadbook: LioRoadbook, at date: Date = Date()) throws -> LioPlanSummary {
        let plan = LioPlanSummary(template: roadbook)
        try save(plan, at: date)
        return plan
    }

    func remove(_ tripID: String) throws {
        let all = try records()
        guard all.contains(where: { $0.plan.tripID == tripID }) else { return }
        try write(all.filter { $0.plan.tripID != tripID })
    }

    private func records() throws -> [(savedAt: Date, plan: LioPlanSummary)] {
        guard isCurrent() else { throw CancellationError() }
        let data: Data
        do {
            data = try Data(contentsOf: file)
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return []
        }
        let decoder = JSONDecoder()
        let found: [(savedAt: Date, plan: LioPlanSummary)]
        switch try decoder.decode(Header.self, from: data).version {
        case 1:
            found = try decoder.decode(ArchiveV1.self, from: data).records.map { record in
                let plan = record.plan
                return (record.savedAt, LioPlanSummary(tripID: plan.tripID, tripVersion: plan.tripVersion, title: plan.title,
                                                       startDate: plan.startDate, undated: plan.undated, days: plan.days))
            }
        case Self.currentVersion:
            found = try decoder.decode(ArchiveV2Read.self, from: data).records.compactMap { entry in
                guard let record = entry.value, let plan = try? record.plan() else { return nil }
                return (record.savedAt, plan)
            }
        case let unknown:
            throw UnsupportedVersion(version: unknown)
        }
        // One copy per trip, the highest version (newest saved on a tie).
        var best: [String: (savedAt: Date, plan: LioPlanSummary)] = [:]
        for entry in found {
            if let kept = best[entry.plan.tripID],
               (kept.plan.tripVersion, kept.savedAt) >= (entry.plan.tripVersion, entry.savedAt) { continue }
            best[entry.plan.tripID] = entry
        }
        return best.values.sorted { $0.savedAt != $1.savedAt ? $0.savedAt > $1.savedAt : $0.plan.tripID < $1.plan.tripID }
    }

    private func write(_ records: [(savedAt: Date, plan: LioPlanSummary)]) throws {
        guard isCurrent() else { throw CancellationError() }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var storedDirectory = directory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try storedDirectory.setResourceValues(attributes)
        let data = try JSONEncoder().encode(Archive(version: Self.currentVersion,
                                                                records: records.map { Record(savedAt: $0.savedAt, plan: $0.plan) }))
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
    /// The saved-plans file is from a newer app: its trips are kept on disk but cannot be shown or changed
    /// here, so the list is not "no trips" and nothing is offered as saveable.
    private(set) var newerVersion = false

    init(store: LioSavedPlans?) {
        self.store = store
        cached = []
        reload()
    }

    var storeID: UUID? { store?.id }
    var available: Bool { store?.current == true }
    /// Saving needs a store this build can write: never over a newer app's file.
    var writable: Bool { available && !newerVersion }
    var unreadable: Bool { available && newerVersion }
    var plans: [LioPlanSummary] { available ? cached : [] }

    private func reload() {
        guard let store else { return }
        do {
            cached = try store.load()
            newerVersion = false
        } catch is LioSavedPlans.UnsupportedVersion {
            newerVersion = true
        } catch {}
    }

    /// The same version of the same trip; a newer version of a saved trip can be saved again.
    func isSaved(_ plan: LioPlanSummary) -> Bool { plans.contains(plan) }

    /// #1725: the popular route is saved as a trip (in either language; the id is the route's).
    func isSavedTemplate(_ roadbook: LioRoadbook) -> Bool {
        let id = LioPlanSummary(template: roadbook).tripID
        return plans.contains { $0.tripID == id }
    }

    func save(_ plan: LioPlanSummary) {
        guard let store else { return }
        do {
            try store.save(plan)
        } catch {}
        reload()
    }

    /// #1723 PR-2: chat trips whose places are being read before they are saved.
    private(set) var savingTripIDs: Set<String> = []
    func isSaving(_ plan: LioPlanSummary) -> Bool { savingTripIDs.contains(plan.tripID) }

    /// #1723 PR-2 (places read on): a saved copy of this trip at this version or newer counts as saved, since it
    /// may carry the read's confirmed places or the newer version the read found.
    func hasSavedCopy(of plan: LioPlanSummary) -> Bool {
        plans.contains { $0.tripID == plan.tripID && $0.tripVersion >= plan.tripVersion }
    }

    /// #1723 PR-2: reads the card's trip for its places, then saves what that decided (the summary on any doubt or
    /// failure, within the reader's deadline). Nil when nothing was started (no store, or already saving it).
    @discardableResult
    func save(_ plan: LioPlanSummary, reference: LioChatTripReference,
              places: LioChatTripPlaces) async -> LioChatTripPlaces.Outcome? {
        guard store != nil, savingTripIDs.insert(plan.tripID).inserted else { return nil }
        defer { savingTripIDs.remove(plan.tripID) }
        let result = await places.plan(for: reference, summary: plan)
        save(result.plan)
        return result.outcome
    }

    /// #1725: saves a popular route as a trip with checked places; nil when nothing was saved.
    @discardableResult
    func saveTemplate(_ roadbook: LioRoadbook) -> LioPlanSummary? {
        guard let store else { return nil }
        let saved = try? store.saveTemplate(roadbook)
        reload()
        return saved.flatMap { cached.contains($0) ? $0 : nil }
    }

    func remove(_ plan: LioPlanSummary) {
        guard let store else { return }
        do {
            try store.remove(plan.tripID)
        } catch {}
        reload()
    }
}
