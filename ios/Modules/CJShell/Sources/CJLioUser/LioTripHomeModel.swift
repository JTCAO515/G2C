import Foundation
import Observation

/// Trip home, phase 1 (办事清单): a calendar day the traveller picked, written `yyyy-MM-dd`.
/// Days, not instants, are compared, so "arrival day" means the same date wherever the phone is.
struct LioTripDay: Codable, Comparable, Hashable, Sendable, CustomStringConvertible {
    let year: Int, month: Int, day: Int

    init?(_ text: String) {
        let parts = text.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 3, parts[0].count == 4, parts[1].count == 2, parts[2].count == 2,
              let year = Int(parts[0]), let month = Int(parts[1]), let day = Int(parts[2]) else { return nil }
        var components = DateComponents(year: year, month: month, day: day)
        components.calendar = Self.gregorian(TimeZone(identifier: "UTC")!)
        guard components.isValidDate else { return nil }
        self.year = year; self.month = month; self.day = day
    }

    /// The day of an instant in the given time zone. Always Gregorian, whatever calendar the phone uses.
    init(date: Date, timeZone: TimeZone = .current) {
        let parts = Self.gregorian(timeZone).dateComponents([.year, .month, .day], from: date)
        year = parts.year!; month = parts.month!; day = parts.day!
    }

    init(from decoder: any Decoder) throws {
        let text = try decoder.singleValueContainer().decode(String.self)
        guard let day = Self(text) else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "bad day"))
        }
        self = day
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(description)
    }

    /// Midnight of this day in the given time zone, for date pickers and local reminders.
    func start(in timeZone: TimeZone = .current) -> Date {
        Self.gregorian(timeZone).date(from: DateComponents(year: year, month: month, day: day))!
    }

    /// Days are clamped to about a century either way, so a damaged plan's day number cannot overflow the calendar.
    func adding(days: Int) -> Self {
        let utc = TimeZone(identifier: "UTC")!
        let span = min(max(days, -36_600), 36_600)
        guard let date = Self.gregorian(utc).date(byAdding: .day, value: span, to: start(in: utc)) else { return self }
        return Self(date: date, timeZone: utc)
    }

    /// Whole days from this day to `other`; negative when `other` is earlier.
    func days(until other: Self) -> Int {
        let utc = TimeZone(identifier: "UTC")!
        return Self.gregorian(utc).dateComponents([.day], from: start(in: utc), to: other.start(in: utc)).day!
    }

    var description: String { String(format: "%04d-%02d-%02d", year, month, day) }

    static func < (lhs: Self, rhs: Self) -> Bool { (lhs.year, lhs.month, lhs.day) < (rhs.year, rhs.month, rhs.day) }

    static func gregorian(_ timeZone: TimeZone) -> Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        return calendar
    }
}

/// What the traveller told the trip home about this trip. Kept only on this device, in the account's folder.
/// The passport nationality is not here: it is the setting Local Support and Arrival Mode already share.
struct LioTripProfile: Codable, Equatable, Sendable {
    static let maximumStayDays = 180

    /// The day the traveller lands in China; nil while the dates are not set.
    var arrival: LioTripDay?
    /// Calendar days in China, arrival and departure included; nil when not known.
    var stayDays: Int?
    /// The first city, as a metro catalogue id (`LioMetroCity.id`); nil when not chosen.
    var cityID: String?
    /// The saved plan (#1453) this trip follows, when the traveller picked one.
    var planID: String?
    /// Whether the traveller flies on to a third country; the transit visa-free rules depend on it.
    var onwardToThirdCountry: Bool?
    let startedAt: Date

    init(arrival: LioTripDay?, stayDays: Int?, cityID: String?, planID: String? = nil,
         onwardToThirdCountry: Bool? = nil, startedAt: Date) {
        self.arrival = arrival
        self.stayDays = stayDays.map { min(max($0, 1), Self.maximumStayDays) }
        self.cityID = cityID.flatMap { $0.isEmpty || $0.utf8.count > 64 ? nil : $0 }
        self.planID = planID.flatMap { $0.isEmpty || $0.utf8.count > 256 ? nil : $0 }
        self.onwardToThirdCountry = onwardToThirdCountry
        self.startedAt = startedAt
    }

    private enum CodingKeys: String, CodingKey {
        case arrival, stayDays, cityID, planID, onwardToThirdCountry, startedAt
    }

    /// The file is read back through the same limits as a new profile.
    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(arrival: try container.decodeIfPresent(LioTripDay.self, forKey: .arrival),
                  stayDays: try container.decodeIfPresent(Int.self, forKey: .stayDays),
                  cityID: try container.decodeIfPresent(String.self, forKey: .cityID),
                  planID: try container.decodeIfPresent(String.self, forKey: .planID),
                  onwardToThirdCountry: try container.decodeIfPresent(Bool.self, forKey: .onwardToThirdCountry),
                  startedAt: try container.decode(Date.self, forKey: .startedAt))
    }

    /// The day the traveller leaves China, when both the arrival and the length are known.
    var lastDay: LioTripDay? {
        guard let arrival, let stayDays else { return nil }
        return arrival.adding(days: max(stayDays, 1) - 1)
    }
}

/// The ticks a traveller made by hand, by task key. A task's wording follows its rule; only the key is kept,
/// so regenerating the list never loses a tick, and a tick whose task no longer exists is simply unused.
struct LioTripTicks: Codable, Equatable, Sendable {
    static let maximumCount = 300
    static let maximumKeyLength = 160

