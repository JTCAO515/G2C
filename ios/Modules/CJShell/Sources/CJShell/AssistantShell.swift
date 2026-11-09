#if os(iOS)
import SwiftUI
import CJMessageHTTP
import CJRunClient
import UIKit

struct AssistantShell: View {
    @Bindable var state: ShellState
    let messageHost: AssistantMessageHost
    let serverHistoryHost: ServerHistoryHost
    let candidateHost: MemoryCandidateContainerHost
    let needsHost: NeedsContainerHost
    let feedbackHost: FeedbackContainerHost
    let runHost: RunContainerHost
    let usageHost: OriginalUsageContainerHost
    let bodyText: String?
    private enum Panel: String, Identifiable { case local, server, needs, feedback, usage, travel, memoryCandidates; var id: String { rawValue } }
    @State private var panel: Panel?
    @State private var feedbackEntry: FeedbackContainerEntry?
    @FocusState private var draftFocused: Bool
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .body) private var controlIconSize = 20.0

    var body: some View {
        let answerEntry = feedbackHost.captureEntry()
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if !messageHost.isConfigured {
                    ShellStatusView(state: state.assistantState, language: state.language)
                }
                conversationContext
                if let text = messageHost.visibleOriginalText {
                    VStack(alignment: .trailing, spacing: 6) {
                        Label(state.language.text("You", "你"), systemImage: "person.crop.circle")
                            .font(.caption.weight(.semibold))
                        RunSelectableText(text: text)
                            .accessibilityLabel(state.language.text("Original message", "原消息"))
                            .accessibilityIdentifier("assistant.originalText")
                    }
                    .padding(14)
                    .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 18))
                    .padding(.leading, dynamicTypeSize.isAccessibilitySize ? 0 : 28)
                }
                MemoryCandidateConversationBubble(host: candidateHost, language: state.language) { panel = .memoryCandidates }
                if let bodyText, !runHost.isShowingOriginal {
                    VStack(alignment: .leading, spacing: 8) {
                        Label(state.language.text("Assistant", "助手"), systemImage: "sparkles")
                            .font(.caption.weight(.semibold))
                        Text(bodyText).textSelection(.enabled)
                    }.shellCard()
                    Button {
                        feedbackEntry = answerEntry; panel = .feedback
                    } label: {
                        feedbackLabel
                    }.buttonStyle(ShellActionButtonStyle())
                }
                RunContainerView(host: runHost, messages: messageHost, language: state.language, openNeeds: { panel = .needs })
                    .shellCard()
                if runHost.originalPresentationID != nil {
                    Button {
                        do { feedbackEntry = try feedbackHost.prepareAnswer(from: runHost) }
                        catch { feedbackEntry = nil } // The panel explicitly reports unavailable; no alternate source.
                        panel = .feedback
                    } label: {
                        feedbackLabel
                    }.buttonStyle(ShellActionButtonStyle()).accessibilityIdentifier("assistant.feedback")
                }
                if messageHost.supportsScopedEdits, let scoped = messageHost.scopedCandidates,messageHost.scopedDisplays?.hasResult != true {
                    ScopedCandidateView(host: scoped, messages: messageHost, language: state.language)
                }
                if let display=messageHost.scopedDisplays {
                    ScopedDisplayView(host:display,runs:runHost,language:state.language,chooseAgain:{ state.selectedTab = .trips })
                }
                if let planning=messageHost.planningCandidates {
                    NeedsPlanningView(host:planning,messages:messageHost,language:state.language)
                }
                MessageRecoveryStatus(host: messageHost, language: state.language)
            }
            .padding(.horizontal)
            .padding(.vertical, 12)
        }
        .scrollDismissesKeyboard(.interactively)
        .clipped()
        .safeAreaInset(edge: .top, spacing: 0) {
            header.accessibilityElement(children: .contain).accessibilityIdentifier("assistant.header")
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            composer.accessibilityElement(children: .contain).accessibilityIdentifier("assistant.composer")
        }
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button(state.language.text("Done", "完成")) { draftFocused = false }
            }
        }
        .onChange(of: state.generation) { _, _ in
            draftFocused = false
            panel = nil; feedbackEntry = nil
        }
        .onChange(of: state.draft) { _, _ in messageHost.saveDraft() }
        .onChange(of: state.selectedTab) { _, tab in
            if tab != .assistant { draftFocused = false }
        }
        .onChange(of: panel) { _, selected in
            if selected != nil { draftFocused = false }
            else { candidateHost.synchronizeConversation() }
        }
        .sheet(item: $panel) { selectedPanel in
            NavigationStack {
                Group {
                    if selectedPanel == .travel {
                        if let travel = messageHost.travelSelection {
                            TravelSelectionView(model:travel,language:state.language,requiresTravel:messageHost.supportsScopedEdits).disabled(messageHost.supportsScopedEdits && messageHost.isBusy)
                        } else {
                            RunReadableText(text:state.language.text("Travel context unavailable", "旅行上下文不可用"))
                        }
                    } else if selectedPanel == .usage {
                        OriginalUsageContainerView(host: usageHost, messages: messageHost, language: state.language)
                    } else if selectedPanel == .feedback {
                        FeedbackContainerView(host: feedbackHost, entry: feedbackEntry, language: state.language)
                    } else if selectedPanel == .needs {
                        NeedsContainerView(host: needsHost, runs: runHost, language: state.language).id(needsHost.viewIdentity)
                    } else if selectedPanel == .server {
                        ServerHistoryView(host: serverHistoryHost, language: state.language)
                    } else if selectedPanel == .memoryCandidates {
                        MemoryCandidateContainerView(host: candidateHost, language: state.language)
                    } else {
                        LocalRecoveryList(host: messageHost, language: state.language)
                            .navigationTitle(state.language.text("Local recovery", "本地恢复"))
                    }
                }
                .toolbar { ToolbarItem(placement: .confirmationAction) {
                    AssistantPanelDoneButton(title:state.language.text("Done", "完成")) { panel = nil }
                }}
            }
        }

    }

    private var feedbackLabel: some View {
        ShellActionLabel(title: state.language.text("Report a problem with this answer", "反馈此回答的问题"),
                         symbol: "exclamationmark.bubble")
    }

    private var conversationContext: some View {
        VStack(alignment: .leading, spacing: 12) {
            ShellCardHeading(title: state.language.text("Conversation context", "会话上下文"),
                             symbol: "bubble.left.and.bubble.right")
            if let conversation = messageHost.selectedConversation {
                if messageHost.supportsTripMessages {
                    RunReadableText(text: state.language.text("Conversation identifier", "会话标识"), style: .caption)
                    RunSelectableText(text: conversation)
                        .accessibilityLabel(state.language.text("Conversation identifier", "会话标识"))
                        .accessibilityValue(conversation)
                        .accessibilityIdentifier("assistant.conversation")
                } else {
                    RunReadableText(text: state.language.text("Conversation: ", "会话：") + conversation, style: .caption)
                        .accessibilityIdentifier("assistant.conversation")
                }
            }
            if messageHost.supportsSending && !messageHost.supportsTripMessages {
                Toggle(isOn: Binding(
                    get: { messageHost.creationIntent == .considerTrip },
                    set: { messageHost.creationIntent = $0 ? .considerTrip : .none }
                )) {
                    HStack(spacing: 8) {
                        Image(systemName: "map").accessibilityHidden(true)
                        RunReadableText(text: state.language.text("Trip planning", "规划行程"))
                    }
                }
                .accessibilityLabel(state.language.text("Trip planning", "规划行程"))
                .disabled(messageHost.isBusy)
                .accessibilityIdentifier("assistant.intent")
            }
            if let travel = messageHost.travelSelection {
                if let version = needsVersion {
                    RunReadableText(text: state.language.text("Journey needs read · version ", "已读取旅行需求 · 版本 ") + String(version), style: .caption)
                        .accessibilityIdentifier("assistant.needs.status")
                } else {
                    let needsStatus = needsHost.isConfigured
                        ? state.language.text("Journey needs not read", "尚未读取旅行需求")
                        : state.language.text("Journey needs unavailable", "旅行需求不可用")
                    RunReadableText(text: needsStatus, style: .caption)
                        .accessibilityIdentifier("assistant.needs.status")
                }
                RunReadableText(text: travelSummary(travel.state), style: .caption)
                    .accessibilityIdentifier("assistant.travel.status")
            }
            if !state.hasDraft || !messageHost.supportsSending, let sendGuidance {
                RunReadableText(text: sendGuidance, style: .caption)
                    .accessibilityIdentifier("assistant.send.guidance")
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8, alignment: .topLeading),
                                     count: dynamicTypeSize.isAccessibilitySize ? 1 : 2), spacing: 8) {
                Button { panel = .needs } label: {
                    ShellActionLabel(title: state.language.text("Journey needs", "本次旅行需求"), symbol: "list.bullet.rectangle")
                }.accessibilityIdentifier("assistant.needs")
                if messageHost.travelSelection != nil {
                    Button { panel = .travel } label: {
                        ShellActionLabel(title: state.language.text("Choose travel context", "选择旅行上下文"), symbol: "suitcase")
                    }.accessibilityIdentifier("assistant.travelContext")
                }
                if messageHost.supportsDemoConversationOpening {
                    let newChat = messageHost.captureNewConversationIntent()
                    Button {
                        if let newChat { messageHost.performConversationIntent(newChat) }
                    } label: {
                        ShellActionLabel(title: state.language.text("New conversation", "新建会话"), symbol: "plus.bubble")
                    }
                    .disabled(newChat == nil).accessibilityIdentifier("assistant.chat.new")
                }
                Button { panel = .server } label: {
                    ShellActionLabel(title: state.language.text("History & drafts", "历史与草稿"), symbol: "clock")
                }
                .accessibilityLabel(state.language.text("Server history and drafts", "服务器历史与草稿"))
                .accessibilityIdentifier("assistant.serverHistory")
                Button { panel = .usage } label: {
                    ShellActionLabel(title: state.language.text("Original usage status", "原调用用量"), symbol: "chart.bar")
                }
            }.buttonStyle(ShellActionButtonStyle())
            if messageHost.supportsDemoConversationOpening, case .unknown = messageHost.conversationState {
                RunReadableText(text: state.language.text("Conversation result unknown. Check the original in local recovery.",
                                                           "会话结果未知，请在本地恢复中核对原请求。"), style: .caption)
                    .accessibilityIdentifier("assistant.chat.status")
            }
            if messageHost.supportsScopedEdits {
                ScopedMessageChoiceView(host: messageHost, language: state.language,
                    openTrips: { state.selectedTab = .trips }, openNeeds: { panel = .needs })
            } else if messageHost.supportsTripDiscussions {
                TripDiscussionChoiceView(host: messageHost, language: state.language,
                    openTrips: { state.selectedTab = .trips })
            }
        }.shellCard()
    }

    private var needsVersion: Int64? {
        guard !needsHost.busy, let value = needsHost.presentation, value.state == .loaded,
              let version = value.snapshot?.version else { return nil }
        return Int64(version)
    }

    private func travelSummary(_ selection: TravelSelectionState) -> String {
        switch selection {
        case .travel(let travel):
            state.language.text("Travel selected · version ", "已选择旅行 · 版本 ") + String(travel.version)
        case .none: state.language.text("Long-term memory only · no travel selected", "仅长期记忆 · 未绑定旅行")
        case .loading: state.language.text("Checking the travel context…", "正在核对旅行上下文…")
        case .unavailable: state.language.text("Travel context unavailable", "旅行上下文不可用")
        case .unselected: state.language.text("Travel context not selected", "尚未选择旅行上下文")
        }
    }

    private var sendGuidance: String? {
        let language = state.language
        guard messageHost.supportsSending else {
            return draftFocused ? language.text("Sending unavailable", "发送尚未开放")
                : language.text("Sending, attachments, voice and gifts are not available yet.", "发送、附件、语音和礼物尚未开放。")
        }
        guard !messageHost.canStartMessage else { return nil }
        if messageHost.isBusy { return language.text("Waiting for the current request…", "正在等待当前请求…") }
        if messageHost.selectedConversation == nil {
            return language.text("Choose a conversation in history. Unsent drafts are saved locally.",
                                 "请在历史中选择会话。未发送草稿会保存在本地。")
        }
        guard !messageHost.supportsTripMessages else { return nil }
        if let travel = messageHost.travelSelection {
            let planning = messageHost.creationIntent == .considerTrip
            if planning && needsVersion == nil {
                return needsHost.isConfigured
                    ? language.text("Read the saved journey needs before sending a plan request.", "发送规划请求前，请先读取已保存的旅行需求。")
                    : language.text("Journey needs are unavailable for this session.", "当前会话的旅行需求不可用。")
            }
            switch travel.state {
            case .unselected, .unavailable:
                return language.text("Choose a travel context before sending.", "发送前请选择旅行上下文。")
            case .none where planning:
                return language.text("Trip planning requires a selected travel context.", "规划行程需要选择实际旅行上下文。")
            case .loading:
                return language.text("Waiting for the travel context to be verified…", "正在等待旅行上下文核实…")
            default: break
            }
        }
        return language.text("Select this conversation in server history to refresh its current state.",
                             "请在服务器历史中选中此会话，刷新当前状态。")
    }

    private var header: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button { panel = .local } label: {
                    Image(systemName: "line.3.horizontal")
                        .font(.system(size: min(controlIconSize, 32)))
                        .frame(width: 44, height: 44)
                        .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
                        .contentShape(RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(state.language.text("Local recovery", "本地恢复"))
                .accessibilityIdentifier("assistant.history")
                Spacer(minLength: 0)
                HStack(spacing: 6) {
                    BrandAvatar(compact: true)
                    RunReadableText(text: state.language.text("Assistant", "助手"), style: .headline)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel(state.language.text("Assistant", "助手"))
                Spacer(minLength: 0)
                unavailableIcon("gift", english: "Gifts — not available", chinese: "礼物——尚未开放")
            }.padding(.horizontal).padding(.vertical, 5)
            Divider()
        }.background(Color(uiColor: .systemBackground))
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 0) {
            Divider()
            if state.hasDraft, messageHost.supportsSending, let sendGuidance {
                Label {
                    RunReadableText(text: sendGuidance, style: .caption)
                } icon: {
                    Image(systemName: "info.circle").font(.caption).accessibilityHidden(true)
                }
                    .padding(.horizontal)
                    .padding(.top, 6)
                    .accessibilityIdentifier("assistant.send.guidance")
            }
            HStack(alignment: .bottom, spacing: 8) {
                unavailableIcon("plus", english: "Attachments — not available", chinese: "附件——尚未开放")
                TextField(state.language.text("Start chatting", "开始聊天"), text: $state.draft, axis: .vertical)
                    .lineLimit(1...(dynamicTypeSize.isAccessibilitySize ? 3 : 5))
                    .focused($draftFocused)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
                    .accessibilityLabel(state.language.text("Message draft", "消息草稿"))
                    .accessibilityIdentifier("assistant.draft")
                    .disabled(messageHost.isBusy)
                if messageHost.supportsSending {
                    Button { messageHost.sendNew(); draftFocused = false } label: {
                        if dynamicTypeSize.isAccessibilitySize {
                            Image(systemName: "arrow.up").frame(minWidth: 36, minHeight: 36)
                        } else {
                            Label(state.language.text("Send", "发送"), systemImage: "arrow.up")
                                .frame(minHeight: 36)
                        }
                    }
                    .buttonStyle(AssistantSendButtonStyle())
                    .disabled(!messageHost.canSend)
                    .accessibilityLabel(state.language.text("Send", "发送"))
                    .accessibilityIdentifier("assistant.send")
                } else if state.hasDraft {
                    unavailableIcon("arrow.up", english: "Send — service not connected", chinese: "发送——服务尚未接入")
                } else {
                    unavailableIcon("mic", english: "Voice — not available", chinese: "语音——尚未开放")
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
        }.background(Color(uiColor: .systemBackground))
    }

    private func unavailableIcon(_ symbol: String, english: String, chinese: String) -> some View {
        Button {} label: {
            Image(systemName: symbol).font(.system(size: min(controlIconSize, 32)))
                .frame(minWidth: 44, minHeight: 44)
        }
            .disabled(true)
            .accessibilityLabel(state.language.text(english, chinese))
    }
}

