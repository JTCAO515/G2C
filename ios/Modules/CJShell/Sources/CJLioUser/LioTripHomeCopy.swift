import Foundation

/// Trip home wording, both languages. Rule facts (days, times, dates) come only from the sourced tables;
/// the wording around them is fixed here.
enum LioTripHomeCopy {
    static func dayText(_ day: LioTripDay, _ language: LioLanguage) -> String {
        let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return language.text("\(day.day) \(months[max(0, min(11, day.month - 1))])", "\(day.month)月\(day.day)日")
    }

    /// "8–14 Dec · 7 days", "12月8日–12月14日 · 7 天", or that the dates are not set.
    static func dates(arrival: LioTripDay?, lastDay: LioTripDay?, _ language: LioLanguage) -> String {
        guard let arrival else { return language.text("Dates not set", "还没定日期") }
        guard let lastDay else { return language.text("From \(dayText(arrival, language))", "\(dayText(arrival, language))起") }
        let days = arrival.days(until: lastDay) + 1
        let span = arrival == lastDay ? dayText(arrival, language)
            : "\(dayText(arrival, language))–\(dayText(lastDay, language))"
        return span + language.text(" · \(days) \(days == 1 ? "day" : "days")", " · \(days) 天")
    }

    static func phase(_ phase: LioTripPhase, _ language: LioLanguage) -> String {
        switch phase {
        case .beforeTrip(let days?) where days == 1: language.text("You arrive tomorrow", "明天到达")
        case .beforeTrip(let days?): language.text("\(days) days until you arrive", "还有 \(days) 天到达")
        case .beforeTrip(nil): language.text("Before your trip", "出发前")
        case .arrivalDay: language.text("Arrival day · Day 1", "今天到达 · 第 1 天")
        case .inChina(let day): language.text("Day \(day) in China", "在华第 \(day) 天")
        case .departureDay(let day): language.text("Day \(day) · Last day", "第 \(day) 天 · 最后一天")
        case .ended: language.text("Trip ended", "旅行已结束")
        }
    }

    static func stage(_ stage: LioTripStage, _ language: LioLanguage) -> String {
        switch stage {
        case .beforeTrip: language.text("Before you fly", "出发前")
        case .arrivalDay: language.text("Arrival day", "落地当天")
        case .inChina: language.text("In China", "在华期间")
        case .departure: language.text("Before you leave", "离境前")
        }
    }

    /// The one line for stages already behind the traveller.
    static func pastSummary(open: Int, done: Int, _ language: LioLanguage) -> String {
        switch (open, done) {
        case (0, _): language.text("All \(done) done", "已完成 \(done) 项")
        case (_, 0): language.text("\(open) not ticked", "还有 \(open) 项没勾")
        default: language.text("\(open) not ticked · \(done) done", "还有 \(open) 项没勾 · 已完成 \(done) 项")
        }
    }

    static func doneCount(_ count: Int, _ language: LioLanguage) -> String {
        language.text("\(count) done", "已完成 \(count) 项")
    }

    // MARK: - Tasks

    /// The six steps of going to China (#1979) are one line each: the line is the whole row, with no heading above
    /// it and no explanation under it (`detail` is empty for them).
    static func title(_ task: LioTripTask, _ language: LioLanguage) -> String {
        switch task.kind {
        case .entry: language.text("Visa-free or visa: use the official channels", "免签或签证，走官方渠道")
        case .arrival(let day, let number): arrival(day: day, number: number, language)
        case .hotel: language.text("Pick a hotel", "选一家酒店")
        case .payment: language.text("Set up Alipay or Weixin Pay", "开通支付宝或微信支付")
        case .internet: language.text("Get an eSIM or roaming", "买好 eSIM 或开漫游")
        case .local: language.text("Set up ride codes and taxis", "设好乘车码和打车")
        case .booking(let id, _, _, _):
            LioAttractionBookingRule.all.first { $0.id == id }.map { rule in
                language.text("Book \(rule.nameEN)", "预约\(rule.nameZH)")
            } ?? language.text("Book a sight", "预约景点")
        case .medicalCard: language.text("Fill in your medical card", "填医疗卡和紧急联系人")
        case .landing: language.text("Passport control, data, hotel", "过关、上网、去酒店")
        case .checkIn: language.text("Check in at your hotel", "办理入住")
        case .business(let business): businessTitle(business, language)
        }
    }

    /// Empty for the six steps: their line is `title`.
    static func detail(_ task: LioTripTask, _ language: LioLanguage) -> String {
        switch task.kind {
        case .entry, .arrival, .payment, .internet, .hotel, .local: ""
        case .booking(let id, let visit, let timing, _):
            booking(id: id, visit: visit, timing: timing, language)
        case .medicalCard:
            language.text("Allergies, medicines and who to call. Kept on this phone only.",
                          "过敏、用药和紧急联系人，只存在这台手机。")
        case .landing: language.text("Follow the arrival checklist step by step.", "跟着落地清单一步步来。")
        case .checkIn: language.text("Show the front desk the check-in card.", "给前台看「办理入住」卡。")
        case .business(let business): businessDetail(business, language)
        }
    }

    // MARK: - Business items (#1765)

