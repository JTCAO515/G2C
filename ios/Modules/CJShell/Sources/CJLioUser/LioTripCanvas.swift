import Foundation

/// #1995 (T-2): the trip canvas, local data version. One China trip is city segments, each of days, each of points
/// (a sight, a meal, a hotel, or a stretch of travel), plus the "want to go" inbox of places not yet placed on a day.
/// It is made from a saved plan (#1453 / #1723) and every change is written back on this phone only; nothing
/// here calls the server.
///
/// Every point says who put it there (`origin`): `lio` for what Lio drafted, `user` for what the traveller added,
/// moved or edited. Touching a point once makes it `user` for good. That is the rule the server's automatic writes
/// will rely on later: Lio may add points, but never change or delete one that is `user`.
struct LioTripCanvas: Equatable, Codable, Sendable {
    static let maximumDays = 120
    static let maximumPoints = 600
    static let maximumWishlist = 100
    static let maximumNameLength = 120
    static let maximumTimeLength = 40

    enum Origin: String, Codable, Sendable { case lio, user }
    enum Mode: String, Codable, Sendable { case walking, transit, taxi }

    /// GCJ-02, as the saved plan's checked places carry it.
    struct Coordinate: Equatable, Codable, Sendable {
        let latitude: Double
        let longitude: Double

        var isValid: Bool {
            latitude.isFinite && longitude.isFinite && (-90...90).contains(latitude) && (-180...180).contains(longitude)
        }
    }

    struct Point: Identifiable, Equatable, Codable, Sendable {
        let id: String
        /// The id of the place in the places library; nil while the place is only a name (most are, for now).
        var placeID: String?
        var nameZH: String
        var nameEN: String
        var address: String?
        var coordinate: Coordinate?
        /// The time slot as the plan wrote it ("09:30", "afternoon"); nil when none.
        var time: String?
        var kind: LioRichItinerary.Kind
        var origin: Origin

        func name(_ language: LioLanguage) -> String {
            let text = language == .chinese ? nameZH : nameEN
            return text.isEmpty ? (nameZH.isEmpty ? nameEN : nameZH) : text
        }
    }

    /// How to get from one point to the one after it. Kept by the pair of points, so a leg comes back if the two
    /// points are put next to each other again, and shows nothing for a pair nobody has planned a way between.
    struct Leg: Equatable, Codable, Sendable {
        let fromID: String
        let toID: String
        let mode: Mode
        let seconds: Double
        let metres: Double

        func description(_ language: LioLanguage) -> String {
            let name: String
            switch mode {
            case .walking: name = language.text("Walk", "步行")
            case .transit: name = language.text("Public transport", "公共交通")
            case .taxi: name = language.text("Taxi", "出租车")
            }
            let minutes = Int(ceil(seconds / 60))
            let kilometres = (metres / 1000).formatted(.number.precision(.fractionLength(0...1)))
            return language.text("\(name) · about \(minutes) min · \(kilometres) km",
                                 "\(name) · 约 \(minutes) 分钟 · \(kilometres) 公里")
        }

        var symbol: String {
            switch mode { case .walking: "figure.walk"; case .transit: "tram"; case .taxi: "car" }
        }
    }

    struct Day: Identifiable, Equatable, Codable, Sendable {
        let id: String
        var date: String?
        var theme: String
        var area: String
        var points: [Point]
    }

    struct Segment: Identifiable, Equatable, Codable, Sendable {
        let id: String
        /// The city's name when the trip has more than one; nil for a trip that stays in one place.
        var name: String?
        var days: [Day]
    }

    /// Where a point is: on a day (by position in its segment) or in the inbox.
    enum Location: Equatable {
        case day(segment: Int, day: Int, index: Int)
        case wishlist(index: Int)
    }

    let tripID: String
    var title: String
    var startDate: String?
    var undated: Bool
    var source: LioPlanSummary.Source
    /// The saved plan's version this canvas was made from.
    var sourceVersion: Int64
    var segments: [Segment]
    /// "Want to go": places kept but not on any day.
    var wishlist: [Point]
    var legs: [Leg]

    // MARK: - Making one

