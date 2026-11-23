import Foundation
import CJTripClient

struct LioTaxiPlace: Codable, Equatable, Identifiable, Sendable {
    struct Coordinate: Codable, Hashable, Sendable {
        enum ReferenceSystem: String, Codable, Sendable {
            case wgs84, gcj02
        }

        let latitude: Double
        let longitude: Double
        let referenceSystem: ReferenceSystem
    }

    struct ID: Hashable {
        let name: String
        let coordinate: Coordinate
    }

    let nameZH: String
    let nameEN: String
    let addressZH: String?
    let coordinate: Coordinate

    var id: ID { ID(name: nameZH, coordinate: coordinate) }

    func name(in language: LioLanguage) -> String {
        language == .chinese ? nameZH : nameEN
    }

    init(nameZH: String, nameEN: String, addressZH: String?, coordinate: Coordinate) {
        self.nameZH = nameZH
        self.nameEN = nameEN
        self.addressZH = addressZH
        self.coordinate = coordinate
    }

    init?(itineraryPlace: LioRichItinerary.Place) {
        guard let point = itineraryPlace.mapPoint else { return nil }
        self.init(nameZH: itineraryPlace.nameZH, nameEN: itineraryPlace.nameEN,
                  addressZH: itineraryPlace.driverAddress,
                  coordinate: Coordinate(latitude: point.latitude, longitude: point.longitude,
                                         referenceSystem: .gcj02))
    }

    init?(tripPlace: TripPlaceProjection) {
        guard let marker = tripPlace.markerCoordinate else { return nil }
        let point = LioItinerary.Point(marker: marker)
        self.init(nameZH: tripPlace.nameZH, nameEN: tripPlace.officialNameEN.value ?? tripPlace.nameZH,
                  addressZH: tripPlace.addressZH.value,
                  coordinate: Coordinate(latitude: point.latitude, longitude: point.longitude,
                                         referenceSystem: .gcj02))
    }
}

@MainActor public struct LioTaxiRecentPlaces {
    public static let directoryName = "taxi-recents"
    public static let fileName = "recent-taxi-places.json"

    public static func storageDirectory(inMessageDirectory directory: URL) -> URL {
        directory.appendingPathComponent(directoryName, isDirectory: true)
    }

    private let directory: URL
    private let isCurrent: @MainActor () -> Bool
    private var file: URL { directory.appendingPathComponent(Self.fileName) }

    init(directory: URL, isCurrent: @escaping @MainActor () -> Bool = { true }) {
        self.directory = directory
        self.isCurrent = isCurrent
    }

    func load() throws -> [LioTaxiPlace] {
        guard isCurrent() else { throw CancellationError() }
        do {
            let data = try Data(contentsOf: file)
            return Array(try JSONDecoder().decode([LioTaxiPlace].self, from: data).prefix(10))
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return []
        }
    }

    func record(_ place: LioTaxiPlace) throws -> [LioTaxiPlace] {
        let others = try load().filter { $0.id != place.id }
        let entries = Array(([place] + others).prefix(10))
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var storedDirectory = directory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try storedDirectory.setResourceValues(attributes)
        let data = try JSONEncoder().encode(entries)
        #if os(iOS)
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file, options: .atomic)
        #endif
        return entries
    }
}
