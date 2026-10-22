#if os(iOS)
import SwiftUI
import CJNeedsClient

struct NeedsContainerView: View {
    let host: NeedsContainerHost
    let language: ShellLanguage
    @State private var revisionText = ""
    private var needsLanguage: NeedsLanguage { language == .english ? .en : .zh }
    var body: some View {
        let action = host.captureAction()
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(language.text("Review or correct only what you know. Dates and budget may stay undecided.", "只查看或纠正已经明确的条件；日期和预算可以保持未定。"))
                Text(language.text("These are user-provided journey details. Fixed or booked items are not verified orders, and edits do not update long-term memory or the formal trip.", "这些是用户提供的本次旅行条件。已订或固定事项不是查证订单，编辑也不会更新长期记忆或正式行程。"))
                    .font(.footnote)
                if let model = host.presentation {
                    Text(model.state.message(needsLanguage)).accessibilityIdentifier("needs.container.state")
                    if let snapshot = model.snapshot {
                        NeedsDetailsView(fields: snapshot.fields, version: snapshot.version, language: needsLanguage)
                    }
                    if let revision = model.revision {
                        Text(language.text("Historical revision", "历史修订")).font(.headline)
                        NeedsDetailsView(fields: revision.fields, version: revision.version, language: needsLanguage)
                        if let bytes = Data(base64Encoded: revision.original_input_utf8_base64),
                           let command = try? JSONDecoder().decode(NeedsSchema.NeedsCommand.self, from: bytes) {
                            Text(command.source.text).textSelection(.enabled)
                            Text(language.text("Original statement for this revision; it is not the source of every retained field.", "这是本次修订的原始说明，不代表所有保留字段的来源。"))
                                .font(.caption)
                        }
                    }
                    if let receipt = model.receipt {
                        Text(language.text("Verified original action: ", "已核对原动作：") + receipt.action_id).font(.caption)
                        Text(language.text("Receipt revision: \(receipt.version). This does not establish the latest version.", "回执修订版本：\(receipt.version)，不代表最新版本。"))
                            .font(.caption)
                    }
                    Button(language.text("Read current needs (keep edits)", "读取当前需求（保留编辑）")) {
                        guard let work = host.prepareDetail(context: action) else { return }
                        Task { await host.perform(work) }
                    }.disabled(action == nil)
                    DisclosureGroup(language.text("Read a historical revision", "读取历史修订")) {
                        TextField(language.text("Revision number", "修订版本号"), text: $revisionText)
                            .keyboardType(.numberPad).textFieldStyle(.roundedBorder)
                        Button(language.text("Read revision", "读取修订")) {
                            guard let version = Int(revisionText), let work = host.prepareRevision(version, context: action) else { return }
                            Task { await host.perform(work) }
                        }.disabled(action == nil || Int(revisionText).map { $0 > 0 } != true)
                    }
                    if let draft = model.draft {
                        DisclosureGroup(language.text("Correct journey details", "纠正本次旅行条件")) {
                            NeedsEditorView(draft: Binding(get: { model.draft ?? draft }, set: { _ = host.updateDraft($0, context: action) }), language: needsLanguage)
                                .disabled(host.busy)
                            Button(language.text("Save corrections", "保存纠正")) {}.disabled(true)
                            Text(language.text("Saving is unavailable. Edits remain only in this screen and clear when the account changes or the app leaves the foreground.", "保存尚不可用。编辑仅保留在当前界面；账号变化或应用离开前台时会清空。"))
                                .font(.footnote)
                        }
                    }
                    Divider()
                    Text(language.text("Original actions for these needs", "此需求的原动作")).font(.headline)
                    Button(language.text("Read original actions", "读取原动作")) { host.loadPending(context: action) }
                        .disabled(action == nil)
                    Text(model.pendingState.message(needsLanguage)).font(.footnote)
                    if model.pendingState == .loaded && host.pendingActions.isEmpty {
                        Text(language.text("No original actions found for this selection.", "未发现此选择对应的原动作。"))
                    }
                    ForEach(host.pendingActions, id: \.actionID) { original in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(original.command.source.text).textSelection(.enabled)
                            Text(language.text("Original version: \(original.command.expected_version)", "原版本：\(original.command.expected_version)")).font(.caption)
                            Button(language.text("Query this original action", "查询此原动作")) {
                                guard let work = host.prepareQuery(original.actionID, context: action) else { return }
                                Task { await host.perform(work) }
                            }.disabled(action == nil)
                        }
                    }
                    Text(language.text("Unknown or unobserved results do not permit resending. Query verifies the original bytes against the exact historical revision.", "结果未知或未观察到不代表可以重新发送；查询会将原始字节与确切历史修订核对。"))
                        .font(.footnote)
                    if host.isSynthetic { Text(language.text("Synthetic test data", "合成测试数据")).font(.caption) }
                } else {
                    Text(language.text("Journey needs are unavailable. A trusted account and current needs selection are required.", "旅行需求尚不可用，需要可信账号和当前需求选择。"))
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding()
        }.navigationTitle(language.text("Journey needs", "本次旅行需求"))
    }
}
#endif
