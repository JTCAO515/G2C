#if os(iOS)
import SwiftUI
import CJFeedbackClient

struct FeedbackContainerView: View {
    let host: FeedbackContainerHost
    let entry: FeedbackContainerEntry?
    let language: ShellLanguage
    var body: some View {
        if let model = host.presentation(for: entry) {
            VStack(spacing: 0) {
                if host.isSynthetic(for: entry) {
                    Text(language.text("Synthetic test data", "合成测试数据")).font(.caption)
                }
                // The public view captures each opaque submit/query/reload work synchronously
                // before Task. Host invalidation retires this model; it is never rebound to B.
                FeedbackView(model: model, language: language == .english ? .english : .chinese)
            }
        } else {
            Text(language.text("Feedback is unavailable for this entry. Reopen it after the account and source are connected.", "此入口的反馈尚不可用，请在账号和来源接入后重新打开。"))
                .padding().navigationTitle(language.text("Feedback", "问题反馈"))
        }
    }
}
#endif
