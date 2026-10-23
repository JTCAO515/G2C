#if os(iOS)
import SwiftUI

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
    @ScaledMetric(relativeTo: .body) private var headerClearance = 112.0

    var body: some View {
        let answerEntry = feedbackHost.captureEntry()
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Keeps meaningful content reachable below the separate floating controls.
                Color.clear.frame(height: draftFocused ? 80 : headerClearance).accessibilityHidden(true)
                if let bodyText, !runHost.isShowingOriginal {
                    Text(bodyText).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    Button(state.language.text("Report a problem with this answer", "反馈此回答的问题")) {
                        feedbackEntry = answerEntry; panel = .feedback
                    }
                }
                Button(state.language.text("Server history and drafts", "服务器历史与草稿")) { panel = .server }
                Button(state.language.text("Journey needs", "本次旅行需求")) { panel = .needs }
                Button(state.language.text("Original usage status", "原调用用量")) { panel = .usage }
                RunContainerView(host: runHost, messages: messageHost, language: state.language)
                MessageRecoveryStatus(host: messageHost, language: state.language)
                if !messageHost.isConfigured {
                    ShellStatusView(state: state.assistantState, language: state.language)
                }
            }
            .padding(.horizontal)
            .padding(.bottom)
        }
        .scrollDismissesKeyboard(.interactively)
        .overlay(alignment: .top) { floatingControls }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
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
                BrandAvatar(compact: draftFocused)
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
            HStack(alignment: .bottom, spacing: 4) {
                unavailableIcon("plus", english: "Attachments — not available", chinese: "附件——尚未开放")
                TextField(state.language.text("Start chatting", "开始聊天"), text: $state.draft, axis: .vertical)
                    .lineLimit(1...5)
                    .focused($draftFocused)
                    .padding(.vertical, 12)
                    .accessibilityLabel(state.language.text("Message draft", "消息草稿"))
                    .accessibilityIdentifier("assistant.draft")
                if state.hasDraft {
                    unavailableIcon("arrow.up", english: "Send — service not connected", chinese: "发送——服务尚未接入")
                } else {
                    unavailableIcon("mic", english: "Voice — not available", chinese: "语音——尚未开放")
                }
            }
            .padding(.horizontal, 4)
            .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 28))
            Text(draftFocused
                 ? state.language.text("Sending unavailable", "发送尚未开放")
                 : state.language.text("Sending, attachments, voice and gifts are not available yet.", "发送、附件、语音和礼物尚未开放。"))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal).padding(.vertical, 8)
        .background(.regularMaterial)
    }

    private func unavailableIcon(_ symbol: String, english: String, chinese: String) -> some View {
        Button {} label: { Image(systemName: symbol).frame(minWidth: 44, minHeight: 44) }
            .disabled(true)
            .accessibilityLabel(state.language.text(english, chinese))
    }
}
#endif
