#if os(iOS)
import SwiftUI
import CJMessageHTTP
import CJRunClient
import CJTripClient

public struct LioHome<MenuContent: View>: View {
    private let language: LioLanguage
    private let isDemo: Bool
    private let menu: MenuContent
    private let tripLibrary: LioTripLibrary?
    private let memoryActions: LioMemoryActionsClient?
    private let savedMemory: AnyView?
    private let recordedMap: (@MainActor (StructuredTripDocument) -> AnyView)?
    @State private var conversation: LioConversation
    @State private var tripPlan: LioTripPlan?
    @State private var draft = ""
    @State private var menuOpen = false
    @State private var source: LioSource?
    @State private var followsAnswer = true
    @State private var tab = Tab.chat
    @State private var memoryBusy = false
    @State private var memoryPending = false
    @State private var memoryNotice: String?
    @State private var activeMemory: LioMemoryWire.Tag?
    @State private var handledTags: Set<LioMemoryWire.Tag> = []
    @State private var refreshRequest = 0
    private struct Observation: Equatable {
        let active: Bool
        let request: Int
    }
    private struct TripObservation: Equatable {
        let active: Bool
        let card: LioTripCard?
    }
    private enum Tab { case chat, trips, memory }
    @FocusState private var typing: Bool
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(language: LioLanguage, service: LioService, isDemo: Bool, tripLibrary: LioTripLibrary? = nil,
                tripHistory: LioTripHistoryClient? = nil,
                memoryActions: LioMemoryActionsClient? = nil,
                savedMemory: AnyView? = nil,
                recordedMap: (@MainActor (StructuredTripDocument) -> AnyView)? = nil, @ViewBuilder menu: () -> MenuContent) {
        self.language = language
        self.isDemo = isDemo
        self.menu = menu()
        self.tripLibrary = tripLibrary
        self.memoryActions = memoryActions
        self.savedMemory = savedMemory
        self.recordedMap = recordedMap
        _conversation = State(initialValue: LioConversation(service: service))
        _tripPlan = State(initialValue: tripHistory.map { LioTripPlan(client: $0) })
    }

    private var latestTripCard: LioTripCard? {
        guard let turn = conversation.turns.last(where: { $0.itinerary != nil }),
              let itinerary = turn.itinerary else { return nil }
        return LioTripCard(turnID: turn.id, itinerary: itinerary)
    }

