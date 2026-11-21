import Foundation

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
}

@MainActor struct LioTaxiRecentPlaces {
    private let directory: URL
    private var file: URL { directory.appendingPathComponent("recent-taxi-places.json") }

    init(directory: URL) {
        self.directory = directory
    }

    func load() throws -> [LioTaxiPlace] {
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
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
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
