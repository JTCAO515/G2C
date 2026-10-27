#if os(iOS)
import SwiftUI
import CJRunClient

struct RunContainerView: View {
    let host: RunContainerHost
    let messages: AssistantMessageHost
    let language: ShellLanguage
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(language.text("Original run", "原运行")).font(.headline)
            if let model = host.displayModel {
                Button(language.text("Use selected accepted message", "使用已选中的已接受消息")) {
                    _ = host.selectAcceptedMessage(from: messages)
                }
                if host.sourceUnavailable {
                    Text(language.text("No current accepted message receipt is available. Select an original message in recovery first.", "没有可用的当前已接受消息回执，请先在恢复列表中选择原消息。"))
                        .font(.footnote)
                }
                // Public view prepares opaque original read work synchronously before Task.
                RunDisplayView(model: model, language: language == .english ? .english : .chinese)
                if host.isSynthetic { Text(language.text("Synthetic test data", "合成测试数据")).font(.caption) }
            } else {
                Text(language.text("Original-run reading is unavailable until trusted session and read resources are connected.", "可信会话和读取资源接入前，原运行读回尚不可用。"))
            }
            Text(language.text("Reads an existing answer only. This does not start, resend or stop a run.", "仅接收已有回答，不会新建、重发或停止运行。"))
                .font(.caption)
        }
        .onAppear { host.setForeground(scenePhase == .active) }
        .onChange(of: scenePhase) { _, phase in host.setForeground(phase == .active) }
        .onDisappear { host.setForeground(false) }
    }
}
#endif
