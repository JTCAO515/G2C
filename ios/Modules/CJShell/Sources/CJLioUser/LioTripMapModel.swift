import Foundation

/// #1996 (T-3): the trip map's own, small input. It does not depend on the trip canvas model (#1995) or on
/// the saved-plans types: anything that can say "day, colour slot, numbered points, optional leg labels"
/// can be drawn. `LioTripMapInput(plan:language:)` (LioTripMapInput+Plan.swift) reads saved plans.
///
/// Coordinates are GCJ-02 (the AMap / 高德 system the place library and saved plans already use). They go to
/// the map layer exactly as given: no conversion anywhere in this file or in a layer. The default MapKit layer
/// can do that because Apple Maps' base map in mainland China is drawn in GCJ-02 too, so a GCJ-02 point lands
/// on the same street; that is JT's 2026-11-27 decision for background-only maps, and the real-device check on
/// six cities (#1996's L3 box) is what confirms the alignment. A layer for a map in another system has to do its
/// own conversion inside the layer, never in this model.
struct LioTripMapInput: Equatable, Sendable {
    struct Point: Equatable, Sendable {
        let id: String
        let name: String
        /// Nil, non-finite or out of range: the point has no position and is listed under the map instead.
        let latitude: Double?
        let longitude: Double?
        /// 1-based place in its day. It stays the same when other points of the day have no coordinates, so it
        /// matches the number the timeline shows.
        let number: Int

        init(id: String, name: String, latitude: Double?, longitude: Double?, number: Int) {
            self.id = id; self.name = name; self.latitude = latitude; self.longitude = longitude; self.number = number
        }

        var coordinate: LioTripMapCoordinate? {
            guard let latitude, let longitude else { return nil }
            return LioTripMapCoordinate(latitude: latitude, longitude: longitude)
        }
    }

    /// A label for the leg from one point to the next one of the day ("Metro 25 min").
    struct Segment: Equatable, Sendable {
        let fromID: String
        let toID: String
        let label: String?

        init(fromID: String, toID: String, label: String?) {
            self.fromID = fromID; self.toID = toID; self.label = label
        }
    }

    struct Day: Equatable, Sendable {
        /// The day's own number, as the trip shows it ("Day 2").
        let number: Int
        /// Which colour the day is drawn in; any integer, taken modulo `LioTripMapPalette.slotCount`.
        let colorSlot: Int
        let points: [Point]
        let segments: [Segment]

        init(number: Int, colorSlot: Int, points: [Point], segments: [Segment] = []) {
            self.number = number; self.colorSlot = colorSlot; self.points = points; self.segments = segments
        }
    }

    let days: [Day]

    init(days: [Day]) { self.days = days }

    var pointCount: Int { days.reduce(0) { $0 + $1.points.count } }
}

/// A validated GCJ-02 point: finite, latitude -90...90, longitude -180...180.
struct LioTripMapCoordinate: Equatable, Hashable, Sendable {
    let latitude: Double
    let longitude: Double

    init?(latitude: Double, longitude: Double) {
        guard latitude.isFinite, longitude.isFinite, (-90...90).contains(latitude), (-180...180).contains(longitude) else {
            return nil
        }
        self.latitude = latitude
        self.longitude = longitude
    }

    /// Two points closer than about ten centimetres are the same place (a hotel at both ends of a day).
    func isSamePlace(as other: LioTripMapCoordinate) -> Bool {
        abs(latitude - other.latitude) < 1e-6 && abs(longitude - other.longitude) < 1e-6
    }
}

/// The part of the map to show: a centre and spans in degrees.
struct LioTripMapRegion: Equatable, Sendable {
    let centerLatitude: Double
    let centerLongitude: Double
    let latitudeSpan: Double
    let longitudeSpan: Double

    /// About one kilometre: one point, or points on top of each other, still get a street-level view.
    static let minimumSpan = 0.01
    /// Room around the outermost points so markers are not cut off at the edge.
    static let padding = 1.4

    /// The smallest region holding every coordinate, padded. Nil for no coordinates. This is plain degrees and does
    /// not cross the antimeridian: trips in China never do.
    init?(covering coordinates: [LioTripMapCoordinate]) {
        guard let first = coordinates.first else { return nil }
        var minLat = first.latitude, maxLat = first.latitude, minLng = first.longitude, maxLng = first.longitude
        for point in coordinates {
            minLat = min(minLat, point.latitude); maxLat = max(maxLat, point.latitude)
            minLng = min(minLng, point.longitude); maxLng = max(maxLng, point.longitude)
        }
        centerLatitude = (minLat + maxLat) / 2
        centerLongitude = (minLng + maxLng) / 2
        latitudeSpan = min(max((maxLat - minLat) * Self.padding, Self.minimumSpan), 180)
        longitudeSpan = min(max((maxLng - minLng) * Self.padding, Self.minimumSpan), 360)
    }
}

