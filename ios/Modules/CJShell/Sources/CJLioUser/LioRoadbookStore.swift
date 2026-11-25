import CryptoKit
import Foundation

/// The on-device copy of a roadbook, so it opens without a connection. This is a storage snapshot of
/// `LioRichItinerary`, not a second trip model: it maps field for field and back.
struct LioRoadbookArchive: Codable, Equatable, Sendable {
    enum Failure: Error, Equatable { case unsupportedVersion, invalidValue }

    static let currentVersion = 1

    struct City: Codable, Equatable, Sendable { let nameZH: String; let nameEN: String }
    struct Place: Codable, Equatable, Sendable {
        let nameZH: String
        let nameEN: String
        let address: String?
        let matched: Bool
        let latitude: Double?
        let longitude: Double?
    }
    struct Stop: Codable, Equatable, Sendable {
        let id: String
        let kind: String
        let text: String
        let time: String?
        let place: Place
        let note: String?
        let tip: String?
        let fixed: Bool?
    }
    struct Leg: Codable, Equatable, Sendable {
        let fromID: String
        let toID: String
        let mode: String?
        let seconds: Double?
        let metres: Double?
    }
    struct Day: Codable, Equatable, Sendable {
        let number: Int
        let date: String?
        let theme: String
        let area: String
        let stops: [Stop]
        let legs: [Leg]
    }
    struct Hotel: Codable, Equatable, Sendable { let id: String; let place: Place; let note: String? }
    struct Detail: Codable, Equatable, Sendable { let stopID: String; let detail: LioRoadbookDetail }

    let version: Int
    let id: String
    let source: String
    let city: City?
    let createdAt: Date
    let title: String
    let undated: Bool
    let days: [Day]
    let lodgingArea: String
    let hotels: [Hotel]
    /// Optional so copies kept before place details existed still open.
    let details: [Detail]?

    init(_ roadbook: LioRoadbook) {
        func place(_ value: LioRichItinerary.Place) -> Place {
            Place(nameZH: value.nameZH, nameEN: value.nameEN, address: value.address, matched: value.matched,
                  latitude: value.point?.latitude, longitude: value.point?.longitude)
        }
        let itinerary = roadbook.itinerary
        version = Self.currentVersion
        id = roadbook.id
        source = roadbook.source.rawValue
        city = roadbook.city.map { City(nameZH: $0.nameZH, nameEN: $0.nameEN) }
        createdAt = roadbook.createdAt
        title = itinerary.title
        undated = itinerary.undated
        days = itinerary.days.map { day in
            Day(number: day.number, date: day.date, theme: day.theme, area: day.area,
                stops: day.stops.map {
                    Stop(id: $0.id, kind: $0.kind.rawValue, text: $0.text, time: $0.time, place: place($0.place),
                         note: $0.note, tip: $0.tip, fixed: $0.fixed)
                },
                legs: day.legs.map {
                    Leg(fromID: $0.fromID, toID: $0.toID, mode: $0.estimate?.mode.rawValue,
                        seconds: $0.estimate?.seconds, metres: $0.estimate?.metres)
                })
        }
        lodgingArea = itinerary.lodgingArea
        hotels = itinerary.hotels.map { Hotel(id: $0.id, place: place($0.place), note: $0.note) }
        let entries = roadbook.details.sorted { $0.key < $1.key }.map { Detail(stopID: $0.key, detail: $0.value) }
        details = entries.isEmpty ? nil : entries
    }

