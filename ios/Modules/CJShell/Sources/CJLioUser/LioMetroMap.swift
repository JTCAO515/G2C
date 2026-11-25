import Foundation

/// Interactive metro map (#1450 item 2). Lines, station order, interchanges and the Chinese and
/// English station names come from each operator's own published data; the file records where and
/// when they were checked. Positions are schematic (drawn by station order), never geographic.
struct LioMetroMap: Equatable, Sendable {
    struct Source: Equatable, Sendable {
        let operatorZH: String
        let operatorEN: String
        let urls: [URL]
        /// `yyyy-MM-dd`, the day the data was last compared with the operator's site.
        let checkedOn: String

        func name(in language: LioLanguage) -> String { language.text(operatorEN, operatorZH) }
    }

    struct Line: Equatable, Identifiable, Sendable {
        let id: String
        let nameZH: String
        let nameEN: String
        /// `#RRGGBB`, the operator's own line colour.
        let color: String
        /// A loop line runs from its last station back to its first.
        let loop: Bool
        /// Station IDs in running order; a branch is its own segment sharing the junction station.
        let segments: [[String]]

        func name(in language: LioLanguage) -> String { language.text(nameEN, nameZH) }

        /// Neighbouring station pairs, including the closing pair of a loop.
        var edges: [(String, String)] {
            segments.flatMap { segment in
                let ids = loop && segments.count == 1 ? segment + [segment[0]] : segment
                return Array(zip(ids, ids.dropFirst()))
            }
        }

        var rgb: (red: Double, green: Double, blue: Double) {
            let value = Int(color.dropFirst(), radix: 16) ?? 0
            return (Double((value >> 16) & 0xFF) / 255, Double((value >> 8) & 0xFF) / 255, Double(value & 0xFF) / 255)
        }
    }

    struct Station: Equatable, Identifiable, Hashable, Sendable {
        let id: String
        let nameZH: String
        let nameEN: String
        /// Schematic position in map units, inside the map's canvas.
        let x: Double
        let y: Double
        /// Every line that stops here, in the order the file lists the lines.
        let lines: [String]

        var isInterchange: Bool { lines.count > 1 }

        func name(in language: LioLanguage) -> String { language.text(nameEN, nameZH) }
    }

    let city: LioMetroCity
    let source: Source
    let width: Double
    let height: Double
    let lines: [Line]
    let stations: [Station]
    private let stationIndex: [String: Int]
    private let lineIndex: [String: Int]

    func station(_ id: String) -> Station? { stationIndex[id].map { stations[$0] } }
    func line(_ id: String) -> Line? { lineIndex[id].map { lines[$0] } }
    func lines(at station: Station) -> [Line] { station.lines.compactMap(line) }

    /// The station closest to a point in map units, if one lies within `radius`.
    func station(nearX x: Double, y: Double, radius: Double) -> Station? {
        var best: (Station, Double)?
        for station in stations {
            let distance = hypot(station.x - x, station.y - y)
            if distance <= radius, distance < (best?.1 ?? .infinity) { best = (station, distance) }
        }
        return best?.0
    }

    /// Stations whose Chinese or English name contains the query, interchanges first.
    func stations(matching query: String) -> [Station] {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let found = text.isEmpty ? stations : stations.filter {
            $0.nameZH.localizedStandardContains(text) || $0.nameEN.localizedStandardContains(text)
        }
        return found.sorted { ($0.isInterchange ? 0 : 1, $0.nameEN) < ($1.isInterchange ? 0 : 1, $1.nameEN) }
    }

    /// What a traveller types into a map or taxi app to find this station.
    func searchName(for station: Station) -> String { station.nameZH + "地铁站" }
}

enum LioMetroMapFailure: Error, Equatable {
    case missing
    case unreadable
    case invalid(String)
}

extension LioMetroMap {
    static let schema = "lio.metro.v1"

    static func bundled(_ city: LioMetroCity) throws -> LioMetroMap {
        guard let name = city.mapResource,
              let url = Bundle.module.url(forResource: name, withExtension: "json") else { throw LioMetroMapFailure.missing }
        return try read(Data(contentsOf: url), city: city)
    }

