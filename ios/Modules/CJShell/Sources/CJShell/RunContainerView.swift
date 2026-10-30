#if os(iOS)
import SwiftUI
import CJRunClient
import CJMessageClient
import CJTripClient

struct RunContainerView: View {
    let host: RunContainerHost
    let messages: AssistantMessageHost
    let language: ShellLanguage
    @Environment(\.scenePhase) private var scenePhase
    private var acceptedMessageID: String? {
        messages.visibleRecord?.phase == .accepted ? messages.visibleRecord?.messageID : nil
    }
    private func followAcceptedMessage() {
        guard host.followsAcceptedMessages, acceptedMessageID != nil,
              host.selectAcceptedMessage(from: messages), let model = host.displayModel else { return }
        let work = model.prepareStream()
        Task { await model.performInitialStream(work) }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            RunReadableText(text:language.text("Original run", "原运行"),style:.headline).accessibilityAddTraits(.isHeader)
            if let model = host.displayModel {
                Button { _ = host.selectAcceptedMessage(from:messages) } label: {
                    RunReadableText(text:language.text("Use selected accepted message", "使用已选中的已接受消息"))
                        .frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle())
                }.disabled(model.cancellationState == .stopping).accessibilityIdentifier("run.selectOriginal")
                if host.sourceUnavailable {
                    Text(language.text("No current accepted message receipt is available. Select an original message in recovery first.", "没有可用的当前已接受消息回执，请先在恢复列表中选择原消息。"))
                        .font(.footnote)
                }
                // Public view prepares opaque original read work synchronously before Task.
                RunDisplayView(model:model,language:language == .english ? .english : .chinese,showAnswerText:host.answerFormat != .placeToolV1)
                if host.answerFormat == .placeToolV1 {
                    switch host.placeProjection {
                    case .waiting:RunReadableText(text:language.text("Waiting for place information…", "正在等待地点资料…"))
                    case .unavailable:RunReadableText(text:language.text("Place information unavailable. Read the original result; do not repeat the request.", "地点资料不可用。请读取原结果，不要重新发送请求。"))
                            .accessibilityIdentifier("place.unavailable")
                    case .loaded(let transcript):PlaceToolTranscriptView(transcript:transcript,language:language == .english ? .english : .simplifiedChinese)
                    }
                }
                if host.isSynthetic { Text(language.text("Synthetic test data", "合成测试数据")).font(.caption) }
            } else {
                Text(language.text("Original-run reading is unavailable until trusted session and read resources are connected.", "可信会话和读取资源接入前，原运行读回尚不可用。"))
            }
            RunReadableText(text: language.text("Reads the selected original answer. Stopping preserves received text and does not undo earlier actions.", "读取选中的原回答。停止会保留已收到的正文，不会撤销此前的操作。"), style: .caption)
        }
        .onAppear { host.setForeground(scenePhase == .active); followAcceptedMessage() }
        .onChange(of: acceptedMessageID) { _, _ in followAcceptedMessage() }
        .onChange(of: scenePhase) { _, phase in host.setForeground(phase == .active) }
        .onDisappear { host.setForeground(false) }
    }
}
#endif
