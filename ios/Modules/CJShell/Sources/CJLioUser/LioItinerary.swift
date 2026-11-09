import CJMessageHTTP
import CJTripClient
import Foundation

struct LioItinerary: Equatable, Identifiable, Sendable {
    struct Point: Equatable, Sendable {
        let latitude: Double
        let longitude: Double
    }

    struct Stop: Equatable, Identifiable, Sendable {
        let id: String
        let name: String
        let time: String?
        let point: Point?
        let fixed: Bool?
        let endTime: String?
        let endDate: String?

        init(id: String, name: String, time: String?, point: Point?, fixed: Bool?,
             endTime: String? = nil, endDate: String? = nil) {
            self.id = id
            self.name = name
            self.time = time
            self.point = point
            self.fixed = fixed
            self.endTime = endTime
            self.endDate = endDate
        }
    }

    struct Day: Equatable, Identifiable, Sendable {
        let number: Int
        let stops: [Stop]
        let date: String?
        let datePending: Bool
        var id: Int { number }

        init(number: Int, stops: [Stop], date: String? = nil, datePending: Bool = false) {
            self.number = number
            self.stops = stops
            self.date = date
            self.datePending = datePending
        }
    }

    let id: String
    let title: String
    let description: String?
    let days: [Day]
}

extension LioItinerary {
    init(_ saved: LioTimelineWire.SavedTrip) {
        self.init(id: saved.id, title: saved.title, description: nil,
                  days: saved.days.enumerated().map { index, day in
            Day(number: index + 1, stops: day.items.map { item in
                Stop(id: item.id, name: item.label, time: item.startTime,
                     point: nil, fixed: item.fixed, endTime: item.endTime)
            }, date: day.date, datePending: day.date == nil)
        })
    }
}


public struct LioTripLibrary {
    let list: @MainActor () async throws -> [StructuredTripSummary]
    let detail: @MainActor (String) async throws -> StructuredTripRecord?

    public init(list: @escaping @MainActor () async throws -> [StructuredTripSummary],
                detail: @escaping @MainActor (String) async throws -> StructuredTripRecord?) {
        self.list = list
        self.detail = detail
    }
}

extension LioItinerary {
    init(_ saved: StructuredTripRecord) {
        var stopsByDate: [String?: [Stop]] = [:]
        for item in saved.document.items {
            let startDate = item.start.date.lioValue
            let endDate = item.end.date.lioValue
            stopsByDate[startDate, default: []].append(
                Stop(id: item.id, name: item.text, time: item.start.time.lioValue,
                     point: nil, fixed: item.fixed.lioValue, endTime: item.end.time.lioValue,
                     endDate: endDate == startDate ? nil : endDate)
            )
        }
        var dates: [String?] = stopsByDate.keys.compactMap { $0 }.sorted().map(Optional.some)
        if stopsByDate.keys.contains(nil) { dates.append(nil) }
        self.init(id: saved.tripID, title: saved.document.title, description: nil,
                  days: dates.enumerated().map { index, date in
            Day(number: index + 1, stops: stopsByDate[date, default: []], date: date, datePending: date == nil)
        })
    }
}

private extension TripObservation {
    var lioValue: Value? {
        if case .known(let value) = self { return value }
        return nil
    }
}
