import SwiftUI
import CJAPI

public enum RunDisplayLanguage: Sendable {
    case english, chinese
    func text(_ en: String, _ zh: String) -> String { self == .english ? en : zh }
}
extension RunDisplayState {
    public func label(_ language: RunDisplayLanguage) -> String {
        switch self {
        case .unselected: language.text("No original message selected", "尚未选择原消息")
        case .ready: language.text("Original run has not been read", "尚未读取原运行")
        case .loading: language.text("Reading original run…", "正在读取原运行…")
        case .unavailable(let failure):
            switch failure {
            case .cancelled: language.text("Read cancelled; result unknown", "读取已取消，结果未知")
            case .rejected(status: 401), .credentialsUnavailable: language.text("Session unavailable; result unknown", "会话不可用，结果未知")
            case .rejected(status: 413): language.text("Display limit exceeded; result unavailable", "超过显示限额，结果不可用")
            case .inconsistentSnapshot: language.text("Conflicting snapshot; result unavailable", "快照不一致，结果不可用")
            default: language.text("Original run unavailable; result unknown", "原运行不可用，结果未知")
            }
        case .loaded(let value):
            switch value.snapshot.status {
            case .queued: language.text("Queued · waiting", "排队中 · 等待运行")
            case .running: language.text("Running · partial text", "运行中 · 部分正文")
            case .completed: language.text("Completed", "已完成")
            case .failed: language.text("Failed · partial text", "运行失败 · 部分正文")
            case .cancelled: language.text("Cancelled · partial text", "已取消 · 部分正文")
            case .context_invalid: language.text("Context invalid · partial text", "上下文失效 · 部分正文")
            case .unknown: language.text("Result unknown · partial text", "结果未知 · 部分正文")
            }
        }
    }
}
/// Embeddable content only. Host owns navigation/source/selection and eager invalidation.
/// No auto-read, retries, polling, server cancellation or implied streaming capability.
@MainActor public struct RunDisplayView: View {
    private let model: RunDisplayModel
    private let language: RunDisplayLanguage
    @Environment(\.scenePhase) private var scenePhase
    public init(model: RunDisplayModel, language: RunDisplayLanguage) { self.model = model; self.language = language }
    public var body: some View {
        let state = model.state
        VStack(alignment: .leading, spacing: 8) {
            Text(state.label(language)).accessibilityIdentifier("run.display.status")
            if case .loaded(let value) = state {
                if !value.snapshot.text.isEmpty {
                    Text(verbatim: value.snapshot.text).textSelection(.enabled).accessibilityIdentifier("run.display.text")
                }
                Text(language.text("Snapshot at read time", "读取时的快照")).font(.caption)
            }
            if case .loading = state { ProgressView() }
            Button(language.text("Read original run", "读取原运行")) {
                let work = model.prepareRead()
                Task { await model.perform(work) }
            }.disabled(disabled(state))
        }
        .onChange(of: scenePhase) { _, phase in if phase != .active { model.invalidate() } }
        .onDisappear { model.invalidate() }
    }
    private func disabled(_ state: RunDisplayState) -> Bool {
        switch state { case .unselected, .loading: true; default: false }
    }
}
