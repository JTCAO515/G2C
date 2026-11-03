#if os(iOS)
import SwiftUI
import CJMemoryClient
import CJRunClient

/// Current protected suggestions only. Original receipts stay in the review
/// page and never supply this bubble's candidate or active-memory state.
struct MemoryCandidateConversationBubble: View {
    let host: MemoryCandidateContainerHost
    let language: ShellLanguage
    let openReview: () -> Void
    var body: some View {
        if let context = host.captureConversationRead() {
            let model = host.presentation
            GroupBox {
                VStack(alignment: .leading, spacing: 12) {
                    RunReadableText(text: language.text("Memory suggestions for this conversation", "此会话的记忆建议"), style: .headline)
                        .accessibilityAddTraits(.isHeader)
                    RunReadableText(text: language.text("Suggestions are not active memories. Review and confirm each one explicitly.", "建议尚不是有效记忆，请逐条核对并明确确认。"))
                    Button {
                        Task { await host.loadSuggestions(context: context) }
                    } label: {
                        RunReadableText(text: language.text("Read current suggestions", "读取当前建议"))
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
                    }.buttonStyle(ShellReadableButtonStyle()).disabled(model?.state.isBusy == true)
                        .accessibilityIdentifier("assistant.memoryCandidates.read")
                    if let model {
                        if model.state == .ready {
                            if let first = model.candidates.first {
                                RunReadableText(text: first.text).accessibilityIdentifier("assistant.memoryCandidates.first")
                                RunReadableText(text: language.text("Preview from the pages read so far. Open the review to see every suggestion in those pages.", "这里只预览已读取页面的第一条，请打开核对页查看这些页面中的全部建议。"))
                            } else {
                                RunReadableText(text: language.text("No suggestions were returned by this read.", "本次读取未返回建议。"))
                                    .accessibilityIdentifier("assistant.memoryCandidates.empty")
                            }
                        } else if model.state == .loading {
                            ProgressView(language.text("Reading suggestions…", "正在读取建议…"))
                        } else if model.state != .unread {
                            RunReadableText(text: language.text("Current suggestions are not verified. This is not an empty or successful result.", "当前建议尚未核实，不能据此视为空或成功。"))
                                .accessibilityIdentifier("assistant.memoryCandidates.unknown")
                        }
                    }
                    Button {
                        guard host.isCurrent(context) else { return }
                        openReview()
                    } label: {
                        RunReadableText(text: language.text("Review suggestions and original operations", "核对建议与原操作"))
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
                    }.buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("assistant.memoryCandidates.review")
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.accessibilityIdentifier("assistant.memoryCandidates.bubble")
        }
    }
}
#endif
