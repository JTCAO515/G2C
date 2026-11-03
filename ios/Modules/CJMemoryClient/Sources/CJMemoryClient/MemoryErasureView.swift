import SwiftUI
import Foundation

/// Online erasure projection only. Overall/local cleanup requires the actual
/// Root's separate physical result; this view never infers it from an online ACK.
public struct MemoryErasureView: View {
    public let model: MemoryErasurePresentation
    public let language: MemoryLanguage
    public let localStatus: String?
    public let canClearLocal: Bool
    public let clearLocal: (() -> Void)?
    @State private var acknowledged = false
    public init(model: MemoryErasurePresentation, language: MemoryLanguage, localStatus: String? = nil,
        canClearLocal: Bool = false, clearLocal: (() -> Void)? = nil) {
        self.model = model; self.language = language; self.localStatus = localStatus
        self.canClearLocal = canClearLocal; self.clearLocal = clearLocal
    }
    public var body: some View {
        ScrollView {
          VStack(alignment: .leading, spacing: 16) {
            if let entry = model.entry {
                Section {
                    MemoryRowText(text: entry.text, style: .body).accessibilityIdentifier("memoryErasure.originalText")
                    MemoryRowText(text: language.text("Deleting stops this memory and all its canonical sources. It also clears this account's trip-derived results and unaccepted proposals/drafts; that range is not limited to a precise match to this item.", "删除会停止使用这条记忆及其全部正式来源，还会清理此账号的行程派生结果和未接受的方案、草稿；这一范围不是只精准匹配本条记忆。"), style: .body)
                        .accessibilityIdentifier("memoryErasure.range")
                    MemoryRowText(text: language.text("Your original chat and accepted formal trips are retained. This does not delete your account or authorize history organization.", "原聊天与已接受的正式行程会保留。这不会注销账号，也不会授权整理历史。"), style: .body)
                        .accessibilityIdentifier("memoryErasure.retained")
                    Toggle(isOn: $acknowledged) {
                        MemoryRowText(text: language.text("I understand and confirm this linked cleanup range", "我已了解并确认上述关联清理范围"), style: .body)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }.disabled(!model.canSubmit).accessibilityIdentifier("memoryErasure.rangeAcknowledgement")
                    MemoryLifecycleButton(title: language.text("Stop using and delete this memory", "停止使用并删除这条记忆"), identifier: "memoryErasure.submit", enabled: model.canSubmit && acknowledged) {
                        if let work = model.prepareSubmission(acknowledged: acknowledged) {
                            acknowledged = false; perform(work)
                        }
                    }
                } header: { heading(language.text("Confirm deletion scope", "确认删除范围")) }
            }
            Section {
                MemoryRowText(text: model.knownStopped ? language.text("Stopped using — the original stop is recorded.", "已停止使用：原停止操作已有记录。") : language.text("Whether use has stopped is not yet confirmed.", "尚未确认是否已停止使用。"), style: .body)
                    .accessibilityIdentifier("memoryErasure.stopUse")
                MemoryRowText(text: status, style: .body).accessibilityIdentifier("memoryErasure.status")
                if model.state.isBusy { ProgressView().accessibilityLabel(language.text("Checking the original deletion", "正在核验原删除操作")) }
            } header: { heading(language.text("Use of this memory", "记忆使用状态")) }
            Section {
                if let progress = model.progress {
                    MemoryRowText(text: (model.progressIsCurrent ? "" : language.text("Last checked: ", "上次核验：")) + phaseTitle(progress.phase), style: .body)
                        .accessibilityIdentifier("memoryErasure.onlineProgress")
                    if !model.progressIsCurrent {
                        MemoryRowText(text: language.text("Current online cleanup progress could not be verified. The earlier stop remains recorded.", "当前线上清理进度尚未核实，已记录的停止使用结果仍保留。"), style: .body)
                            .accessibilityIdentifier("memoryErasure.staleProgress")
                    }
                    ForEach(progress.steps, id: \.target) { step in
                        MemoryRowText(text: targetTitle(step.target) + " · " + stepTitle(step.state), style: .body)
                    }
                } else {
                    MemoryRowText(text: language.text("Online cleanup progress has not been verified. This is not proof of physical completion.", "线上清理进度尚未核实，不能据此认为物理清理已完成。"), style: .body)
                        .accessibilityIdentifier("memoryErasure.unverifiedProgress")
                }
                MemoryRowText(text: language.text("Online results do not establish cleanup on this device or another device. Requests already sent to a model, previously displayed history and external-provider retention cannot be withdrawn here.", "线上结果不代表本机或其他设备已完成清理。已发给模型的请求、此前显示的历史，以及外部服务留存无法在这里撤回。"), style: .body)
                    .accessibilityIdentifier("memoryErasure.limits")
            } header: { heading(language.text("Online cleanup progress", "线上清理进度")) }
            if let localStatus {
                Section {
                    MemoryRowText(text: localStatus, style: .body).accessibilityIdentifier("memoryErasure.localProgress")
                    MemoryLifecycleButton(title: language.text("Clear this memory's local copies", "清理这条记忆的本机副本"),
                        identifier: "memoryErasure.clearLocal", enabled: canClearLocal) { clearLocal?() }
                    MemoryRowText(text: language.text("This result covers this device's matching memory save and edit journals only. It does not confirm online cleanup or another device.", "此结果仅涵盖本机对应条目的记忆保存和编辑日志，不代表线上或其他设备已清理。"), style: .body)
                } header: { heading(language.text("This device's cleanup progress", "本机清理进度")) }
            }
            Section {
                MemoryLifecycleButton(title: language.text("Load original deletions", "读取原删除记录"), identifier: "memoryErasure.loadOriginals", enabled: model.canRecover) {
                    if let work = model.prepareOriginals() { perform(work) }
                }
                ForEach(model.originals, id: \.utf8Identity) { original in
                    MemoryLifecycleButton(title: language.text("Original deletion: ", "原删除：") + original.actionID,
                        identifier: "memoryErasure.original." + original.actionID, enabled: !model.state.isBusy) {
                        acknowledged = false; model.selectOriginal(actionID: original.actionID)
                    }
                }
                if let original = model.original {
                    MemoryRowText(text: original.actionID, style: .caption).accessibilityIdentifier("memoryErasure.originalID")
                    MemoryLifecycleButton(title: language.text("Check original deletion", "查询原删除"), identifier: "memoryErasure.query", enabled: model.canRecover) {
                        if let work = model.prepareQuery() { perform(work) }
                    }
                    MemoryRowText(text: language.text("The original scope also covers this account's trip-derived results and unaccepted drafts, while retaining original chat and accepted formal trips. After checking progress, you may explicitly continue that same deletion. This can advance untouched steps without issuing an already-started step again.", "原范围还包括此账号的行程派生结果和未接受草稿，保留原聊天与已接受的正式行程。核验进度后，你可明确继续同一原删除，处理尚未开始的步骤；已开始的步骤不会重新派发。"), style: .body)
                    MemoryLifecycleButton(title: language.text("Continue this original deletion", "继续同一原删除"), identifier: "memoryErasure.reconcile", enabled: model.canReconcile) {
                        if let work = model.prepareReconciliation() { perform(work) }
                    }
                }
                MemoryRowText(text: language.text("An uncertain result or a missing progress record never creates a new deletion. Keep the original; its continue action requires a successful original-progress read first.", "结果未知或查不到进度时，不会创建新删除。请保留原记录；继续原操作前必须成功读取它的进度。"), style: .body)
            } header: { heading(language.text("Original operation recovery", "原操作恢复")) }
          }.padding()
        }
        .navigationTitle(language.text("Delete memory", "删除记忆"))
        .onChange(of: model.entry?.id) { _, _ in acknowledged = false }
    }
    private func perform(_ work: MemoryErasurePresentationWork) { Task { await model.perform(work) } }
    private func heading(_ text: String) -> some View { MemoryRowText(text: text, style: .caption).accessibilityAddTraits(.isHeader) }
    private var status: String {
        switch model.state {
        case .unconfigured: language.text("Deletion is unavailable for this account. Nothing was submitted.", "当前账号的删除功能不可用，未提交操作。")
        case .unselected: language.text("Choose a currently read memory, or load an original deletion to query it.", "请选择当前已读取的记忆，或读取原删除记录后查询。")
        case .ready: language.text("Read and confirm the linked cleanup range before deleting.", "删除前请核对并确认关联清理范围。")
        case .preparing: language.text("Preserving the original deletion request…", "正在保留原删除请求…")
        case .submitting: language.text("Submitting the original deletion operation…", "正在提交原删除操作…")
        case .loading: language.text("Reading original deletion records…", "正在读取原删除记录…")
        case .reconciling: language.text("Checking the original deletion; no new request is being submitted.", "正在查询原删除，没有提交新请求。")
        case .known: language.text("The original stop is recorded. See online cleanup progress separately.", "原停止操作已记录，线上清理进度请另行查看。")
        case .unknown: language.text("The current result is uncertain. Query the original without resending.", "当前结果尚不明确，请查询原操作，不要重新发送。")
        case .conflict: language.text("The request conflicted. Keep the original record and query it; no replacement deletion was sent.", "请求发生冲突，请保留并查询原记录；未发送替代删除操作。")
        case .unavailable: language.text("The original result could not be verified. This does not establish that use has stopped or cleanup is complete.", "暂时无法核验原结果，不能据此认为已停止使用或清理完成。")
        case .recoveryUnavailable: language.text("The local original could not be verified. Keep it; this does not prove it was never submitted.", "暂时无法核验本机原记录。请保留它，这不代表从未提交。")
        }
    }
    private func phaseTitle(_ phase: MemoryErasurePhase) -> String {
        switch phase {
        case .inProgress: language.text("Online cleanup in progress", "线上清理进行中")
        case .unknown: language.text("Online cleanup outcome unknown", "线上清理结果未知")
        case .blocked: language.text("Online cleanup blocked", "线上清理受阻")
        case .failed: language.text("Online cleanup reported failure", "线上清理报告失败")
        case .complete: language.text("Listed online content cleanup confirmed", "所列线上内容已确认清理")
        }
    }
    private func stepTitle(_ state: MemoryErasureStepState) -> String {
        switch state {
        case .pending: language.text("pending", "待处理")
        case .inProgress: language.text("in progress", "进行中")
        case .unknown: language.text("unknown", "未知")
        case .failed: language.text("failed", "失败")
        case .confirmed: language.text("confirmed", "已确认")
        }
    }
    private func targetTitle(_ target: MemoryErasureTarget) -> String {
        switch target {
        case .message: language.text("Linked message copies", "消息中的关联副本")
        case .run: language.text("Linked run content", "运行关联内容")
        case .usage: language.text("Linked usage content", "用量记录关联内容")
        case .derived: language.text("Candidates and derived summaries", "候选与派生摘要")
        case .management: language.text("Memory changes", "记忆变更记录")
        case .trip: language.text("Owned trip-derived results and unaccepted drafts", "账号行程派生结果与未接受草稿")
        case .memory: language.text("Memory and source content", "记忆与来源内容")
        case .metadata: language.text("Original cleanup content", "原清理记录内容")
        }
    }
}
private extension MemoryErasureOriginal { var utf8Identity: Data { Data(actionID.utf8) } }
