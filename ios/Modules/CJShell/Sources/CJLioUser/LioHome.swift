#if os(iOS)
import SwiftUI
import UIKit
import CJMessageHTTP
import CJRunClient
import CJTripClient

public struct LioHome<MenuContent: View>: View {
    private let language: LioLanguage
    private let isDemo: Bool
    private let reconnect: (@MainActor () -> Void)?
    private let session: LioSessionAvailability?
    private let runtimeService: LioService
    private let runtimeTripHistory: LioTripHistoryClient?
    @State private var boundRuntime: UUID?
    @State private var warmRestoration = false
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
    @State private var restoreChatFailure: LioFailureDiagnosis?
    @State private var restoreChatRequest = 0
    @State private var showsProblemNotes = false
    @State private var draft = ""
    @State private var chatDrafts: [Data: String] = [:]
    @State private var questionDrafts: [Data: LioQuestionDraft] = [:]
    @State private var profileEdit: ProfileEdit?
    @State private var menuOpen = false
    @State private var followsAnswer = true
    @State private var opening = Opening.beforeNext
    @State private var tab = Tab.chat
    @State private var tripPath: [LioTripRoute] = []
    @Namespace private var tripZoomNamespace
    @State private var memoryBusy = false
    @State private var memoryPending = false
    @State private var memoryNotice: String?
    @State private var activeMemory: LioMemoryWire.Tag?
    @State private var activeMemoryTurn: Data?
    @State private var memoryFeedback: [LioMemoryWire.Tag: LioMemoryFeedback] = [:]
    @State private var handledTags: Set<LioMemoryWire.Tag> = []
    @State private var refreshRequest = 0
    @State private var jumpRequest = 0
    @State private var sendCount = 0
    @State private var entering: Set<LioEntranceKey> = []
    @State private var completedBodies: Set<Data> = []
    @State private var seenMemoryTags: Set<LioMemoryWire.Tag> = []
    @State private var savedCelebrations = 0
    @State private var chatFading = false
    @State private var timing = LioTimingLog()
    private struct Observation: Equatable {
        let active: Bool
        let request: Int
    }
    private struct Restoration: Equatable {
        let request: Int
        let revision: UUID?
        let available: Bool
    }
    private enum SessionRefreshFailure: Error { case changedConversation }
    private struct TripObservation: Equatable {
        let active: Bool
        let card: LioTripCard?
        let plan: ObjectIdentifier?
    }
    private enum Tab { case chat, trips, memory }
    private enum Opening: Equatable { case beforeNext, before(Data), hidden }
    private struct ProfileEdit: Identifiable {
        let id = UUID()
        let owner: LioConversation
        let turnID: Data
        let entry: LioExplorationPresentation.ProfileEntry
    }
    @FocusState private var typing: Bool
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.colorScheme) private var colorScheme

    public init(language: LioLanguage, service: LioService, isDemo: Bool, chatLibrary: LioChatLibrary? = nil,
                tripLibrary: LioTripLibrary? = nil,
                tripHistory: LioTripHistoryClient? = nil,
                memoryActions: LioMemoryActionsClient? = nil,
                savedMemory: AnyView? = nil,
                recordedMap: (@MainActor (StructuredTripDocument) -> AnyView)? = nil,
                session: LioSessionAvailability? = nil,
                reconnect: (@MainActor () -> Void)? = nil, @ViewBuilder menu: () -> MenuContent) {
        self.language = language
        self.isDemo = isDemo
        self.reconnect = reconnect
        self.session = session
        self.runtimeService = service
        self.runtimeTripHistory = tripHistory
        _boundRuntime = State(initialValue: session?.revision)
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
        _opening = State(initialValue: chatLibrary?.continuity?.selectedID == nil ? .beforeNext : .hidden)
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

    private var memorySuggestions: [String] {
        guard memoryActions != nil, session?.available != false, !restoringChat,
              conversation.timelineFailure == nil else { return [] }
        return conversation.turns.reversed().flatMap { turn in
            turn.memoryTags.filter { !handledTags.contains($0) }.map(\.text)
        }
    }

    public var body: some View {
        let currentConversation = conversation
        let pending = conversation.pending
        let canObserve = scenePhase == .active && pending == nil && !restoringChat && session?.available != false
        let tripCard = latestTripCard
        let tripPlan = tripPlan
        TabView(selection: $tab) {
            chat
                .background(LioTabBarAppearance().frame(width: 0, height: 0))
                .tabItem { Label(language.text("Chat", "聊天"), systemImage: "bubble.left") }
                .tag(Tab.chat)
            LioTripsView(itineraries: conversation.itineraries, language: language, library: tripLibrary,
                         tripPlan: tripPlan, currentPlan: tripPlan?.current(for: tripCard),
                         canUndo: canObserve && tripPlan?.requestedCard == tripCard,
                         recordedMap: recordedMap, sessionRevision: session?.revision,
                         zoomNamespace: tripZoomNamespace, path: $tripPath) { tab = .chat }
                .background(LioTabBarAppearance().frame(width: 0, height: 0))
                .tabItem { Label(language.text("Trips", "行程"), systemImage: "suitcase") }
                .tag(Tab.trips)
            if let savedMemory {
                savedMemory
                    .environment(\.lioMemorySuggestions, memorySuggestions)
                    .background(LioTabBarAppearance().frame(width: 0, height: 0))
                    .tabItem { Label(language.text("Memory", "记忆"), systemImage: "bookmark") }
                    .tag(Tab.memory)
            }
        }
        .tint(LioTheme.vermilion)
        .sensoryFeedback(.success, trigger: savedCelebrations)
        .disabled(restoringChat || session?.available == false)
        .opacity(restoringChat && !warmRestoration ? 0 : 1)
        .overlay {
            if restoringChat && !warmRestoration {
                VStack(spacing: 20) {
                    if let failure = restoreChatFailure {
                        Text(failure.message(language))
                            .foregroundStyle(LioTheme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(failure.nextStep(language))
                            .foregroundStyle(LioTheme.inkSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        // Same accessible actions as the saved sign-in recovery page.
                        Button { restoreChatRequest += 1 } label: {
                            Text(language.text("Try again", "重试")).frame(minHeight: 44)
                        }
                        .buttonStyle(.borderedProminent)
                        .foregroundStyle(LioTheme.onVermilion)
                        Button { showsProblemNotes = true } label: {
                            Text(language.text("View problem notes", "查看问题记录"))
                                .foregroundStyle(LioTheme.inkSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .frame(minHeight: 44)
                        }
                        .buttonStyle(.plain)
                    } else {
                        ProgressView(language.text("Opening your conversation…", "正在打开你的对话…"))
                    }
                }
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)
                .padding(28)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(LioTheme.paper)
                .tint(LioTheme.vermilion)
                .accessibilityIdentifier("lio.chat.recovery")
            }
        }
        .sheet(isPresented: $showsProblemNotes) { problemNotesSheet }
        .safeAreaInset(edge: .top, spacing: 0) {
            if restoringChat && warmRestoration { sessionRecoveryBanner }
        }
        .task(id: Restoration(request: restoreChatRequest, revision: session?.revision, available: session?.available != false)) {
            if session?.available == false {
                warmRestoration = true
                restoringChat = true
                restoreChatFailure = nil
                conversation.suspendForSessionRefresh()
                return
            }
            let rebind = session?.revision != boundRuntime
            guard restoringChat || rebind else { return }
            if rebind {
                warmRestoration = true
                restoringChat = true
                conversation.suspendForSessionRefresh()
            }
            restoreChatFailure = nil
            let expected = chatID
            do {
                let chat = try await chatLibrary?.restore?()
                try Task.checkCancellation()
                if warmRestoration {
                    guard (chat?.id ?? chatLibrary?.currentID) == expected else {
                        throw SessionRefreshFailure.changedConversation
                    }
                    selectedChat = chat
                    defaultTripPlan = runtimeTripHistory.map { LioTripPlan(client: $0) }
                    conversation.resumeAfterSessionRefresh(service: chat?.service ?? runtimeService,
                                                           restoredUnsentFirst: chat?.restoredUnsentFirst)
                    if chat?.restoredUnsentFirst != nil, let continuity = chatLibrary?.continuity {
                        setDraft(continuity.draft)
                    }
                } else if let chat {
                    selectedChat = chat
                    conversation = LioConversation(service: chat.service)
                    opening = .hidden
                }
                if !warmRestoration, let continuity = chatLibrary?.continuity { setDraft(continuity.draft) }
                boundRuntime = session?.revision
                restoringChat = false
                warmRestoration = false
                refreshRequest += 1
            } catch is CancellationError {
                return
            } catch {
                restoreChatFailure = chatLibrary?.diagnose?(error)
                    ?? .classify(error, stage: .selectedChat, observation: nil)
            }
        }
        .onChange(of: chatLibrary?.continuity?.positionIssue, initial: true) { _, issue in
            guard let issue, scenePhase == .active else { return }
            LioDiagnosticLog.shared.record(error: issue.problem, stage: .localRecord, at: issue.at)
        }
        .onChange(of: tab) { _, _ in typing = false }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { typing = false }
        }
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
        .sheet(item: $profileEdit) { edit in
            LioProfileChangeSheet(entry: edit.entry, language: language,
                                  canSend: canRespond(to: edit.turnID, in: edit.owner)) { text in
                guard canRespond(to: edit.turnID, in: edit.owner) else { return }
                _ = sendQuestion(text)
            }
        }
    }

    @ViewBuilder
    private func chatMessages(_ scroll: ScrollViewProxy) -> some View {
        let pending = conversation.pending
        let earlierID = conversation.nextBefore.map { Data($0.utf8) }
        if let chatID, let retained = chatLibrary?.continuity?.retainedUnsent[chatID] {
            ForEach(Array(retained.enumerated()), id: \.offset) { _, question in
                VStack(alignment: .leading, spacing: 8) {
                    Text(language.text("Unsent message", "未发送的内容"))
                        .font(.headline)
                    RunSelectableText(text: question.text, color: LioTheme.ink)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                .accessibilityIdentifier("lio.unsent.message")
            }
        }
        if let failure = conversation.timelineFailure {
            readFailureMessage(failure)
        }
        if conversation.turns.isEmpty && conversation.timelineFailure == nil {
            if conversation.hasLoadedTimeline {
                if opening == .beforeNext { openingMessage }
                examples
            } else if conversation.timelineUnavailable {
                Text(language.text("Couldn’t show earlier messages. Try again.", "暂时看不到更早的消息，请再试一次。"))
                Button { refreshRequest += 1 } label: {
                    Text(language.text("Try reading again", "再次查看"))
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .accessibilityIdentifier("lio.read.retry")
            } else {
                ProgressView().accessibilityLabel(language.text("Opening your conversation…", "正在打开你的对话…"))
            }
        }
        ForEach(conversation.turns) { turn in
            VStack(alignment: .leading, spacing: 22) {
                if turn.id == earlierID { earlierMessages(scroll) }
                if opening == .before(turn.id) { openingMessage }
                turnView(turn, scroll: scroll)
            }
        }
        if let memoryNotice { Text(memoryNotice).font(.footnote) }
        if memoryPending, activeMemoryTurn == nil {
            Text(language.text("Waiting to save your choice…", "正在等待保存你的选择…"))
                .font(.footnote)
                .accessibilityIdentifier("lio.memory.waiting")
        }
        Color.clear.frame(height: 1).id("lio.bottom")
    }

    private var chat: some View {
        let pending = conversation.pending
        let latest = conversation.turns.last
        return ScrollViewReader { scroll in
            VStack(spacing: 0) {
                floatingControls
                GeometryReader { viewport in
                    ScrollView {
                        Group {
                            if dynamicTypeSize.isAccessibilitySize && !conversation.turns.contains(where: { $0.exploration != nil }) {
                                // Eager measurement keeps a tall card's bottom reachable at accessibility sizes.
                                VStack(alignment: .leading, spacing: 22) { chatMessages(scroll) }
                            } else {
                                LazyVStack(alignment: .leading, spacing: 22) { chatMessages(scroll) }
                            }
                        }
                        .frame(maxWidth: 680)
                        .padding(.horizontal, 18)
                        .padding(.top, 12)
                        .padding(.bottom, 12)
                        .frame(maxWidth: .infinity)
                        .opacity(chatFading ? 0 : 1)
                        .allowsHitTesting(!chatFading)
                    }
                    .frame(width: viewport.size.width, height: viewport.size.height)
                    .clipped()
                    .contentShape(Rectangle())
                    .scrollClipDisabled(false)
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
                        if followsAnswer, let pending, let latest, latest.id == pending.id { followReply(latest, scroll: scroll) }
                    }
                    .onChange(of: latest?.status) { _, status in
                        if status == .finished, let latest, latest.answer.isEmpty { timing.mark(.finished, latest.id) }
                        if followsAnswer, status == .finished, let latest { followReply(latest, scroll: scroll) }
                    }
                    .onChange(of: jumpRequest) { _, _ in
                        followsAnswer = true
                        withAnimation(LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion)) {
                            scroll.scrollTo("lio.bottom", anchor: .bottom)
                        }
                    }
                }
                if let continuity = chatLibrary?.continuity, continuity.positionIssue != nil {
                    positionSaveNotice(continuity)
                }
                composer
            }
        }
        .background(LioTheme.paper)
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
                                startNewChat(chatLibrary)
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
                .toolbarBackground(LioTheme.paper, for: .navigationBar)
                .toolbarBackground(.visible, for: .navigationBar)
                .toolbarColorScheme(colorScheme, for: .navigationBar)
                .navigationTitle(language.text("Menu", "菜单"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .principal) {
                        RunReadableText(text: language.text("Menu", "菜单"), style: .headline, color: LioTheme.ink)
                            .fixedSize()
                            .accessibilityAddTraits(.isHeader)
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button { menuOpen = false } label: {
                            RunReadableText(text: language.text("Done", "完成"), color: LioTheme.vermilion)
                                .fixedSize()
                                .frame(minHeight: 44)
                        }
                        .accessibilityLabel(language.text("Done", "完成"))
                    }
                }
            }
            .tint(LioTheme.vermilion)
            .preferredColorScheme(colorScheme)
        }
    }

    private var sessionRecoveryBanner: some View {
        HStack(alignment: .center, spacing: 12) {
            if let failure = restoreChatFailure {
                RunReadableText(text: failure.message(language), color: LioTheme.ink)
                    .accessibilityIdentifier("lio.session.notice")
                Button(language.text("Try again", "重试")) { restoreChatRequest += 1 }
                    .frame(minHeight: 44)
                    .accessibilityIdentifier("lio.session.retry")
            } else if session?.showsRetry == true {
                RunReadableText(text: session?.problem?.message(language)
                    ?? language.text("Couldn’t connect. Your sign-in is still saved.", "暂时连接不上，登录信息仍已保留。"), color: LioTheme.ink)
                    .accessibilityIdentifier("lio.session.notice")
                if let reconnect {
                    Button(language.text("Try again", "重试"), action: reconnect)
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("lio.session.retry")
                }
            } else {
                ProgressView()
                RunReadableText(text: language.text("Restoring your chat…", "正在恢复对话…"), color: LioTheme.ink)
                    .accessibilityIdentifier("lio.session.progress")
            }
        }
        .font(.body)
        .tint(LioTheme.vermilion)
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(LioTheme.surfaceSunken)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("lio.session.recovery.banner")
    }

    private var timingLanguage: String { language == .english ? "en" : "zh-Hans" }

    private var canSwitchChat: Bool {
        scenePhase == .active && conversation.pending == nil && !memoryBusy && !memoryPending
            && tripPlan?.busy != true && tripPlan?.pending != true && !chatFading
            && !restoringChat && !conversation.sessionSuspended && session?.available != false
    }

    /// Fades the current conversation out for `chatFadeOut` seconds, switches, then fades the opening in.
    /// The switch itself and its guard are unchanged; Reduce Motion switches at once.
    /// While the old chat fades out nothing else can switch, send or be tapped; the switch then re-checks
    /// its conditions, so a deferred new chat never overrides something that changed meanwhile.
    private func startNewChat(_ library: LioChatLibrary) {
        guard canSwitchChat else { return }
        guard !reduceMotion else {
            switchChat(library.newChat(), opening: .beforeNext)
            return
        }
        menuOpen = false
        withAnimation(.easeOut(duration: LioTheme.Motion.chatFadeOut)) { chatFading = true }
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(LioTheme.Motion.chatFadeOut))
            withAnimation(LioTheme.Motion.change) {
                chatFading = false
                if canSwitchChat { switchChat(library.newChat(), opening: .beforeNext) }
            }
        }
    }

    private func switchChat(_ chat: LioChatSession, opening: Opening = .hidden) {
        guard canSwitchChat else { return }
        if chat.id != chatID {
            let nextDraft: String
            if let continuity = chatLibrary?.continuity {
                nextDraft = continuity.switchChat(to: chat.id, leaving: chatID, currentDraft: draft)
            } else {
                if let chatID { chatDrafts[chatID] = draft }
                nextDraft = chatDrafts.removeValue(forKey: chat.id) ?? ""
            }
            selectedChat = chat
            conversation = LioConversation(service: chat.service)
            questionDrafts = [:]
            profileEdit = nil
            self.opening = opening
            draft = nextDraft
            tripPath = []
            memoryNotice = nil
            followsAnswer = true
            entering = []
            completedBodies = []
            seenMemoryTags = []
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
            .lioFloatingSurface(Circle(), interactive: true)
            .accessibilityLabel(language.text("Menu", "菜单"))
            .accessibilityIdentifier("lio.menu")
            Spacer(minLength: 0)
            VStack(spacing: LioTheme.Spacing.xxs) {
                LioPortrait(size: 44)
                    .lioEntrance(.launch, active: !LioLaunchMotion.played) { LioLaunchMotion.played = true }
                // The identifier sits on the name alone so the accessibility frame doesn't include the avatar.
                Text("Lio")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                    .accessibilityIdentifier("lio.name")
            }
            Spacer(minLength: 0)
            if let chatLibrary {
                Button {
                    startNewChat(chatLibrary)
                } label: {
                    controlIcon("square.and.pencil")
                }
                .buttonStyle(.plain)
                .lioFloatingSurface(Circle(), interactive: true)
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
        .lioFloatingGroup()
    }

    /// A 44pt round control. The symbol stops growing at xxxLarge so it stays inside the circle;
    /// the controls carry accessibility labels for larger text needs.
    private func controlIcon(_ symbol: String) -> some View {
        Image(systemName: symbol)
            .font(.body.weight(.semibold))
            .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
            .frame(width: 44, height: 44)
            .foregroundStyle(LioTheme.ink)
            .contentShape(Circle())
    }

    private var openingText: String {
        language.text("Hi, I'm Lio. Tell me the city, how many days you have and what you enjoy, and I'll plan where to go and how to get around each day. Where are you headed?",
                      "你好，我是 Lio。告诉我城市、天数和喜好，我帮你排好每天去哪、怎么走。这次想去哪儿？")
    }

    private var openingMessage: some View {
        lioReply {
            RunReadableText(text: openingText, color: LioTheme.ink, lineSpacing: 4)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("lio.opening")
                .contextMenu {
                    Button {
                        UIPasteboard.general.string = openingText
                    } label: {
                        Label(language.text("Copy", "复制"), systemImage: "doc.on.doc")
                    }
                    .accessibilityIdentifier("lio.copy.opening")
                }
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
                        setDraft(starter.prefix)
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

    private func preparePendingQuestion() {
        guard let question = conversation.pending else { return }
        entering.formUnion([LioEntranceKey(turn: question.id, part: .answer),
                            LioEntranceKey(turn: question.id, part: .card),
                            LioEntranceKey(turn: question.id, part: .memory)])
        if !question.isResend { entering.insert(LioEntranceKey(turn: question.id, part: .question)) }
        if let chatID, chatLibrary?.continuity?.blankIDs.contains(chatID) == true {
            chatLibrary?.continuity?.firstQuestions[chatID] = question
        }
    }

    private func sendQuestion(_ text: String) -> Bool {
        guard !chatFading, scenePhase == .active else { return false }
        let showedWelcome = opening == .beforeNext && conversation.turns.isEmpty && conversation.hasLoadedTimeline
        guard conversation.send(text, language: language) else { return false }
        followsAnswer = true
        sendCount += 1
        if let id = conversation.pending?.id {
            timing.start(id, language: timingLanguage)
            entering.formUnion([LioEntranceKey(turn: id, part: .question), LioEntranceKey(turn: id, part: .answer)])
        }
        preparePendingQuestion()
        if showedWelcome, let id = conversation.pending?.id { opening = .before(id) }
        else if opening == .beforeNext { opening = .hidden }
        typing = false
        return true
    }

    private func setDraft(_ value: String) {
        draft = value
        chatLibrary?.continuity?.updateDraft(value, for: chatID)
    }

    private func positionSaveNotice(_ position: LioChatContinuity) -> some View {
        HStack(alignment: .center, spacing: 12) {
            RunReadableText(text: language.text("Draft isn’t saved on this device yet.", "草稿暂未保留在本机。"), color: LioTheme.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityIdentifier("lio.position.notice")
            Button { position.retryKeepingPosition() } label: {
                Text(language.text("Retry", "重试"))
                    .foregroundStyle(LioTheme.ink)
                    .frame(minWidth: 60, minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.position.retry")
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LioTheme.surfaceSunken)
    }

    private var composer: some View {
        let placeholder = language.text("Start chatting", "开始聊天")
        let canSend = !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && conversation.pending == nil
            && !chatFading
        let showsJump = !followsAnswer && !conversation.turns.isEmpty
        return HStack(alignment: .center, spacing: 10) {
            TextField(placeholder, text: Binding(get: { draft }, set: { setDraft($0) }), prompt: Text(placeholder).foregroundStyle(LioTheme.inkSecondary), axis: .vertical)
                .font(.body)
                .lineLimit(1...5)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
                .focused($typing)
                .accessibilityIdentifier("lio.composer")
            Button {
                if let continuity = chatLibrary?.continuity {
                    continuity.withPositionChange {
                        if sendQuestion(draft) { setDraft("") }
                    }
                } else if sendQuestion(draft) { setDraft("") }
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
        .lioFloatingSurface(Capsule())
        .overlay(alignment: .top) {
            if showsJump {
                Button { jumpRequest += 1 } label: { controlIcon("arrow.down") }
                    .buttonStyle(.plain)
                    .lioFloatingSurface(Circle(), interactive: true)
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
                .allowsHitTesting(false)
                .accessibilityHidden(true)
        }
    }

    private func chooseMemory(_ choice: LioMemoryWire.Choice, tag: LioMemoryWire.Tag, turnID: Data,
                              client: LioMemoryActionsClient) async {
        guard !memoryBusy, !memoryPending, !handledTags.contains(tag) else { return }
        memoryBusy = true
        defer { memoryBusy = false }
        memoryNotice = nil
        memoryFeedback.removeValue(forKey: tag)
        do {
            if try client.hasPendingChoice() {
                memoryPending = true
                return
            }
            activeMemory = tag
            activeMemoryTurn = turnID
            finishMemoryChoice(try await client.choose(choice, tag: tag))
        } catch is CancellationError {
            return
        } catch {
            showMemoryFeedback(.saveUnavailable)
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
                showMemoryFeedback(.readUnavailable)
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
            showMemoryFeedback(.remembered)
        case .dismissed:
            memoryNotice = nil
        case .changed:
            showMemoryFeedback(.changed)
        }
        if let activeMemory { handledTags.insert(activeMemory) }
        activeMemory = nil
        activeMemoryTurn = nil
        memoryPending = false
        refreshRequest += 1
    }

    private func showMemoryFeedback(_ kind: LioMemoryFeedbackKind) {
        if let activeMemory, let activeMemoryTurn {
            memoryFeedback[activeMemory] = LioMemoryFeedback(tag: activeMemory, turnID: activeMemoryTurn, kind: kind)
            memoryNotice = nil
        } else {
            memoryNotice = kind.text(language)
        }
    }

    private func turnView(_ turn: LioTurn, scroll: ScrollViewProxy) -> some View {
        let owner = conversation
        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 4) {
                Spacer(minLength: dynamicTypeSize.isAccessibilitySize ? 12 : 64)
                if turn.status == .failed(.notSent) {
                    Button {
                        if turn.id == conversation.turns.last?.id { followsAnswer = true }
                        conversation.resend(turn.id)
                        timing.start(turn.id, language: timingLanguage)
                        preparePendingQuestion()
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
                RunSelectableText(text: turn.question.text, color: LioTheme.ink, fitsContentWidth: true)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(LioTheme.surfaceSunken,
                                in: UnevenRoundedRectangle(topLeadingRadius: LioTheme.Radius.card, bottomLeadingRadius: LioTheme.Radius.card,
                                                           bottomTrailingRadius: LioTheme.Radius.tail, topTrailingRadius: LioTheme.Radius.card))
                    .accessibilityIdentifier("lio.question")
                    .lioEntrance(.rise, active: entering.contains(LioEntranceKey(turn: turn.id, part: .question))) {
                        entering.remove(LioEntranceKey(turn: turn.id, part: .question))
                    }
            }
            if case .failed = turn.status {
                EmptyView()
            } else if let display = turn.exploration {
                explorationReply(turn, display: display, scroll: scroll)
            } else if !turn.answer.isEmpty {
                let answerKey = LioEntranceKey(turn: turn.id, part: .answer)
                lioReply {
                    LioStreamingText(source: turn.answer, streaming: turn.status == .answering,
                                     animate: entering.contains(answerKey), language: language,
                                     presentationActive: !chatFading && !menuOpen && tab == .chat,
                                     onFirstVisible: {
                        guard conversation === owner, !chatFading else { return }
                        timing.mark(.firstText, turn.id)
                    }, onComplete: {
                        guard conversation === owner, !chatFading else { return }
                        timing.mark(.finished, turn.id)
                        completedBodies.insert(turn.id)
                    }, onLayout: {
                        guard conversation === owner, scenePhase == .active, tab == .chat,
                              followsAnswer, conversation.turns.last?.id == turn.id else { return }
                        scroll.scrollTo("lio.bottom", anchor: .bottom)
                    })
                }
                .lioEntrance(.fade, active: entering.contains(answerKey)) { entering.remove(answerKey) }
            }
            messageStatus(turn)
            if let memoryActions {
                ForEach(turn.memoryTags.filter { !handledTags.contains($0) }) { tag in
                    memorySuggestion(tag, turnID: turn.id, client: memoryActions)
                        .lioEntrance(.rise, active: entering.contains(LioEntranceKey(turn: turn.id, part: .memory))
                            && !seenMemoryTags.contains(tag) && scenePhase == .active)
                        .onAppear { if conversation === owner { seenMemoryTags.insert(tag) } }
                }
                ForEach(memoryFeedback.values.filter {
                    $0.turnID == turn.id && ($0.kind.replacesPrompt || !turn.memoryTags.contains($0.tag))
                }.sorted { $0.tag.id < $1.tag.id }) { feedback in
                    LioMemoryFeedbackView(feedback: feedback, language: language) {
                        memoryFeedback.removeValue(forKey: feedback.tag)
                    }
                    .transition(.opacity)
                }
                .animation(LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion),
                           value: memoryFeedback.count)
            }
            if let itinerary = turn.itinerary {
                let entrance = LioEntranceKey(turn: turn.id, part: .card)
                let fresh = entering.contains(entrance)
                let card = LioTripCard(turnID: turn.id, itinerary: itinerary)
                let isLatest = card == latestTripCard
                let current = isLatest ? tripPlan?.current(in: card) : nil
                if !fresh || cardBodyReady(turn) {
                    LioResultEntrance(fresh: fresh, presentationActive: !chatFading && !menuOpen && tab == .chat, onShown: {
                        guard conversation === owner else { return }
                        entering.remove(entrance)
                        if scenePhase == .active, !chatFading, !menuOpen, tab == .chat {
                            savedCelebrations += 1
                            if followsAnswer, conversation.turns.last?.id == turn.id { scroll.scrollTo("lio.bottom", anchor: .bottom) }
                        }
                    }) { celebrate in
                        LioItineraryCard(itinerary: current ?? itinerary, language: language, celebrate: celebrate) {
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
        }
    }

    @ViewBuilder
    private func explorationReply(_ turn: LioTurn, display: LioExplorationDisplay, scroll: ScrollViewProxy) -> some View {
        let presentation = display.presentation
        if !presentation.segments.isEmpty || !presentation.profile.isEmpty || !presentation.notices.isEmpty
            || !presentation.exits.isEmpty || !presentation.answer.isEmpty || !display.questions.isEmpty {
            let owner = conversation
            let questions = Binding<LioQuestionDraft> {
                var value = questionDrafts[turn.id] ?? display.draft()
                value.apply(messageID: display.messageID, questions: display.questions)
                return value
            } set: { value in
                if conversation === owner { questionDrafts[turn.id] = value }
            }
            LioExplorationReplyView(presentation: presentation, questions: questions, language: language,
                                    canSend: canRespond(to: turn.id, in: owner), editProfile: { entry in
                guard canRespond(to: turn.id, in: owner) else { return }
                profileEdit = ProfileEdit(owner: owner, turnID: turn.id, entry: entry)
            }) { text in
                guard canRespond(to: turn.id, in: owner) else { return }
                _ = sendQuestion(text)
            }
            .accessibilityIdentifier("lio.exploration.\(display.messageID)")
            .id(LioEntranceKey(turn: turn.id, part: .answer))
            .onChange(of: display, initial: true) { _, value in
                guard conversation === owner else { return }
                var selection = questionDrafts[turn.id] ?? value.draft()
                selection.apply(messageID: value.messageID, questions: value.questions)
                questionDrafts[turn.id] = selection
                if !value.presentation.segments.isEmpty || !value.presentation.answer.isEmpty {
                    recordExplorationBody(turn, presentation: value.presentation)
                    if followsAnswer, owner.turns.last?.id == turn.id { followReply(turn, scroll: scroll) }
                }
            }
            .onChange(of: turn.status) { _, _ in
                guard conversation === owner else { return }
                recordExplorationBody(turn, presentation: presentation)
            }
        }
    }

    private func recordExplorationBody(_ turn: LioTurn, presentation: LioExplorationPresentation) {
        guard !presentation.segments.isEmpty || !presentation.answer.isEmpty else { return }
        timing.mark(.firstText, turn.id)
        // This renderer exposes the admitted body at once. #913's segment pacing will own completion later.
        if turn.status == .finished { timing.mark(.finished, turn.id) }
    }

    private func followReply(_ turn: LioTurn, scroll: ScrollViewProxy) {
        if turn.exploration != nil {
            scroll.scrollTo(LioEntranceKey(turn: turn.id, part: .answer), anchor: .top)
        } else {
            scroll.scrollTo("lio.bottom", anchor: .bottom)
        }
    }

    private func canRespond(to turnID: Data, in owner: LioConversation) -> Bool {
        conversation === owner && conversation.turns.last?.id == turnID && canSwitchChat
    }

    private func cardBodyReady(_ turn: LioTurn) -> Bool {
        switch turn.status {
        // Native4's separate segment renderer does not use this pacing callback yet.
        // Keep its saved cards visible until #933 wires that renderer's completion.
        case .finished: turn.exploration != nil || turn.answer.isEmpty || completedBodies.contains(turn.id)
        case .failed: true
        case .thinking, .working, .answering: false
        }
    }

    private func memorySuggestion(_ tag: LioMemoryWire.Tag, turnID: Data,
                                  client: LioMemoryActionsClient) -> some View {
        LioMemoryConfirmation(text: tag.text, language: language, disabled: memoryBusy || memoryPending,
                              waiting: memoryPending && activeMemory == tag,
                              notice: memoryFeedback[tag]?.kind.text(language),
                              remember: { Task { await chooseMemory(.remember, tag: tag, turnID: turnID, client: client) } },
                              dismiss: { Task { await chooseMemory(.dismiss, tag: tag, turnID: turnID, client: client) } })
    }

    private var problemNotesSheet: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                Button { showsProblemNotes = false } label: {
                    Text(language.text("Done", "完成"))
                        .foregroundStyle(LioTheme.ink)
                        .frame(minWidth: 44, minHeight: 44)
                }
                .buttonStyle(.plain)
                .frame(maxWidth: .infinity, alignment: .trailing)
                .accessibilityIdentifier("lio.problems.done")
                LioProblemNotesSection(language: language, notes: .shared)
            }
            .frame(maxWidth: 480, alignment: .leading)
            .padding(24)
            .frame(maxWidth: .infinity)
        }
        .background(LioTheme.paper)
    }

    private func readFailureMessage(_ failure: LioRequestProblem) -> some View {
        let canReconnect = failure.needsReconnect && reconnect != nil
        return VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            RunReadableText(text: failure.message(language), color: LioTheme.ink)
                .accessibilityIdentifier("lio.read.failure")
            RunReadableText(text: failure.nextStep(language), color: LioTheme.inkSecondary)
            Button {
                if canReconnect { reconnect?() }
                else { refreshRequest += 1 }
            } label: {
                Text(canReconnect ? language.text("Reconnect", "重新连接") : language.text("Try reading again", "再次查看"))
                    .foregroundStyle(LioTheme.ink)
                    .frame(minHeight: 44)
            }
            .disabled(scenePhase != .active || (conversation.pending != nil && !canReconnect))
            .accessibilityIdentifier("lio.read.retry")
            Button { showsProblemNotes = true } label: {
                Text(language.text("View problem notes", "查看问题记录"))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .frame(minHeight: 44)
            }
            .accessibilityIdentifier("lio.read.problems")
        }
    }

    @ViewBuilder
    private func messageStatus(_ turn: LioTurn) -> some View {
        switch turn.status {
        case .thinking, .working:
            let input = LioThinkingInput(turn.exploration?.progress)
            LioThinkingIndicator(since: timing.indicatorStart(turn.id), progress: input.progress, planningDays: input.planningDays,
                                 language: language) { timing.mark(.indicator, turn.id) }
        case .failed(let failure):
            if let readFailure = turn.readFailure {
                readFailureMessage(readFailure)
            } else {
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
            if failure == .serviceLimit || (failure == .unavailable && turn.fromTimeline) {
                Text(language.text(
                    "If this keeps happening, view problem notes and contact the demo organiser.",
                    "如果持续失败，请查看问题记录并联系内测负责人。"))
                    .font(.caption)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.failure.next-step")
                Button { showsProblemNotes = true } label: {
                    RunReadableText(text: language.text("View problem notes", "查看问题记录"), color: LioTheme.ink)
                        .frame(minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("lio.failure.problems")
            }
            if failure == .unfinished {
                Button(language.text("Ask again", "重新问")) {
                    followsAnswer = true
                    conversation.askAgain(turn.id)
                    if let pending = conversation.pending {
                        timing.start(pending.id, language: timingLanguage)
                    }
                    preparePendingQuestion()
                }
                    .buttonStyle(.borderedProminent)
                    .tint(LioTheme.vermilion)
                    .foregroundStyle(LioTheme.onVermilion)
                    .controlSize(.large)
                    .disabled(conversation.pending != nil)
                    .accessibilityIdentifier("lio.askAgain")
            }
            }
        case .answering, .finished:
            EmptyView()
        }
    }
}
#endif
