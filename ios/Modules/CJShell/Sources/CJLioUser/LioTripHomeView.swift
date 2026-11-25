#if os(iOS)
import SwiftUI

/// The Trips tab as this trip's home (行程首页 · 办事清单, phase 1), behind `G2CTripHomeEnabled`.
/// Tasks come from `LioTripChecklist`; "Go" opens the tool that does each one, and coming back re-reads the
/// tools' state on this phone. Saved trips and earlier plans stay one tap away in "All trips".
struct LioTripHome: View {
    let language: LioLanguage
    /// Plans saved on this device (#1453), newest first.
    let plans: [LioPlanSummary]
    let tools: LioTripHomeTools
    let showAllTrips: () -> Void
    let openChat: () -> Void
    /// Debug previews pin the clock and the zone; nil follows the phone.
    var fixedNow: Date?
    var timeZone: TimeZone = .current
    @State private var model: LioTripHomeModel
    @AppStorage(LioTripHomeNationality.key) private var nationality = ""
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @Environment(\.lioMedicalCard) private var medicalCard
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.colorScheme) private var colorScheme
    @State private var path: [Page] = []
    @State private var refresh = 0
    @State private var hotel: LioStayHotel?
    @State private var reminders: Set<String> = []
    @State private var sheet: Sheet?
    @State private var showsMedicalCard = false
    @State private var confirmsEnd = false
    @State private var shownDone: Set<LioTripStage> = []
    @State private var showsPast = false

    enum Page: Hashable { case task(String), schedule, arrival, hotel, roadbook }
    private enum Sheet: String, Identifiable {
        case start, edit, taxi, driver
        var id: Self { self }
    }

    init(language: LioLanguage, store: LioTripHomeStore?, plans: [LioPlanSummary], tools: LioTripHomeTools,
         showAllTrips: @escaping () -> Void, openChat: @escaping () -> Void,
         fixedNow: Date? = nil, timeZone: TimeZone = .current, model: LioTripHomeModel? = nil) {
        self.language = language
        self.plans = plans
        self.tools = tools
        self.showAllTrips = showAllTrips
        self.openChat = openChat
        self.fixedNow = fixedNow
        self.timeZone = timeZone
        _model = State(initialValue: model ?? LioTripHomeModel(store: store))
    }

    var body: some View {
        NavigationStack(path: $path) {
            TimelineView(.everyMinute) { context in
                let list = checklist(at: fixedNow ?? context.date)
                ScrollView {
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
                        if list.hasTrip {
                            header(list)
                            if let now = list.now { nowCard(now, list) }
                            // JT 2026-11-25: in China, today's plan sits right under "Now".
                            if list.showsScheduleFirst { schedule(list) }
                            ForEach(LioTripStage.allCases.filter { $0 >= list.phase.stage }, id: \.self) { stage in
                                taskGroup(stage, list)
                            }
                            if !list.showsScheduleFirst { schedule(list) }
                            shortcuts
                            pastStages(list)
                        } else {
                            LioTripHomeStart(language: language, openChat: openChat) { sheet = .start }
                        }
                        if model.saveFailed {
                            Label(language.text("This change could not be saved on this phone.", "这次改动没能存到手机上。"),
                                  systemImage: "exclamationmark.triangle")
                                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                                .accessibilityIdentifier("lio.trip-home.save-failed")
                        }
                    }
                    .padding(LioTheme.Spacing.md)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .accessibilityIdentifier("lio.trip-home")
            }
            .lioPage()
            .navigationTitle(language.text("Trips", "行程"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(LioTheme.paper, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(colorScheme, for: .navigationBar)
            .toolbar { toolbar }
            .navigationDestination(for: Page.self) { page in destination(page) }
        }
        .tint(LioTheme.vermilion)
        .task(id: refresh) { await readTools() }
        .onChange(of: path) { _, pages in if pages.isEmpty { refresh += 1 } }
        .onChange(of: scenePhase) { _, phase in if phase == .active { refresh += 1 } }
        .sheet(item: $sheet, onDismiss: { refresh += 1 }) { sheet in sheetContent(sheet) }
        .fullScreenCover(isPresented: $showsMedicalCard, onDismiss: { refresh += 1 }) {
            if let medicalCard {
                NavigationStack { LioMedicalCardView(language: language, storage: medicalCard, opensDisplay: false) }
            }
        }
        .confirmationDialog(language.text("End this trip?", "结束这趟旅行？"), isPresented: $confirmsEnd, titleVisibility: .visible) {
            Button(language.text("End trip", "结束旅行"), role: .destructive) { model.clear() }
            Button(language.text("Cancel", "取消"), role: .cancel) {}
        } message: {
            Text(language.text("This clears the trip’s dates, city and ticks on this phone. Saved plans and what you keep in the tools stay.",
                               "会清掉这趟旅行在手机上的日期、城市和勾选。已保存的行程和各工具里的内容都保留。"))
        }
    }

    // MARK: - State

    private func checklist(at date: Date) -> LioTripChecklist {
        LioTripChecklist(.init(
            now: date, timeZone: timeZone, profile: model.profile, plans: plans, ticks: model.ticks,
            entry: tools.arrival?.entry(model.profile, nationality, date),
            arrivalChecklist: tools.arrival?.checklist(),
            hotelSaved: tools.hotelStore == nil ? nil : hotel != nil,
            showCards: tools.showCards,
            attractionBooking: tools.reminders != nil,
            scheduledReminders: reminders))
    }

    private func readTools() async {
        model.reload()
        hotel = tools.savedHotel()
        if let scheduler = tools.reminders { reminders = await scheduler.center.pendingIDs() }
    }

    private func tick(_ task: LioTripTask) {
        switch task.tick {
        case .manual: model.setTick(task.key, done: !task.isDone)
        case .arrivalStep(let step): tools.arrival?.setStep(step, !task.isDone)
        case .statusOnly: return
        }
        refresh += 1
    }

    private func open(_ task: LioTripTask) {
        if case .medicalCard = task.kind, medicalCard != nil {
            showsMedicalCard = true
        } else {
            path.append(.task(task.key))
        }
    }

    // MARK: - Header

    private func title(_ list: LioTripChecklist) -> String {
        if let city = model.profile?.cityID.flatMap(LioMetroCity.named) { return city.name(in: language) }
        if let plan = list.plan, !plan.title.isEmpty { return plan.title }
        return language.text("Your China trip", "这趟中国之行")
    }

    private func header(_ list: LioTripChecklist) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text(title(list))
                .font(LioTheme.display(.largeTitle).bold())
                .foregroundStyle(LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text(LioTripHomeCopy.dates(arrival: list.arrival, lastDay: list.lastDay, language))
                .font(.subheadline)
                .foregroundStyle(LioTheme.inkSecondary)
            Label(LioTripHomeCopy.phase(list.phase, language), systemImage: phaseSymbol(list.phase))
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(LioTheme.ink)
                .padding(.horizontal, LioTheme.Spacing.sm)
                .padding(.vertical, LioTheme.Spacing.xs)
                .background(LioTheme.surfaceSunken, in: Capsule())
                .accessibilityIdentifier("lio.trip-home.phase")
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lio.trip-home.header")
    }

    private func phaseSymbol(_ phase: LioTripPhase) -> String {
        switch phase {
        case .beforeTrip: "calendar"
        case .arrivalDay: "airplane.arrival"
        case .inChina: "sun.max"
        case .departureDay: "airplane.departure"
        case .ended: "checkmark.seal"
        }
    }

    // MARK: - Now

    @ViewBuilder private func nowCard(_ now: LioTripNow, _ list: LioTripChecklist) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            Label(language.text("Now", "现在"), systemImage: "sparkle")
                .font(.caption.weight(.semibold))
                .foregroundStyle(LioTheme.vermilion)
                .accessibilityAddTraits(.isHeader)
            switch now {
            case .prepare(let done, let total, let next):
                nowText(language.text("\(done) of \(total) ready", "准备进度 \(done)/\(total)"),
                        next.map { language.text("Next: \(LioTripHomeCopy.title($0, language))", "下一件：\(LioTripHomeCopy.title($0, language))") })
                progress(done, total)
                if let next { primary(LioTripHomeCopy.go(language), "lio.trip-home.now.go") { open(next) } }
            case .ready:
                nowText(language.text("All set before you fly", "出发前的事都办好了"),
                        LioTripHomeCopy.phase(list.phase, language))
                if list.plan != nil { secondary(language.text("See the plan", "查看日程"), "lio.trip-home.now.plan") { path.append(.schedule) } }
            case .landing(let done, let total):
                nowText(language.text("Arrival checklist: \(done) of \(total)", "落地清单 \(done)/\(total)"),
                        language.text("Passport control, data and the ride to your hotel, step by step.", "过关、上网、去酒店，一步步来。"))
                progress(done, total)
                primary(language.text("Open Arrival Mode", "打开落地模式"), "lio.trip-home.now.arrival") { path.append(.arrival) }
            case .landingTasks(let done, let total, let next):
                nowText(language.text("Today: \(done) of \(total) done", "今天要办 \(done)/\(total)"),
                        next.map { language.text("Next: \(LioTripHomeCopy.title($0, language))", "下一件：\(LioTripHomeCopy.title($0, language))") })
                progress(done, total)
                if let next { primary(LioTripHomeCopy.go(language), "lio.trip-home.now.go") { open(next) } }
            case .today(let day, let next, let remaining):
                todayCard(day: day, next: next, remaining: remaining, list: list)
            case .backToHotel(let saved):
                backToHotelCard(saved: saved)
            case .ended(let days):
                nowText(language.text("Your trip has ended", "这趟旅行结束了"),
                        days.map { language.text("\($0) days in China. Start a new trip when you plan the next one.", "在中国的 \($0) 天结束了。下次出发前再开始新的旅行。") })
                primary(language.text("Start a new trip", "开始新的旅行"), "lio.trip-home.now.new-trip") { confirmsEnd = true }
            }
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("lio.trip-home.now")
    }

    @ViewBuilder private func todayCard(day: Int, next: LioTripStopRef?, remaining: Int, list: LioTripChecklist) -> some View {
        let todayStops = list.schedule.first { $0.isToday }?.stops ?? []
        if let next {
            nowText([next.time, next.name].compactMap { $0 }.joined(separator: " "),
                    language.text("Today · Day \(day) · \(remaining) more \(remaining == 1 ? "place" : "places")",
                                  "今天 · 第 \(day) 天 · 还有 \(remaining) 个地点"))
            primary(language.text("See today", "查看今天"), "lio.trip-home.now.today") { path.append(.schedule) }
        } else if todayStops.isEmpty {
            nowText(language.text("Nothing planned for today", "今天还没有安排"),
                    language.text("Today · Day \(day)", "今天 · 第 \(day) 天"))
            primary(language.text("Ask Lio about today", "和 Lio 聊聊今天去哪"), "lio.trip-home.now.chat") { openChat() }
        } else {
            nowText(language.text("That’s everything for today", "今天的安排都走完了"),
                    language.text("Today · Day \(day)", "今天 · 第 \(day) 天"))
            secondary(language.text("See today", "查看今天"), "lio.trip-home.now.today") { path.append(.schedule) }
        }
    }

    @ViewBuilder private func backToHotelCard(saved: Bool) -> some View {
        if saved, let hotel {
            nowText(language.text("Back to your hotel", "回酒店"),
                    language.text("\(hotel.place.nameEN) · \(hotel.place.nameZH)", hotel.place.nameZH))
            if taxiEntry != nil {
                primary(language.text("Taxi back", "打车回酒店"), "lio.trip-home.now.taxi") { sheet = .taxi }
            }
            secondary(language.text("Show the driver", "给司机看"), "lio.trip-home.now.driver") { sheet = .driver }
        } else {
            nowText(language.text("Back to your hotel", "回酒店"),
                    language.text("Set your hotel once, then get back with one tap.", "设好住的酒店，以后一键回去。"))
            primary(language.text("Set my hotel", "设置我的酒店"), "lio.trip-home.now.set-hotel") { path.append(.hotel) }
        }
    }

    private func nowText(_ title: String, _ detail: String?) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            Text(title)
                .font(LioTheme.display(.title2).weight(.semibold))
                .foregroundStyle(LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let detail {
                Text(detail).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func progress(_ done: Int, _ total: Int) -> some View {
        ProgressView(value: Double(done), total: Double(max(total, 1)))
            .tint(LioTheme.jade)
            .accessibilityLabel(language.text("Progress", "进度"))
            .accessibilityValue(language.text("\(done) of \(total)", "\(done)/\(total)"))
    }

    private func primary(_ title: String, _ identifier: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) { Text(title).multilineTextAlignment(.center) }
            .buttonStyle(LioPrimaryButtonStyle())
            .accessibilityIdentifier(identifier)
    }

    private func secondary(_ title: String, _ identifier: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) { Text(title).multilineTextAlignment(.center) }
            .buttonStyle(LioSecondaryButtonStyle())
            .accessibilityIdentifier(identifier)
    }

    // MARK: - Tasks

    @ViewBuilder private func taskGroup(_ stage: LioTripStage, _ list: LioTripChecklist) -> some View {
        let tasks = list.tasks(in: stage)
        if !tasks.isEmpty {
            let open = tasks.filter { !$0.isDone }
            let done = tasks.filter(\.isDone)
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                HStack(alignment: .firstTextBaseline) {
                    Text(LioTripHomeCopy.stage(stage, language))
                        .font(LioTheme.display(.title3).weight(.semibold))
                        .foregroundStyle(LioTheme.ink)
                        .accessibilityAddTraits(.isHeader)
                    Spacer(minLength: LioTheme.Spacing.xs)
                    Text(language.text("\(open.count) to do", "\(open.count) 项待办"))
                        .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                }
                ForEach(open) { task in taskRow(task) }
                if !done.isEmpty {
                    if shownDone.contains(stage) {
                        ForEach(done) { task in taskRow(task) }
                        foldButton(language.text("Hide done", "收起已完成"), "lio.trip-home.done.\(stage.rawValue)") {
                            shownDone.remove(stage)
                        }
                    } else {
                        foldButton(LioTripHomeCopy.doneCount(done.count, language), "lio.trip-home.done.\(stage.rawValue)") {
                            shownDone.insert(stage)
                        }
                    }
                }
            }
            .accessibilityIdentifier("lio.trip-home.stage.\(stage.rawValue)")
        }
    }

    /// Stages already behind the traveller, as one line at the end (JT 2026-11-25); it opens to their groups.
    @ViewBuilder private func pastStages(_ list: LioTripChecklist) -> some View {
        let tasks = list.pastTasks
        if !tasks.isEmpty {
            let open = tasks.filter { !$0.isDone }.count
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                Button { showsPast.toggle() } label: {
                    HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xs) {
                        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                            Text(language.text("Earlier stages", "之前的阶段"))
                                .font(.headline).foregroundStyle(LioTheme.ink)
                            Text(LioTripHomeCopy.pastSummary(open: open, done: tasks.count - open, language))
                                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                        }
                        Spacer(minLength: LioTheme.Spacing.xs)
                        Image(systemName: showsPast ? "chevron.up" : "chevron.down")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(LioTheme.inkSecondary)
                            .accessibilityHidden(true)
                    }
                    .padding(LioTheme.Spacing.sm)
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                    .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .combine)
                .accessibilityValue(showsPast ? language.text("Expanded", "已展开") : language.text("Collapsed", "已收起"))
                .accessibilityIdentifier("lio.trip-home.past")
                if showsPast {
                    ForEach(LioTripStage.allCases.filter { $0 < list.phase.stage }, id: \.self) { stage in
                        taskGroup(stage, list)
                    }
                }
            }
        }
    }

    private func foldButton(_ title: String, _ identifier: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: "chevron.down")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(LioTheme.inkSecondary)
                .frame(minHeight: 44, alignment: .leading)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(identifier)
    }

    private func taskRow(_ task: LioTripTask) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: LioTheme.Spacing.xs))
            : AnyLayout(HStackLayout(alignment: .top, spacing: LioTheme.Spacing.sm))
        return layout {
            HStack(alignment: .top, spacing: LioTheme.Spacing.sm) {
                tickControl(task)
                taskText(task)
            }
            if !typeSize.isAccessibilitySize { Spacer(minLength: 0) }
            Button { open(task) } label: {
                Text(task.isDone ? language.text("View", "查看") : LioTripHomeCopy.go(language))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(task.isDone ? LioTheme.inkSecondary : LioTheme.vermilion)
                    .padding(.horizontal, LioTheme.Spacing.sm)
                    .frame(minWidth: 44, minHeight: 44)
                    .background(LioTheme.surfaceSunken, in: Capsule())
            }
            .buttonStyle(.plain)
            .accessibilityLabel((task.isDone ? language.text("View: ", "查看：") : language.text("Go: ", "去办："))
                                + LioTripHomeCopy.title(task, language))
            .accessibilityIdentifier("lio.trip-home.go.\(task.key)")
        }
        .padding(LioTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("lio.trip-home.task.\(task.key)")
    }

    @ViewBuilder private func tickControl(_ task: LioTripTask) -> some View {
        let symbol = task.isDone ? "checkmark.circle.fill" : (task.tick == .statusOnly ? "circle.dotted" : "circle")
        let image = Image(systemName: symbol)
            .font(.title2)
            .foregroundStyle(task.isDone ? LioTheme.jade : LioTheme.inkSecondary)
            .frame(width: 44, height: 44)
        switch task.tick {
        case .manual, .arrivalStep:
            Button { tick(task) } label: { image.contentShape(Rectangle()) }
                .buttonStyle(.plain)
                .accessibilityLabel(LioTripHomeCopy.title(task, language))
                .accessibilityValue(LioTripHomeCopy.status(task, language))
                .accessibilityHint(language.text("Double-tap to tick or untick.", "轻点两下勾选或取消。"))
                .accessibilityIdentifier("lio.trip-home.tick.\(task.key)")
        case .statusOnly:
            image
                .accessibilityElement()
                .accessibilityLabel(LioTripHomeCopy.title(task, language))
                .accessibilityValue(task.isDone ? LioTripHomeCopy.status(task, language)
                                    : language.text("Done once it is saved in the tool", "在工具里存好后自动完成"))
                .accessibilityIdentifier("lio.trip-home.tick.\(task.key)")
        }
    }

    private func taskText(_ task: LioTripTask) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            Text(LioTripHomeCopy.title(task, language))
                .font(.headline)
                .foregroundStyle(task.isDone ? LioTheme.inkSecondary : LioTheme.ink)
                .strikethrough(task.isDone, color: LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(LioTripHomeCopy.detail(task, language))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if case .booking(let id, _, _, let reminderSet) = task.kind {
                if reminderSet {
                    Label(LioTripHomeCopy.reminderSet(language), systemImage: "bell.fill")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(LioTheme.jade)
                }
                if let source = LioTripHomeCopy.bookingSource(id: id, language) {
                    Text(source).font(.caption).foregroundStyle(LioTheme.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .accessibilityElement(children: .combine)
    }

    // MARK: - Day by day

    @ViewBuilder private func schedule(_ list: LioTripChecklist) -> some View {
        if list.phase != .ended || list.plan == nil {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                Text(language.text("Day by day", "日程"))
                    .font(LioTheme.display(.title3).weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
                if let plan = list.plan {
                    Text(plan.title).font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary)
                    ForEach(list.schedule) { day in scheduleDay(day) }
                    secondary(language.text("See all \(plan.days.count) days", "查看完整日程（共 \(plan.days.count) 天）"),
                              "lio.trip-home.schedule.all") { path.append(.schedule) }
                } else {
                    Text(language.text("No day-by-day plan yet. Lio can plan it with you.", "还没有按天的安排，可以请 Lio 一起排。"))
                        .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    secondary(language.text("Plan with Lio", "和 Lio 规划"), "lio.trip-home.schedule.chat") { openChat() }
                }
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .accessibilityIdentifier("lio.trip-home.schedule")
        }
    }

    private func scheduleDay(_ day: LioTripScheduleDay) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            HStack(spacing: LioTheme.Spacing.xs) {
                Text([language.text("Day \(day.number)", "第 \(day.number) 天"),
                      day.date.map { LioTripHomeCopy.dayText($0, language) }].compactMap { $0 }.joined(separator: " · "))
                    .font(.headline).foregroundStyle(LioTheme.ink)
                if day.isToday {
                    Text(language.text("Today", "今天"))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(LioTheme.onVermilion)
                        .padding(.horizontal, LioTheme.Spacing.xs)
                        .padding(.vertical, 2)
                        .background(LioTheme.vermilion, in: Capsule())
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.isHeader)
            if day.stops.isEmpty {
                Text(language.text("Nothing planned yet.", "这一天还没有安排。")).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
            ForEach(Array(day.stops.prefix(4).enumerated()), id: \.offset) { _, stop in
                HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.sm) {
                    Text(stop.time ?? "—")
                        .font(.footnote.monospacedDigit())
                        .foregroundStyle(LioTheme.inkSecondary)
                        .frame(minWidth: 44, alignment: .leading)
                    Text(stop.name).font(.body).foregroundStyle(LioTheme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityElement(children: .combine)
            }
            if day.stops.count > 4 {
                Text(language.text("\(day.stops.count - 4) more", "还有 \(day.stops.count - 4) 个地点"))
                    .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
        }
        .accessibilityIdentifier("lio.trip-home.schedule.day.\(day.number)")
    }

    // MARK: - Tools for this trip

    private struct Shortcut: Identifiable {
        let id: String
        let symbol: String
        let title: String
        let page: Page
    }

    private var shortcutItems: [Shortcut] {
        var items: [Shortcut] = []
        if tools.arrival != nil {
            items.append(.init(id: "arrival", symbol: "airplane.arrival", title: language.text("Arrival Mode", "落地模式"), page: .arrival))
        }
        if tools.hotelStore != nil {
            items.append(.init(id: "hotel", symbol: "bed.double", title: language.text("Back to Hotel", "回酒店"), page: .hotel))
        }
        if tools.roadbooks {
            items.append(.init(id: "roadbook", symbol: "book.closed", title: language.text("Offline & export", "离线与导出"), page: .roadbook))
        }
        return items
    }

    @ViewBuilder private var shortcuts: some View {
        let items = shortcutItems
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                Text(language.text("For this trip", "这趟旅行用得上"))
                    .font(LioTheme.display(.title3).weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: LioTheme.Spacing.sm, alignment: .top),
                                         count: typeSize.isAccessibilitySize ? 1 : 2), spacing: LioTheme.Spacing.sm) {
                    ForEach(items) { item in
                        Button { path.append(item.page) } label: {
                            HStack(spacing: LioTheme.Spacing.sm) {
                                Image(systemName: item.symbol)
                                    .font(.body.weight(.semibold))
                                    .foregroundStyle(LioTheme.vermilion)
                                    .frame(width: 32, height: 32)
                                    .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                                    .accessibilityHidden(true)
                                Text(item.title).font(.headline).foregroundStyle(LioTheme.ink)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 0)
                            }
                            .padding(LioTheme.Spacing.sm)
                            .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
                            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                            .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("lio.trip-home.tool.\(item.id)")
                    }
                }
            }
        }
    }

    // MARK: - Navigation, sheets, toolbar

    @ViewBuilder private func destination(_ page: Page) -> some View {
        let now = fixedNow ?? .now
        switch page {
        case .task(let key):
            if let task = checklist(at: now).tasks.first(where: { $0.key == key }) {
                LioTripTaskPage(task: task, language: language, profile: model.profile, tools: tools, now: now)
            } else {
                ContentUnavailableView(language.text("This is no longer on your list", "这件事已经不在清单上了"),
                                       systemImage: "checklist")
            }
        case .schedule:
            if let plan = checklist(at: now).plan {
                LioItineraryTimelineView(itinerary: plan.itinerary, language: language, startDate: plan.startDate)
            }
        case .arrival:
            if let arrival = tools.arrival { arrival.checklistPage(model.profile) }
        case .hotel:
            LioReturnHotelView(language: language, store: tools.hotelStore, detailsStore: tools.detailsStore, taxiEntry: taxiEntry)
        case .roadbook:
            LioRoadbookLibraryView(language: language, store: tools.roadbookStore,
                                   candidates: plans.map { LioRoadbook(savedPlan: $0) })
        }
    }

    @ViewBuilder private func sheetContent(_ sheet: Sheet) -> some View {
        switch sheet {
        case .start, .edit:
            LioTripHomeStartSheet(language: language, initial: sheet == .edit ? model.profile : nil,
                                  nationality: $nationality) { profile in
                if sheet == .edit { model.update { $0 = profile } } else { model.start(profile) }
            }
        case .taxi:
            if let taxiEntry, let hotel {
                NavigationStack {
                    LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                                recentStore: taxiEntry.recentStore, destination: hotel.place)
                }
            }
        case .driver:
            if let hotel {
                LioDriverSign(language: language, nameZH: hotel.place.nameZH, nameEN: hotel.place.nameEN,
                              addressZH: hotel.place.addressZH, requestZH: LioStayHotel.driverRequestZH,
                              identifierPrefix: "lio.trip-home.driver")
            }
        }
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .principal) { Color.clear.frame(width: 1, height: 1).accessibilityHidden(true) }
        ToolbarItem(placement: .topBarTrailing) {
            Button(language.text("All trips", "所有行程"), action: showAllTrips)
                .accessibilityIdentifier("lio.trip-home.all-trips")
        }
        if model.profile != nil {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button { sheet = .edit } label: {
                        Label(language.text("Edit dates and city", "修改日期和城市"), systemImage: "calendar")
                    }
                    Button(role: .destructive) { confirmsEnd = true } label: {
                        Label(language.text("End this trip", "结束这趟旅行"), systemImage: "flag.checkered")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle").frame(minWidth: 44, minHeight: 44)
                }
                .accessibilityLabel(language.text("Trip options", "旅行选项"))
                .accessibilityIdentifier("lio.trip-home.menu")
            }
        }
    }
}
#endif
