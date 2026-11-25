#if os(iOS)
import SwiftUI

/// 工具 → 景点预约: popular sights grouped by city, each with its booking rule in one line.
struct LioAttractionBookingView: View {
    let language: LioLanguage
    var reminders = LioAttractionReminderScheduler(center: LioSystemReminderCenter())
    var today: Date = .now

    private var cities: [(String, [LioAttractionBookingRule])] {
        var order: [String] = []
        var groups: [String: [LioAttractionBookingRule]] = [:]
        for rule in LioAttractionBookingRule.all {
            let city = rule.city(language)
            if groups[city] == nil { order.append(city) }
            groups[city, default: []].append(rule)
        }
        return order.map { ($0, groups[$0] ?? []) }
    }

    var body: some View {
        ScrollView { content }
            .foregroundStyle(LioTheme.ink)
            .background(LioTheme.paper)
            .tint(LioTheme.vermilion)
            .navigationTitle(language.text("Sight Bookings", "景点预约"))
            .navigationBarTitleDisplayMode(.inline)
    }

    var content: some View {
            VStack(alignment: .leading, spacing: 20) {
                Text(language.text("Many museums and landmarks in China need a real-name booking days ahead. Here is when tickets open, and Lio can remind you.",
                                   "国内不少博物馆和景点需要提前几天实名预约。这里列出什么时候放票，Lio 可以提醒你。"))
                    .foregroundStyle(LioTheme.inkSecondary)
                ForEach(cities, id: \.0) { city, rules in
                    VStack(alignment: .leading, spacing: 10) {
                        Text(city).font(.headline).accessibilityAddTraits(.isHeader)
                        ForEach(rules) { rule in
                            NavigationLink {
                                LioAttractionBookingDetail(rule: rule, language: language, reminders: reminders, today: today)
                            } label: {
                                row(rule)
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("lio.booking.rule.\(rule.id)")
                        }
                    }
                }
                Text(LioAttractionBookingRule.officialFirst(language))
                    .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .foregroundStyle(LioTheme.ink)
            .tint(LioTheme.vermilion)
    }

    private func row(_ rule: LioAttractionBookingRule) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Text(rule.name(language)).font(.body.weight(.semibold))
                LioAttractionBookingBadge(rule: rule, language: language, today: today)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

/// One line under an itinerary stop, roadbook entry or Lio answer that names a sight with a rule.
struct LioAttractionBookingBadge: View {
    let rule: LioAttractionBookingRule
    let language: LioLanguage
    var today: Date = .now

    private var symbol: String {
        switch rule.requirement {
        case .required: "ticket"
        case .bookingOrOnSite, .notRequired: "checkmark.circle"
        case .unknown: "questionmark.circle"
        }
    }

    var body: some View {
        Label(rule.summary(language, on: today), systemImage: symbol)
            .font(.subheadline)
            .foregroundStyle(rule.requirement == .required ? LioTheme.vermilion : LioTheme.inkSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("lio.booking.badge.\(rule.id)")
    }
}

struct LioAttractionBookingDetail: View {
    let rule: LioAttractionBookingRule
    let language: LioLanguage
    let reminders: LioAttractionReminderScheduler
    var today: Date = .now
    @State private var visit: Date
    @State private var scheduled = false
    @State private var notice: String?
    @State private var working = false

    init(rule: LioAttractionBookingRule, language: LioLanguage, reminders: LioAttractionReminderScheduler,
         today: Date = .now, visit: Date? = nil) {
        self.rule = rule
        self.language = language
        self.reminders = reminders
        self.today = today
        let calendar = LioAttractionBookingRule.calendar
        _visit = State(initialValue: visit ?? calendar.date(byAdding: .day, value: 10, to: calendar.startOfDay(for: today)) ?? today)
    }

    private var stale: Bool { rule.isStale(on: today) }
    private var request: LioAttractionReminder.Request? {
        LioAttractionReminder.request(for: rule, visit: visit, now: today, language: language)
    }

    var body: some View {
        ScrollView { content }
            .foregroundStyle(LioTheme.ink)
            .background(LioTheme.paper)
            .tint(LioTheme.vermilion)
            .navigationTitle(rule.name(language))
            .navigationBarTitleDisplayMode(.inline)
            .task(id: request?.id) {
                if let id = request?.id { scheduled = await reminders.isScheduled(id) } else { scheduled = false }
            }
    }

    var content: some View {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(rule.name(language)).font(LioTheme.display(.title2)).accessibilityAddTraits(.isHeader)
                    if language == .english { Text(rule.nameZH).foregroundStyle(LioTheme.inkSecondary) }
                    LioAttractionBookingBadge(rule: rule, language: language, today: today)
                }
                if !stale { facts }
                reminder
                links
                sources
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .foregroundStyle(LioTheme.ink)
            .tint(LioTheme.vermilion)
            .environment(\.timeZone, LioAttractionBookingRule.calendar.timeZone)
    }

    private var facts: some View {
        VStack(alignment: .leading, spacing: 10) {
            Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 12, verticalSpacing: 10) {
            fact(language.text("Booking", "预约"), requirementText)
            if let days = rule.windowDays {
                fact(language.text("Book ahead", "最多提前"), language.text("Up to \(days) days", "\(days) 天"))
            }
            if rule.requirement == .required || rule.requirement == .bookingOrOnSite {
                fact(language.text("Tickets open", "放票时间"),
                     rule.releaseTime.map { language.text("\($0.text) Beijing time", "北京时间 \($0.text)") }
                        ?? language.text("Not published", "官方未写"))
            }
            fact(language.text("Passport", "护照"), rule.passport == .accepted
                 ? language.text("Accepted for booking", "可用护照预约")
                 : language.text("Not mentioned in the rules", "官方规则未提护照"))
            if let closed = closedText { fact(language.text("Closed", "闭馆"), closed) }
            }
            ForEach(rule.limits(language) + rule.notes(language), id: \.self) { line in
                Label(line, systemImage: "info.circle").font(.subheadline).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private var requirementText: String {
        switch rule.requirement {
        case .required: language.text("Real-name booking required", "需实名预约")
        case .bookingOrOnSite: language.text("Book ahead or buy on site", "可预约，也可现场购票")
        case .notRequired: language.text("Not needed for regular galleries", "常设展免预约")
        case .unknown: language.text("Not listed yet", "暂未收录")
        }
    }

    private var closedText: String? {
        guard let days = rule.closedWeekdays else { return nil }
        if days.isEmpty { return language.text("Open every day", "每天开放") }
        let names = days.sorted().map { day in
            let en = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            let zh = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
            return language.text(en[(day - 1) % 7], zh[(day - 1) % 7])
        }.joined(separator: language.text(", ", "、"))
        return rule.openOnPublicHolidays ? names + language.text(" (open on public holidays)", "（法定节假日除外）") : names
    }

    private func fact(_ title: String, _ value: String) -> some View {
        GridRow {
            Text(title).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
            Text(value).font(.body).fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var reminder: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(language.text("Release reminder", "放票提醒")).font(.headline).accessibilityAddTraits(.isHeader)
            DatePicker(language.text("Visit day", "参观日"), selection: $visit,
                       in: LioAttractionBookingRule.calendar.startOfDay(for: today)..., displayedComponents: .date)
                .environment(\.calendar, LioAttractionBookingRule.calendar)
                .frame(minHeight: 44)
            if rule.closedOn(visit) {
                Label(language.text("Closed on this day. Pick another day unless it is a public holiday.",
                                    "这一天闭馆（法定节假日除外），建议换一天。"), systemImage: "exclamationmark.triangle")
                    .font(.subheadline)
            }
            Text(planText).font(.subheadline).fixedSize(horizontal: false, vertical: true)
            if let request {
                Button {
                    Task { await toggle(request) }
                } label: {
                    Label(scheduled ? language.text("Cancel reminder", "取消提醒") : language.text("Remind me", "提醒我"),
                          systemImage: scheduled ? "bell.slash" : "bell")
                        .foregroundStyle(LioTheme.onVermilion)
                        .frame(maxWidth: .infinity, minHeight: 44)
                }
                .buttonStyle(.borderedProminent)
                .disabled(working)
                .accessibilityIdentifier("lio.booking.remind")
            }
            if let notice { Text(notice).font(.footnote).foregroundStyle(LioTheme.inkSecondary) }
            Text(language.text("Reminders stay on this iPhone as local notifications; nothing is uploaded.",
                               "提醒只在本机用系统通知，不上传任何数据。"))
                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private var planText: String {
        let format = Date.FormatStyle(date: .abbreviated, time: .shortened)
            .locale(Locale(identifier: language == .chinese ? "zh_CN" : "en_GB"))
        var style = format
        style.timeZone = LioAttractionBookingRule.calendar.timeZone
        var dayStyle = Date.FormatStyle(date: .abbreviated, time: .omitted)
            .locale(Locale(identifier: language == .chinese ? "zh_CN" : "en_GB"))
        dayStyle.timeZone = LioAttractionBookingRule.calendar.timeZone
        switch LioAttractionReminder.plan(for: rule, visit: visit, now: today) {
        case .exact(let opens, let fire):
            return language.text("Tickets open \(opens.formatted(style)) Beijing time. Lio reminds you at \(fire.formatted(style)).",
                                 "北京时间 \(opens.formatted(style)) 放票，Lio 会在 \(fire.formatted(style)) 提醒你。")
        case .firstDay(let day, _):
            return language.text("Booking opens on \(day.formatted(dayStyle)); the release time is not published, so Lio reminds you that morning.",
                                 "\(day.formatted(dayStyle)) 起可预约，官方未写放票时间，Lio 当天上午提醒你。")
        case .opensSoon(let opens):
            return language.text("Tickets open at \(opens.formatted(style)) Beijing time, in a few minutes.",
                                 "北京时间 \(opens.formatted(style)) 放票，马上就到。")
        case .alreadyOpen: return language.text("Booking for this day is already open.", "这一天已经可以预约。")
        case .unknownWindow: return language.text("The booking window is not published, so no reminder can be set.", "官方未写提前几天放票，暂不能设提醒。")
        case .notNeeded: return language.text("No booking needed.", "不需要预约。")
        case .pastVisit: return language.text("Pick a future day.", "请选今天以后的日期。")
        case .stale: return language.text("These rules are due for review before then; check the official channel nearer the time.",
                                          "到那时规则可能已变化，请临近时查官方渠道。")
        }
    }

    private func toggle(_ request: LioAttractionReminder.Request) async {
        working = true
        defer { working = false }
        if scheduled {
            await reminders.cancel(request.id)
            scheduled = false
            notice = language.text("Reminder cancelled.", "已取消提醒。")
            return
        }
        do {
            switch try await reminders.schedule(request) {
            case .scheduled:
                scheduled = true
                notice = language.text("Reminder set.", "已设好提醒。")
            case .notAllowed:
                notice = language.text("Turn on notifications for Go2China in Settings to get reminders.",
                                       "请在系统设置里允许 Go2China 发送通知。")
            }
        } catch {
            notice = language.text("Could not set the reminder. Try again.", "提醒没设成功，请重试。")
        }
    }

    private var links: some View {
        VStack(alignment: .leading, spacing: 10) {
            Link(destination: rule.officialChannel.url) {
                Label(language.text("Book on \(rule.officialChannel.nameEN)", "去\(rule.officialChannel.nameZH)预约"),
                      systemImage: "arrow.up.right.square")
                    .foregroundStyle(LioTheme.vermilion)
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            }
            .accessibilityIdentifier("lio.booking.official")
            Text(language.text("Booking and payment happen on the official channel; Go2China does not sell tickets.",
                               "预约和付款都在官方渠道完成，Go2China 不售票。"))
                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
        }
    }

    private var sources: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(language.text("Checked on \(rule.checkedOn). \(LioAttractionBookingRule.officialFirst(language))",
                               "核对日期 \(rule.checkedOn)。\(LioAttractionBookingRule.officialFirst(language))"))
            ForEach(rule.sources, id: \.self) { source in
                Link(destination: source) {
                    Text(source.absoluteString).lineLimit(1).truncationMode(.middle)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                }
            }
        }
        .font(.footnote)
        .foregroundStyle(LioTheme.inkSecondary)
    }
}

#if DEBUG
/// Mock-up of the proposed itinerary hook: a stop whose place matches a rule gets the badge and a
/// "Book" link. The real stop card belongs to the itinerary owner; this only shows the placement.
struct LioAttractionBookingStopSample: View {
    let language: LioLanguage
    var today: Date = LioAttractionBookingRule.day("2026-11-25")!

    private let stops: [(String, String, String, String)] = [
        ("09:00", "故宫博物院", "The Palace Museum", "Enter from the Meridian Gate"),
        ("13:30", "南锣鼓巷", "Nanluoguxiang", "Lunch and a stroll in the hutongs"),
        ("15:30", "中国国家博物馆", "National Museum of China", "Ancient China gallery"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(language.text("Day 2 · Central axis", "第 2 天 · 中轴线")).font(LioTheme.display(.title2))
            ForEach(Array(stops.enumerated()), id: \.offset) { index, stop in
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 12) {
                        Text("\(index + 1)").font(.headline).foregroundStyle(LioTheme.onVermilion)
                            .frame(minWidth: 32, minHeight: 32).background(LioTheme.vermilion, in: Circle())
                        Text(stop.0).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    }
                    Text(language.text(stop.2, stop.1)).font(.headline)
                    Text(stop.3).font(.body)
                    if let rule = LioAttractionBookingRule.match(nameZH: stop.1, nameEN: stop.2) {
                        HStack {
                            LioAttractionBookingBadge(rule: rule, language: language, today: today)
                            Spacer(minLength: 8)
                            Text(language.text("Book", "预约")).font(.subheadline.weight(.semibold))
                                .padding(.horizontal, 14).frame(minHeight: 44)
                                .background(LioTheme.surfaceSunken, in: Capsule())
                        }
                    }
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            }
        }
        .padding(18)
        .foregroundStyle(LioTheme.ink)
    }
}

#Preview("Itinerary hook") {
    ScrollView { LioAttractionBookingStopSample(language: .english) }.background(LioTheme.paper)
}

#Preview("Tools list") {
    NavigationStack {
        LioAttractionBookingView(language: .chinese, today: LioAttractionBookingRule.day("2026-11-25")!)
    }
}

#Preview("Detail") {
    NavigationStack {
        LioAttractionBookingDetail(rule: LioAttractionBookingRule.all[0], language: .english,
                                   reminders: .init(center: LioSystemReminderCenter()),
                                   today: LioAttractionBookingRule.day("2026-11-25")!,
                                   visit: LioAttractionBookingRule.day("2026-12-05")!)
    }
}
#endif
#endif
