#if os(iOS)
import SwiftUI

/// The Trips tab as this trip's home (行程首页 · 办事清单, phase 1), behind `G2CTripHomeEnabled`.
/// Tasks come from `LioTripChecklist`; "Go" opens the tool that does each one, and coming back re-reads the
/// tools' state on this phone. Saved trips and earlier plans stay one tap away in "All trips".
/// #1979: there is no start page. The page opens on "Your China trip" with the six steps in order; a step that
/// needs an answer (passport, arrival day, hotel level) asks for it when "Go" is tapped.
struct LioTripHome: View {
    let language: LioLanguage
    /// Plans saved on this device (#1453), newest first.
    let plans: [LioPlanSummary]
    /// Saved trips are on this phone but were written by a newer app; they are kept, not shown as none.
    var plansUnreadable = false
    /// The saved-trips store, so a template opened from this Roadbook entry can be used as my trip (#1725).
    var savedPlans: LioSavedPlansModel? = nil
    let tools: LioTripHomeTools
    let showAllTrips: () -> Void
    let openChat: () -> Void
    /// Debug previews pin the clock and the zone; nil follows the phone.
    var fixedNow: Date?
    var timeZone: TimeZone = .current
    @State private var model: LioTripHomeModel
    @LioNationalityBinding private var sharedNationality
    /// Debug previews keep the passport in memory instead of the shared setting (#1665 review P3-3).
    @State private var previewNationality = ""
    /// Set by Debug previews only.
    private let keepsSettingsInMemory: Bool
    /// #1995: `G2CTripCanvasEnabled`. Off, nothing on this page changes.
    private let canvasEnabled: Bool
    private let canvasStore: LioTripCanvasStore?
    private var nationality: Binding<String> { keepsSettingsInMemory ? $previewNationality : $sharedNationality }
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @Environment(\.lioMedicalCard) private var medicalCard
    @Environment(\.lioHotelFinder) private var hotelFinder
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.colorScheme) private var colorScheme
    @Environment(LioRouter.self) private var router: LioRouter?
    @Environment(\.openURL) private var openURL
    @State private var path: [Page] = []
    @State private var refresh = 0
    @State private var hotel: LioStayHotel?
    @State private var reminders: Set<String> = []
    @State private var sheet: Sheet?
    @State private var showsMedicalCard = false
    @State private var confirmsEnd = false
    @State private var shownDone: Set<LioTripStage> = []
    @State private var showsPast = false
    /// What to do once the sheet that asked a question has closed (#1979).
    @State private var after: After?

    enum Page: Hashable { case task(String), schedule, arrival, hotel, roadbook, canvas }
    private enum Sheet: String, Identifiable {
        case edit, taxi, driver, passport, arrival, stay
        var id: Self { self }
    }
    private enum After { case entryPage, hotelSearch }

    init(language: LioLanguage, store: LioTripHomeStore?, plans: [LioPlanSummary], plansUnreadable: Bool = false,
         savedPlans: LioSavedPlansModel? = nil, tools: LioTripHomeTools,
         showAllTrips: @escaping () -> Void, openChat: @escaping () -> Void,
         fixedNow: Date? = nil, timeZone: TimeZone = .current, model: LioTripHomeModel? = nil,
         keepsSettingsInMemory: Bool = false, canvasEnabled: Bool = LioTripCanvasFeature.enabledInBuild) {
        self.language = language
        self.keepsSettingsInMemory = keepsSettingsInMemory
        self.canvasEnabled = canvasEnabled
        canvasStore = canvasEnabled ? LioTripCanvasStore(tripHome: store) : nil
        self.plans = plans
        self.plansUnreadable = plansUnreadable
        self.savedPlans = savedPlans
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
                        if plansUnreadable { newerPlansNotice }
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
        .sheet(item: $sheet, onDismiss: { refresh += 1; continueAfterSheet() }) { sheet in sheetContent(sheet) }
        .fullScreenCover(isPresented: $showsMedicalCard, onDismiss: { refresh += 1 }) {
            if let medicalCard {
                NavigationStack { LioMedicalCardView(language: language, storage: medicalCard, opensDisplay: false) }
            }
        }
        .confirmationDialog(language.text("End this trip?", "结束这趟旅行？"), isPresented: $confirmsEnd, titleVisibility: .visible) {
            Button(language.text("End trip", "结束旅行"), role: .destructive) {
                model.end(plan: checklist(at: fixedNow ?? .now).plan?.tripID)
                // #1741: a new trip starts with Arrival Mode's checklist unticked.
                tools.arrival?.clearProgress()
            }
            Button(language.text("Cancel", "取消"), role: .cancel) {}
        } message: {
            Text(language.text("This clears the trip’s dates, city and ticks on this phone. Saved plans and what you keep in the tools stay.",
                               "会清掉这趟旅行在手机上的日期、城市和勾选。已保存的行程和各工具里的内容都保留。"))
        }
    }

    /// The saved trips need a newer app; they stay on this phone untouched.
    private var newerPlansNotice: some View {
        Label(language.text("Your saved trips were saved by a newer version of the app. Update the app to see them; they stay on this phone.",
                            "已保存的行程来自更新版本的 App。请更新 App 后查看；行程仍保存在手机上。"),
              systemImage: "arrow.down.app")
            .font(.subheadline).foregroundStyle(LioTheme.ink)
            .accessibilityIdentifier("lio.trip-home.plans-newer-version")
    }

    // MARK: - State

    private func checklist(at date: Date) -> LioTripChecklist {
        LioTripChecklist(.init(
            now: date, timeZone: timeZone, profile: model.profile, plans: plans, endedPlanIDs: model.endedPlanIDs, ticks: model.ticks,
            entry: tools.arrival?.entry(model.profile, nationality.wrappedValue, date),
            arrivalChecklist: tools.arrival?.checklist(),
            hotelSaved: tools.hotelStore == nil ? nil : hotel != nil,
            showCards: tools.showCards,
            attractionBooking: tools.reminders != nil,
            scheduledReminders: reminders,
            reminderScope: tools.reminders?.scope ?? LioAttractionReminderScope(account: nil),
            business: tools.business,
            routableTools: routableTools))
    }

    /// The tools the router can open here (#1765, #1979), as trip places decide it (#1740): the Tools tab must be
    /// shown and the tool visible in this build.
    private var routableTools: Set<LioTool> {
        guard router?.toolsShown == true else { return [] }
        var context = LioToolContext(language: language)
        context.taxiEntry = taxiEntry
        context.hotelFinder = hotelFinder
        return Set(LioToolCatalog.visible(context.availability()))
    }

    private func readTools() async {
        model.reload()
        hotel = tools.savedHotel()
        if let scheduler = tools.reminders { reminders = Set(await scheduler.scheduled().map(\.id)) }
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
        switch task.kind {
        case .business(let business):
            switch business.action {
            case .officialPage(let url): openURL(url)
            case .route(let route): router?.open(route)
            case nil: return
            }
        case .medicalCard where medicalCard != nil:
            showsMedicalCard = true
        // #1979: a step that needs an answer asks for it first, once.
        case .entry where nationality.wrappedValue.isEmpty:
            after = .entryPage
            sheet = .passport
        case .arrival:
            sheet = .arrival
        case .hotel:
            sheet = .stay
        case .local:
            if let route = LioRoute(tool: .metro) { router?.open(route) }
        default:
            path.append(.task(task.key))
        }
    }

    /// The step's page once its question has been answered; closing the question without answering goes nowhere.
    private func continueAfterSheet() {
        guard let next = after else { return }
        after = nil
        switch next {
        case .entryPage:
            if !nationality.wrappedValue.isEmpty { path.append(.task("entry")) }
        case .hotelSearch:
            // The hotel search when this build has it; else Back to Hotel's "my hotel" page, as before.
            if routableTools.contains(.hotels), let route = LioRoute(tool: .hotels) {
                router?.open(route)
            } else if tools.hotelStore != nil {
                path.append(.task("hotel"))
            }
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
            // #1979: with no dates there is nothing to say yet, so no "Before your trip" label.
            if list.phase != .beforeTrip(daysToGo: nil) {
                Label(LioTripHomeCopy.phase(list.phase, language), systemImage: phaseSymbol(list.phase))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                    .padding(.horizontal, LioTheme.Spacing.sm)
                    .padding(.vertical, LioTheme.Spacing.xs)
                    .background(LioTheme.surfaceSunken, in: Capsule())
                    .accessibilityIdentifier("lio.trip-home.phase")
            }
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
                if let next, next.hasGo { primary(LioTripHomeCopy.go(language), "lio.trip-home.now.go") { open(next) } }
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
                if let next, next.hasGo { primary(LioTripHomeCopy.go(language), "lio.trip-home.now.go") { open(next) } }
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
            nowText([next.time, next.name(language)].compactMap { $0 }.joined(separator: " "),
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
                // #1979: the steps of going to China are one ordered list with ticks, with no heading and no count.
                if stage != .beforeTrip {
                    HStack(alignment: .firstTextBaseline) {
                        Text(LioTripHomeCopy.stage(stage, language))
                            .font(LioTheme.display(.title3).weight(.semibold))
                            .foregroundStyle(LioTheme.ink)
                            .accessibilityAddTraits(.isHeader)
                        Spacer(minLength: LioTheme.Spacing.xs)
                        Text(language.text("\(open.count) to do", "\(open.count) 项待办"))
                            .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                    }
                }
                if stage == .beforeTrip {
                    ForEach(tasks) { task in taskRow(task) }
                } else {
                    ForEach(open) { task in taskRow(task) }
                }
                if stage != .beforeTrip, !done.isEmpty {
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
            if task.hasGo {
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

    /// The task's words, read as one element; a sourced business item adds its official links under them (#1765).
    private func taskText(_ task: LioTripTask) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            taskWords(task)
            if case .business(let business) = task.kind, let source = business.source {
                businessSources(source, key: task.key)
            }
        }
    }

    private func taskWords(_ task: LioTripTask) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            Text(LioTripHomeCopy.title(task, language))
                .font(.headline)
                .foregroundStyle(task.isDone ? LioTheme.inkSecondary : LioTheme.ink)
                .strikethrough(task.isDone, color: LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
            let detail = LioTripHomeCopy.detail(task, language)
            if !detail.isEmpty {
                Text(detail)
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
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

    /// A sourced business item's check day and its official pages (#1765), each opened in the browser.
    private func businessSources(_ source: LioTripBusinessTask.Source, key: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(LioTripHomeCopy.businessSource(source, language))
                .font(.caption).foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(Array(source.urls.enumerated()), id: \.offset) { index, url in
                Link(destination: url) {
                    Label(url.host ?? url.absoluteString, systemImage: "arrow.up.right.square")
                        .font(.caption)
                        .frame(minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .foregroundStyle(LioTheme.vermilion)
                .accessibilityIdentifier("lio.trip-home.source.\(key).\(index)")
            }
        }
    }

    // MARK: - Day by day

    @ViewBuilder private func schedule(_ list: LioTripChecklist) -> some View {
        if list.phase != .ended {
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
                    Text(stop.name(language)).font(.body).foregroundStyle(LioTheme.ink)
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
        if canvasEnabled {
            items.append(.init(id: "canvas", symbol: "calendar", title: language.text("Trip canvas", "行程画布"), page: .canvas))
        }
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
        case .schedule where canvasEnabled:
            canvasScreen(checklist(at: now).plan)
        case .canvas:
            canvasScreen(checklist(at: now).plan)
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
                                   candidates: plans.map { LioRoadbook(savedPlan: $0) },
                                   savedPlans: savedPlans)
        }
    }

    /// #1995: the trip canvas of this trip's plan (or its own, with no plan), from the timeline's own entries. The map's
    /// place is left empty here; the map view (#1996) is wired in when it lands.
    private func canvasScreen(_ plan: LioPlanSummary?) -> some View {
        LioTripCanvasScreen(language: language, plan: plan, store: canvasStore, openChat: openChat)
    }

    @ViewBuilder private func sheetContent(_ sheet: Sheet) -> some View {
        switch sheet {
        case .edit:
            if let profile = model.profile {
                LioTripHomeStartSheet(language: language, initial: profile, nationality: nationality,
                                      offersBusiness: tools.business != nil) { profile in
                    model.update { $0 = profile }
                }
            }
        case .passport:
            NavigationStack {
                LioTripNationalityPicker(language: language, selection: nationality,
                                         question: language.text("Which passport do you travel on?", "用哪国护照？"))
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button(language.text("Cancel", "取消")) { self.sheet = nil }
                        }
                    }
            }
        case .arrival:
            LioTripArrivalAsk(language: language, profile: model.profile) { day, number in
                model.updateOrStart { profile in
                    profile.arrival = day
                    profile.arrivalNumber = number
                }
            }
        case .stay:
            LioTripStayAsk(language: language, stars: model.profile?.stayStars) { stars in
                model.updateOrStart { $0.stayStars = stars }
                after = .hotelSearch
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
