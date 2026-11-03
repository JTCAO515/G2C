#if os(iOS)
import SwiftUI
import CJMemoryClient
import CJRunClient

struct MemoryCandidateContainerView: View {
    let host: MemoryCandidateContainerHost
    let language: ShellLanguage
    @Environment(\.scenePhase) private var scenePhase
    private func synchronizeAndRead() {
        let context = host.captureConversationRead()
        Task { await host.loadSuggestions(context: context, onlyIfUnread: true) }
    }
    var body: some View {
        VStack(spacing: 0) {
            if let model = host.presentation {
                let context = host.captureConversationRead()
                MemoryCandidateView(model: model, language: language == .english ? .english : .chinese,
                    makeReviewTravel: {
                        guard let context else { throw MemoryFailure.staleBinding }
                        return try host.makeReviewTravelSelection(context: context)
                    })
            } else {
                ScrollView {
                    RunReadableText(text: language.text("Suggestions are unavailable until this account and its selected conversation are connected. No review was submitted.", "当前账号与已选会话接入后才能查看建议，未提交核对操作。"))
                        .padding().accessibilityIdentifier("memoryCandidate.unavailable")
                }.navigationTitle(language.text("Memory suggestions", "记忆建议"))
            }
        }
        .onAppear { synchronizeAndRead() }
        .onChange(of: host.selectedConversation) { _, _ in synchronizeAndRead() }
        .onChange(of: scenePhase) { _, phase in if phase == .active { synchronizeAndRead() } }
        .onDisappear { host.retirePresentation() }
    }
}
#endif
