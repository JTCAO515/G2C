import Foundation

/// #1997: a popular route (a template roadbook) used as the traveller's trip becomes a trip canvas directly: city
/// segment, days, points. The points are the traveller's own (`origin == .user`): they chose the route, Lio did not
/// write it. Each place is looked up in the places library for its id; a place the library does not know keeps only its
/// name and its checked point. Behind `G2CTripCanvasEnabled`; with it off nothing here is called.
extension LioPlanSummary {
    /// "beijing" for `template:beijing-3d`: the library's city id, which is the first word of the route's id.
    var templateCityID: String? {
        guard source == .template, tripID.hasPrefix(Self.templatePrefix) else { return nil }
        let city = tripID.dropFirst(Self.templatePrefix.count).split(separator: "-").first.map(String.init)?.lowercased()
        return city?.isEmpty == false ? city : nil
    }
}

extension LioTripCanvas {
    /// The canvas of a popular route. Its id is the saved route's (`template:<route>`), so the canvas and the trip saved
    /// by "Use as my trip" are one trip.
    init(template roadbook: LioRoadbook, lookup: any LioPlaceLookup = LioPlaceLookups.standard) {
        let plan = LioPlanSummary(template: roadbook)
        self = LioTripCanvas(plan: plan).resolvingPlaces(with: lookup, city: plan.templateCityID)
    }

    /// Gives every point that has no library id the one the lookup finds for its name (Chinese name first, then English).
    /// A point that already has an id is left alone. The checked point the point came with stays; the library's point
    /// is used only for a place that had none. Nothing else about the point changes, `origin` included.
    func resolvingPlaces(with lookup: any LioPlaceLookup, city: String?) -> LioTripCanvas {
        var canvas = self
        func resolved(_ point: Point) -> Point {
            guard point.placeID == nil else { return point }
            let names = point.nameEN == point.nameZH ? [point.nameZH] : [point.nameZH, point.nameEN]
            for name in names where !name.isEmpty {
                guard let match = lookup.match(name: name, city: city), !match.placeID.isEmpty,
                      match.placeID.utf8.count <= Self.maximumPlaceIDBytes else { continue }
                var point = point
                point.placeID = match.placeID
                if point.coordinate == nil, let found = match.coordinate, found.isValid { point.coordinate = found }
                return point
            }
            return point
        }
        for s in canvas.segments.indices {
            for d in canvas.segments[s].days.indices {
                canvas.segments[s].days[d].points = canvas.segments[s].days[d].points.map(resolved)
            }
        }
        canvas.wishlist = canvas.wishlist.map(resolved)
        return canvas
    }

    static let maximumPlaceIDBytes = 128
}

extension LioTripCanvasStore {
    /// Makes the canvas of a popular route and keeps it on this phone. A second tap, or a route used again, gives back
    /// the canvas that is already there: nothing the traveller has changed is written over. Throws when the file cannot
    /// be read or written (a newer app's, or a phone that cannot open it).
    @discardableResult
    func useTemplate(_ roadbook: LioRoadbook, lookup: any LioPlaceLookup = LioPlaceLookups.standard) throws -> LioTripCanvas {
        let id = LioPlanSummary(template: roadbook).tripID
        if let existing = try canvas(for: id) { return existing }
        let made = LioTripCanvas(template: roadbook, lookup: lookup)
        try save(made)
        return made
    }
}

/// What the Roadbook pages need to turn "Use as my trip" into a canvas (only handed to them when the canvas switch is on).
struct LioTemplateCanvasUse {
    let store: LioTripCanvasStore
    var lookup: any LioPlaceLookup = LioPlaceLookups.standard
    /// Opens the canvas of the trip with this id.
    let open: @MainActor (String) -> Void
}
