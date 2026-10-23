#if canImport(SwiftUI)
import SwiftUI

/// A read-only component for Memory > account. Host owns provenance and lifecycle.
/// No task on appearance; only the user's explicit button starts one GET.
@MainActor public struct CleanupProgressView: View {
    private let model: CleanupViewModel
    private let originalBinding: @MainActor () -> CleanupBinding?
    private let language: CleanupLanguage
    @State private var task: Task<Void, Never>?

    public init(model: CleanupViewModel, language: CleanupLanguage,
                originalBinding: @escaping @MainActor () -> CleanupBinding?) {
        self.model = model; self.language = language; self.originalBinding = originalBinding
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(language.text("Cleanup progress", "清理进度")).font(.headline)
            Text(language.text(
                "Reads the existing operation for the current account. This does not start account deletion.",
                "读取当前账号已有操作的进度。此操作不会发起账号注销。"))
            content
            Button(language.text("Read original progress", "读取原操作进度")) {
                task?.cancel()
                guard let original = originalBinding() else { model.invalidate(); return }
                do {
                    let prepared = try model.prepare(original)
                    task = Task { await model.read(prepared) }
                } catch { /* prepare already cleared the old projection */ }
            }
            .buttonStyle(.bordered)
            .disabled(model.state == .loading)
            Button(language.text("Clear display / cancel read", "清空显示／取消读取")) {
                task?.cancel(); task = nil; model.invalidate()
            }
            .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onDisappear { task?.cancel(); task = nil; model.invalidate() }
    }
    @ViewBuilder private var content: some View {
        switch model.state {
        case .unavailable: Text(language.text(
            "Unavailable. A trusted original operation and a current valid session are required.",
            "暂不可用。需要可信的原操作来源和当前有效会话。"))
        case .loading: ProgressView(language.text("Reading…", "正在读取…"))
        case .failed(let failure): Text(language.failure(failure))
        case .loaded(let progress):
            Text(language.label(progress.status.rawValue)).font(.headline)
            Text(language.text("Revision: ", "版本：") + String(progress.revision))
            ForEach(Array(progress.steps.enumerated()), id: \.offset) { _, step in
                VStack(alignment: .leading, spacing: 4) {
                    Text(verbatim: step.target).font(.subheadline)
                    Text(language.label(step.state.rawValue))
                    Text(language.label(step.reason.rawValue)).font(.caption)
                }.accessibilityElement(children: .combine)
            }
            ForEach(progress.reasons, id: \.self) { reason in Text(language.label(reason.rawValue)) }
            Text(language.text(
                "This is the original frozen operation's metadata only. It does not prove all account data, backups, offline devices or external copies are erased.",
                "此处仅显示原冻结操作的元数据，不能证明全部账号数据、备份、离线设备或外部副本已清除。"))
                .font(.footnote)
        }
    }
}
#endif

public enum CleanupLanguage: Sendable {
    case english, chinese
    func text(_ english: String, _ chinese: String) -> String { self == .chinese ? chinese : english }
    func failure(_ value: CleanupFailure) -> String {
        switch value {
        case .unavailable, .stale: text("Progress unavailable; cleanup is not confirmed.", "进度暂不可用，尚未确认清理完成。")
        case .invalidResponse: text("Invalid progress response; cleanup is not confirmed.", "进度响应无效，尚未确认清理完成。")
        case .exchangeUnknown: text("Read result unknown. Request the original progress explicitly when ready.", "读取结果未知。准备好后可主动读取原操作进度。")
        case .rejected(let code): text("Read rejected (HTTP \(code)); cleanup is not confirmed.", "读取被拒绝（HTTP \(code)），尚未确认清理完成。")
        }
    }
    func label(_ code: String) -> String {
        switch code {
        case "blocked": text("Blocked", "受阻")
        case "unknown": text("Unknown", "未知")
        case "failed": text("Failed", "失败")
        case "complete": text("Original operation confirmed", "原操作已确认")
        case "awaiting_revocation": text("Awaiting access revocation", "等待访问撤销确认")
        case "in_progress": text("In progress", "进行中")
        case "pending": text("Pending", "待处理")
        case "confirmed": text("Original result confirmed", "原结果已确认")
        case "original_result_confirmed": text("Original result confirmed", "原结果已确认")
        case "original_result_unknown": text("Original result unknown", "原结果未知")
        case "original_result_failed": text("Original result failed", "原结果失败")
        case "hook_unavailable": text("Cleanup hook unavailable", "清理接口暂不可用")
        case "original_call_in_progress": text("Original call still in progress", "原调用仍在进行")
        case "revocation_unconfirmed": text("Access revocation unconfirmed", "访问撤销尚未确认")
        case "task_stop_unconfirmed": text("Task stopping unconfirmed", "任务停止尚未确认")
        case "pending_original_result": text("Awaiting original result", "等待原结果")
        case "coverage_incomplete": text("Coverage incomplete", "覆盖范围不完整")
        case "registry_review_required": text("Registry review required", "需要核对存储清单")
        default: text("Unrecognized progress", "无法识别的进度")
        }
    }
}
