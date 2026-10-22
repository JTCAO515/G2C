#if os(iOS)
import SwiftUI

struct AssistantShell: View {
    @Bindable var state: ShellState
    let messageHost: AssistantMessageHost
    let bodyText: String?
    @State private var showingHistory = false
    @FocusState private var draftFocused: Bool
    @ScaledMetric(relativeTo: .body) private var headerClearance = 112.0

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Keeps meaningful content reachable below the separate floating controls.
                Color.clear.frame(height: draftFocused ? 80 : headerClearance).accessibilityHidden(true)
                if let bodyText {
                    Text(bodyText).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }
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
            showingHistory = false
        }
        .sheet(isPresented: $showingHistory) {
            NavigationStack {
                LocalRecoveryList(host: messageHost, language: state.language)
                .navigationTitle(state.language.text("Local recovery", "本地恢复"))
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button(state.language.text("Done", "完成")) { showingHistory = false }
                    }
                }
            }
        }
    }

    private var floatingControls: some View {
        HStack(alignment: .top) {
            Button { showingHistory = true } label: {
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
                Image(systemName: "person.crop.circle")
                    .font(draftFocused ? .title3 : .largeTitle).accessibilityHidden(true)
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
