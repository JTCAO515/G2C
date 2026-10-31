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
    private struct FactPanel: Identifiable { let id: UUID }
    @State private var factPanel: FactPanel?
    private var acceptedMessageID: String? {
        messages.visibleRecord?.phase == .accepted ? messages.visibleRecord?.messageID : nil
    }
    private func followAcceptedMessage() {
        guard host.followsAcceptedMessages, acceptedMessageID != nil,
              host.selectAcceptedMessage(from: messages), let model = host.displayModel else { return }
        if model.supportsStreaming {
            let work = model.prepareStream()
            Task { await model.performInitialStream(work) }
        } else {
            let work = model.prepareRead()
            Task { await model.perform(work) }
        }
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
                if host.answerFormat == .factToolV1,case .loaded = host.factProjection {
                        Button {
                            guard let id = host.originalPresentationID else { return }
                            factPanel = FactPanel(id:id)
                        } label: {
                            RunReadableText(text:language.text("Read complete sources", "读取完整来源"))
                                .frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle())
                        }.buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("fact.sources.open")
                }
                // Public view prepares opaque original read work synchronously before Task.
                RunDisplayView(model:model,language:language == .english ? .english : .chinese,showAnswerText:host.answerFormat == .plainText)
                if host.answerFormat == .placeToolV1 {
                    switch host.placeProjection {
                    case .waiting:RunReadableText(text:language.text("Waiting for place information…", "正在等待地点资料…"))
                    case .unavailable:RunReadableText(text:language.text("Place information unavailable. Read the original result; do not repeat the request.", "地点资料不可用。请读取原结果，不要重新发送请求。"))
                            .accessibilityIdentifier("place.unavailable")
                    case .loaded(let transcript):PlaceToolTranscriptView(transcript:transcript,language:language == .english ? .english : .simplifiedChinese)
                    }
                }
                if host.answerFormat == .factToolV1 {
                    switch host.factProjection {
                    case .waiting:RunReadableText(text:language.text("Waiting for synthetic evidence…", "正在等待合成证据…")).accessibilityIdentifier("fact.waiting")
                    case .unavailable:RunReadableText(text:language.text("Fact information unavailable. Read the original result; do not repeat the request.", "事实资料不可用。请读取原结果，不要重新发送请求。")).accessibilityIdentifier("fact.unavailable")
                    case .loaded(let transcript):
                        FactToolTranscriptView(transcript:transcript,language:language == .english ? .english : .simplifiedChinese)
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
        .onChange(of:host.originalPresentationID) { _,id in
            if factPanel?.id != id { factPanel = nil }
        }
        .sheet(item:$factPanel) { panel in
            NavigationStack {
                FactSourcePanel(host:host,language:language,expected:panel.id)
            }.presentationDetents([.large])
        }
    }
}

private struct FactSourcePanel: View {
    let host: RunContainerHost
    let language: ShellLanguage
    let expected: UUID
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        ScrollView {
            if host.originalPresentationID == expected,case .loaded(let transcript) = host.factProjection {
                FactToolTranscriptView(transcript:transcript,language:language == .english ? .english : .simplifiedChinese)
            } else {
                RunReadableText(text:language.text("Original source unavailable. Close this panel and select the current original result.", "原来源已不可用。请关闭面板并选择当前原结果。"))
                    .accessibilityIdentifier("fact.sources.unavailable")
            }
        }.padding().accessibilityIdentifier("fact.sources.content")
            .navigationTitle(language.text("Sources", "来源")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement:.confirmationAction) {
                AssistantPanelDoneButton(title:language.text("Done", "完成"),identifier:"fact.sources.done") {dismiss()}
            } }
    }
}
#endif