    /// An empty canvas, for a traveller with no saved plan yet; the inbox and "add a day" still work.
    init(emptyTripID tripID: String = LioTripCanvas.standaloneID, title: String = "") {
        self.tripID = tripID; self.title = title; startDate = nil; undated = true; source = .chat; sourceVersion = 0
        segments = [Segment(id: "segment-1", name: nil, days: [])]
        wishlist = []; legs = []
    }

    static let standaloneID = "local"

    /// The canvas of a saved plan. A chat plan is Lio's draft (`lio`); a popular route the traveller took as their own
    /// trip is theirs (`user`), so an automatic write never rewrites it. Places keep their names, and the checked ones
    /// their address and point; the way between two stops is kept where the plan had an estimate.
    init(plan: LioPlanSummary) {
        let itinerary = plan.itinerary
        let origin: Origin = plan.source == .chat ? .lio : .user
        var usedPoints = Set<String>()
        var usedDays = Set<String>()
        var total = 0
        var legs: [Leg] = []
        var days: [Day] = []
        for day in itinerary.days.prefix(Self.maximumDays) {
            var ids: [String: String] = [:]
            var points: [Point] = []
            for stop in day.stops where total < Self.maximumPoints {
                var id = stop.id.isEmpty ? "point" : String(stop.id.prefix(Self.maximumNameLength))
                var suffix = 1
                while !usedPoints.insert(id).inserted { suffix += 1; id = "\(stop.id)#\(suffix)" }
                ids[stop.id] = id
                total += 1
                let place = stop.place
                let point = place.mapPoint.map { Coordinate(latitude: $0.latitude, longitude: $0.longitude) }
                points.append(Point(id: id, placeID: nil, nameZH: Self.clip(place.nameZH), nameEN: Self.clip(place.nameEN),
                                    address: place.driverAddress.map(Self.clip), coordinate: point?.isValid == true ? point : nil,
                                    time: stop.time.map { String($0.prefix(Self.maximumTimeLength)) }, kind: stop.kind, origin: origin))
            }
            for leg in day.legs {
                guard let estimate = leg.estimate, estimate.seconds.isFinite, estimate.metres.isFinite,
                      let from = ids[leg.fromID], let to = ids[leg.toID] else { continue }
                let mode: Mode
                switch estimate.mode { case .walking: mode = .walking; case .transit: mode = .transit; case .taxi: mode = .taxi }
                legs.append(Leg(fromID: from, toID: to, mode: mode, seconds: estimate.seconds, metres: estimate.metres))
            }
            var dayID = "day-\(day.number)"
            var suffix = 1
            while !usedDays.insert(dayID).inserted { suffix += 1; dayID = "day-\(day.number)#\(suffix)" }
            days.append(Day(id: dayID, date: day.date, theme: day.theme, area: day.area, points: points))
        }
        tripID = plan.tripID; title = itinerary.title; startDate = plan.startDate; undated = itinerary.undated
        source = plan.source; sourceVersion = plan.tripVersion
        segments = [Segment(id: "segment-1", name: nil, days: days)]
        wishlist = []; self.legs = legs
    }

    private static func clip(_ text: String) -> String { String(text.prefix(maximumNameLength)) }

    // MARK: - Reading

    var days: [Day] { segments.flatMap(\.days) }
    var pointCount: Int { days.reduce(wishlist.count) { $0 + $1.points.count } }
    var isEmpty: Bool { pointCount == 0 }
    /// The traveller has changed or added something here, so a newer copy of the plan must not replace it.
    var hasUserEdits: Bool { !wishlist.isEmpty || days.contains { $0.points.contains { $0.origin == .user } } }

    /// "Day N" counts across the whole trip, whatever the segment.
    func dayNumber(_ dayID: String) -> Int? { days.firstIndex { $0.id == dayID }.map { $0 + 1 } }

    func point(_ id: String) -> Point? {
        switch locate(id) {
        case .day(let s, let d, let i)?: segments[s].days[d].points[i]
        case .wishlist(let i)?: wishlist[i]
        case nil: nil
        }
    }

    func locate(_ id: String) -> Location? {
        for (s, segment) in segments.enumerated() {
            for (d, day) in segment.days.enumerated() {
                if let i = day.points.firstIndex(where: { $0.id == id }) { return .day(segment: s, day: d, index: i) }
            }
        }
        return wishlist.firstIndex { $0.id == id }.map { .wishlist(index: $0) }
    }

