import CJMessageHTTP
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

        init(id: String, name: String, time: String?, point: Point?, fixed: Bool?, endTime: String? = nil) {
            self.id = id
            self.name = name
            self.time = time
            self.point = point
            self.fixed = fixed
            self.endTime = endTime
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
