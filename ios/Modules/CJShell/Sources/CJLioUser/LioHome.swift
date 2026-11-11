#if os(iOS)
import SwiftUI
import CJMessageHTTP
import CJRunClient
import CJTripClient

public struct LioHome<MenuContent: View>: View {
    private let language: LioLanguage
    private let isDemo: Bool
    private let menu: MenuContent
    private let chatLibrary: LioChatLibrary?
    private let tripLibrary: LioTripLibrary?
    private let memoryActions: LioMemoryActionsClient?
    private let savedMemory: AnyView?
    private let recordedMap: (@MainActor (StructuredTripDocument) -> AnyView)?
    @State private var conversation: LioConversation
    @State private var defaultTripPlan: LioTripPlan?
    @State private var selectedChat: LioChatSession?
    @State private var restoringChat: Bool
    @State private var restoreChatFailed = false
    @State private var restoreChatRequest = 0
    @State private var draft = ""
    @State private var chatDrafts: [Data: String] = [:]
    @State private var menuOpen = false
    @State private var followsAnswer = true
    @State private var opening = Opening.beforeNext
    @State private var didEnterBackground = false
    @State private var tab = Tab.chat
    @State private var tripPath: [LioTripRoute] = []
    @State private var memoryBusy = false
    @State private var memoryPending = false
    @State private var memoryNotice: String?
    @State private var activeMemory: LioMemoryWire.Tag?
    @State private var handledTags: Set<LioMemoryWire.Tag> = []
    @State private var refreshRequest = 0
    @State private var jumpRequest = 0
    @State private var sendCount = 0
    private struct Observation: Equatable {
        let active: Bool
        let request: Int
    }
    private struct TripObservation: Equatable {
        let active: Bool
        let card: LioTripCard?
        let plan: ObjectIdentifier?
    }
    private enum Tab { case chat, trips, memory }
    private enum Opening: Equatable { case beforeNext, before(Data), hidden }
    @FocusState private var typing: Bool
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    public init(language: LioLanguage, service: LioService, isDemo: Bool, chatLibrary: LioChatLibrary? = nil,
                tripLibrary: LioTripLibrary? = nil,
                tripHistory: LioTripHistoryClient? = nil,
                memoryActions: LioMemoryActionsClient? = nil,
                savedMemory: AnyView? = nil,
                recordedMap: (@MainActor (StructuredTripDocument) -> AnyView)? = nil, @ViewBuilder menu: () -> MenuContent) {
        self.language = language
        self.isDemo = isDemo
        self.menu = menu()
        self.chatLibrary = chatLibrary
        self.tripLibrary = tripLibrary
        self.memoryActions = memoryActions
        self.savedMemory = savedMemory
        self.recordedMap = recordedMap
        _conversation = State(initialValue: LioConversation(service: service))
        _defaultTripPlan = State(initialValue: tripHistory.map { LioTripPlan(client: $0) })
        _draft = State(initialValue: chatLibrary?.continuity?.draft ?? "")
        _restoringChat = State(initialValue: chatLibrary?.continuity?.selectedID != nil)
    }

    private var chatID: Data? { selectedChat?.id ?? chatLibrary?.currentID }

    private var tripPlan: LioTripPlan? {
        if chatID == chatLibrary?.currentID { return defaultTripPlan }
        return selectedChat?.trips?.plan
    }

    private var latestTripCard: LioTripCard? {
        guard let turn = conversation.turns.last(where: { $0.itinerary != nil }),
              let itinerary = turn.itinerary else { return nil }
        return LioTripCard(turnID: turn.id, itinerary: itinerary)
    }