    func leg(from: String, to: String) -> Leg? { legs.first { $0.fromID == from && $0.toID == to } }

    /// The way from the point at `index` of the day to the next one, when the plan has it.
    func leg(after index: Int, in day: Day) -> Leg? {
        guard index + 1 < day.points.count else { return nil }
        return leg(from: day.points[index].id, to: day.points[index + 1].id)
    }

    private func dayPosition(_ dayID: String) -> (segment: Int, day: Int)? {
        for (s, segment) in segments.enumerated() {
            if let d = segment.days.firstIndex(where: { $0.id == dayID }) { return (s, d) }
        }
        return nil
    }

    // MARK: - Changing

    /// Moves a point to a day, so it ends up at `index` of that day's list (clamped; the list counted without the
    /// point). A point moved from the inbox or another day is the traveller's from then on. Nothing happens, and
    /// nothing is marked, when the point is already there.
    @discardableResult
    mutating func move(_ id: String, toDay dayID: String, at index: Int) -> Bool {
        guard let from = locate(id), let target = dayPosition(dayID) else { return false }
        var length = segments[target.segment].days[target.day].points.count
        if case .day(let s, let d, _) = from, s == target.segment, d == target.day { length -= 1 }
        let at = min(max(index, 0), length)
        if case .day(let s, let d, let i) = from, s == target.segment, d == target.day, i == at { return false }
        var point = take(from)
        point.origin = .user
        segments[target.segment].days[target.day].points.insert(point, at: at)
        return true
    }

    /// Moves a point to the end of a day.
    @discardableResult
    mutating func moveToEnd(_ id: String, ofDay dayID: String) -> Bool {
        move(id, toDay: dayID, at: Int.max)
    }

    /// Moves a point into the "want to go" inbox (at `index`, or the end). It keeps no day and no way to its neighbours.
    @discardableResult
    mutating func moveToWishlist(_ id: String, at index: Int = Int.max) -> Bool {
        guard let from = locate(id) else { return false }
        var length = wishlist.count
        if case .wishlist = from { length -= 1 }
        let at = min(max(index, 0), length)
        if case .wishlist(let i) = from, i == at { return false }
        var point = take(from)
        point.origin = .user
        wishlist.insert(point, at: at)
        return true
    }

    /// A point dropped on another point takes that point's position, on its day or in the inbox.
    @discardableResult
    mutating func move(_ id: String, onto targetID: String) -> Bool {
        guard id != targetID, locate(id) != nil, let target = locate(targetID) else { return false }
        switch target {
        case .day(let s, let d, let i): return move(id, toDay: segments[s].days[d].id, at: i)
        case .wishlist(let i): return moveToWishlist(id, at: i)
        }
    }

    /// Up (`-1`) or down (`+1`) one place in its own day or in the inbox; false at either end.
    @discardableResult
    mutating func shift(_ id: String, by step: Int) -> Bool {
        switch locate(id) {
        case .day(let s, let d, let i)?:
            let to = i + step
            guard (0..<segments[s].days[d].points.count).contains(to) else { return false }
            return move(id, toDay: segments[s].days[d].id, at: to)
        case .wishlist(let i)?:
            guard (0..<wishlist.count).contains(i + step) else { return false }
            return moveToWishlist(id, at: i + step)
        case nil:
            return false
        }
    }

    /// Takes a point off the canvas, with the ways that led to or from it.
    @discardableResult
    mutating func remove(_ id: String) -> Point? {
        guard let from = locate(id) else { return nil }
        let point = take(from)
        legs.removeAll { $0.fromID == id || $0.toID == id }
        return point
    }

