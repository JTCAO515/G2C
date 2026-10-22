#if os(iOS)
import SwiftUI
import CJUsageClient

struct OriginalUsageContainerView: View {
    let host: OriginalUsageContainerHost
    let messages: AssistantMessageHost
    let language: ShellLanguage
    @Environment(\.scenePhase) private var scenePhase
    private var usageLanguage: UsageLanguage { language == .english ? .english : .chinese }
    var body: some View {
        let state = host.state
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Button(language.text("Resolve usage link for selected message", "解析所选原消息的用量关联")) {
                    host.resolveCurrentMessage(from: messages)
                }.disabled(!host.canResolve)
                switch state {
                case .unavailable:
                    Text(UsageFailure.unavailable.label(usageLanguage))
                case .loading:
                    ProgressView(language.text("Reading original record…", "正在读取原记录…"))
                case .failed(let failure):
                    Text(failure.label(usageLanguage))
                case .sourceReady(let source):
                    Text(language.text("Original link found. Usage status has not been read yet.", "已找到原关联，尚未查询用量状态。"))
                    LabeledContent(language.text("Original message", "原消息"), value: source.messageID)
                    LabeledContent(language.text("Original attempt", "原调用"), value: source.attemptID)
                    Button(language.text("Read original attempt status", "查询原调用状态"), action: host.readResolvedStatus)
                        .disabled(!host.canReadStatus)
                case .loaded(let value):
                    UsageStatusView(state: .loaded(value), language: usageLanguage, readOriginal: host.readResolvedStatus)
                    LabeledContent(language.text("Original operation", "原操作"), value: value.operationID)
                    LabeledContent(language.text("Original run", "原运行"), value: value.runID)
                }
                Text(language.text("A stored link does not confirm execution or payment. Reads do not start or resend an attempt.", "存储关联不代表已执行或已付款；查询不会启动或重发调用。"))
                    .font(.footnote)
            }.frame(maxWidth: .infinity, alignment: .leading).padding()
        }
        .navigationTitle(language.text("Original usage status", "原调用用量"))
        .onAppear { host.setForeground(scenePhase == .active) }
        .onChange(of: scenePhase) { _, phase in host.setForeground(phase == .active) }
        .onDisappear { host.setForeground(false) }
    }
}
#endif
