#if os(iOS)
import SwiftUI
import CJMessageHTTP

struct AssistantShell: View {
    @Bindable var state: ShellState
    let messageHost: AssistantMessageHost
    let serverHistoryHost: ServerHistoryHost
    let needsHost: NeedsContainerHost
    let feedbackHost: FeedbackContainerHost
    let runHost: RunContainerHost
    let usageHost: OriginalUsageContainerHost
    let bodyText: String?
    private enum Panel: String, Identifiable { case local, server, needs, feedback, usage; var id: String { rawValue } }
    @State private var panel: Panel?
    @State private var feedbackEntry: FeedbackContainerEntry?
    @FocusState private var draftFocused: Bool
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .body) private var controlIconSize = 20.0

    var body: some View {
        let answerEntry = feedbackHost.captureEntry()
        VStack(spacing: 0) {
            floatingControls.padding(.bottom, dynamicTypeSize.isAccessibilitySize ? 8 : 12)
            ScrollView {
            VStack(alignment: .leading, spacing: 16) {
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
                Button(state.language.text("Journey needs", "本次旅行需求")) { panel = .needs }
                Button(state.language.text("Original usage status", "原调用用量")) { panel = .usage }
                RunContainerView(host: runHost, messages: messageHost, language: state.language)
                MessageRecoveryStatus(host: messageHost, language: state.language)
                if let text = messageHost.visibleOriginalText {
                    Text(text).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .trailing)
                        .accessibilityIdentifier("assistant.originalText")
                }
            }
            .padding(.horizontal)
            .padding(.bottom)
        }
            .scrollDismissesKeyboard(.interactively)
            .clipped()
            composer
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
        }
        .sheet(item: $panel) { selectedPanel in
            NavigationStack {
                Group {
                    if selectedPanel == .usage {
                        OriginalUsageContainerView(host: usageHost, messages: messageHost, language: state.language)
                    } else if selectedPanel == .feedback {
                        FeedbackContainerView(host: feedbackHost, entry: feedbackEntry, language: state.language)
                    } else if selectedPanel == .needs {
                        NeedsContainerView(host: needsHost, language: state.language).id(needsHost.viewIdentity)
                    } else if selectedPanel == .server {
                        ServerHistoryView(host: serverHistoryHost, language: state.language)
                    } else {
                        LocalRecoveryList(host: messageHost, language: state.language)
                            .navigationTitle(state.language.text("Local recovery", "本地恢复"))
                    }
                }
                .toolbar { ToolbarItem(placement: .confirmationAction) {
                    Button(state.language.text("Done", "完成")) { panel = nil }
                        .accessibilityIdentifier("assistant.panel.done")
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
                if let conversation = messageHost.selectedConversation {
                    Text(state.language.text("Conversation: ", "会话：") + conversation)
                        .font(.caption).accessibilityIdentifier("assistant.conversation")
                }
                Toggle(isOn: Binding(
                    get: { messageHost.creationIntent == .considerTrip },
                    set: { messageHost.creationIntent = $0 ? .considerTrip : .none })) {
                    Text(state.language.text("Trip planning", "规划行程"))
                        .font(.body).foregroundStyle(Color(uiColor: .label))
                }
                    .disabled(messageHost.isBusy)
                    .accessibilityIdentifier("assistant.intent")
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
#endif
