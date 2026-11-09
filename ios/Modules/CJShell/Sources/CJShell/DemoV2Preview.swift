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
    @State private var fixtureConversation: String?
    @State private var fixtureTurn: PreviewTurn?
    @State private var newConversationRequested = false
    @State private var nextFailure: DemoV2DeliveryNotice?
    @State private var deliveryNotice: DemoV2DeliveryNotice?
    @State private var unresolved: DemoV2Dialogue.OriginalMessage?
    @State private var history: [HistoryEntry] = []
    @State private var activeCard: DemoV2Message?
    @State private var trip: [DemoV2Day] = []
    @State private var memory: String?
    @State private var memoryPaused = false
    @State private var confirmingMemoryDeletion = false
    @State private var edit: Edit?
    @State private var editText = ""
    @State private var needsCorrection: String?
    @State private var editingNeeds = false
    @State private var editingPlan = false

    private enum Page { case invite, consent, conversation }
    private enum Edit: String, Identifiable {
        case afternoon, memory, history
        var id: Self { self }
    }

    private struct HistoryEntry: Identifiable {
        let id: String
        let messages: [DemoV2Message]
        let draft: String
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
                        VStack(spacing: 0) {
                            previewBanner
                            DemoV2ConversationView(language: language, messages: messages, activeCardID: activeCard?.id,
                                                   draft: $draft,
                                                   canSend: canSend,
                                                   onSend: send, onAction: handle,
                                                   deliveryNotice: deliveryNotice, onCheckOriginal: checkOriginal)
                        }
                            .navigationTitle(ShellTab.assistant.title(language))
                            .navigationBarTitleDisplayMode(.inline)
                            .toolbar {
                                ToolbarItem(placement: .topBarLeading) {
                                    Menu {
                                        Button(language.text("New chat", "新对话"), systemImage: "square.and.pencil", action: startNewChat)
                                            .disabled(unresolved != nil)
                                        Button(language.text("History", "历史对话"), systemImage: "clock") {
                                            edit = .history
                                        }
                                        .disabled(unresolved != nil)
                                        Menu(language.text("Sample result for next send", "下次发送使用样例结果")) {
                                            Button(language.text("Network unavailable", "网络不可用")) { nextFailure = .offline }
                                            Button(language.text("Daily limit", "每日额度用完")) { nextFailure = .dailyLimit }
                                            Button(language.text("Unknown result", "结果未知")) { nextFailure = .unknown }
                                            Button(language.text("Request failed", "请求失败")) { nextFailure = .rejected }
                                        }
                                        .disabled(unresolved != nil)
                                    } label: {
                                        Label(language.text("Conversation", "对话"), systemImage: "ellipsis.circle")
                                    }
                                }
                                ToolbarItem(placement: .topBarTrailing) { languageMenu }
                            }
                    }
                    .tabItem { Label(ShellTab.assistant.title(language), systemImage: "bubble.left.and.bubble.right") }
                    .tag(ShellTab.assistant)
                    NavigationStack { trips }
                        .tabItem { Label(ShellTab.trips.title(language), systemImage: "map") }
                        .tag(ShellTab.trips)
                    NavigationStack {
                        VStack {
                            previewBanner
                            Text(language.text("Coming soon", "尚未开放"))
                            Spacer()
                        }
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
        .environment(\.locale, Locale(identifier: language.rawValue))
        .sheet(item: $edit) { field in
            if field == .history {
                historySheet
            } else {
                editSheet(field)
            }
        }
    }

    private func editSheet(_ field: Edit) -> some View {
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

    private var historySheet: some View {
        NavigationStack {
            List {
                if history.allSatisfy({ $0.id == fixtureConversation }) {
                    RunReadableText(text: language.text("No previous conversations", "还没有历史对话"))
                }
                ForEach(history.filter { $0.id != fixtureConversation }) { entry in
                    Button {
                        openHistory(entry)
                    } label: {
                        RunReadableText(text: entry.messages.first(where: \.fromUser)?.text ?? language.text("Conversation", "对话"))
                            .frame(minHeight: 44, alignment: .leading)
                    }
                }
            }
            .navigationTitle(language.text("History", "历史对话"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(language.text("Done", "完成")) { edit = nil }
                }
            }
        }
    }

    private var previewBanner: some View {
        Text(language.text("Local preview · scripted sample data", "本地预览 · 合成示例"))
            .font(.caption.weight(.semibold))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
    }

    private var onboarding: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                previewBanner
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
        let afternoon = trip.lazy.flatMap(\.stops).first(where: { $0.id == "gallery" && $0.locked == false })
        return ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                previewBanner
                DemoV2TripsView(language: language, days: trip, onPlan: { shell.selectedTab = .assistant },
                               onEdit: afternoon.map { stop in
                                   {
                                       editText = stop.place
                                       edit = .afternoon
                                   }
                               },
                               onAsk: {
                                   shell.selectedTab = .assistant
                                   draft = language.text("Change the second afternoon to a walk.", "把第二天下午换成散步。")
                               })
            }
            .padding(16)
        }
        .navigationTitle(ShellTab.trips.title(language))
    }

    private var memories: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                previewBanner
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
                        confirmingMemoryDeletion = true
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
        .confirmationDialog(language.text("Delete this preference?", "删除这个偏好吗？"),
                            isPresented: $confirmingMemoryDeletion, titleVisibility: .visible) {
            Button(language.text("Delete preference", "确认删除"), role: .destructive) {
                memory = nil
                memoryPaused = false
            }
            Button(language.text("Cancel", "取消"), role: .cancel) {}
        }
    }

    private var canSend: Bool {
        unresolved == nil && deliveryNotice != .dailyLimit &&
            !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func archiveCurrent() {
        guard let fixtureConversation, !messages.isEmpty else { return }
        history.removeAll { $0.id == fixtureConversation }
        history.insert(.init(id: fixtureConversation, messages: messages, draft: draft), at: 0)
    }

    private func openHistory(_ entry: HistoryEntry) {
        guard unresolved == nil else { return }
        archiveCurrent()
        fixtureConversation = entry.id
        fixtureTurn = nil
        messages = entry.messages
        draft = entry.draft
        activeCard = nil
        newConversationRequested = false
        editingNeeds = false
        editingPlan = false
        if deliveryNotice != .dailyLimit { deliveryNotice = nil }
        edit = nil
    }

    private func startNewChat() {
        guard unresolved == nil else { return }
        archiveCurrent()
        messages.removeAll()
        activeCard = nil
        draft = ""
        fixtureConversation = nil
        fixtureTurn = nil
        newConversationRequested = true
        if deliveryNotice != .dailyLimit { deliveryNotice = nil }
        editingNeeds = false
        editingPlan = false
    }

    private func send() {
        guard canSend, let original = try? makeOriginal() else { return }
        if let nextFailure {
            self.nextFailure = nil
            deliveryNotice = nextFailure
            if nextFailure == .unknown { unresolved = original }
            return
        }
        guard let turn = try? PreviewTurn(original: original) else { return }
        deliveryNotice = nil
        fixtureConversation = turn.receipt.conversation_id
        fixtureTurn = turn
        newConversationRequested = false
        let text = turn.original.command.text
        messages.append(.init(id: turn.receipt.message_id, fromUser: true, text: text))
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
        } else if query.contains("preference") || query.contains("sights per day") || query.contains("偏好") || query.contains("几个景点") {
            reply(memoryPaused ? noSavedPreference : memory ?? noSavedPreference)
        } else {
            showSampleReply(for: turn)
        }
    }

    private func makeOriginal() throws -> DemoV2Dialogue.OriginalMessage {
        let destination = newConversationRequested ? .newConversation
            : fixtureConversation.map(DemoV2Dialogue.Destination.conversation) ?? .initial
        return try .init(.init(id: UUID(), text: draft, language: language, destination: destination))
    }

    private func checkOriginal() {
        guard let unresolved else { return }
        // Exercise the actual null-envelope decoder using the fixture. There is no I/O.
        let raw = Data(#"{"version":"DEMO-dialogue-receipt.1","request_id":"fixture","receipt":null}"#.utf8)
        if case .notObserved? = try? DemoV2Dialogue.response(raw, status: 200, contentType: "application/json",
                                                            original: unresolved, operation: .reconcile) {
            deliveryNotice = .notObserved
        }
    }

    private var noSavedPreference: String {
        language.text("There’s no active saved preference for this sample.", "这个示例没有启用中的已保存偏好。")
    }

    private func showSampleReply(for turn: PreviewTurn) {
        do {
            let status = try turn.event("status", payload: ["stage": "completed", "status": "completed"])
            let answer = try turn.event("answer_delta", payload: [
                "text": language.text("For the metro, check the station’s route map before boarding.", "乘地铁前，可以先看站内线路图。")
            ])
            let source = try turn.event("source", payload: [
                "source_id": "sample-transport", "label": language.text("Source 1", "来源 1"), "state": "unknown"
            ])
            var projection = DemoV2RunProjection()
            [answer, source, status].forEach { projection.apply($0) }
            let citations = projection.sources.map { citation in
                DemoV2Source(id: citation.source_id, title: citation.label,
                             details: language.text("This sample has no verified external source.", "此示例没有已核实的外部来源。"),
                             link: citation.openableURL)
            }
            reply(projection.answer, status: projection.activity(language), sources: citations)
        } catch {
            reply(language.text("The local fixture did not produce a readable result.", "本地样例没有产生可读取的结果。"))
        }
    }

    private func handle(_ id: String, _ action: DemoV2CardAction) {
        guard let activeCard, activeCard.id == id else { return }
        self.activeCard = nil
        switch (activeCard.card, action) {
        case (.needs, .confirmNeeds):
            showSampleTrip()
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
        guard let index = trip.firstIndex(where: { $0.stops.contains(where: { $0.id == "gallery" }) }) else { return }
        let day = trip[index]
        let stops = day.stops.map { stop in
            guard stop.id == "gallery", stop.locked == false else { return stop }
            return DemoV2Day.Stop(id: stop.id, time: stop.time, place: place, source: stop.source, location: stop.location)
        }
        trip[index] = .init(id: day.id, title: day.title, stops: stops, date: day.date)
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

    private func showSampleTrip() {
        guard let fixtureTurn else { return }
        do {
            func stop(_ id: String, label: String, place: String?, start: String, end: String, fixed: Bool?) -> [String: Any] {
                [
                    "item_id": id, "label": label, "place": place.map { $0 as Any } ?? NSNull(),
                    "starts_at": start, "ends_at": end, "time_zone": "Asia/Shanghai",
                    "source_ids": ["sample"], "fixed": fixed.map { $0 as Any } ?? NSNull()
                ]
            }
            let days: [[String: Any]] = [
                ["date": "2026-11-10", "items": [
                    stop("arrival", label: language.text("Arrive in Beijing", "抵达北京"), place: "Beijing",
                         start: "2026-11-10T14:00", end: "2026-11-10T15:00", fixed: false)
                ]],
                ["date": "2026-11-11", "items": [
                    stop("meeting", label: language.text("Hotel lobby meeting", "酒店大堂集合"),
                         place: language.text("Hotel lobby", "酒店大堂"),
                         start: "2026-11-11T09:00", end: "2026-11-11T10:00", fixed: true),
                    stop("gallery", label: language.text("Visit a gallery", "参观展馆"), place: nil,
                         start: "2026-11-11T14:00", end: "2026-11-11T15:00", fixed: false)
                ]],
                ["date": "2026-11-12", "items": [
                    stop("departure", label: language.text("Leave Beijing", "离开北京"), place: nil,
                         start: "2026-11-12T16:00", end: "2026-11-12T17:00", fixed: nil)
                ]]
            ]
            let event = try fixtureTurn.event("trip_candidate", payload: [
                "card_id": "sample-trip-card", "version": 1, "status": "pending", "proposal_id": "sample-proposal",
                "trip_id": NSNull(), "expected_trip_version": NSNull(), "candidate_hash": String(repeating: "a", count: 64),
                "days": days
            ])
            guard case .trip(let candidate) = event.payload else { throw DemoV2Dialogue.Failure.invalidEvent }
            let source = language.text("Fictional itinerary example", "虚构行程示例")
            let projection = candidate.displayedDays(language: language, sourceLabels: ["sample": source])
            reply(language.text("Here’s a three-day suggestion.", "这是一份三天行程建议。"), card: .itinerary(projection))
        } catch {
            reply(language.text("The local itinerary sample couldn’t be read.", "无法读取本地行程样例。"))
        }
    }

    private func button(_ title: String, symbol: String, prominent: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) { ShellActionLabel(title: title, symbol: symbol) }
            .buttonStyle(ShellActionButtonStyle(emphasized: prominent))
    }
}

private struct PreviewTurn {
    let original: DemoV2Dialogue.OriginalMessage
    let receipt: DemoV2Dialogue.Receipt

    init(original: DemoV2Dialogue.OriginalMessage) throws {
        let command = original.command
        self.original = original
        let raw = try JSONSerialization.data(withJSONObject: [
            "version": "DEMO-dialogue-receipt.1", "request_id": UUID().uuidString,
            "receipt": [
                "message_id": command.message_id,
                "conversation_id": command.conversation_id ?? "demo-dialogue-" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased(),
                "run_id": UUID().uuidString.lowercased(),
                "input_sha256": original.sha256
            ]
        ])
        guard case .accepted(let receipt) = try DemoV2Dialogue.response(
            raw, status: 200, contentType: "application/json", original: original, operation: .submit
        ) else { throw DemoV2Dialogue.Failure.invalidResponse }
        self.receipt = receipt
    }

    func event(_ kind: String, payload: [String: Any]) throws -> DemoV2Dialogue.Event {
        let data = try JSONSerialization.data(withJSONObject: [
            "version": "DEMO-dialogue-event.1", "event_id": UUID().uuidString.lowercased(),
            "conversation_id": receipt.conversation_id, "message_id": receipt.message_id,
            "run_id": receipt.run_id, "kind": kind, "payload": payload
        ])
        let event = try JSONDecoder().decode(DemoV2Dialogue.Event.self, from: data)
        try event.checkOriginal(receipt)
        return event
    }
}
#endif
