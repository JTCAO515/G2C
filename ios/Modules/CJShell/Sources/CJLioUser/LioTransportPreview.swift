#if DEBUG
import Foundation

/// Debug-only sample timetable for `--lio-transport-preview` (#1519). Numbers, times and prices are made up
/// and the screen says so; real data comes from `TRANSPORT.1` once JT approves a source (#1518).
extension LioTransportService {
    static let preview = LioTransportService { route in
        try await Task.sleep(for: .milliseconds(400))
        let from = route.from
        let to = route.to
        let departureStation = sampleCoordinate(for: from.stations[0])
        let trains = [
            train("G\(sampleNumber(route, 2))", departureStation, to.stations[0], "08:00", "12:28", 268,
                  second: 62_600, first: 100_600),
            train("G\(sampleNumber(route, 14))", departureStation, to.stations[0], "10:00", "14:48", 288,
                  second: 59_300, first: 95_800),
            train("D\(sampleNumber(route, 312))", from.stations[from.stations.count - 1], to.stations[to.stations.count - 1],
                  "19:45", "07:36", 711, second: 30_900, first: nil),
        ]
        let flights = [
            flight("MU\(sampleNumber(route, 5101))", "东方航空", "China Eastern", from.airports[from.airports.count - 1],
                   to.airports[0], "07:30", "09:40", 130, economy: 78_000),
            flight("CA\(sampleNumber(route, 1858))", "中国国际航空", "Air China", from.airports[0],
                   to.airports[to.airports.count - 1], "13:05", "15:25", 140, economy: 96_000),
        ]
        return LioTransportResult(query: route, rail: .options(trains), flight: .options(flights), bus: .guideOnly,
                                  isSample: true)
    }

    private static func sampleNumber(_ route: LioTransportQuery, _ base: Int) -> Int {
        base + (route.from.id.count + route.to.id.count) % 7
    }

    /// Sample coordinates so the taxi hand-off can be tried in Debug; not used outside the preview.
    private static func sampleCoordinate(for hub: LioTransportHub) -> LioTransportHub {
        let known: [String: (Double, Double)] = [
            "上海虹桥站": (31.1947, 121.3203),
            "北京南站": (39.8653, 116.3783),
        ]
        guard let point = known[hub.nameZH] else { return hub }
        return hub.with(coordinate: .init(latitude: point.0, longitude: point.1, referenceSystem: .wgs84))
    }

    private static func train(_ number: String, _ departure: LioTransportHub, _ arrival: LioTransportHub,
                              _ depart: String, _ arrive: String, _ minutes: Int,
                              second: Int, first: Int?) -> LioTransportOption {
        var fares = [LioTransportFare(classZH: "二等座", classEN: "Second class", priceMinor: second)]
        if let first { fares.append(LioTransportFare(classZH: "一等座", classEN: "First class", priceMinor: first)) }
        return LioTransportOption(mode: .rail, number: number, carrierZH: nil, carrierEN: nil, departure: departure,
                                  arrival: arrival, departTime: depart, arriveTime: arrive, durationMinutes: minutes,
                                  fares: fares)
    }

    private static func flight(_ number: String, _ carrierZH: String, _ carrierEN: String,
                               _ departure: LioTransportHub, _ arrival: LioTransportHub,
                               _ depart: String, _ arrive: String, _ minutes: Int, economy: Int) -> LioTransportOption {
        LioTransportOption(mode: .flight, number: number, carrierZH: carrierZH, carrierEN: carrierEN,
                           departure: departure, arrival: arrival, departTime: depart, arriveTime: arrive,
                           durationMinutes: minutes,
                           fares: [LioTransportFare(classZH: "经济舱", classEN: "Economy", priceMinor: economy)])
    }
}
#endif
