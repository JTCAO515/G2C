import CJMessageHTTP
import CJTripClient
import Foundation

enum LioRichProjectionFailure: Error { case unavailable }

extension LioRichItinerary {
    /// Project validated external text at the public-display boundary. This value
    /// does not authorize a read, save, undo, map lookup or source eligibility.
    init(_ document: RichStructuredTripDocument, language: LioLanguage) throws {
        var visibleText = [document.title, document.lodging.area]
        for day in document.days { visibleText += [day.theme, day.area] }
        for item in document.items {
            visibleText += [item.calendarItem.value.text, item.place.nameZH, item.place.nameEN]
            visibleText += [item.place.address, item.note, item.tip?.text].compactMap { $0 }
        }
        for hotel in document.lodging.recommendations {
            visibleText += [hotel.place.nameZH, hotel.place.nameEN]
            visibleText += [hotel.place.address, hotel.note].compactMap { $0 }
        }
        guard visibleText.allSatisfy(LioPublicDisplay.permitsText) else { throw LioRichProjectionFailure.unavailable }

        func place(_ source: RichStructuredTripDocument.Place) -> Place {
            let point = source.coordinate.map {
                LioItinerary.Point(latitude: NSDecimalNumber(decimal: $0.latitude.value).doubleValue,
                                   longitude: NSDecimalNumber(decimal: $0.longitude.value).doubleValue)
            }
            return Place(nameZH: source.nameZH, nameEN: source.nameEN, address: source.address, matched: source.matched, point: point)
        }
        func stop(_ source: RichStructuredTripDocument.Item) -> Stop {
            let item = source.calendarItem, value = item.value
            let startDate = document.days[item.startDayIndex - 1].date
            let endDate = document.days[item.endDayIndex - 1].date
            let time = LioItinerary.Stop(id: value.id, name: value.text, time: value.start.time.lioValue,
                point: nil, fixed: value.fixed.lioValue, endTime: value.end.time.lioValue,
                endDate: endDate == startDate ? nil : endDate,
                endDayNumber: document.calendar == .undated && item.startDayIndex != item.endDayIndex ? item.endDayIndex : nil)
            let ending = time.endingText(language)
            let interval: String?
            if let start = time.time { interval = ending.isEmpty ? start : "\(start)–\(ending)" }
            else { interval = ending.isEmpty ? nil : language.text("Until \(ending)", "至 \(ending)") }
            let kind: Kind
            switch source.kind { case .sight: kind = .sight; case .meal: kind = .meal; case .hotel: kind = .hotel
            case .transport: kind = .transport; case .freeTime: kind = .freeTime }
            return Stop(id: value.id, kind: kind, text: value.text, time: interval, place: place(source.place),
                        note: source.note, tip: source.tip?.text, fixed: value.fixed.lioValue)
        }
        func leg(_ source: RichStructuredTripDocument.Leg) throws -> Leg {
            let estimate: Leg.Estimate?
            if let value = source.estimate {
                // The data codec preserves arbitrary integer tokens. The current
                // native duration/distance formatter needs finite Double values;
                // refuse an unrepresentable display instead of inventing zero.
                guard let seconds = Double(value.duration.token), seconds.isFinite,
                      let metres = Double(value.distance.token), metres.isFinite else { throw LioRichProjectionFailure.unavailable }
                let mode: Leg.Mode
                switch value.mode { case .walking: mode = .walking; case .transit: mode = .transit; case .taxi: mode = .taxi }
                estimate = .init(mode: mode, seconds: seconds, metres: metres)
            } else { estimate = nil }
            return Leg(fromID: source.fromItemID, toID: source.toItemID, estimate: estimate)
        }
        let days = try document.days.map { day in
            try Day(number: day.index, date: day.date, theme: day.theme, area: day.area,
                    stops: document.items.filter { $0.calendarItem.startDayIndex == day.index }.map(stop),
                    legs: document.legs.filter { $0.dayIndex == day.index }.map(leg))
        }
        self.init(title: document.title, undated: document.calendar == .undated, days: days,
                  lodgingArea: document.lodging.area, hotels: document.lodging.recommendations.enumerated().map { index, hotel in
            Hotel(id: "lodging.\(index)", place: place(hotel.place), note: hotel.note)
        })
    }
}