    public var body: some View {
        let currentConversation = conversation
        let pending = conversation.pending
        let canObserve = scenePhase == .active && pending == nil && !restoringChat
        let tripCard = latestTripCard
        let tripPlan = tripPlan
        TabView(selection: $tab) {
            chat
                .tabItem { Label(language.text("Chat", "聊天"), systemImage: "bubble.left") }
                .tag(Tab.chat)
            LioTripsView(itineraries: conversation.itineraries, language: language, library: tripLibrary,
                         tripPlan: tripPlan, currentPlan: tripPlan?.current(for: tripCard),
                         canUndo: canObserve && tripPlan?.requestedCard == tripCard,
                         recordedMap: recordedMap, path: $tripPath) { tab = .chat }
                .tabItem { Label(language.text("Trips", "行程"), systemImage: "suitcase") }
                .tag(Tab.trips)
            if let savedMemory {
                savedMemory
                    .tabItem { Label(language.text("Memory", "记忆"), systemImage: "bookmark") }
                    .tag(Tab.memory)
            }
        }
        .tint(LioTheme.vermilion)
        .disabled(restoringChat)
        .opacity(restoringChat ? 0 : 1)
        .overlay {
            if restoringChat {
                VStack(spacing: 20) {
                    if restoreChatFailed {
                        Text(language.text("Couldn’t open your conversation. Try again when you’re connected.", "暂时无法打开对话，请联网后重试。"))
                        Button(language.text("Try again", "重试")) { restoreChatRequest += 1 }
                    } else {
                        ProgressView(language.text("Opening your conversation…", "正在打开你的对话…"))
                    }
                }
                .multilineTextAlignment(.center)
                .padding(28)
                .accessibilityIdentifier("lio.chat.recovery")
            }
        }
        .task(id: restoreChatRequest) {
            guard restoringChat else { return }
            restoreChatFailed = false
            do {
                if let chat = try await chatLibrary?.restore?() {
                    try Task.checkCancellation()
                    selectedChat = chat
                    conversation = LioConversation(service: chat.service)
                    opening = .beforeNext
                }
                try Task.checkCancellation()
                if let continuity = chatLibrary?.continuity { draft = continuity.draft }
                restoringChat = false
            } catch is CancellationError {
                return
            } catch { restoreChatFailed = true }
        }
        .onChange(of: draft) { _, value in chatLibrary?.continuity?.draft = value }
        .onChange(of: tab) { _, _ in typing = false }
        .task(id: Observation(active: canObserve, request: refreshRequest)) {
            if canObserve { await currentConversation.refreshTimeline() }
        }
        .task(id: TripObservation(active: canObserve, card: tripCard, plan: tripPlan.map(ObjectIdentifier.init))) {
            if canObserve { await tripPlan?.reload(for: tripCard) }
        }
        .task(id: tripPlan?.pending == true && scenePhase == .active) {
            if scenePhase == .active, tripPlan?.pending == true { await tripPlan?.awaitUndo() }
        }
        .task(id: scenePhase) {
            guard scenePhase == .active, let memoryActions else { return }
            do {
                memoryPending = try memoryActions.hasPendingChoice()
            } catch {
                memoryNotice = language.text("Couldn’t show your saved choice.", "暂时无法显示你的选择。")
            }
        }
        .task(id: memoryPending && scenePhase == .active) {
            guard memoryPending, scenePhase == .active, let memoryActions else { return }
            await awaitMemoryChoice(memoryActions)
        }
        .task(id: pending?.id) {
            if let pending { await conversation.receive(pending) }
        }
    }

