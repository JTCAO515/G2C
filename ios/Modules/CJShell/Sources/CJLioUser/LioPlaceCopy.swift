import Foundation

/// Words on the place page (#1992). The keys and wording of the first group are `codex-inbox/G4/ui-copy.json`
/// (`place.*`); the second group is not in that file yet, so its wording is a placeholder for the copy review
/// (`isPlaceholder`). Swapping a string changes only this file.
enum LioPlaceCopy: String, CaseIterable, Sendable {
    // In ui-copy.json.
    case addToTrip = "place.add_to_trip.button"
    case taxi = "place.taxi.button"
    case showDriver = "place.show_driver.button"
    case navigate = "place.navigate.button"
    case book = "place.book.button"
    case hours = "place.hours.label"
    case tickets = "place.tickets.label"
    case bookingMethod = "place.booking_method.label"
    case directions = "place.directions.label"
    case nearbyFood = "place.nearby_food.label"
    case officialInfo = "place.official_info.button"

    // Placeholders: not in ui-copy.json.
    case about = "place.about.label"
    case imagePlaceholder = "place.image.placeholder"
    case hoursInChinese = "place.hours.in_chinese"
    case notFoundTitle = "place.not_found.title"
    case notFoundBody = "place.not_found.body"
    case mapsUnavailable = "place.maps_unavailable.message"
    case ok = "place.ok.button"
    case passportRequired = "place.tickets.passport_required"
    case bookingRequired = "place.booking.required"
    case bookingRecommended = "place.booking.recommended"
    case bookingNone = "place.booking.none"
    case noFixedClosingDay = "place.closed.none"
    case metroLabel = "place.metro.label"
    case terminalsLabel = "place.terminals.label"
    case tipsLabel = "place.tips.label"
    case coordinateMissing = "place.directions.no_coordinate"

    /// Wording that has not been through the copy review.
    var isPlaceholder: Bool {
        switch self {
        case .addToTrip, .taxi, .showDriver, .navigate, .book, .hours, .tickets, .bookingMethod, .directions,
             .nearbyFood, .officialInfo: false
        default: true
        }
    }

    private var words: (en: String, zh: String) {
        switch self {
        case .addToTrip: ("Add to trip", "加入行程")
        case .taxi: ("Get a ride", "打车去")
        case .showDriver: ("Show the driver", "给司机看")
        case .navigate: ("Get directions", "导航")
        case .book: ("Book", "预约")
        case .hours: ("Opening hours", "开放时间")
        case .tickets: ("Tickets", "门票")
        case .bookingMethod: ("How to book", "预约方式")
        case .directions: ("How to get there", "怎么过去")
        case .nearbyFood: ("Food & drink nearby", "附近吃喝")
        case .officialInfo: ("Check official info", "查官方信息")
        case .about: ("About", "简介")
        case .imagePlaceholder: ("No photo yet", "暂无图片")
        case .hoursInChinese: ("Hours as published by the venue, in Chinese", "以下为场馆公布的开放时间")
        case .notFoundTitle: ("We don’t have this place yet", "还没有收录这个地点")
        case .notFoundBody: ("It isn’t in our guide yet. Try another place.", "指南里暂时没有它，换一个地点试试。")
        case .mapsUnavailable: ("Maps couldn’t open this place.", "地图无法打开这个地点。")
        case .ok: ("OK", "好")
        case .passportRequired: ("Passport required", "需要护照")
        case .bookingRequired: ("Booking required", "需要预约")
        case .bookingRecommended: ("Booking recommended", "建议预约")
        case .bookingNone: ("No booking needed", "无需预约")
        case .noFixedClosingDay: ("No regular closing day", "没有固定闭馆日")
        case .metroLabel: ("Nearest metro", "最近的地铁")
        case .terminalsLabel: ("Terminals", "航站楼")
        case .tipsLabel: ("Tips for travellers", "出行提示")
        case .coordinateMissing: ("Location not confirmed yet", "位置尚未确认")
        }
    }

    func text(_ language: LioLanguage) -> String {
        language == .chinese ? words.zh : words.en
    }

    /// `place.official_info.checked_on`: "Checked on {date}" / "核对于{date}".
    static func checkedOn(_ date: String, _ language: LioLanguage) -> String {
        language == .chinese ? "核对于\(date)" : "Checked on \(date)"
    }
}