/// What a map layer draws: the points that have a position, the lines between neighbours of the same day,
/// and, for the page around the map, the day legend and the points without a position.
struct LioTripMapScene: Equatable, Sendable {
    struct Pin: Equatable, Identifiable, Sendable {
        /// The caller's point id: what `onSelect` receives.
        let id: String
        /// Unique inside the scene even when a caller reuses an id (day index and number).
        let key: String
        let dayNumber: Int
        /// Already within `0..<LioTripMapPalette.slotCount`.
        let colorSlot: Int
        let number: Int
        let name: String
        let coordinate: LioTripMapCoordinate
        let accessibilityLabel: String
    }

    struct Line: Equatable, Identifiable, Sendable {
        var id: String { key }
        let key: String
        let dayNumber: Int
        let colorSlot: Int
        let from: LioTripMapCoordinate
        let to: LioTripMapCoordinate
        let label: String?

        var midpoint: LioTripMapCoordinate {
            LioTripMapCoordinate(latitude: (from.latitude + to.latitude) / 2,
                                 longitude: (from.longitude + to.longitude) / 2) ?? from
        }
    }

    struct Unplaced: Equatable, Identifiable, Sendable {
        var id: String { key }
        let pointID: String
        let key: String
        let dayNumber: Int
        let colorSlot: Int
        let number: Int
        let name: String
    }

    /// One entry per day that has at least one pin, in day order.
    struct Legend: Equatable, Identifiable, Sendable {
        var id: String { key }
        let key: String
        let dayNumber: Int
        let colorSlot: Int
        let pinCount: Int
    }

    let pins: [Pin]
    let lines: [Line]
    let unplaced: [Unplaced]
    let legend: [Legend]
    /// Nil when nothing can be drawn.
    let fit: LioTripMapRegion?

    var isEmpty: Bool { pins.isEmpty }
    var hasNoPoints: Bool { pins.isEmpty && unplaced.isEmpty }

    init(_ input: LioTripMapInput, language: LioLanguage) {
        var pins: [Pin] = [], lines: [Line] = [], unplaced: [Unplaced] = [], legend: [Legend] = []
        for (dayIndex, day) in input.days.enumerated() {
            let slot = LioTripMapPalette.normalized(day.colorSlot)
            var placed: [Pin] = []
            for point in day.points {
                let key = "\(dayIndex)-\(point.number)"
                if let coordinate = point.coordinate {
                    placed.append(Pin(id: point.id, key: key, dayNumber: day.number, colorSlot: slot, number: point.number,
                                      name: point.name, coordinate: coordinate,
                                      accessibilityLabel: language.text(
                                        "Day \(day.number), stop \(point.number): \(point.name)",
                                        "第 \(day.number) 天，第 \(point.number) 站：\(point.name)")))
                } else {
                    unplaced.append(Unplaced(pointID: point.id, key: key, dayNumber: day.number, colorSlot: slot,
                                             number: point.number, name: point.name))
                }
            }
            // A line joins neighbours among the points that are drawn; a skipped point with no position does not
            // break the route. Its leg label belongs to the unseen stretch, so a joined pair keeps a label only
            // when the day names exactly that pair.
            for (before, after) in zip(placed, placed.dropFirst()) where !before.coordinate.isSamePlace(as: after.coordinate) {
                let label = day.segments.first { $0.fromID == before.id && $0.toID == after.id }?.label
                lines.append(Line(key: "\(dayIndex)-\(before.number)-\(after.number)", dayNumber: day.number, colorSlot: slot,
                                  from: before.coordinate, to: after.coordinate,
                                  label: label.flatMap { $0.isEmpty ? nil : $0 }))
            }
            if !placed.isEmpty {
                legend.append(Legend(key: "\(dayIndex)", dayNumber: day.number, colorSlot: slot, pinCount: placed.count))
            }
            pins += placed
        }
        self.pins = pins
        self.lines = lines
        self.unplaced = unplaced
        self.legend = legend
        fit = LioTripMapRegion(covering: pins.map(\.coordinate))
    }
}