    private var chat: some View {
        let pending = conversation.pending
        let latest = conversation.turns.last
        let earlierID = conversation.nextBefore.map { Data($0.utf8) }
        return ScrollViewReader { scroll in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 22) {
                    if conversation.turns.isEmpty {
                        if opening == .beforeNext { openingMessage }
                        examples
                    }
                    ForEach(conversation.turns) { turn in
                        VStack(alignment: .leading, spacing: 22) {
                            if turn.id == earlierID { earlierMessages(scroll) }
                            if opening == .before(turn.id) { openingMessage }
                            turnView(turn)
                        }
                    }
                    if !conversation.turns.isEmpty, opening == .beforeNext, pending == nil {
                        openingMessage
                    }
                    if let memoryNotice { Text(memoryNotice).font(.footnote) }
                    if memoryPending {
                        Text(language.text("Waiting to save your choice…", "正在等待保存你的选择…"))
                            .font(.footnote)
                            .accessibilityIdentifier("lio.memory.waiting")
                    }
                    Color.clear.frame(height: 1).id("lio.bottom")
                }
                .frame(maxWidth: 680)
                .padding(.horizontal, 18)
                .padding(.top, 12)
                .padding(.bottom, 12)
                .frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            .simultaneousGesture(DragGesture(minimumDistance: 12).onChanged { _ in
                followsAnswer = false
            })
            .onChange(of: latest?.id) { _, _ in
                guard followsAnswer else { return }
                if reduceMotion { scroll.scrollTo("lio.bottom", anchor: .bottom) }
                else { withAnimation(LioTheme.Motion.change) { scroll.scrollTo("lio.bottom", anchor: .bottom) } }
            }
            .onChange(of: latest?.answer) { _, _ in
                if followsAnswer, let pending, latest?.id == pending.id { scroll.scrollTo("lio.bottom", anchor: .bottom) }
            }
            .onChange(of: latest?.status) { _, status in
                if followsAnswer && status == .finished { scroll.scrollTo("lio.bottom", anchor: .bottom) }
            }
            .onChange(of: jumpRequest) { _, _ in
                followsAnswer = true
                withAnimation(LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion)) {
                    scroll.scrollTo("lio.bottom", anchor: .bottom)
                }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .background { didEnterBackground = true }
                guard phase == .active, didEnterBackground else { return }
                didEnterBackground = false
                opening = .beforeNext
                followsAnswer = true
                if !conversation.turns.isEmpty, pending == nil { scroll.scrollTo("lio.bottom", anchor: .bottom) }
            }
        }
        .background(LioTheme.paper)
        .safeAreaInset(edge: .top, spacing: 0) {
            floatingControls
                .background {
                    LioTheme.paper
                        .ignoresSafeArea(edges: .top)
                        .overlay(alignment: .bottom) { fade(from: .top) }
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .sheet(isPresented: $menuOpen) {
            NavigationStack {
                List {
                    if isDemo {
                        Text(language.text("Sample replies only", "仅提供演示回答"))
                            .lioRow()
                    }
                    if let chatLibrary {
                        Section {
                            Button {
                                guard canSwitchChat else { return }
                                switchChat(chatLibrary.newChat(), opening: .beforeNext)
                            } label: {
                                Label(language.text("New chat", "新对话"), systemImage: "square.and.pencil")
                            }
                            .disabled(!canSwitchChat)
                            .accessibilityIdentifier("lio.chat.new")
                            NavigationLink {
                                LioChatHistoryView(library: chatLibrary, language: language, currentID: chatID,
                                                   canSwitch: canSwitchChat, select: { switchChat($0) })
                            } label: {
                                Label(language.text("Chat history", "历史对话"), systemImage: "clock")
                            }
                            .accessibilityIdentifier("lio.chat.history")
                        }
                        .lioRow()
                    }
                    menu.lioRow()
                }
                .lioPage()
                .navigationTitle(language.text("Menu", "菜单"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button(language.text("Done", "完成")) { menuOpen = false }
                    }
                }
            }
            .tint(LioTheme.vermilion)
        }
    }

    private var canSwitchChat: Bool {
        scenePhase == .active && conversation.pending == nil && !memoryBusy && !memoryPending
            && tripPlan?.busy != true && tripPlan?.pending != true
    }

    private func switchChat(_ chat: LioChatSession, opening: Opening = .hidden) {
        guard canSwitchChat else { return }
        if chat.id != chatID {
            if let chatID { chatDrafts[chatID] = draft }
            selectedChat = chat
            chatLibrary?.continuity?.selectedID = chat.id
            conversation = LioConversation(service: chat.service)
            self.opening = opening
            draft = chatDrafts.removeValue(forKey: chat.id) ?? ""
            tripPath = []
            memoryNotice = nil
            followsAnswer = true
            refreshRequest += 1
        }
        menuOpen = false
    }

    private func earlierMessages(_ scroll: ScrollViewProxy) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Button(language.text("Earlier messages", "更早的消息")) {
                followsAnswer = false
                Task {
                    if let id = await conversation.loadEarlier() {
                        scroll.scrollTo(id, anchor: .top)
                    }
                }
            }
            .disabled(conversation.loadingEarlier)
            .accessibilityIdentifier("lio.earlier")
            if conversation.loadingEarlier { ProgressView() }
            if conversation.earlierUnavailable {
                Text(language.text("Couldn’t show earlier messages. Try again.", "暂时看不到更早的消息，请再试一次。"))
                    .font(.footnote)
            }
        }
    }

    private var floatingControls: some View {
        HStack(alignment: .top, spacing: LioTheme.Spacing.xs) {
            Button {
                typing = false
                menuOpen = true
            } label: {
                controlIcon("line.3.horizontal")
            }
            .buttonStyle(.plain)
            .accessibilityLabel(language.text("Menu", "菜单"))
            .accessibilityIdentifier("lio.menu")
            Spacer(minLength: 0)
            VStack(spacing: LioTheme.Spacing.xxs) {
                LioPortrait(size: 44)
                // The identifier sits on the name alone so the accessibility frame doesn't include the avatar.
                Text("Lio")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                    .accessibilityIdentifier("lio.name")
            }
            Spacer(minLength: 0)
            if let chatLibrary {
                Button {
                    guard canSwitchChat else { return }
                    switchChat(chatLibrary.newChat(), opening: .beforeNext)
                } label: {
                    controlIcon("square.and.pencil")
                }
                .buttonStyle(.plain)
                .disabled(!canSwitchChat)
                .accessibilityLabel(language.text("New chat", "新对话"))
                .accessibilityIdentifier("lio.chat.newShortcut")
            } else {
                Color.clear.frame(width: 44, height: 44).accessibilityHidden(true)
            }
        }
        .padding(.horizontal, LioTheme.Spacing.md)
        .padding(.top, LioTheme.Spacing.xxs)
        .padding(.bottom, LioTheme.Spacing.xs)
    }

    /// A 44pt round control. The symbol stops growing at xxxLarge so it stays inside the circle;
    /// the controls carry accessibility labels for larger text needs.
    private func controlIcon(_ symbol: String) -> some View {
        Image(systemName: symbol)
            .font(.body.weight(.semibold))
            .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
            .frame(width: 44, height: 44)
            .foregroundStyle(LioTheme.ink)
            .lioCard(Circle())
    }

    /// A short paper-to-clear fade where content scrolls under the top controls or the composer.
    private func fade(from edge: VerticalEdge) -> some View {
        LinearGradient(colors: [LioTheme.paper, LioTheme.paper.opacity(0)],
                       startPoint: edge == .top ? .top : .bottom, endPoint: edge == .top ? .bottom : .top)
            .frame(height: LioTheme.Spacing.sm)
            .offset(y: edge == .top ? LioTheme.Spacing.sm : -LioTheme.Spacing.sm)
    }

    private var openingMessage: some View {
        lioReply {
            replyText(Text(language.text("Hi, I’m Lio, your personal travel agent. How can I help?",
                                         "你好，我是 Lio，你的个人旅行助手。有什么可以帮你？")))
                .accessibilityIdentifier("lio.opening")
        }
    }

    /// A Lio turn: a small avatar and name, then the reply in a `surface` bubble whose corner nearest the
    /// avatar is tucked in. JT 2026-11-11 kept bubbles for Lio's replies instead of plain page text (D2).
    private func lioReply<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            lioByline
            content()
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .lioCard(UnevenRoundedRectangle(topLeadingRadius: LioTheme.Radius.tail,
                                                bottomLeadingRadius: LioTheme.Radius.card,
                                                bottomTrailingRadius: LioTheme.Radius.card,
                                                topTrailingRadius: LioTheme.Radius.card))
                .padding(.trailing, dynamicTypeSize.isAccessibilitySize ? 0 : LioTheme.Spacing.xl)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var lioByline: some View {
        HStack(spacing: 6) {
            LioPortrait(size: 22)
            Text("Lio")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(LioTheme.ink)
        }
        .accessibilityHidden(true)
    }

    private func replyText(_ content: Text) -> some View {
        content
            .font(.body)
            .foregroundStyle(LioTheme.ink)
            .lineSpacing(4)
            .fixedSize(horizontal: false, vertical: true)
    }

    private var examples: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: LioTheme.Spacing.xs) {
                ForEach(Array(LioDemo.starters(language).enumerated()), id: \.offset) { index, starter in
                    Button {
                        draft = starter.prefix
                        typing = true
                    } label: {
                        VStack(spacing: LioTheme.Spacing.xs) {
                            Image(systemName: starter.symbol)
                                .font(.title3)
                                .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                                .foregroundStyle(LioTheme.vermilion)
                                .frame(width: 44, height: 44)
                                .background(LioTheme.surfaceSunken, in: Circle())
                                .accessibilityHidden(true)
                            Text(starter.label)
                                .font(.caption)
                                .foregroundStyle(LioTheme.ink)
                                .fixedSize(horizontal: true, vertical: false)
                        }
                        .frame(minWidth: 64, minHeight: 64)
                        .padding(.horizontal, LioTheme.Spacing.xxs)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(starter.label)
                    .accessibilityHint(language.text("Adds a starter. Finish your question, then send it.",
                                                     "填入开头，补充问题后自行发送。"))
                    .accessibilityIdentifier("lio.example.\(index)")
                }
            }
            .padding(.vertical, LioTheme.Spacing.xxs)
        }
    }

    private func recordPendingFirstQuestion() {
        if let question = conversation.pending, let chatID, chatLibrary?.continuity?.blankIDs.contains(chatID) == true {
            chatLibrary?.continuity?.firstQuestions[chatID] = question
        }
    }

    private var composer: some View {
        let placeholder = language.text("Start chatting", "开始聊天")
        let canSend = !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && conversation.pending == nil
        let showsJump = !followsAnswer && !conversation.turns.isEmpty
        return HStack(alignment: .center, spacing: 10) {
            TextField(placeholder, text: $draft, prompt: Text(placeholder).foregroundStyle(LioTheme.inkSecondary), axis: .vertical)
                .lineLimit(1...5)
                .frame(minHeight: 44)
                .focused($typing)
                .accessibilityIdentifier("lio.composer")
            Button {
                followsAnswer = true
                sendCount += 1
                conversation.send(draft, language: language)
                recordPendingFirstQuestion()
                if opening == .beforeNext, let id = conversation.pending?.id { opening = .before(id) }
                draft = ""
                typing = false
            } label: {
                Image(systemName: "arrow.up")
                    .font(.body.weight(.semibold))
                    .frame(width: 44, height: 44)
                    .foregroundStyle(canSend ? LioTheme.onVermilion : LioTheme.inkSecondary)
                    .background(canSend ? LioTheme.vermilion : LioTheme.surfaceSunken, in: Circle())
            }
            .disabled(!canSend)
            .buttonStyle(.plain)
            .sensoryFeedback(.impact(weight: .light), trigger: sendCount)
            .accessibilityLabel(language.text("Send", "发送"))
            .accessibilityIdentifier("lio.send")
        }
        .padding(.leading, 16)
        .padding(5)
        .lioCard(Capsule())
        .overlay(alignment: .top) {
            if showsJump {
                Button { jumpRequest += 1 } label: { controlIcon("arrow.down") }
                    .buttonStyle(.plain)
                    .accessibilityLabel(language.text("Jump to latest", "回到最新"))
                    .accessibilityIdentifier("lio.jumpToLatest")
                    .offset(y: -(44 + LioTheme.Spacing.sm))
                    .transition(.opacity)
            }
        }
        .animation(LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion), value: showsJump)
        .frame(maxWidth: 680)
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background {
            LioTheme.paper
                .overlay(alignment: .top) { fade(from: .bottom) }
                .allowsHitTesting(false)
                .accessibilityHidden(true)
        }
    }

    private func chooseMemory(_ choice: LioMemoryWire.Choice, tag: LioMemoryWire.Tag,
                              client: LioMemoryActionsClient) async {
        guard !memoryBusy, !memoryPending, !handledTags.contains(tag) else { return }
        memoryBusy = true
        defer { memoryBusy = false }
        memoryNotice = nil
        do {
            if try client.hasPendingChoice() {
                memoryPending = true
                return
            }
            activeMemory = tag
            finishMemoryChoice(try await client.choose(choice, tag: tag))
        } catch is CancellationError {
            return
        } catch {
            memoryNotice = language.text("Couldn’t save your choice right now.", "暂时无法保存你的选择。")
        }
    }

    private func awaitMemoryChoice(_ client: LioMemoryActionsClient) async {
        while !Task.isCancelled {
            do {
                guard let state = try await client.reconcileChoice() else {
                    memoryPending = false
                    return
                }
                if state != .pending {
                    finishMemoryChoice(state)
                    return
                }
            } catch is CancellationError {
                return
            } catch {
                memoryNotice = language.text("Couldn’t show your saved choice.", "暂时无法显示你的选择。")
            }
            do {
                try await Task.sleep(for: .seconds(5))
            } catch {
                return
            }
        }
    }

    private func finishMemoryChoice(_ state: LioMemoryActionsClient.State) {
        switch state {
        case .pending:
            memoryPending = true
            return
        case .remembered:
            memoryNotice = language.text("Remembered", "已记住")
        case .dismissed:
            memoryNotice = nil
        case .changed:
            memoryNotice = language.text("That suggestion changed.", "这条建议已有变化。")
        }
        if let activeMemory { handledTags.insert(activeMemory) }
        activeMemory = nil
        memoryPending = false
        refreshRequest += 1
    }

    private func turnView(_ turn: LioTurn) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 4) {
                Spacer(minLength: dynamicTypeSize.isAccessibilitySize ? 12 : 64)
                if turn.status == .failed(.notSent) {
                    Button {
                        if turn.id == conversation.turns.last?.id { followsAnswer = true }
                        conversation.resend(turn.id)
                        recordPendingFirstQuestion()
                    } label: {
                        Image(systemName: "exclamationmark.circle.fill")
                            .foregroundStyle(LioTheme.danger)
                            .frame(width: 44, height: 44)
                    }
                    .buttonStyle(.plain)
                    .disabled(conversation.pending != nil)
                    .accessibilityLabel(language.text("Send again", "重新发送"))
                    .accessibilityIdentifier("lio.resend")
                }
                Text(turn.question.text)
                    .foregroundStyle(LioTheme.ink)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(LioTheme.surfaceSunken,
                                in: UnevenRoundedRectangle(topLeadingRadius: LioTheme.Radius.card, bottomLeadingRadius: LioTheme.Radius.card,
                                                           bottomTrailingRadius: LioTheme.Radius.tail, topTrailingRadius: LioTheme.Radius.card))
                    .textSelection(.enabled)
                    .accessibilityIdentifier("lio.question")
            }
            if case .failed = turn.status {
                EmptyView()
            } else if !turn.answer.isEmpty {
                if let answer = LioReplyMarkdown.render(turn.answer) {
                    if !answer.characters.isEmpty {
                        lioReply {
                            replyText(Text(answer))
                                .textSelection(.enabled)
                                .accessibilityIdentifier("lio.answer")
                        }
                    }
                } else {
                    lioReply {
                        replyText(Text(language.text("This reply can’t be shown right now.", "这条回答暂时无法显示。")))
                            .accessibilityIdentifier("lio.reply.unavailable")
                    }
                }
            }
            messageStatus(turn)
            if let memoryActions {
                ForEach(turn.memoryTags.filter { !handledTags.contains($0) }) { tag in
                    memorySuggestion(tag, client: memoryActions)
                }
            }
            if let itinerary = turn.itinerary {
                let card = LioTripCard(turnID: turn.id, itinerary: itinerary)
                let isLatest = card == latestTripCard
                let current = isLatest ? tripPlan?.current(in: card) : nil
                LioItineraryCard(itinerary: current ?? itinerary, language: language) {
                    if tripLibrary != nil { tripPath = [LioTripRoute(id: itinerary.id, visit: UUID())] }
                    tab = .trips
                } actions: {
                    if isLatest, let tripPlan {
                        if current != nil, let target = tripPlan.target {
                            Button(language.text("Undo", "撤销")) {
                                Task {
                                    guard latestTripCard == card, conversation.pending == nil else { return }
                                    await tripPlan.undo(target)
                                }
                            }
                            .buttonStyle(.bordered)
                            .disabled(tripPlan.busy || tripPlan.pending || conversation.pending != nil || scenePhase != .active)
                            .accessibilityIdentifier("lio.chat.trip.undo")
                        }
                        if tripPlan.pending {
                            Text(language.text("Waiting for the trip to update…", "正在等行程更新…"))
                                .font(.footnote)
                        }
                        if let notice = tripPlan.notice {
                            Text(notice.text(language)).font(.footnote)
                        }
                    }
                }
            }
        }
    }

    private func memorySuggestion(_ tag: LioMemoryWire.Tag, client: LioMemoryActionsClient) -> some View {
        let text = tag.text.trimmingCharacters(in: .whitespacesAndNewlines)
        let preference = text.last.map { ".。!?！？".contains($0) } == true ? String(text.dropLast()) : text
        let actions = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
            : AnyLayout(HStackLayout(spacing: 10))
        return VStack(alignment: .leading, spacing: 6) {
            Label {
                RunReadableText(text: language.text("Remember: \(preference)?", "记住：\(preference)？"))
            } icon: {
                Image(systemName: "bookmark").foregroundStyle(LioTheme.gold).accessibilityHidden(true)
            }
            .font(.subheadline.weight(.semibold))
            actions {
                Button {
                    Task { await chooseMemory(.remember, tag: tag, client: client) }
                } label: {
                    // White on the dark-mode vermilion fill is below 4.5:1, so the label uses onVermilion.
                    Text(language.text("Remember", "记住"))
                        .foregroundStyle(memoryBusy || memoryPending ? LioTheme.inkSecondary : LioTheme.onVermilion)
                }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("lio.memory.remember")
                Button(language.text("Dismiss", "不用")) {
                    Task { await chooseMemory(.dismiss, tag: tag, client: client) }
                }
                .buttonStyle(.borderless)
                .accessibilityIdentifier("lio.memory.dismiss")
            }
            .controlSize(.large)
            .disabled(memoryBusy || memoryPending)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.small))
    }

    @ViewBuilder
    private func messageStatus(_ turn: LioTurn) -> some View {
        switch turn.status {
        case .thinking, .working:
            statusLine(language.text("Lio is replying…", "Lio 正在回复…"))
        case .failed(let failure):
            let message = switch failure {
            case .notSent: language.text("Message couldn’t be sent. Check your connection and tap to try again.",
                                         "消息没发出去。检查网络后，点感叹号重发。")
            case .invalidInput: language.text("This message couldn’t be sent. Please try a different message.",
                                              "这条消息没发出去，请换个说法再试。")
            case .dailyLimit: language.text("You’ve used all your questions for today. Try again tomorrow.",
                                            "今天的问题额度已用完，明天再来聊吧。")
            case .serviceLimit: language.text("Lio couldn’t finish this request within the current limit.",
                                              "这次没能在限额内答完。")
            case .unfinished: language.text("I couldn’t finish this one.", "这次没答完。")
            case .waiting: language.text("I don’t have an answer for this yet.", "这条消息暂时还没有回答。")
            case .unavailable where turn.fromTimeline:
                language.text("I couldn’t complete this request.", "这次没能完成你的请求。")
            case .unavailable: language.text("Chat isn’t available right now.", "现在暂时不能聊天。")
            }
            Text(message)
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.failure")
            if failure == .unfinished {
                Button(language.text("Ask again", "重新问")) {
                    followsAnswer = true
                    conversation.askAgain(turn.id)
                    recordPendingFirstQuestion()
                }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                    .disabled(conversation.pending != nil)
                    .accessibilityIdentifier("lio.askAgain")
            }
        case .answering, .finished:
            EmptyView()
        }
    }

    /// Waiting for Lio: the avatar and moving dots where the reply will appear. Read aloud as the title.
    private func statusLine(_ title: String) -> some View {
        HStack(spacing: LioTheme.Spacing.xs) {
            LioPortrait(size: 22)
            Image(systemName: "ellipsis")
                .font(.title3.weight(.bold))
                .foregroundStyle(LioTheme.inkSecondary)
                .symbolEffect(.variableColor.iterative, options: .repeating, isActive: !reduceMotion)
        }
        .frame(minHeight: 28)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(title)
        .accessibilityAddTraits(.isStaticText)
        .accessibilityIdentifier("lio.progress")
    }
}
#endif
