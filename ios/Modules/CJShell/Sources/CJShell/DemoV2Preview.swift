#if DEBUG && os(iOS) && targetEnvironment(simulator)
import SwiftUI
import CJRunClient

/// Local scripted preview. This entry has no session, transport or persistent storage.
public struct DemoV2Preview: View {
    @Bindable private var shell: ShellState
    @State private var page: Page = .invite
    @State private var invite = ""
    @State private var draft = ""
    @State private var messages: [DemoV2Message] = []
    @State private var activeCard: DemoV2Message?
    @State private var trip: [DemoV2Day] = []
    @State private var memory: String?
    @State private var memoryPaused = false
    @State private var edit: Edit?
    @State private var editText = ""
    @State private var needsCorrection: String?
    @State private var editingNeeds = false
    @State private var editingPlan = false

    private enum Page { case invite, consent, conversation }
    private enum Edit: String, Identifiable {
        case afternoon, memory
        var id: Self { self }
    }

    public init(shell: ShellState) { self.shell = shell }

    private var language: ShellLanguage { shell.language }

    public var body: some View {
        Group {
            switch page {
            case .invite, .consent:
                NavigationStack { onboarding }
            case .conversation:
                TabView(selection: $shell.selectedTab) {
                    NavigationStack {
                        DemoV2ConversationView(language: language, messages: messages, activeCardID: activeCard?.id,
                                               draft: $draft, canSend: !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                                               onSend: send, onAction: handle)
                            .navigationTitle(ShellTab.assistant.title(language))
                            .navigationBarTitleDisplayMode(.inline)
                            .toolbar { ToolbarItem(placement: .topBarTrailing) { languageMenu } }
                    }
                    .tabItem { Label(ShellTab.assistant.title(language), systemImage: "bubble.left.and.bubble.right") }
                    .tag(ShellTab.assistant)
                    NavigationStack { trips }
                        .tabItem { Label(ShellTab.trips.title(language), systemImage: "map") }
                        .tag(ShellTab.trips)
                    NavigationStack {
                        Text(language.text("Coming soon", "尚未开放"))
                            .navigationTitle(ShellTab.plugins.title(language))
                    }
                    .tabItem { Label(ShellTab.plugins.title(language), systemImage: "square.grid.2x2") }
                    .tag(ShellTab.plugins)
                    NavigationStack { memories }
                        .tabItem { Label(ShellTab.memory.title(language), systemImage: "tray") }
                        .tag(ShellTab.memory)
                }
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            Text(language.text("Local preview · scripted sample data", "本地预览 · 合成示例"))
                .font(.caption.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
                .background(.background)
        }
        .environment(\.locale, Locale(identifier: language.rawValue))
        .sheet(item: $edit) { field in
            NavigationStack {
                Form {
                    TextField(field == .memory ? language.text("Preference", "偏好") : language.text("Afternoon plan", "下午安排"),
                              text: $editText)
                }
                .navigationTitle(language.text("Edit", "修改"))
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button(language.text("Cancel", "取消")) { edit = nil }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(language.text("Save", "保存")) {
                            if field == .memory { memory = editText }
                            else { replaceAfternoon(with: editText) }
                            edit = nil
                        }
                        .disabled(editText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
            }
        }
    }

    private var onboarding: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if page == .invite {
                    Text(language.text("Use the sample code DEMO.", "请输入示例邀请码 DEMO。"))
                    TextField(language.text("Invitation code", "邀请码"), text: $invite)
                        .textFieldStyle(.roundedBorder)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                    button(language.text("Sign in", "登录"), symbol: "arrow.right", prominent: true) {
                        invite = ""
                        page = .consent
                    }
                    .disabled(invite != "DEMO")
                } else {
                    RunReadableText(text: language.text(
                        "This is an internal demo. Please use fictional trip details and leave out personal information. Placeholder pending #225.",
                        "本次为内部演示。请使用虚构的旅行信息，勿填写个人信息。待 #225 定案后替换。"))
                    button(language.text("Agree and continue", "同意并继续"), symbol: "checkmark", prominent: true) {
                        page = .conversation
                    }
                    button(language.text("Back", "返回"), symbol: "arrow.left") { page = .invite }
                }
            }
            .shellCard()
            .padding(16)
        }
        .navigationTitle(page == .invite ? language.text("Sign in", "登录") : language.text("Internal demo consent", "内部演示同意"))
        .toolbar { ToolbarItem(placement: .topBarTrailing) { languageMenu } }
    }

