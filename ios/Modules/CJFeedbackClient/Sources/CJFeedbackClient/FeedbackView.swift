import SwiftUI
import CJAPI

public enum FeedbackLanguage: Sendable { case english, chinese }

/// The same component embeds in Answer and Memory. Host owns trusted context and identity lifetime.
public struct FeedbackView: View {
    public let model: FeedbackPresentation
    public let language: FeedbackLanguage
    public init(model: FeedbackPresentation, language: FeedbackLanguage) { self.model = model; self.language = language }
    private func text(_ en: String, _ zh: String) -> String { language == .chinese ? zh : en }
    public var body: some View {
        Form {
            Section {
                Text(text("Describe the problem and what you expected. Include only what you choose to share; omit passwords and secrets.", "请描述问题和期望。只填写你愿意分享的内容，请勿包含密码或密钥。"))
                    .font(.footnote)
                TextField(text("Problem", "问题"), text: Binding(get: { model.problem }, set: { model.edit(problem: $0, expectation: model.expectation) }), axis: .vertical)
                    .lineLimit(3...8).disabled(!model.canEdit).accessibilityIdentifier("feedback.problem")
                TextField(text("Expected result (optional)", "期望结果（可选）"), text: Binding(get: { model.expectation }, set: { model.edit(problem: model.problem, expectation: $0) }), axis: .vertical)
                    .lineLimit(2...6).disabled(!model.canEdit).accessibilityIdentifier("feedback.expectation")
                if model.context != nil && model.original == nil {
                    Toggle(text("Associate this message", "关联当前消息"), isOn: Binding(get: { model.includeContext }, set: { model.associateContext($0) }))
                        .disabled(!model.canEdit).accessibilityIdentifier("feedback.associate")
                    Text(text("Only message and optional run references are sent. The server checks access.", "仅传送消息与可选运行引用，由服务器核验访问权限。"))
                        .font(.footnote)
                }
                Button(text("Submit feedback", "提交反馈")) {
                    if let work = model.prepareSubmit() { Task { await model.perform(work) } }
                }
                .disabled(!model.submissionAvailable || !model.canEdit)
                .accessibilityIdentifier("feedback.submit")
            }
            Section {
                if model.state.isBusy { ProgressView() }
                Text(status).accessibilityIdentifier("feedback.status")
                if model.original != nil && model.state != .submitted {
                    Button(text("Check original submission", "查询原反馈")) {
                        if let work = model.prepareQuery() { Task { await model.perform(work) } }
                    }.disabled(model.state.isBusy).accessibilityIdentifier("feedback.query")
                }
                Button(text("Load pending feedback", "读取待核对反馈")) {
                    if let work = model.prepareReload() { Task { await model.perform(work) } }
                }.disabled(model.state.isBusy || model.binding == nil)
                ForEach(model.pendingActions, id: \.actionID) { pending in
                    Button(text("Review pending feedback", "查看待核对反馈")) { model.selectPending(actionID: pending.actionID) }
                        .disabled(model.state.isBusy)
                }
            }
            if let receipt = model.receipt {
                Section(text("Submission record", "提交记录")) {
                    Text(receipt.submitted_at, style: .date)
                    Text(receipt.submitted_at, style: .time)
                    if case .FeedbackSourceObservation(let source) = receipt.source {
                        Text(text("Historical source observation", "原始来源观察"))
                        LabeledContent(text("Run status at read", "读取时运行状态"), value: sourceStatus(source.run_status_at_read))
                        LabeledContent(text("Event progress at read", "读取时事件进度"), value: String(source.event_highwater_at_read))
                        Text(text("This is the original read-time observation, not current run status. Model/rule versions, usage, duration and tool results were not provided.", "这是原记录读取时的观察，不代表当前运行状态。模型或规则版本、用量、耗时和工具结果未提供。"))
                            .font(.footnote)
                    }
                }
            }
        }
        .navigationTitle(text("Feedback", "问题反馈"))
    }
    private var status: String {
        switch model.state {
        case .unavailable: text("Submission is unavailable in this configuration. Your text has not been submitted.", "当前配置无法提交反馈。填写的内容尚未提交。")
        case .editing: text("Ready to describe your feedback.", "请填写反馈。")
        case .loading: text("Loading pending feedback…", "正在读取待核对反馈…")
        case .submitting: text("Submitting feedback…", "正在提交反馈…")
        case .reconciling: text("Checking the original submission…", "正在查询原反馈…")
        case .unknown: text("Submission is not confirmed. Keep the original feedback and check its status; do not resubmit.", "提交结果尚未确认。请保留原反馈并查询状态，不要重新提交。")
        case .conflict: text("The original action conflicts. Your text and recovery record are retained; check the original submission.", "原动作发生冲突。原填写内容和恢复记录已保留，请查询原反馈。")
        case .submitted: text("Feedback submitted.", "反馈已提交。")
        case .invalidInput: text("Enter a problem, shorten long text, and remove unsupported characters.", "请填写问题、缩短过长的文字并移除不支持的字符。")
        case .recoveryUnavailable: text("Pending feedback could not be verified. Keep its original record; this does not mean it was not submitted.", "暂时无法核验待处理反馈。请保留原记录，这不代表未提交。")
        }
    }
    private func sourceStatus(_ status: Components.Schemas.FeedbackSourceObservation.run_status_at_readPayload) -> String {
        switch status {
        case .queued: text("Queued", "排队中")
        case .running: text("Running", "运行中")
        case .completed: text("Completed", "已结束")
        case .failed: text("Failed", "失败")
        case .cancelled: text("Cancelled", "已取消")
        case .context_invalid: text("Context invalid", "上下文失效")
        case .unknown: text("Unknown", "未知")
        }
    }
}

#Preview("English · unavailable") {
    FeedbackView(model: FeedbackPresentation(client: nil), language: .english)
}
#Preview("中文 · 当前无法提交") {
    FeedbackView(model: FeedbackPresentation(client: nil), language: .chinese)
}
