import Foundation

/// The hotel the traveller is staying at (#1573): one tap to take a taxi back or show the driver.
/// Set by hand, saved from a hotel search result, or picked from the trip's places. Kept on this device only.
struct LioStayHotel: Codable, Equatable, Sendable {
    enum Source: String, Codable, Sendable {
        case manual, hotelSearch, trip
    }

    static let maximumRoomNumberLength = 12

    let place: LioTaxiPlace
    let roomNumber: String?
    let source: Source

    init(place: LioTaxiPlace, roomNumber: String?, source: Source) {
        self.place = place
        let room = roomNumber?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        self.roomNumber = room.isEmpty ? nil : String(room.prefix(Self.maximumRoomNumberLength))
        self.source = source
    }

    private enum CodingKeys: String, CodingKey { case place, roomNumber, source }

    /// A file written by hand or by an older build goes through the same cleaning as a new hotel.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(place: try container.decode(LioTaxiPlace.self, forKey: .place),
                  roomNumber: try container.decodeIfPresent(String.self, forKey: .roomNumber),
                  source: try container.decode(Source.self, forKey: .source))
    }

    /// The request above the hotel's name on the driver sign.
    static let driverRequestZH = "请送我回这家酒店"

    var showCardHotel: LioShowCardInput.Hotel {
        LioShowCardInput.Hotel(nameZH: place.nameZH, addressZH: place.addressZH)
    }
}

enum LioReturnHotel {
    private static let hotelWordsZH = ["酒店", "宾馆", "饭店", "旅馆", "客栈", "民宿", "公寓", "招待所", "青旅", "旅舍"]
    private static let hotelWordsEN = ["hotel", "inn", "hostel", "guesthouse", "guest house", "resort", "apartment", "lodge"]

    /// Trip places that look like somewhere to stay come first; nothing is chosen for the traveller.
    static func candidates(from places: [LioTaxiPlace]) -> [LioTaxiPlace] {
        let stays = places.filter(looksLikeStay)
        return stays + places.filter { !looksLikeStay($0) }
    }

    static func looksLikeStay(_ place: LioTaxiPlace) -> Bool {
        let english = place.nameEN.lowercased()
        return hotelWordsZH.contains(where: place.nameZH.contains)
            || hotelWordsEN.contains { english.range(of: "\\b" + $0 + "\\b", options: .regularExpression) != nil }
    }

    /// Asking Lio to go back to the hotel, such as 回酒店 or "back to my hotel". Searching for hotels is not.
    static func isReturnRequest(_ text: String) -> Bool {
        let lower = text.lowercased()
        let chinese = ["回酒店", "回宾馆", "回饭店", "回旅馆", "回民宿", "回住处", "回住的地方"]
        if chinese.contains(where: text.contains) { return true }
        let place = #"(hotel|hostel|accommodation)\b(?!\s+(search|list|results?|prices?|deals?))"#
        let patterns = [
            #"\b(go|get|going|getting|take|bring|drive|head|heading|walk|ride)(\s+me|\s+us)?\s+back\s+to\s+(my\s+|our\s+|the\s+)?"# + place,
            #"\breturn\s+to\s+(my\s+|our\s+|the\s+)?"# + place,
            #"\bback\s+to\s+(my|our)\s+"# + place,
            #"^\s*back\s+to\s+(the\s+)?"# + place,
        ]
        return patterns.contains { lower.range(of: $0, options: .regularExpression) != nil }
    }
}

/// `G2CShowCardEnabled`: off unless the build says YES (same rule as `G2CRoadbookEnabled`).
enum LioShowCardFeature {
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }
}

/// The stay hotel for the signed-in account, in its message folder; account cleanup removes it.
@MainActor public struct LioReturnHotelStore {
    nonisolated public static let directoryName = "return-hotel"
    nonisolated public static let fileName = "return-hotel.json"

    nonisolated public static func storageDirectory(inMessageDirectory directory: URL) -> URL {
        directory.appendingPathComponent(directoryName, isDirectory: true)
    }

    let directory: URL
    private let isCurrent: @MainActor () -> Bool
    private var file: URL { directory.appendingPathComponent(Self.fileName) }

    init(directory: URL, isCurrent: @escaping @MainActor () -> Bool) {
        self.directory = directory
        self.isCurrent = isCurrent
    }

    private struct Archive: Codable {
        let version: Int
        let hotel: LioStayHotel?
    }

    /// A damaged or newer file reads as no hotel, so the traveller can set it again.
    func load() throws -> LioStayHotel? {
        guard isCurrent() else { throw CancellationError() }
        let data: Data
        do {
            data = try Data(contentsOf: file)
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return nil
        }
        guard let archive = try? JSONDecoder().decode(Archive.self, from: data), archive.version == 1 else { return nil }
        return archive.hotel
    }

    func save(_ hotel: LioStayHotel) throws {
        try write(Archive(version: 1, hotel: hotel))
    }

    func clear() throws {
        guard isCurrent() else { throw CancellationError() }
        do {
            try FileManager.default.removeItem(at: file)
        } catch let error as CocoaError where error.code == .fileNoSuchFile {
            return
        }
    }

    private func write(_ archive: Archive) throws {
        guard isCurrent() else { throw CancellationError() }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var storedDirectory = directory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try storedDirectory.setResourceValues(attributes)
        let data = try JSONEncoder().encode(archive)
        #if os(iOS)
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file, options: .atomic)
        #endif
    }
}

/// What the Tools tab needs for Back to Hotel (#1574), so its entry stays a few lines.
@MainActor enum LioReturnHotelTools {
    /// The account's message folder is the parent of its roadbook folder (`LioAccountFolders.roadbooks`);
    /// sign-out cleans this same folder (`LioReturnHotelCleanup`, `LioShowCardDetailsCleanup`).
    nonisolated static func messageDirectory(roadbookDirectory: URL?) -> URL? {
        roadbookDirectory?.deletingLastPathComponent()
    }

    static func hotelStore(roadbookDirectory: URL?, isCurrent: @escaping @MainActor () -> Bool) -> LioReturnHotelStore? {
        messageDirectory(roadbookDirectory: roadbookDirectory).map {
            LioReturnHotelStore(directory: LioReturnHotelStore.storageDirectory(inMessageDirectory: $0), isCurrent: isCurrent)
        }
    }

    static func detailsStore(roadbookDirectory: URL?, isCurrent: @escaping @MainActor () -> Bool) -> LioShowCardDetailsStore? {
        messageDirectory(roadbookDirectory: roadbookDirectory).map {
            LioShowCardDetailsStore(directory: LioShowCardDetailsStore.storageDirectory(inMessageDirectory: $0), isCurrent: isCurrent)
        }
    }
}