    func roadbook() throws -> LioRoadbook {
        guard version == Self.currentVersion else { throw Failure.unsupportedVersion }
        guard !id.isEmpty, let source = LioRoadbook.Source(rawValue: source) else { throw Failure.invalidValue }
        func place(_ value: Place) throws -> LioRichItinerary.Place {
            let point: LioItinerary.Point?
            switch (value.latitude, value.longitude) {
            case let (latitude?, longitude?):
                guard (-90...90).contains(latitude), (-180...180).contains(longitude) else { throw Failure.invalidValue }
                point = .init(latitude: latitude, longitude: longitude)
            case (nil, nil): point = nil
            default: throw Failure.invalidValue
            }
            return .init(nameZH: value.nameZH, nameEN: value.nameEN, address: value.address, matched: value.matched, point: point)
        }
        let days = try days.map { day in
            let stops = try day.stops.map { stop in
                guard let kind = LioRichItinerary.Kind(rawValue: stop.kind) else { throw Failure.invalidValue }
                return LioRichItinerary.Stop(id: stop.id, kind: kind, text: stop.text, time: stop.time,
                                             place: try place(stop.place), note: stop.note, tip: stop.tip, fixed: stop.fixed)
            }
            let legs = try day.legs.map { leg in
                let estimate: LioRichItinerary.Leg.Estimate?
                switch (leg.mode, leg.seconds, leg.metres) {
                case let (mode?, seconds?, metres?):
                    guard let mode = LioRichItinerary.Leg.Mode(rawValue: mode), seconds.isFinite, metres.isFinite,
                          seconds >= 0, metres >= 0 else { throw Failure.invalidValue }
                    estimate = .init(mode: mode, seconds: seconds, metres: metres)
                case (nil, nil, nil): estimate = nil
                default: throw Failure.invalidValue
                }
                return LioRichItinerary.Leg(fromID: leg.fromID, toID: leg.toID, estimate: estimate)
            }
            return LioRichItinerary.Day(number: day.number, date: day.date, theme: day.theme, area: day.area,
                                        stops: stops, legs: legs)
        }
        let hotels = try hotels.map { LioRichItinerary.Hotel(id: $0.id, place: try place($0.place), note: $0.note) }
        let itinerary = LioRichItinerary(title: title, undated: undated, days: days, lodgingArea: lodgingArea, hotels: hotels)
        let stopIDs = Set(days.flatMap(\.stops).map(\.id))
        var restored: [String: LioRoadbookDetail] = [:]
        for entry in details ?? [] {
            guard stopIDs.contains(entry.stopID), restored[entry.stopID] == nil else { throw Failure.invalidValue }
            restored[entry.stopID] = entry.detail
        }
        return LioRoadbook(id: id, source: source, city: city.map { .init(nameZH: $0.nameZH, nameEN: $0.nameEN) },
                           createdAt: createdAt, itinerary: itinerary, details: restored)
    }
}

/// Roadbooks kept on this phone inside the signed-in account's message folder (like taxi recents and
/// translation history), so they go with the account's local data: protected on disk, left out of backups,
/// never uploaded. One JSON file per roadbook, named by a hash so an id never becomes a path.
@MainActor struct LioRoadbookStore {
    enum Failure: Error, Equatable { case notCurrent }

    nonisolated static let directoryName = "roadbooks"

    nonisolated static func storageDirectory(inMessageDirectory directory: URL) -> URL {
        directory.appendingPathComponent(directoryName, isDirectory: true)
    }

    let directory: URL
    /// False once the account that owns the folder has signed out or changed.
    let isCurrent: @MainActor () -> Bool

    init(directory: URL, isCurrent: @escaping @MainActor () -> Bool = { true }) {
        self.directory = directory
        self.isCurrent = isCurrent
    }

    #if DEBUG
    /// Debug previews only: a folder outside any account.
    static func preview() throws -> LioRoadbookStore {
        let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                  appropriateFor: nil, create: true)
        return LioRoadbookStore(directory: support.appendingPathComponent("LioRoadbookPreview", isDirectory: true))
    }
    #endif

    func save(_ roadbook: LioRoadbook) throws {
        guard isCurrent() else { throw Failure.notCurrent }
        try prepareDirectory()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(LioRoadbookArchive(roadbook))
        #if os(iOS)
        try data.write(to: file(for: roadbook.id), options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file(for: roadbook.id), options: [.atomic])
        #endif
    }

    /// Newest first. A copy that cannot be read is skipped rather than stopping the library from opening.
    func load() -> [LioRoadbook] {
        guard isCurrent(), let files = try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) else {
            return []
        }
        return files.filter { $0.pathExtension == "json" }.compactMap { file in
            guard let data = try? Data(contentsOf: file),
                  let archive = try? JSONDecoder().decode(LioRoadbookArchive.self, from: data) else { return nil }
            return try? archive.roadbook()
        }
        .sorted { $0.createdAt != $1.createdAt ? $0.createdAt > $1.createdAt : $0.id < $1.id }
    }

    func contains(_ id: String) -> Bool { isCurrent() && FileManager.default.fileExists(atPath: file(for: id).path) }

    /// Removes this device's copy at the traveller's request; the trip itself is not touched.
    func remove(_ id: String) throws {
        guard isCurrent() else { throw Failure.notCurrent }
        let file = file(for: id)
        guard FileManager.default.fileExists(atPath: file.path) else { return }
        try FileManager.default.removeItem(at: file)
    }

    private func file(for id: String) -> URL {
        let name = SHA256.hash(data: Data(id.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(name).appendingPathExtension("json")
    }

    private func prepareDirectory() throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var folder = directory
        try folder.setResourceValues(values)
    }
}