    private struct File: Decodable {
        struct Source: Decodable { let operatorZH, operatorEN: String; let urls: [String]; let checkedOn: String }
        struct Canvas: Decodable { let width, height: Double }
        struct Line: Decodable {
            let id, nameZH, nameEN, color: String
            let loop: Bool
            let segments: [[String]]
        }
        struct Station: Decodable {
            let id, nameZH, nameEN: String
            let x, y: Double
            let lines: [String]
        }
        let schema: String
        let city: String
        let source: Source
        let canvas: Canvas
        let lines: [Line]
        let stations: [Station]
    }

    /// Decodes and checks a map file: every line has stations, names exist in both languages,
    /// colours are valid, and a station's lines agree with the lines that list it.
    static func read(_ data: Data, city: LioMetroCity) throws -> LioMetroMap {
        guard let file = try? JSONDecoder().decode(File.self, from: data) else { throw LioMetroMapFailure.unreadable }
        guard file.schema == schema else { throw LioMetroMapFailure.invalid("schema") }
        guard file.city == city.rawValue else { throw LioMetroMapFailure.invalid("city") }
        let urls = file.source.urls.compactMap(URL.init(string:))
        guard !file.source.operatorZH.isEmpty, !file.source.operatorEN.isEmpty, !urls.isEmpty,
              urls.count == file.source.urls.count, urls.allSatisfy({ $0.scheme == "https" && $0.host != nil }),
              isDay(file.source.checkedOn) else { throw LioMetroMapFailure.invalid("source") }
        guard file.canvas.width > 0, file.canvas.height > 0, !file.lines.isEmpty, !file.stations.isEmpty else {
            throw LioMetroMapFailure.invalid("empty")
        }
        let stationIDs = file.stations.map(\.id), lineIDs = file.lines.map(\.id)
        guard Set(stationIDs).count == stationIDs.count else { throw LioMetroMapFailure.invalid("duplicate station") }
        guard Set(lineIDs).count == lineIDs.count else { throw LioMetroMapFailure.invalid("duplicate line") }
        let known = Set(stationIDs)
        var listed: [String: [String]] = [:]
        for line in file.lines {
            guard !line.nameZH.isEmpty, !line.nameEN.isEmpty, isColor(line.color), !line.segments.isEmpty,
                  line.segments.allSatisfy({ $0.count >= 2 && $0.allSatisfy(known.contains) }) else {
                throw LioMetroMapFailure.invalid("line \(line.id)")
            }
            for id in Set(line.segments.joined()) { listed[id, default: []].append(line.id) }
        }
        for station in file.stations {
            guard !station.nameZH.trimmingCharacters(in: .whitespaces).isEmpty,
                  !station.nameEN.trimmingCharacters(in: .whitespaces).isEmpty,
                  (0...file.canvas.width).contains(station.x), (0...file.canvas.height).contains(station.y) else {
                throw LioMetroMapFailure.invalid("station \(station.id)")
            }
            guard station.lines == (listed[station.id] ?? []) else {
                throw LioMetroMapFailure.invalid("station lines \(station.id)")
            }
        }
        let names = file.stations.map(\.nameZH)
        guard Set(names).count == names.count else { throw LioMetroMapFailure.invalid("duplicate name") }

        let stations = file.stations.map {
            Station(id: $0.id, nameZH: $0.nameZH, nameEN: $0.nameEN, x: $0.x, y: $0.y, lines: $0.lines)
        }
        let lines = file.lines.map {
            Line(id: $0.id, nameZH: $0.nameZH, nameEN: $0.nameEN, color: $0.color, loop: $0.loop, segments: $0.segments)
        }
        return LioMetroMap(
            city: city,
            source: .init(operatorZH: file.source.operatorZH, operatorEN: file.source.operatorEN, urls: urls,
                          checkedOn: file.source.checkedOn),
            width: file.canvas.width, height: file.canvas.height, lines: lines, stations: stations,
            stationIndex: Dictionary(uniqueKeysWithValues: stations.enumerated().map { ($1.id, $0) }),
            lineIndex: Dictionary(uniqueKeysWithValues: lines.enumerated().map { ($1.id, $0) })
        )
    }

    static func isColor(_ value: String) -> Bool {
        value.count == 7 && value.first == "#" && value.dropFirst().allSatisfy(\.isHexDigit)
    }

    private static func isDay(_ value: String) -> Bool { day(value) != nil }

