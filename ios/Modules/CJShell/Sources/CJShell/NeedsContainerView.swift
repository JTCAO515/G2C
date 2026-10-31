#if os(iOS)
import SwiftUI
import UIKit
import CJNeedsClient
import CJRunClient

struct NeedsContainerView: View {
    let host: NeedsContainerHost
    let runs: RunContainerHost?
    let language: ShellLanguage
    @State private var revisionText = ""
    private var needsLanguage: NeedsLanguage { language == .english ? .en : .zh }
    var body: some View {
        let action = host.captureAction()
        let containerID = host.viewIdentity
        let cancellation = host.captureCancellation()
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                RunReadableText(text: language.text("Review or correct only what you know. Dates and budget may stay undecided.", "只查看或纠正已经明确的条件；日期和预算可以保持未定。"))
                RunReadableText(text: language.text("Manual changes do not update long-term memory or the formal trip. Booking and lock declarations are unverified user claims.", "手工改动不会更新长期记忆或正式行程。预订和固定意图均是未经外部核实的用户陈述。"), style: .caption)
                if let model = host.presentation {
                    RunReadableText(text: model.state.message(needsLanguage)).accessibilityIdentifier("needs.container.state")
                    if host.busy {
                        ProgressView()
                        command(language.text("Stop waiting for this original response", "停止等待此原响应"), id: "needs.cancel", disabled: cancellation == nil) { host.cancel(cancellation) }
                        RunReadableText(text: language.text("Stopping does not undo a possible save. Reconcile the same original action.", "停止等待不会撤销可能已经完成的保存；请核对同一原动作。"), style: .caption)
                    }
                    command(language.text("Read current needs (keep edits)", "读取当前需求（保留编辑）"), id: "needs.read", disabled: action == nil) {
                        guard let work = host.prepareDetail(context: action) else { return }
                        Task { await host.perform(work) }
                    }
                    if model.canSave {
                        if model.snapshot == nil && model.draft == nil {
                            command(language.text("Start a new requirements record", "开始一份新的需求记录"), id: "needs.beginNew", disabled: action == nil) { _ = host.beginNew(context: action) }
                        }
                        if let snapshot = model.snapshot {
                            command(language.text("Replace local edit using read version \(snapshot.version)", "以读到的版本 \(snapshot.version) 替换本地编辑"), id: "needs.useCurrent", disabled: action == nil) {
                                _ = host.beginCorrection(context: action)
                            }
                            RunReadableText(text: language.text("This explicit choice replaces unsaved edits, while preserving every original action. Reading alone never updates the editor's version.", "此明确选择会替换未保存编辑，但保留全部原动作。仅仅读取不会更新编辑器的基准版本。"), style: .caption)
                        }
                    }
                    if let issue = host.manualIssue {
                        RunReadableText(text: issue == .reconcileOriginals
                            ? language.text("Reconcile all original actions below before starting another save. Unknown and null results do not allow a replacement.", "开始另一次保存前，请先核对下方所有原动作。未知或未观察到的结果不允许替换动作。")
                            : language.text("Original storage is unavailable. Saving remains closed; keep the existing records.", "原动作存储不可用，保存保持关闭；请保留现有记录。"))
                            .accessibilityIdentifier("needs.manualIssue")
                    }
                    if let runs { preview(runs, action: action) }
                    if let draft = model.draft {
                        RunReadableText(text: language.text("Unsaved local edit · based on version \(draft.expectedVersion)", "未保存的本地编辑 · 基于版本 \(draft.expectedVersion)"))
                            .accessibilityIdentifier("needs.editor.basis")
                        if !draft.currencyReviewRequired.isEmpty {
                            RunReadableText(text: language.text("Changing currency does not convert prior amounts. Re-enter each amount or explicitly mark it unknown: ", "改变币种不会换算此前金额。请重新输入或明确标记未知：") +
                                draft.currencyReviewRequired.sorted(by: { $0.rawValue < $1.rawValue }).map { $0.label(needsLanguage) }.joined(separator: ", "))
                                .accessibilityIdentifier("needs.currencyReview")
                        }
                        command(language.text("Save explicit corrections", "保存明确的纠正"), id: "needs.save",
                                disabled: action == nil || !host.canSave || !draft.currencyReviewRequired.isEmpty) {
                            guard let work = host.prepareSave(context: action) else { return }
                            Task { await host.perform(work) }
                        }
                        DisclosureGroup {
                            NeedsEditorView(draft: Binding(get: { model.draft ?? draft }, set: { _ = host.updateDraft($0, context: action) }), language: needsLanguage)
                                .disabled(host.busy)
                        } label: { NeedsFormLabel(text: language.text("Edit journey details", "编辑本次旅行条件")).accessibilityIdentifier("needs.editor.open") }.id(draft.editorID)
                        if !model.canSave {
                            RunReadableText(text: language.text("Saving is unavailable. Edits remain local and clear with account/background changes.", "保存尚不可用。编辑仅保留在本地内存中；账号变化或进入后台时会清空。"), style: .caption)
                        }
                    }
                    if let snapshot = model.snapshot {
                        DisclosureGroup {
                            NeedsDetailsView(fields: snapshot.fields, version: snapshot.version, language: needsLanguage, identifierPrefix: "needs.detail")
                        } label: { NeedsFormLabel(text: language.text("Last read user-provided record", "上次读到的用户提供记录")).accessibilityIdentifier("needs.detail.open") }
                    }
                    if let revision = model.revision {
                        DisclosureGroup {
                            NeedsDetailsView(fields: revision.fields, version: revision.version, language: needsLanguage, identifierPrefix: "needs.history")
                            if let bytes = Data(base64Encoded: revision.original_input_utf8_base64),
                               let command = try? JSONDecoder().decode(NeedsSchema.NeedsCommand.self, from: bytes) {
                                RunSelectableText(text: command.source.text).accessibilityIdentifier("needs.history.statement")
                            }
                            RunReadableText(text: language.text("This original statement belongs to that revision, not every retained field. It does not establish the latest version.", "此原始说明属于该次修订，不代表所有保留字段的来源，也不代表最新版本。"), style: .caption)
                        } label: { NeedsFormLabel(text: language.text("Original action's historical revision", "原动作的历史修订")).accessibilityIdentifier("needs.history.open") }
                    }
                    if let receipt = model.receipt {
                        RunReadableText(text: language.text("Verified original action: ", "已核对原动作：") + receipt.action_id, style: .caption)
                            .accessibilityIdentifier("needs.receipt")
                    }
                    originals(action: action)
                    DisclosureGroup(language.text("Read a historical version", "读取历史版本")) {
                        TextField(language.text("Version number", "版本号"), text: $revisionText).keyboardType(.numberPad)
                            .textFieldStyle(.roundedBorder).accessibilityIdentifier("needs.revision.number")
                        command(language.text("Read version", "读取版本"), id: "needs.revision.read", disabled: action == nil || Int(revisionText).map { $0 > 0 } != true) {
                            guard let version = Int(revisionText), let work = host.prepareRevision(version, context: action) else { return }
                            Task { await host.perform(work) }
                        }
                    }
                    if let entry = host.feasibilityPresentation {
                        FeasibilityHostView(host: host, entry: entry, language: language).id(entry.id)
                    } else {
                        command(language.text("Review read record's evaluation", "查看已读记录的评估"), id: "needs.feasibility.open", disabled: action == nil || model.state != .loaded || model.snapshot == nil) {
                            _ = host.openFeasibility(context: action)
                        }
                        RunReadableText(text: language.text("Unconfirmed extraction, unsaved edits and historical receipts are not evaluation inputs.", "未确认提取、未保存编辑和历史回执不作为评估输入。"), style: .caption)
                    }
                    if host.isSynthetic { RunReadableText(text: language.text("Synthetic local test data", "本地合成测试数据"), style: .caption).accessibilityIdentifier("needs.synthetic") }
                    RunReadableText(text: language.text("Device timezone: ", "设备时区：") + TimeZone.current.identifier, style: .caption).accessibilityIdentifier("needs.deviceTimezone")
                } else {
                    RunReadableText(text: language.text("Journey needs are unavailable. A trusted account and explicit record selection are required.", "旅行需求不可用，需要可信账号和明确的记录选择。"))
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding()
        }.disclosureGroupStyle(NeedsDisclosureStyle(language: needsLanguage))
            .clipped().accessibilityIdentifier("needs.content")
            .scrollDismissesKeyboard(.interactively)
            .toolbar { ToolbarItem(placement: .topBarLeading) {
                Button {
                    UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                } label: {
                    Image(systemName: "keyboard.chevron.compact.down")
                        .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
                }.accessibilityLabel(language.text("Hide keyboard", "收起键盘")).accessibilityIdentifier("needs.keyboard.done")
            } }
            .onDisappear { if let containerID { host.leaveContainer(id: containerID) } }
            .navigationTitle(language.text("Needs", "需求")).navigationBarTitleDisplayMode(.inline)
    }
    @ViewBuilder private func preview(_ runs: RunContainerHost, action: NeedsContainerAction?) -> some View {
        switch host.preview(from: runs) {
        case .loaded(let value):
            let source = runs.originalPresentationID
            VStack(alignment: .leading, spacing: 10) {
                RunReadableText(text: language.text("Synthetic extraction · UNCONFIRMED / UNSAVED", "合成提取 · 未确认／未保存"), style: .headline).accessibilityIdentifier("needs.preview.status")
                RunReadableText(text: language == .english ? value.english : value.chinese)
                ForEach(value.questions.indices, id: \.self) { i in
                    RunReadableText(text: language == .english ? value.questions[i].english : value.questions[i].chinese).accessibilityIdentifier("needs.preview.question.\(i)")
                }
                if !value.deferredMemoryRequests.isEmpty {
                    RunReadableText(text: language.text("Long-term requests are NOT saved to Memory; confirm them separately.", "长期请求尚未保存到记忆，需要另行明确确认。"))
                        .accessibilityIdentifier("needs.preview.memoryDeferred")
                    ForEach(value.deferredMemoryRequests.indices, id: \.self) { i in RunSelectableText(text: value.deferredMemoryRequests[i]).accessibilityIdentifier("needs.preview.deferred.\(i)") }
                }
                command(language.text("Copy candidates into the unsaved editor", "将候选值复制到未保存编辑中"), id: "needs.preview.copy", disabled: action == nil || host.presentation?.draft == nil || source == nil) {
                    guard let source else { return }
                    _ = host.applyPreview(from: runs, expectedSource: source, context: action)
                }
                DisclosureGroup {
                    NeedsDetailsView(unconfirmedFields: value.fields, language: needsLanguage)
                } label: { NeedsFormLabel(text: language.text("Read unconfirmed extracted values", "读取未确认提取值")).accessibilityIdentifier("needs.preview.fields.open") }
                DisclosureGroup(language.text("Original accepted message", "已接受的原消息")) {
                    RunSelectableText(text: value.sourceText).accessibilityIdentifier("needs.preview.original")
                }
            }
        case .waiting: RunReadableText(text: language.text("No completed extraction preview is available yet.", "尚无完成的需求提取预览。"), style: .caption).accessibilityIdentifier("needs.preview.waiting")
        case .unavailable: RunReadableText(text: language.text("No current original extraction preview. Read the original run; do not resend it automatically.", "没有当前原需求提取预览。请读取原运行，不要自动重发。"), style: .caption).accessibilityIdentifier("needs.preview.unavailable")
        }
    }
    @ViewBuilder private func originals(action: NeedsContainerAction?) -> some View {
        if let model = host.presentation {
            Divider()
            RunReadableText(text: language.text("Original actions · same account", "原动作 · 同一账号"), style: .headline)
            command(language.text("Read original actions", "读取原动作"), id: "needs.originals.read", disabled: action == nil) { host.loadPending(context: action) }
            RunReadableText(text: model.pendingState.message(needsLanguage), style: .caption)
            ForEach(host.originalActions, id: \.actionID) { original in
                VStack(alignment: .leading, spacing: 8) {
                    RunSelectableText(text: original.command.source.text)
                    RunReadableText(text: language.text("Original record/version: ", "原记录／版本：") + original.needsID + " / " + String(original.command.expected_version), style: .caption)
                    command(language.text("Query this original action", "查询此原动作"), id: "needs.original.query." + original.actionID, disabled: action == nil) {
                        guard let work = host.prepareQuery(original.actionID, context: action) else { return }
                        Task { await host.perform(work) }
                    }
                    if model.canSave && model.verifiedActionIDs.contains(original.actionID) {
                        command(language.text("Replay this verified original (same bytes)", "重放此已核对原动作（相同字节）"), id: "needs.original.replay." + original.actionID, disabled: action == nil) {
                            guard let work = host.prepareReplay(original.actionID, context: action) else { return }
                            Task { await host.perform(work) }
                        }
                    }
                }
            }
            RunReadableText(text: language.text("Unknown or null results permit only original reconciliation. Replay is available only after exact historical verification and never uses a replacement ID.", "未知或空结果仅允许核对原动作。只有核对确切历史版本后才能明确重放，且不更换动作 ID。"), style: .caption)
        }
    }
    private func command(_ title: String, id: String, disabled: Bool, perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            RunReadableText(text: title).frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(ShellReadableButtonStyle()).disabled(disabled).accessibilityIdentifier(id)
    }
}
#endif