/// A toolbar hosts this complete native control, preserving both UIKit hit
/// testing and content-size-category updates; a label-only bridge loses the hit.
struct AssistantPanelDoneButton: UIViewRepresentable {
    let title: String
    var identifier: String = "assistant.panel.done"
    let action: @MainActor () -> Void
    func makeCoordinator() -> Coordinator { Coordinator(action) }
    func makeUIView(context: Context) -> UIButton {
        let button=UIButton(type:.system)
        button.titleLabel?.adjustsFontForContentSizeCategory=true
        button.accessibilityIdentifier=identifier
        button.addTarget(context.coordinator,action:#selector(Coordinator.activate),for:.touchUpInside)
        return button
    }
    func updateUIView(_ button: UIButton,context: Context) {
        context.coordinator.action=action
        button.setTitle(title,for:.normal)
        button.setTitleColor(.label,for:.normal)
        button.titleLabel?.font=UIFont.preferredFont(forTextStyle:.body,compatibleWith:button.traitCollection)
        button.accessibilityLabel=title
    }
    func sizeThatFits(_ proposal: ProposedViewSize,uiView: UIButton,context: Context) -> CGSize? {
        let size=uiView.intrinsicContentSize
        return CGSize(width:max(44,size.width),height:max(44,size.height))
    }
    final class Coordinator: NSObject {
        var action: @MainActor () -> Void
        init(_ action: @escaping @MainActor () -> Void) { self.action=action }
        @MainActor @objc func activate() { action() }
    }
}
#endif