    public var body: some View {
        let pending = conversation.pending
        let canObserve = scenePhase == .active && pending == nil
        let tripCard = latestTripCard
        TabView(selection: $tab) {
            chat
                .tabItem { Label(language.text("Chat", "聊天"), systemImage: "bubble.left") }
                .tag(Tab.chat)
            LioTripsView(itineraries: conversation.itineraries, language: language, library: tripLibrary,
                         tripPlan: tripPlan, currentPlan: tripPlan?.current(for: tripCard),
                         canUndo: canObserve && tripPlan?.requestedCard == tripCard,
                         recordedMap: recordedMap) { tab = .chat }
                .tabItem { Label(language.text("Trips", "行程"), systemImage: "suitcase") }
                .tag(Tab.trips)
            if let savedMemory {
                savedMemory
                    .tabItem { Label(language.text("Memory", "记忆"), systemImage: "bookmark") }
                    .tag(Tab.memory)
            }
        }
        .onChange(of: tab) { _, _ in typing = false }
        .task(id: Observation(active: canObserve, request: refreshRequest)) {
            if canObserve { await conversation.refreshTimeline() }
        }
        .task(id: TripObservation(active: canObserve, card: tripCard)) {
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
                    if conversation.turns.isEmpty { examples }
                    ForEach(conversation.turns) { turn in
                        VStack(alignment: .leading, spacing: 22) {
                            if turn.id == earlierID { earlierMessages(scroll) }
                            turnView(turn)
                        }
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
                .padding(.top, 86)
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
                else { withAnimation(.easeOut(duration: 0.22)) { scroll.scrollTo("lio.bottom", anchor: .bottom) } }
            }
            .onChange(of: latest?.answer) { _, _ in
                if followsAnswer, let pending, latest?.id == pending.id { scroll.scrollTo("lio.bottom", anchor: .bottom) }
            }
            .onChange(of: latest?.status) { _, status in
                if followsAnswer && status == .finished { scroll.scrollTo("lio.bottom", anchor: .bottom) }
            }
        }
        .background(Color(uiColor: .systemBackground))
        .overlay(alignment: .top) { floatingControls }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .sheet(isPresented: $menuOpen) {
            NavigationStack {
                List {
                    if isDemo {
                        Text(language.text("Sample replies only", "仅提供演示回答"))
                    }
                    menu
                }
                .navigationTitle(language.text("Menu", "菜单"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button(language.text("Done", "完成")) { menuOpen = false }
                    }
                }
            }
        }
        .sheet(item: $source) { selected in
            LioSourceSheet(source: selected, language: language)
        }
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
        ZStack(alignment: .leading) {
            HStack(spacing: 8) {
                Image("LioAvatar", bundle: .module)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 34, height: 34)
                    .clipShape(Circle())
                    .accessibilityHidden(true)
                Text("Lio").font(.headline)
            }
            .padding(6)
            .padding(.trailing, 8)
            .background(.regularMaterial, in: Capsule())
            .frame(maxWidth: .infinity)
            .accessibilityIdentifier("lio.name")
            Button {
                typing = false
                menuOpen = true
            } label: {
                Text("≋")
                    .font(.title3.weight(.medium))
                    .frame(width: 48, height: 48)
                    .background(.regularMaterial, in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(language.text("Menu", "菜单"))
            .accessibilityIdentifier("lio.menu")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
    }

    private var examples: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(language.text("Where are you headed?", "你想去哪儿？"))
                .font(.title2.weight(.semibold))
            if isDemo {
                Text(language.text("Try a sample question.", "可以先试一个示例问题。"))
                    .font(.subheadline)
                    .foregroundStyle(Color.primary.opacity(0.78))
            }
            ForEach(Array(LioDemo.examples(language).enumerated()), id: \.offset) { index, example in
                Button {
                    draft = example
                    typing = true
                } label: {
                    HStack(spacing: 12) {
                        RunReadableText(text: example)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: "arrow.up.left").accessibilityHidden(true)
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .frame(minHeight: 48)
                    .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(example)
                .accessibilityIdentifier("lio.example.\(index)")
            }
        }
    }

    private var composer: some View {
        let placeholder = language.text("Start chatting", "开始聊天")
        let canSend = !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && conversation.pending == nil
        return HStack(alignment: .bottom, spacing: 10) {
            TextField(placeholder, text: $draft, prompt: Text(placeholder).foregroundStyle(Color.primary.opacity(0.78)), axis: .vertical)
                .lineLimit(1...5)
                .frame(minHeight: 44)
                .focused($typing)
                .accessibilityIdentifier("lio.composer")
            Button {
                followsAnswer = true
                conversation.send(draft, language: language)
                draft = ""
                typing = false
            } label: {
                Image(systemName: "arrow.up")
                    .font(.body.weight(.semibold))
                    .frame(width: 44, height: 44)
                    .foregroundStyle(canSend ? Color(uiColor: .systemBackground) : Color.primary.opacity(0.72))
                    .background(canSend ? Color.primary : Color(uiColor: .tertiarySystemFill), in: Circle())
            }
            .disabled(!canSend)
            .buttonStyle(.plain)
            .accessibilityLabel(language.text("Send", "发送"))
            .accessibilityIdentifier("lio.send")
        }
        .padding(.leading, 16)
        .padding(5)
        .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 27))
        .frame(maxWidth: 680)
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(Color(uiColor: .systemBackground))
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
                Spacer(minLength: 32)
                if turn.status == .failed(.notSent) {
                    Button {
                        if turn.id == conversation.turns.last?.id { followsAnswer = true }
                        conversation.resend(turn.id)
                    } label: {
                        Image(systemName: "exclamationmark.circle.fill")
                            .foregroundStyle(.red)
                            .frame(width: 44, height: 44)
                    }
                    .buttonStyle(.plain)
                    .disabled(conversation.pending != nil)
                    .accessibilityLabel(language.text("Send again", "重新发送"))
                    .accessibilityIdentifier("lio.resend")
                }
                Text(turn.question.text)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 19))
                    .textSelection(.enabled)
                    .accessibilityIdentifier("lio.question")
            }
            if !turn.answer.isEmpty {
                Text(turn.answer)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
                    .accessibilityIdentifier("lio.answer")
            }
            messageStatus(turn)
            if let itinerary = turn.itinerary {
                let card = LioTripCard(turnID: turn.id, itinerary: itinerary)
                let isLatest = card == latestTripCard
                let current = isLatest ? tripPlan?.current(in: card) : nil
                LioItineraryCard(itinerary: current ?? itinerary, language: language) {
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
            if let memoryActions {
                ForEach(turn.memoryTags.filter { !handledTags.contains($0) }) { tag in
                    VStack(alignment: .leading, spacing: 4) {
                        RunReadableText(text: language.text("Remember: \(tag.text)?", "记住：\(tag.text)？"))
                        HStack {
                            Button(language.text("Remember", "记住")) {
                                Task { await chooseMemory(.remember, tag: tag, client: memoryActions) }
                            }
                            .buttonStyle(.bordered)
                            .accessibilityIdentifier("lio.memory.remember")
                            Button(language.text("Dismiss", "不用")) {
                                Task { await chooseMemory(.dismiss, tag: tag, client: memoryActions) }
                            }
                            .buttonStyle(.borderless)
                            .accessibilityIdentifier("lio.memory.dismiss")
                        }
                        .disabled(memoryBusy || memoryPending)
                    }
                    .padding(.vertical, 4)
                }
            }
            ForEach(turn.sources) { item in
                Button { source = item } label: {
                    Label(item.title, systemImage: "link")
                        .font(.footnote)
                        .padding(.horizontal, 11)
                        .frame(minHeight: 44)
                        .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.source")
            }
        }
    }

    @ViewBuilder
    private func messageStatus(_ turn: LioTurn) -> some View {
        switch turn.status {
        case .thinking:
            statusLine(language.text("Thinking…", "思考中…"))
        case .working(let activity):
            let status = switch activity {
            case .places: language.text("Looking up places…", "正在找地点…")
            case .weather: language.text("Checking the weather…", "正在查天气…")
            case .directions: language.text("Looking for directions…", "正在找路线…")
            case .travelInformation: language.text("Checking travel information…", "正在查旅行信息…")
            }
            statusLine(status)
        case .failed(let failure):
            let message = switch failure {
            case .notSent: language.text("Message couldn’t be sent. Check your connection and tap to try again.",
                                         "消息没发出去。检查网络后，点感叹号重发。")
            case .dailyLimit: language.text("You’ve used today’s 40 questions. Try again tomorrow.",
                                            "今天的 40 个问题已用完，明天再来聊吧。")
            case .unfinished: language.text("I couldn’t finish this one.", "这次没答完。")
            case .waiting: language.text("I don’t have an answer for this yet.", "这条消息暂时还没有回答。")
            case .unavailable: language.text("Chat isn’t available right now.", "现在暂时不能聊天。")
            }
            Text(message)
                .font(.footnote)
                .foregroundStyle(Color.primary.opacity(0.78))
                .accessibilityIdentifier("lio.failure")
            if failure == .unfinished {
                Button(language.text("Ask again", "重新问")) {
                    followsAnswer = true
                    conversation.askAgain(turn.id)
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

    private func statusLine(_ title: String) -> some View {
        Label(title, systemImage: "ellipsis.bubble")
            .font(.footnote)
            .foregroundStyle(Color.primary.opacity(0.78))
            .accessibilityIdentifier("lio.progress")
    }
}

private struct LioSourceSheet: View {
    let source: LioSource
    let language: LioLanguage
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Text(source.title).textSelection(.enabled)
                if let url = source.url {
                    Link(language.text("Open source", "打开来源"), destination: url)
                } else {
                    Text(language.text("No link for this source.", "这条来源没有链接。"))
                        .foregroundStyle(Color.primary.opacity(0.78))
                }
            }
            .navigationTitle(language.text("Source", "来源"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(language.text("Done", "完成")) { dismiss() }
                }
            }
        }
    }
}
#endif