    private var languageMenu: some View {
        Menu {
            Button("English") { shell.selectLanguage(.english) }
            Button("简体中文") { shell.selectLanguage(.chinese) }
        } label: {
            Label(language.text("Language", "语言"), systemImage: "globe")
        }
    }

    private var trips: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if trip.isEmpty {
                    ShellCardHeading(title: language.text("No saved trips yet", "还没有已采用的行程"), symbol: "map")
                    button(language.text("Plan a trip", "去规划行程"), symbol: "bubble.left") { shell.selectedTab = .assistant }
                } else {
                    ForEach(trip) { DemoV2DayCard(day: $0, language: language) }
                    if let afternoon = trip.first(where: { $0.id == "2" })?.stops.first(where: { $0.id == "gallery" && !$0.locked }) {
                        button(language.text("Edit itinerary", "直接编辑"), symbol: "pencil") {
                            editText = afternoon.place
                            edit = .afternoon
                        }
                    }
                    button(language.text("Edit with Assistant", "问助手修改"), symbol: "bubble.left") {
                        shell.selectedTab = .assistant
                        draft = language.text("Change the second afternoon to a walk.", "把第二天下午换成散步。")
                    }
                }
            }
            .shellCard()
            .padding(16)
        }
        .navigationTitle(ShellTab.trips.title(language))
    }

    private var memories: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let memory {
                    RunSelectableText(text: memory)
                    button(language.text("Edit preference", "编辑偏好"), symbol: "pencil") {
                        editText = memory
                        edit = .memory
                    }
                    if memoryPaused { Text(language.text("Paused", "已停用")) }
                    button(memoryPaused ? language.text("Resume", "恢复") : language.text("Pause", "停用"),
                           symbol: memoryPaused ? "play" : "pause") { memoryPaused.toggle() }
                    button(language.text("Delete", "删除"), symbol: "trash") {
                        self.memory = nil
                        memoryPaused = false
                    }
                } else {
                    ShellCardHeading(title: language.text("No saved memories yet", "还没有已保存的记忆"), symbol: "bookmark")
                    Text(language.text("You can save a preference in the conversation.", "你可以在对话里确认保存偏好。"))
                }
            }
            .shellCard()
            .padding(16)
        }
        .navigationTitle(ShellTab.memory.title(language))
    }

    private func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        messages.append(.init(id: UUID().uuidString, fromUser: true, text: text))
        draft = ""
        let query = text.lowercased()
        if editingNeeds || query.contains("plan") || query.contains("规划") {
            needsCorrection = editingNeeds ? text : nil
            editingNeeds = false
            reply(language.text("Here’s what I understood. Check the details before I suggest a plan.", "这是我理解的需求，请核对后再生成行程建议。"),
                  card: .needs(details))
        } else if editingPlan || (!trip.isEmpty && (query.contains("change") || query.contains("换成"))) {
            editingPlan = false
            reply("", card: .changes(before: language.text("14:00 · Visit a gallery", "14:00 · 参观展馆"),
                                     after: language.text("14:00 · Take a walk", "14:00 · 散步"),
                                     locked: language.text("09:00 fixed meeting stays unchanged", "09:00 固定集合保留")))
        } else if query.contains("like") || query.contains("喜欢") {
            reply(language.text("I can take that into account when suggesting trips.", "我可以在推荐行程时考虑这个偏好。"),
                  card: .memory(text))
        } else {
            reply(language.text("For the metro, check the station’s route map before boarding.", "乘地铁前，可以先看站内线路图。"),
                  status: language.text("Sample run · checked transport information", "示例运行 · 已核对交通信息"),
                  sources: [.init(id: "sample-transport", title: language.text("Source 1", "来源 1"),
                                  details: language.text("Synthetic transport reference for this local preview.", "此条为本地预览的合成交通引用。"))])
        }
    }

    private func handle(_ id: String, _ action: DemoV2CardAction) {
        guard let activeCard, activeCard.id == id else { return }
        self.activeCard = nil
        switch (activeCard.card, action) {
        case (.needs, .confirmNeeds):
            reply(language.text("Here’s a three-day suggestion.", "这是一份三天行程建议。"), card: .itinerary(sampleTrip))
        case (.needs, .editNeeds):
            editingNeeds = true
            reply(language.text("What would you like to change in your trip details?", "你想修改哪些旅行需求？"))
        case (.itinerary(let days), .adoptTrip):
            trip = days
            reply(language.text("This plan is now in Trips.", "这份行程已出现在行程页。"))
        case (.itinerary, .reviseTrip):
            editingNeeds = true
            reply(language.text("What would you like to change?", "你想改哪些安排？"))
        case (.changes, .applyChange):
            replaceAfternoon(with: language.text("Take a walk", "散步"))
            reply(language.text("Your itinerary has been updated.", "行程已更新。"))
        case (.memory(let text), .remember):
            memory = text
            memoryPaused = false
            reply(language.text("Preference saved.", "偏好已保存。"))
        case (.memory, .dismissMemory):
            reply(language.text("I’ll leave it out of Memory.", "这条不会存入记忆。"))
        default:
            break
        }
    }

    private func reply(_ text: String, status: String? = nil, sources: [DemoV2Source] = [], card: DemoV2Card? = nil) {
        let message = DemoV2Message(id: UUID().uuidString, fromUser: false, text: text, status: status, sources: sources, card: card)
        messages.append(message)
        activeCard = card == nil ? nil : message
    }

    private func replaceAfternoon(with place: String) {
        guard let index = trip.firstIndex(where: { $0.id == "2" }) else { return }
        let day = trip[index]
        let stops = day.stops.map { stop in
            guard stop.id == "gallery", !stop.locked else { return stop }
            return DemoV2Day.Stop(id: stop.id, time: stop.time, place: place, source: stop.source)
        }
        trip[index] = .init(id: day.id, title: day.title, stops: stops)
    }

    private var details: [DemoV2Card.Detail] {
        var result: [DemoV2Card.Detail] = [
            .init(id: "date", label: language.text("Dates", "日期"), value: language.text("3 days · dates to confirm", "三天 · 待确认具体日期")),
            .init(id: "city", label: language.text("City", "城市"), value: language.text("Beijing", "北京")),
            .init(id: "party", label: language.text("Travelers", "人数"), value: language.text("To confirm", "待确认")),
            .init(id: "pace", label: language.text("Pace", "节奏"), value: language.text("Relaxed", "轻松")),
            .init(id: "fixed", label: language.text("Fixed plans", "固定安排"), value: language.text("09:00 meeting on day 2", "第二天 09:00 集合"))
        ]
        if let needsCorrection {
            result.append(.init(id: "correction", label: language.text("Your correction", "你的修改"), value: needsCorrection))
        }
        return result
    }

    private var sampleTrip: [DemoV2Day] {
        let source = language.text("Fictional itinerary example", "虚构行程示例")
        return [
            .init(id: "1", title: language.text("Day 1", "第 1 天"), stops: [
                .init(id: "arrival", time: "14:00", place: language.text("Arrive in Beijing", "抵达北京"), source: source)
            ]),
            .init(id: "2", title: language.text("Day 2", "第 2 天"), stops: [
                .init(id: "meeting", time: "09:00", place: language.text("Hotel lobby meeting", "酒店大堂集合"), source: source, locked: true),
                .init(id: "gallery", time: "14:00", place: language.text("Visit a gallery", "参观展馆"), source: source)
            ]),
            .init(id: "3", title: language.text("Day 3", "第 3 天"), stops: [
                .init(id: "departure", time: "16:00", place: language.text("Leave Beijing", "离开北京"), source: source)
            ])
        ]
    }

    private func button(_ title: String, symbol: String, prominent: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) { ShellActionLabel(title: title, symbol: symbol) }
            .buttonStyle(ShellActionButtonStyle(emphasized: prominent))
    }
}
#endif
