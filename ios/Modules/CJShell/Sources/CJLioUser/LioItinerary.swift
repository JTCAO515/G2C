import CJMessageHTTP
import CJTripClient
import Foundation

struct LioItinerary: Equatable, Identifiable, Sendable {
    enum CalendarState: Equatable, Sendable {
        case undated, dated(startDate: String)
    }
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

        func title(_ language: LioLanguage, calendar: CalendarState? = nil) -> String {
            if calendar == .undated { return language.text("Day \(number)", "第 \(number) 天") }
            if let date { return date }
            if datePending { return language.text("Date to be decided", "日期待定") }
            return language.text("Day \(number)", "第 \(number) 天")
        }
    }

    let id: String
    let title: String
    let description: String?
    let days: [Day]
    let calendar: CalendarState?

    init(id: String, title: String, description: String?, days: [Day], calendar: CalendarState? = nil) {
        self.id = id
        self.title = title
        self.description = description
        self.days = days
        self.calendar = calendar
    }

    func planningIntroduction(_ language: LioLanguage) -> String? {
        if let description { return description }
        guard !days.isEmpty else { return nil }
        let count = days.count
        let dated = days.filter { $0.date != nil }.count
        if dated == count {
            return language.text("I planned a \(count)-day trip around the dates below.", "我按下面的日期安排了 \(count) 天行程。")
        }
        if dated == 0 {
            return language.text("I planned a \(count)-day trip with the dates left open.", "我先安排了 \(count) 天行程，日期可以之后再定。")
        }
        return language.text("I planned a \(count)-day trip and left some dates open.", "我安排了 \(count) 天行程，有些日期可以之后再定。")
    }
}

extension LioItinerary {
    /// The caller supplies a validated summary; this projection is display data, not a saved-source permit.
    init(_ card: LioCalendarTripCard) {
        let calendar: CalendarState?
        switch card.calendar {
        case .undated: calendar = .undated
        case .dated(let date): calendar = .dated(startDate: date)
        case nil: calendar = nil
        }
        self.init(id: card.id, title: card.title, description: nil,
                  days: card.days.enumerated().map { position, day in
            Day(number: day.index.map(Int.init) ?? position + 1,
                stops: day.items.map { item in
                    Stop(id: item.id, name: item.label, time: item.startTime, point: nil,
                         fixed: item.fixed, endTime: item.endTime)
                }, date: day.date, datePending: calendar == nil && day.date == nil)
        }, calendar: calendar)
    }
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
    init(_ saved: StructuredTripRecord, places: [TripPlaceProjection] = []) {
        var stopsByDate: [String?: [Stop]] = [:]
        for item in saved.document.items {
            let startDate = item.start.date.lioValue
            let endDate = item.end.date.lioValue
            let coordinate = places.first { item.sourceReferences.contains($0.id) }?.markerCoordinate
            let point = coordinate.map {
                Point(latitude: NSDecimalNumber(decimal: $0.latitude.value).doubleValue,
                      longitude: NSDecimalNumber(decimal: $0.longitude.value).doubleValue)
            }
            stopsByDate[startDate, default: []].append(
                Stop(id: item.id, name: item.text, time: item.start.time.lioValue,
                     point: point, fixed: item.fixed.lioValue, endTime: item.end.time.lioValue,
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
