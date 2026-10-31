#if os(iOS)
import SwiftUI
import CJMessageHTTP
import CJRunClient
import UIKit

private struct ShellHeaderHeight: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

struct AssistantShell: View {
    @Bindable var state: ShellState
    let messageHost: AssistantMessageHost
    let serverHistoryHost: ServerHistoryHost
    let needsHost: NeedsContainerHost
    let feedbackHost: FeedbackContainerHost
    let runHost: RunContainerHost
    let usageHost: OriginalUsageContainerHost
    let bodyText: String?
    private enum Panel: String, Identifiable { case local, server, needs, feedback, usage, travel; var id: String { rawValue } }
    @State private var panel: Panel?
    @State private var feedbackEntry: FeedbackContainerEntry?
    @FocusState private var draftFocused: Bool
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var headerHeight: CGFloat = 0
    @ScaledMetric(relativeTo: .body) private var controlIconSize = 20.0

    var body: some View {
        let answerEntry = feedbackHost.captureEntry()
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Color.clear.frame(height: dynamicTypeSize.isAccessibilitySize ? 0 : headerHeight + 12)
                    .accessibilityHidden(true)
                if !messageHost.isConfigured {
                    ShellStatusView(state: state.assistantState, language: state.language)
                }
                unavailableHint
                if let bodyText, !runHost.isShowingOriginal {
                    Text(bodyText).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    Button(state.language.text("Report a problem with this answer", "反馈此回答的问题")) {
                        feedbackEntry = answerEntry; panel = .feedback
                    }
                }
                Button(state.language.text("Server history and drafts", "服务器历史与草稿")) { panel = .server }
                    .accessibilityIdentifier("assistant.serverHistory")
                Button(state.language.text("Journey needs", "本次旅行需求")) { panel = .needs }.accessibilityIdentifier("assistant.needs")
                Button(state.language.text("Original usage status", "原调用用量")) { panel = .usage }
                if messageHost.supportsTripDiscussions {
                    if let conversation=messageHost.selectedConversation {
                        RunReadableText(text:state.language.text("Conversation: ","会话：")+conversation,style:.caption)
                            .accessibilityIdentifier("assistant.conversation")
                    }
                    TripDiscussionChoiceView(host:messageHost,language:state.language,openTrips:{ state.selectedTab = .trips })
                }
                if messageHost.travelSelection != nil {
                    Button { panel = .travel } label: {
                        RunReadableText(text:state.language.text("Choose travel context", "选择旅行上下文"))
                            .frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle())
                    }.buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("assistant.travelContext")
                }
                RunContainerView(host: runHost, messages: messageHost, language: state.language, openNeeds: { panel = .needs })
                MessageRecoveryStatus(host: messageHost, language: state.language)
                if let text = messageHost.visibleOriginalText {
                    RunSelectableText(text: text).frame(maxWidth: .infinity, alignment: .trailing)
                        .accessibilityLabel(state.language.text("Original message", "原消息"))
                        .accessibilityIdentifier("assistant.originalText")
                }
            }
            .padding(.horizontal)
            .padding(.bottom)
        }
        .scrollDismissesKeyboard(.interactively)
        .clipped()
        .safeAreaInset(edge: .top, spacing: 0) {
            Color.clear.frame(height: dynamicTypeSize.isAccessibilitySize ? headerHeight + 8 : 0)
                .accessibilityHidden(true)
        }
        .overlay(alignment: .top) {
            floatingControls.accessibilityElement(children:.contain).accessibilityIdentifier("assistant.header").background {
                GeometryReader { geometry in
                    Color.clear.preference(key: ShellHeaderHeight.self, value: geometry.size.height)
                }
            }
        }
        .onPreferenceChange(ShellHeaderHeight.self) { headerHeight = $0 }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer.accessibilityElement(children:.contain).accessibilityIdentifier("assistant.composer") }
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
        }
        .sheet(item: $panel) { selectedPanel in
            NavigationStack {
                Group {
                    if selectedPanel == .travel {
                        if let travel = messageHost.travelSelection {
                            TravelSelectionView(model:travel,language:state.language)
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

    private var floatingControls: some View {
        HStack(alignment: .top) {
            Button { panel = .local } label: {
                VStack(spacing: 5) {
                    Capsule().frame(width: 20, height: 2)
                    Capsule().frame(width: 20, height: 2)
                }
                .frame(minWidth: 44, minHeight: 44)
                .contentShape(Circle())
            }
            .background(.thinMaterial, in: Circle())
            .accessibilityLabel(state.language.text("Local recovery", "本地恢复"))
            .accessibilityIdentifier("assistant.history")
            Spacer(minLength: 8)
            VStack(spacing: 4) {
                BrandAvatar(compact: draftFocused || dynamicTypeSize.isAccessibilitySize)
                if !draftFocused {
                    Text(state.language.text("Assistant", "助手")).font(.headline)
                }
            }
            .padding(8)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 20))
            .accessibilityElement(children: .combine)
            .accessibilityLabel(state.language.text("Assistant", "助手"))
            Spacer(minLength: 8)
            unavailableIcon("gift", english: "Gifts — not available", chinese: "礼物——尚未开放")
                .background(.thinMaterial, in: Circle())
        }.padding(.horizontal).padding(.top, 8)
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 6) {
            if messageHost.supportsSending {
                if !messageHost.supportsTripDiscussions,let conversation = messageHost.selectedConversation {
                    RunReadableText(text: state.language.text("Conversation: ", "会话：") + conversation, style: .caption)
                        .accessibilityIdentifier("assistant.conversation")
                }
                if !messageHost.supportsTripDiscussions { Toggle(isOn: Binding(
                    get: { messageHost.creationIntent == .considerTrip },
                    set: { messageHost.creationIntent = $0 ? .considerTrip : .none })) {
                    RunReadableText(text: state.language.text("Trip planning", "规划行程"))
                }
                    .accessibilityLabel(state.language.text("Trip planning", "规划行程"))
                    .disabled(messageHost.isBusy)
                    .accessibilityIdentifier("assistant.intent")
                }
            }
            HStack(alignment: .bottom, spacing: 4) {
                unavailableIcon("plus", english: "Attachments — not available", chinese: "附件——尚未开放")
                TextField(state.language.text("Start chatting", "开始聊天"), text: $state.draft, axis: .vertical)
                    .lineLimit(1...(dynamicTypeSize.isAccessibilitySize ? 3 : 5))
                    .focused($draftFocused)
                    .padding(.vertical, 12)
                    .accessibilityLabel(state.language.text("Message draft", "消息草稿"))
                    .accessibilityIdentifier("assistant.draft")
                    .disabled(messageHost.isBusy)
                if state.hasDraft {
                    if messageHost.supportsSending {
                        Button { messageHost.sendNew(); draftFocused = false } label: {
                            Image(systemName: "arrow.up").font(.system(size: min(controlIconSize, 32)))
                                .frame(minWidth: 44, minHeight: 44)
                        }
                        .disabled(!messageHost.canSend)
                        .accessibilityLabel(state.language.text("Send", "发送"))
                        .accessibilityIdentifier("assistant.send")
                    } else {
                        unavailableIcon("arrow.up", english: "Send — service not connected", chinese: "发送——服务尚未接入")
                    }
                } else {
                    unavailableIcon("mic", english: "Voice — not available", chinese: "语音——尚未开放")
                }
            }
            .padding(.horizontal, 4)
            .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 28))
        }
        .padding(.horizontal).padding(.vertical, 8)
        .background(.regularMaterial)
    }

    private var unavailableHint: some View {
        Text(messageHost.supportsSending
                 ? state.language.text("Choose a conversation in history. Unsent drafts are saved locally.", "请在历史中选择会话。未发送草稿会保存在本地。")
                 : draftFocused
                 ? state.language.text("Sending unavailable", "发送尚未开放")
                 : state.language.text("Sending, attachments, voice and gifts are not available yet.", "发送、附件、语音和礼物尚未开放。"))
                .font(.caption).foregroundStyle(.primary).fixedSize(horizontal: false, vertical: true)
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
