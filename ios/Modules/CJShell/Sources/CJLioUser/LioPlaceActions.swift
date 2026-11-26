import Foundation

/// The buttons under a place in a trip (#1740): taxi, show the driver, directions and booking. Each one appears
/// only when it can work for that place; there are no greyed-out buttons. Taxi and booking open their tools through
/// `LioRouter` with a `LioRoute`, so the registry (#1724) decides whether the tool is there and what it reads.
///
/// - Taxi: only a checked place with a checked coordinate (`mapPoint`).
/// - Show the driver: any place with a name; an unchecked place's card says the address is not confirmed.
/// - Directions: the checked coordinate in a maps app; without one, a search for the checked address or the name,
///   except for free time and travel stops, which are not somewhere to navigate to.
/// - Booking: sights, and any place that matches a sight booking rule; the route carries the sight.
struct LioPlaceActions: Equatable, Sendable {
    enum Action: String, CaseIterable, Sendable {
        case taxi, driver, navigate, book
    }

    struct Navigation: Equatable, Sendable {
        let name: String
        /// The checked GCJ-02 coordinate, when there is one.
        let point: LioItinerary.Point?
        /// What is searched for when there is no coordinate: the checked address, else the name.
        let query: String

        /// Maps links in the order to try them.
        var urls: [URL] {
            if let point { return LioPlaceActions.directionURLs(latitude: point.latitude, longitude: point.longitude, name: name) }
            return LioMetroStationAction.directionURLs(cityZH: "", name: query)
        }
    }

    /// Request line on the driver card.
    static let driverRequestZH = "请送我到这里"

    let taxi: LioRoute?
    let driver: LioShowCardContent?
    let navigation: Navigation?
    let booking: LioRoute?

    /// The buttons to show, in order.
    var actions: [Action] {
        var actions: [Action] = []
        if taxi != nil { actions.append(.taxi) }
        if driver != nil { actions.append(.driver) }
        if navigation != nil { actions.append(.navigate) }
        if booking != nil { actions.append(.book) }
        return actions
    }

    /// `available` says whether a tool can be opened here (shown in this build and a router is present).
    init(stop: LioRichItinerary.Stop, available: (LioTool) -> Bool,
         entries: [LioToolEntry] = LioToolRegistry.entries) {
        let place = stop.place
        let nameZH = place.nameZH.trimmingCharacters(in: .whitespacesAndNewlines)
        let nameEN = place.nameEN.trimmingCharacters(in: .whitespacesAndNewlines)
        let address = place.driverAddress?.trimmingCharacters(in: .whitespacesAndNewlines)
        let checkedAddress = address?.isEmpty == false ? address : nil

        if let point = place.mapPoint, !nameZH.isEmpty, available(.taxi) {
            var parameters = ["destination": nameZH,
                              "lat": String(point.latitude), "lng": String(point.longitude)]
            if !nameEN.isEmpty, nameEN != nameZH { parameters["destinationEN"] = nameEN }
            if let checkedAddress { parameters["address"] = checkedAddress }
            taxi = LioRoute(tool: .taxi, parameters: parameters, entries: entries)
        } else {
            taxi = nil
        }

        if nameZH.isEmpty {
            driver = nil
        } else {
            var card = LioShowCardContent.driver(nameZH: nameZH, nameEN: nameEN.isEmpty ? nil : nameEN,
                                                 addressZH: checkedAddress, requestZH: Self.driverRequestZH)
            if !place.matched {
                card.noteZH = "地址未确认"
                card.noteEN = "Address not confirmed"
            }
            driver = card
        }

        if let point = place.mapPoint {
            navigation = Navigation(name: nameZH.isEmpty ? nameEN : nameZH, point: point, query: checkedAddress ?? nameZH)
        } else if stop.kind != .freeTime, stop.kind != .transport, let query = checkedAddress ?? (nameZH.isEmpty ? nil : nameZH) {
            navigation = Navigation(name: nameZH, point: nil, query: query)
        } else {
            navigation = nil
        }

        let rule = LioAttractionBookingRule.match(nameZH: nameZH, nameEN: nameEN)
        if (stop.kind == .sight || rule != nil), available(.attractionBooking), let sight = rule?.id ?? (nameZH.isEmpty ? nil : nameZH) {
            booking = LioRoute(tool: .attractionBooking, parameters: ["sight": sight], entries: entries)
        } else {
            booking = nil
        }
    }

    /// AMap first (GCJ-02 coordinates, `dev=0`), then Apple Maps; nothing is sent to our servers.
    static func directionURLs(latitude: Double, longitude: Double, name: String) -> [URL] {
        var amap = URLComponents(string: "iosamap://path")!
        amap.queryItems = [.init(name: "sourceApplication", value: "Go2China"), .init(name: "dlat", value: "\(latitude)"),
                           .init(name: "dlon", value: "\(longitude)"), .init(name: "dname", value: name),
                           .init(name: "dev", value: "0"), .init(name: "t", value: "0")]
        var apple = URLComponents(string: "https://maps.apple.com/")!
        apple.queryItems = [.init(name: "daddr", value: "\(latitude),\(longitude)"), .init(name: "q", value: name)]
        return [amap.url, apple.url].compactMap { $0 }
    }
}

extension LioTaxiPlace {
    /// Route parameters the taxi tool reads (#1740): the destination's Chinese name and GCJ-02 coordinate, with
    /// its English name and checked address when known.
    static let routeParameters: Set<String> = ["destination", "destinationEN", "address", "lat", "lng"]

    /// The destination a taxi route carries, or nil when it has no name or no usable coordinate. Routes can come
    /// from links, so the coordinate is checked here.
    init?(route: LioRoute) {
        guard let name = route["destination"], let latText = route["lat"], let lngText = route["lng"],
              let latitude = Double(latText), let longitude = Double(lngText),
              latitude.isFinite, longitude.isFinite, (-90...90).contains(latitude), (-180...180).contains(longitude)
        else { return nil }
        self.init(nameZH: name, nameEN: route["destinationEN"] ?? name, addressZH: route["address"],
                  coordinate: Coordinate(latitude: latitude, longitude: longitude, referenceSystem: .gcj02))
    }
}

extension LioAttractionBookingRule {
    /// The rule a booking route names (#1740): by rule id, else by a sight name; nil opens the list.
    static func rule(route: LioRoute) -> LioAttractionBookingRule? {
        guard let sight = route["sight"] else { return nil }
        return all.first { $0.id == sight } ?? match(nameZH: sight, nameEN: sight)
    }
}