    private static func day(_ value: String) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "Asia/Shanghai")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: value)
    }

    /// "Source: Beijing Subway official site, checked 24 Nov 2026" in the reader's language.
    func sourceLine(in language: LioLanguage) -> String {
        let parts = source.checkedOn.split(separator: "-").compactMap { Int($0) }
        let checked: String
        if parts.count == 3 {
            let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            checked = language.text("\(parts[2]) \(months[parts[1] - 1]) \(parts[0])", "\(parts[0])年\(parts[1])月\(parts[2])日")
        } else {
            checked = source.checkedOn
        }
        return language.text(
            "Lines and stations: \(source.operatorEN) official website, checked \(checked). Schematic, not to scale.",
            "线路与站点：\(source.operatorZH)官网，核对于\(checked)。示意图，不按比例。"
        )
    }
}

/// What the station sheet does with a station: pick the taxi destination and build map links.
enum LioMetroStationAction {
    /// Prefer a result named after the station; otherwise the search's own first answer.
    static func bestPlace(_ places: [LioTaxiPlace], for station: LioMetroMap.Station) -> LioTaxiPlace? {
        places.first { $0.nameZH.contains(station.nameZH) && $0.nameZH.contains("站") }
            ?? places.first { $0.nameZH.contains(station.nameZH) }
            ?? places.first
    }

    /// AMap searches by name (no coordinates are bundled); Apple Maps is the fallback.
    static func directionURLs(cityZH: String, name: String) -> [URL] {
        var amap = URLComponents(string: "iosamap://poi")!
        amap.queryItems = [.init(name: "sourceApplication", value: "Go2China"), .init(name: "name", value: cityZH + name),
                           .init(name: "dev", value: "0")]
        var apple = URLComponents(string: "https://maps.apple.com/")!
        apple.queryItems = [.init(name: "q", value: cityZH + name)]
        return [amap.url, apple.url].compactMap { $0 }
    }
}

/// Zoom and pan of the map on screen (#1450). The view commits a viewport only when a gesture
/// ends or a zoom button is pressed; a live pinch or drag is drawn on top of it, so a gesture the
/// system cancels simply disappears instead of leaving stale state for the next one.
struct LioMetroViewport: Equatable {
    static let maximumZoom: CGFloat = 12

    var zoom: CGFloat = 1
    /// Offset of the map's centre from the view's centre, in points.
    var pan: CGSize = .zero

    /// Zoom by `magnification` about `anchor` (an offset from the view's centre), keeping the
    /// point under the fingers where it is. Zoom stays between the whole map and `maximumZoom`.
    func pinched(by magnification: CGFloat, about anchor: CGPoint) -> Self {
        let newZoom = min(max(zoom * magnification, 1), Self.maximumZoom)
        let ratio = newZoom / zoom
        return Self(zoom: newZoom, pan: CGSize(width: anchor.x - (anchor.x - pan.width) * ratio,
                                               height: anchor.y - (anchor.y - pan.height) * ratio))
    }

    func dragged(by translation: CGSize) -> Self {
        Self(zoom: zoom, pan: CGSize(width: pan.width + translation.width, height: pan.height + translation.height))
    }

    /// What is on screen while gestures are live: the drag first, then the pinch about its anchor.
    func showing(magnification: CGFloat?, anchor: CGPoint, drag: CGSize) -> Self {
        let moved = dragged(by: drag)
        return magnification.map { moved.pinched(by: $0, about: anchor) } ?? moved
    }

    /// The viewport to keep when a pinch ends while a drag may still be live, chosen so the
    /// picture does not move: drawing it with that drag gives what was just on screen.
    func endingPinch(by magnification: CGFloat, about anchor: CGPoint, liveDrag: CGSize) -> Self {
        let shown = showing(magnification: magnification, anchor: anchor, drag: liveDrag)
        return shown.dragged(by: CGSize(width: -liveDrag.width, height: -liveDrag.height))
    }

    /// Keep at least a quarter of the view covered by the map. `content` is the map's size in
    /// points at zoom 1 (fitted to the view).
    func clamped(content: CGSize, view: CGSize) -> Self {
        let limitX = max(0, (content.width * zoom - view.width) / 2) + view.width * 0.25
        let limitY = max(0, (content.height * zoom - view.height) / 2) + view.height * 0.25
        return Self(zoom: zoom, pan: CGSize(width: min(max(pan.width, -limitX), limitX),
                                            height: min(max(pan.height, -limitY), limitY)))
    }
}
