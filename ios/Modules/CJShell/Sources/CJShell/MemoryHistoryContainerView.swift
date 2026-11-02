#if os(iOS)
import SwiftUI
import CJMemoryClient
import CJRunClient

struct MemoryHistoryContainerView: View {
    let host: MemoryHistoryContainerHost
    let language: ShellLanguage
    private func synchronizeAndRead() {
        host.synchronizeConversation()
        guard let model = host.presentation, model.state == .unread,
              let work = model.prepareRead() else { return }
        Task { await model.perform(work) }
    }
    var body: some View {
        VStack(spacing: 0) {
            if let model = host.presentation {
                MemoryHistoryView(model: model, language: language == .english ? .english : .chinese)
            } else {
                ScrollView {
                    RunReadableText(text: language.text("History settings are unavailable until this account and its selected conversation are connected. No permission change was sent.", "当前账号与已选会话接入后才能查看历史设置，未发送权限变更。"))
                        .padding().accessibilityIdentifier("historyConsent.unavailable")
                }.navigationTitle(language.text("Conversation history", "会话历史整理"))
            }
        }
        .onAppear { synchronizeAndRead() }
        .onChange(of: host.selectedConversation) { _, _ in synchronizeAndRead() }
        .onDisappear { host.retirePresentation() }
    }
}
#endif
