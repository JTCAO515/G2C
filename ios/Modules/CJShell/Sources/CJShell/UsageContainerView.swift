#if os(iOS)
import SwiftUI
import CJUsageClient

struct UsageContainerView: View {
    let host: UsageContainerHost
    let language: ShellLanguage
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        let state = host.state
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                UsageStatusView(state: state, language: language == .english ? .english : .chinese,
                                readOriginal: host.readOriginal)
                    .disabled(!host.canRead)
                if !host.hasOriginalSource {
                    Text(language.text("Original usage status is not available yet.", "原调用用量状态暂不可用。"))
                        .font(.footnote)
                }
                if case .loaded(let value) = state {
                    LabeledContent(language.text("Original attempt", "原 attempt"), value: value.attemptID)
                    LabeledContent(language.text("Original operation", "原操作"), value: value.operationID)
                    LabeledContent(language.text("Original run", "原运行"), value: value.runID)
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding()
        }
        .navigationTitle(language.text("Original usage status", "原调用用量"))
        .onAppear { host.setForeground(scenePhase == .active) }
        .onChange(of: scenePhase) { _, phase in host.setForeground(phase == .active) }
        .onDisappear { host.setForeground(false) }
    }
}
#endif
