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
/// Explicit reads; cancellation is available only with the separate development capability.
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
            if let progress = model.streamProgress {
                Text(verbatim: progress.text).textSelection(.enabled).accessibilityIdentifier("run.stream.text")
                Text(language.text("Received text · final state not yet verified", "已接收正文 · 最终状态尚未核实"))
                    .font(.caption)
            }
            if model.readsDraftStatus {
                VStack(alignment: .leading, spacing: 4) {
                    Text(language.text("Draft result", "草稿结果")).font(.headline)
                    Text(model.draftStatus.label(language))
                        .font(.body.leading(.loose)).lineLimit(nil)
                        .fixedSize(horizontal: false, vertical: true).padding(.vertical, 2)

                    if case .loaded(let value) = model.draftStatus {
                        Text(language.text("Run state at draft read: ", "读取草稿时的运行状态：") + draftRunLabel(value.run_status.rawValue))
                            .font(.caption).fixedSize(horizontal: false, vertical: true)

                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("run.draft.status")
            }
            if model.supportsCancellation {
                if model.cancellationState == .stopping {
                    Text(language.text("Stopping the original run…", "正在停止原运行…")).accessibilityIdentifier("run.stop.status")
                } else if model.cancellationState == .unknown {
                    Text(language.text("Stop result unknown. Check the original run before trying again.", "停止结果未知，请先查询原运行。")).accessibilityIdentifier("run.stop.status")
                }
                Button(language.text("Stop generation", "停止生成")) {
                    let work = model.prepareCancellation()
                    Task { await model.performCancellation(work) }
                }.disabled(!model.canCancel).accessibilityIdentifier("run.stop")
            }
            if case .loading = state { ProgressView() }
            Button(language.text("Read original run", "读取原运行")) {
                let work = model.prepareRead()
                Task { await model.perform(work) }
            }.disabled(disabled(state) || model.cancellationState == .stopping).accessibilityIdentifier("run.snapshot.read")
            Button(language.text("Follow / resume this answer", "接收／继续此回答")) {
                let work = model.prepareStream()
                Task { await model.perform(work) }
            }.disabled(disabled(state) || model.cancellationState == .stopping).accessibilityIdentifier("run.stream.read")
        }
        .onChange(of: scenePhase) { _, phase in if phase != .active { model.invalidate() } }
        .onDisappear { model.invalidate() }
    }
    private func draftRunLabel(_ status: String) -> String {
        switch status {
        case "queued": language.text("Queued", "排队中")
        case "running": language.text("Running", "运行中")
        case "completed": language.text("Completed", "已完成")
        case "failed": language.text("Failed", "失败")
        case "cancelled": language.text("Cancelled", "已取消")
        case "context_invalid": language.text("Context invalid", "上下文失效")
        default: language.text("Unknown", "未知")
        }
    }
    private func disabled(_ state: RunDisplayState) -> Bool {
        switch state { case .unselected, .loading: true; default: false }
    }
}