    private(set) var done: [String: Date] = [:]

    init(done: [String: Date] = [:]) {
        let valid = done.filter { !$0.key.isEmpty && $0.key.utf8.count <= Self.maximumKeyLength }
        self.done = valid.count <= Self.maximumCount ? valid
            : Dictionary(uniqueKeysWithValues: valid.sorted { $0.value > $1.value }.prefix(Self.maximumCount).map { ($0.key, $0.value) })
    }

    private enum CodingKeys: String, CodingKey { case done }

    /// The file is read back through the same limits as new ticks.
    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(done: try container.decode([String: Date].self, forKey: .done))
    }

    func isDone(_ key: String) -> Bool { done[key] != nil }

    /// Ticks or unticks a task; the oldest ticks are dropped beyond the cap.
    mutating func set(_ key: String, done value: Bool, at date: Date) {
        guard key.utf8.count <= Self.maximumKeyLength else { return }
        if value { done[key] = date } else { done[key] = nil }
        if done.count > Self.maximumCount {
            let keep = done.sorted { $0.value > $1.value }.prefix(Self.maximumCount)
            done = Dictionary(uniqueKeysWithValues: keep.map { ($0.key, $0.value) })
        }
    }
}

/// The trip home's file in the signed-in account's message folder. Account cleanup removes it
/// (`LioTripHomeCleanup`); another account can neither read nor write it.
@MainActor public struct LioTripHomeStore {
    public static let directoryName = "trip-home"
    public static let fileName = "trip-home.json"

    public static func storageDirectory(inMessageDirectory directory: URL) -> URL {
        directory.appendingPathComponent(directoryName, isDirectory: true)
    }

    struct Snapshot: Codable, Equatable, Sendable {
        var profile: LioTripProfile?
        var ticks = LioTripTicks()
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

    private struct Archive: Codable {
        let version: Int
        let snapshot: Snapshot?
    }

    /// A damaged or newer file reads as an empty trip home, so the traveller can start again.
    func load() throws -> Snapshot {
        guard isCurrent() else { throw CancellationError() }
        let data: Data
        do {
            data = try Data(contentsOf: file)
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return Snapshot()
        }
        guard let archive = try? JSONDecoder().decode(Archive.self, from: data), archive.version == 1 else { return Snapshot() }
        return archive.snapshot ?? Snapshot()
    }

    func save(_ snapshot: Snapshot) throws {
        guard isCurrent() else { throw CancellationError() }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var storedDirectory = directory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try storedDirectory.setResourceValues(attributes)
        let data = try JSONEncoder().encode(Archive(version: 1, snapshot: snapshot))
        #if os(iOS)
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file, options: .atomic)
        #endif
    }

    func clear() throws {
        guard isCurrent() else { throw CancellationError() }
        do {
            try FileManager.default.removeItem(at: file)
        } catch let error as CocoaError where error.code == .fileNoSuchFile {
            return
        }
    }
}

/// The trip home's profile and ticks for the current account. Nothing shows once the account is no longer
/// current; a failed write keeps what was shown before and says so, and nothing is reported as saved.
@MainActor @Observable
final class LioTripHomeModel {
    private let store: LioTripHomeStore?
    private var cached: LioTripHomeStore.Snapshot
    /// Set when the last save did not reach the device; cleared by the next successful one.
    private(set) var saveFailed = false

    init(store: LioTripHomeStore?, initial: LioTripHomeStore.Snapshot = .init()) {
        self.store = store
        cached = (try? store?.load()) ?? initial
    }

    var storeID: UUID? { store?.id }
    /// Without a store (no account folder) the trip home still works for this session but keeps nothing.
    var persists: Bool { store?.current == true }
    private var visible: Bool { store == nil || store?.current == true }

    var profile: LioTripProfile? { visible ? cached.profile : nil }
    var ticks: LioTripTicks { visible ? cached.ticks : LioTripTicks() }

    func reload() {
        guard let store, store.current, let snapshot = try? store.load() else { return }
        cached = snapshot
    }

    func start(_ profile: LioTripProfile) {
        // A new trip starts with no ticks: a tick belongs to the trip it was made for.
        write(.init(profile: profile, ticks: LioTripTicks()))
    }

    func update(_ change: (inout LioTripProfile) -> Void) {
        guard var profile = cached.profile else { return }
        change(&profile)
        write(.init(profile: profile, ticks: cached.ticks))
    }

    func setTick(_ key: String, done: Bool, at date: Date = .now) {
        var ticks = cached.ticks
        ticks.set(key, done: done, at: date)
        write(.init(profile: cached.profile, ticks: ticks))
    }

    /// Ends this trip on the phone: the profile and ticks go; saved plans and tool data stay where they are.
    func clear() {
        guard visible else { return }
        if let store {
            do {
                try store.clear()
            } catch {
                saveFailed = true
                return
            }
        }
        saveFailed = false
        cached = .init()
    }

    private func write(_ snapshot: LioTripHomeStore.Snapshot) {
        guard visible else { return }
        if let store {
            do {
                try store.save(snapshot)
            } catch {
                saveFailed = true
                return
            }
        }
        saveFailed = false
        cached = snapshot
    }
}

/// `G2CTripHomeEnabled` in the build's Info.plist; off unless it says YES. JT decides which build turns it on.
enum LioTripHomeFeature {
    static let infoKey = "G2CTripHomeEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool { enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) }
}