    /// Puts a place the traveller named into "want to go". False when the inbox or the canvas is full or the name is blank.
    @discardableResult
    mutating func addWish(id: String, name: String, nameEN: String? = nil, placeID: String? = nil,
                          coordinate: Coordinate? = nil) -> Bool {
        let zh = Self.clip(name.trimmingCharacters(in: .whitespacesAndNewlines))
        guard !zh.isEmpty, wishlist.count < Self.maximumWishlist, pointCount < Self.maximumPoints, locate(id) == nil else { return false }
        let en = nameEN.map { Self.clip($0.trimmingCharacters(in: .whitespacesAndNewlines)) }.flatMap { $0.isEmpty ? nil : $0 } ?? zh
        wishlist.append(Point(id: id, placeID: placeID, nameZH: zh, nameEN: en, address: nil,
                              coordinate: coordinate?.isValid == true ? coordinate : nil, time: nil, kind: .unspecified, origin: .user))
        return true
    }

    /// Changes a point's name or time. The name is the one shown in `language`; the other language's name is kept,
    /// unless it was only a copy of the old one (a chat plan has one name for both), when both follow. A point edited
    /// at all is the traveller's, even when only the time changed.
    @discardableResult
    mutating func edit(_ id: String, name: String? = nil, in language: LioLanguage = .chinese, time: String?? = nil) -> Bool {
        guard let at = locate(id), let original = self.point(id) else { return false }
        var point = original
        if let name {
            let clean = Self.clip(name.trimmingCharacters(in: .whitespacesAndNewlines))
            guard !clean.isEmpty else { return false }
            let shared = point.nameZH == point.nameEN
            if language == .chinese || shared { point.nameZH = clean }
            if language == .english || shared { point.nameEN = clean }
        }
        if let time {
            let clean = time.map { String($0.trimmingCharacters(in: .whitespacesAndNewlines).prefix(Self.maximumTimeLength)) }
            point.time = clean?.isEmpty == true ? nil : clean
        }
        guard point != original else { return false }
        point.origin = .user
        switch at {
        case .day(let s, let d, let i): segments[s].days[d].points[i] = point
        case .wishlist(let i): wishlist[i] = point
        }
        return true
    }

    /// A new, empty day at the end of the trip; its id, or nil at the cap.
    @discardableResult
    mutating func addDay() -> String? {
        guard days.count < Self.maximumDays else { return nil }
        if segments.isEmpty { segments = [Segment(id: "segment-1", name: nil, days: [])] }
        var number = days.count + 1
        let used = Set(days.map(\.id))
        while used.contains("day-\(number)") { number += 1 }
        let id = "day-\(number)"
        segments[segments.count - 1].days.append(Day(id: id, date: nil, theme: "", area: "", points: []))
        return id
    }

    private mutating func take(_ location: Location) -> Point {
        switch location {
        case .day(let s, let d, let i): segments[s].days[d].points.remove(at: i)
        case .wishlist(let i): wishlist.remove(at: i)
        }
    }

    // MARK: - Reading it back from a file

    /// Counts, ids and coordinates as a file might break them: such a canvas is dropped, not repaired.
    var isValid: Bool {
        guard !tripID.isEmpty, tripID.utf8.count <= 256, days.count <= Self.maximumDays, pointCount <= Self.maximumPoints,
              wishlist.count <= Self.maximumWishlist else { return false }
        let all = days.flatMap(\.points) + wishlist
        guard Set(all.map(\.id)).count == all.count, Set(days.map(\.id)).count == days.count else { return false }
        return all.allSatisfy { point in
            !point.id.isEmpty && point.id.utf8.count <= 512 && point.nameZH.count <= Self.maximumNameLength
                && point.nameEN.count <= Self.maximumNameLength && (point.time?.count ?? 0) <= Self.maximumTimeLength
                && (point.coordinate?.isValid ?? true)
        } && legs.allSatisfy { $0.seconds.isFinite && $0.metres.isFinite && $0.seconds >= 0 && $0.metres >= 0 }
    }

    /// The canvas to show: the saved one, unless the plan has a newer version and the traveller changed nothing here,
    /// in which case the newer plan is converted afresh. (Merging a newer Lio draft into a canvas the traveller has
    /// edited comes with the server's automatic write.)
    static func resolved(stored: LioTripCanvas?, plan: LioPlanSummary) -> LioTripCanvas {
        guard let stored, stored.tripID == plan.tripID else { return LioTripCanvas(plan: plan) }
        if plan.tripVersion > stored.sourceVersion, !stored.hasUserEdits { return LioTripCanvas(plan: plan) }
        return stored
    }
}

extension LioRichItinerary.Kind: Codable {}