    /// Sourced titles are shown as they are; the visa item is only ever "the official channels".
    static func businessTitle(_ task: LioTripBusinessTask, _ language: LioLanguage) -> String {
        if let title = task.title { return title.text(language) }
        switch task.item {
        case .visa: return language.text("Check the official visa channels", "查看官方签证渠道")
        case .meeting: return language.text("Make a meeting card", "准备会面卡")
        case .cards: return language.text("Bring your business cards", "带上名片")
        case .registration: return language.text("Pre-register as a buyer", "采购商预登记")
        case .phrases: return language.text("Business phrases and translation", "商务常用语和翻译")
        case .venue: return language.text("Getting to the venue", "去展馆")
        }
    }

    /// An entry's own text while it is within its review period; afterwards only "go by the official notice".
    /// Items without an entry describe the tool they open and state no facts.
    static func businessDetail(_ task: LioTripBusinessTask, _ language: LioLanguage) -> String {
        if task.source?.officialOnly == true {
            return language.text("This may have changed since it was checked. Go by the latest official notice; the official pages are below.",
                                 "核对后可能有变化，以官方最新通知为准，官方页面在下面。")
        }
        if let text = task.text { return text.text(language) }
        switch task.item {
        case .meeting:
            return language.text("Who you are meeting, when and where, in large Chinese for the driver or the front desk.",
                                 "约见的人、时间和地点，用大字中文给司机或前台看。")
        case .cards:
            return language.text("For the fair and your meetings. Tick it when they are packed.", "展会和会面时用，收好后自己勾上。")
        case .phrases:
            return language.text("Translation is in Tools; business phrases are under Show Cards › Business.",
                                 "翻译在工具里；商务常用语在「出示卡」的「商务」里。")
        case .registration, .visa, .venue:
            return language.text("Go by the latest official notice.", "以官方最新通知为准。")
        }
    }

    /// Under every sourced business item: official rules apply, and the day the entry was checked.
    static func businessSource(_ source: LioTripBusinessTask.Source, _ language: LioLanguage) -> String {
        let checked = dayText(source.checkedOn, language)
        return language.text("Official notices apply · checked \(checked)", "以官方为准 · 核对于 \(checked)")
    }

    /// "Arriving 8 Dec · CA1234", or the ask while the day is not given.
    static func arrival(day: LioTripDay?, number: String?, _ language: LioLanguage) -> String {
        guard let day else { return language.text("Add your arrival day and flight or train", "填到达日期和航班或车次") }
        let when = language.text("Arriving \(dayText(day, language))", "\(dayText(day, language))到达")
        return [when, number].compactMap { $0 }.joined(separator: " · ")
    }

    static func booking(id: String, visit: LioTripDay?, timing: LioTripBookingTiming, _ language: LioLanguage) -> String {
        let visitText = visit.map { language.text("Visit \(dayText($0, language))", "\(dayText($0, language))参观") }
        func joined(_ second: String) -> String { [visitText, second].compactMap { $0 }.joined(separator: " · ") }
        switch timing {
        case .opensAt(let date):
            let day = LioTripDay(date: date, timeZone: LioTripChecklist.beijing)
            let clock = LioAttractionBookingRule.Clock(hour: LioAttractionBookingRule.calendar.component(.hour, from: date),
                                                       minute: LioAttractionBookingRule.calendar.component(.minute, from: date)).text
            return joined(language.text("tickets open \(dayText(day, language)) at \(clock), Beijing time",
                                        "\(dayText(day, language)) \(clock) 放票（北京时间）"))
        case .opensOn(let day):
            return joined(language.text("booking opens \(dayText(day, language)); release time not published",
                                        "\(dayText(day, language))起可约，官方未公布放票时间"))
        case .openNow:
            return joined(language.text("booking is open now", "现在可以预约"))
        case .windowNotPublished:
            return joined(language.text("how far ahead you can book is not published", "官方未公布提前几天放票"))
        case .checkOfficial:
            return language.text("Rules may have changed; check the official channel.", "规则可能已变化，请查官方渠道。")
        case .noVisitDay:
            return language.text("Real-name booking. Pick a visit day to set a release reminder.",
                                 "需实名预约，选好参观日就能设放票提醒。")
        }
    }

    /// The rule's official channel and the day it was checked, under every booking task.
    static func bookingSource(id: String, _ language: LioLanguage) -> String? {
        guard let rule = LioAttractionBookingRule.all.first(where: { $0.id == id }) else { return nil }
        return language.text("Official rules apply · \(rule.officialChannel.name(language)) · checked \(checkedText(rule.checkedOn, language))",
                             "以官方为准 · \(rule.officialChannel.name(language)) · 核对于 \(checkedText(rule.checkedOn, language))")
    }

    static func checkedText(_ day: String, _ language: LioLanguage) -> String {
        LioTripDay(day).map { dayText($0, language) } ?? day
    }

    static func reminderSet(_ language: LioLanguage) -> String { language.text("Reminder set", "已设提醒") }

    static func status(_ task: LioTripTask, _ language: LioLanguage) -> String {
        switch task.done {
        case .open: language.text("Not done", "未完成")
        case .ticked: language.text("Done", "已完成")
        case .automatic: language.text("Done, from your saved details", "已完成（按已保存的信息）")
        case .followsArrival: language.text("Done in Arrival Mode", "已在落地模式勾选")
        }
    }

    static func go(_ language: LioLanguage) -> String { language.text("Go", "去办") }
}
