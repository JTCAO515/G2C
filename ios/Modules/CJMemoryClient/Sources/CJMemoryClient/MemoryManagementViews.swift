import SwiftUI
import CJAPI

public struct MemoryManagementControls: View {
    let client: MemoryClient
    let selection: MemoryManagementSelection
    let binding: MemoryBinding
    let language: MemoryLanguage
    public init(client: MemoryClient, selection: MemoryManagementSelection, binding: MemoryBinding, language: MemoryLanguage) {
        self.client = client; self.selection = selection; self.binding = binding; self.language = language
    }
    public var body: some View {
        MemoryManagementControlsContent(client: client, selection: selection, binding: binding, language: language)
            .id(selection.readStamp).id(binding)
    }
}
private enum MemoryLifecycleUIState {
    case idle, submitting, querying, confirmed, notObserved, unknown, storageUnavailable
    case rejected(Int, String)
    func label(_ language: MemoryLanguage) -> String {
        switch self {
        case .idle: ""
        case .submitting: language.text("Submitting original action…", "正在提交原操作…")
        case .querying: language.text("Checking original action…", "正在核对原操作…")
        case .confirmed: language.text("Original action confirmed. Refresh the item for its current state.", "原操作已确认；请刷新条目查看当前状态。")
        case .notObserved: language.text("Result unknown: original receipt not observed. Do not resend.", "结果未知，尚未查到原回执，不可重新发送。")
        case .unknown: language.text("Result unknown. Query the original action only.", "结果未知，请仅查询原操作。")
        case .storageUnavailable: language.text("Original action storage could not be read. Nothing will be resent.", "无法读取原操作存储，不会重新发送。")
        case .rejected(let status, let code):
            language.text("Original action failed: ", "原操作已明确失败：") + String(status) + " / " + code
                + language.text(". Original input retained. Refresh and review before a new action.", "。原输入保留，请刷新并重新审阅后再发起新操作。")
        }
    }
}
private enum MemoryLifecycleIntent { case pause, resume, edit, stopUse }
private struct MemoryLifecycleButton: View {
    let title: String
    let identifier: String
    let enabled: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            MemoryRowText(text: title, style: .body)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(.plain).disabled(!enabled).accessibilityIdentifier(identifier)
    }
}
private struct MemoryManagementControlsContent: View {
    let client: MemoryClient
    let selection: MemoryManagementSelection
    let binding: MemoryBinding
    let language: MemoryLanguage
    @State private var confirming: MemoryLifecycleIntent?
    @State private var started = false
    @State private var editing = false
    @State private var editText: String
    @State private var status = MemoryLifecycleUIState.idle
    @State private var originalActionID: String?
    @State private var request = UUID()
    @FocusState private var textFocused: Bool
    init(client: MemoryClient, selection: MemoryManagementSelection, binding: MemoryBinding, language: MemoryLanguage) {
        self.client = client; self.selection = selection; self.binding = binding; self.language = language
        _editText = State(initialValue: selection.text)
    }
    private func failed(_ value: (status: Int, code: String)) -> MemoryLifecycleUIState { .rejected(value.status, value.code) }
    private func perform(queryOnly: Bool = false, _ action: @escaping () async throws -> MemoryManagementResult) {
        guard client.managementPresentationIsCurrent(binding) else { return }
        let token = UUID(); request = token
        status = queryOnly ? .querying : .submitting
        Task {
            do {
                guard client.managementPresentationIsCurrent(binding), token == request else { return }
                let result = try await action()
                guard client.managementPresentationIsCurrent(binding), token == request, !Task.isCancelled else { return }
                originalActionID = client.managementActionID(for: selection, binding: binding)
                switch result {
                case .historicalReceipt, .historicalStopUseReceipt:
                    status = .confirmed
                case .rejected(let code, let reason): status = failed((code, reason))
                case .notObserved:
                    if let id = originalActionID, let failure = try client.managementFailure(actionID: id, binding: binding) { status = failed(failure) }
                    else { status = .notObserved }
                }
            } catch {
                guard client.managementPresentationIsCurrent(binding), token == request else { return }
                originalActionID = client.managementActionID(for: selection, binding: binding)
                do {
                    if let id = originalActionID, let failure = try client.managementFailure(actionID: id, binding: binding) { status = failed(failure) }
                    else { status = .unknown }
                } catch {
                    guard client.managementPresentationIsCurrent(binding), token == request else { return }
                    status = .storageUnavailable
                }
            }
        }
    }
    private func confirm(_ intent: MemoryLifecycleIntent) {
        guard !started, client.managementPresentationIsCurrent(binding) else { return }
        textFocused = false; started = true; confirming = nil
        switch intent {
        case .pause: perform { try await client.applyManagement(.pause, selection: selection, binding: binding) }
        case .resume: perform { try await client.applyManagement(.resume, selection: selection, binding: binding) }
        case .edit:
            let originalInput = editText
            perform { try await client.editMemory(text: originalInput, selection: selection, binding: binding) }
        case .stopUse: perform { try await client.stopUsingMemory(selection: selection, binding: binding) }
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            MemoryRowText(text: language.text("The service verifies source permission and whether this action is allowed. A disabled label alone does not grant resume.", "服务端会核验来源权限与操作条件；“已停用”不代表一定可恢复。"), style: .caption)
            if !client.managementAvailable { MemoryRowText(text: language.text("Memory management is not available yet.", "逐条记忆管理尚未开放。"), style: .body) }
            MemoryLifecycleButton(title: language.text("Request pause", "请求暂停"), identifier: "memory.manage.pause", enabled: client.managementAvailable && !started) { confirming = .pause }
            MemoryLifecycleButton(title: language.text("Request resume", "请求恢复"), identifier: "memory.manage.resume", enabled: client.managementAvailable && !started) { confirming = .resume }
            if selection.kind != .inference && (selection.status == .active || selection.status == .disabled) {
                if editing {
                    if started {
                        MemoryRowText(text: editText, style: .body).accessibilityIdentifier("memory.manage.originalText")
                    } else {
                        TextField(language.text("Edit memory text", "编辑记忆内容"), text: $editText, axis: .vertical)
                            .textFieldStyle(.roundedBorder).frame(minHeight: 44).focused($textFocused)
                            .contentShape(Rectangle()).onTapGesture { textFocused = true }
                            .accessibilityIdentifier("memory.manage.text")
                    }
                    MemoryLifecycleButton(title: language.text("Save edited memory", "保存编辑后的记忆"), identifier: "memory.manage.saveEdit",
                        enabled: client.managementAvailable && !started && memoryText(editText)) { textFocused = false; confirming = .edit }
                } else {
                    MemoryLifecycleButton(title: language.text("Edit memory text", "编辑记忆内容"), identifier: "memory.manage.edit", enabled: client.managementAvailable && !started) { editing = true }
                }
            }
            MemoryRowText(text: language.text("Stop using preserves the original record and history; it does not physically delete data.", "停止使用会保留原记录与历史，不会物理删除数据。"), style: .caption)
            MemoryLifecycleButton(title: language.text("Stop using this memory", "停止使用这条记忆"), identifier: "memory.manage.stopUse",
                enabled: client.managementAvailable && !started && selection.status != .withdrawn) { confirming = .stopUse }
            MemoryRowText(text: status.label(language), style: .body).accessibilityIdentifier("memory.manage.status")
            if let originalActionID {
                MemoryRowText(text: originalActionID, style: .caption).accessibilityIdentifier("memory.manage.actionID")
                MemoryLifecycleButton(title: language.text("Query original action", "查询原操作"), identifier: "memory.manage.query", enabled: client.managementAvailable) {
                    perform(queryOnly: true) { try await client.queryManagement(actionID: originalActionID, binding: binding) }
                }
            }
        }
        .confirmationDialog(language.text("Confirm the requested memory action", "确认本次记忆操作"), isPresented: Binding(
            get: { confirming != nil }, set: { if !$0 { confirming = nil } })) {
                if let intent = confirming {
                    switch intent {
                    case .pause: Button(language.text("Confirm pause", "确认暂停")) { confirm(intent) }
                    case .resume: Button(language.text("Confirm resume", "确认恢复")) { confirm(intent) }
                    case .edit: Button(language.text("Confirm edited text", "确认编辑内容")) { confirm(intent) }
                    case .stopUse: Button(language.text("Confirm stop using", "确认停止使用")) { confirm(intent) }
                    }
                }
                Button(language.text("Cancel", "取消"), role: .cancel) { confirming = nil }
            }
        #if os(iOS)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button(language.text("Done", "完成")) { textFocused = false }
                    .accessibilityIdentifier("memory.manage.keyboard.done")
            }
        }
        #endif
    }
}

/// Reopen recovery is query-only and always uses the stored original action ID.
public struct MemoryManagementRecoveryView: View {
    let client: MemoryClient
    let pending: MemoryManagementPending
    let binding: MemoryBinding
    let language: MemoryLanguage
    public init(client: MemoryClient, pending: MemoryManagementPending, binding: MemoryBinding, language: MemoryLanguage) {
        self.client = client; self.pending = pending; self.binding = binding; self.language = language
    }
    public var body: some View {
        MemoryManagementRecoveryContent(client: client, pending: pending, binding: binding, language: language)
            .id(Data(pending.actionID.utf8)).id(binding)
    }
}
private struct MemoryManagementRecoveryContent: View {
    let client: MemoryClient
    let pending: MemoryManagementPending
    let binding: MemoryBinding
    let language: MemoryLanguage
    @State private var busy = false
    @State private var message = MemoryLifecycleUIState.idle
    private var originalEdit: Result<String?, Error> {
        Result {
            if case .edit(let action) = try pending.action { return action.text }
            return nil
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            MemoryRowText(text: language.text("Original memory action · query only", "原记忆操作 · 仅查询"), style: .body)
            MemoryRowText(text: pending.actionID, style: .caption).accessibilityIdentifier("memory.manage.recoveryID")
            MemoryRowText(text: pending.sourceID, style: .caption)
            switch originalEdit {
            case .success(.some(let text)): MemoryRowText(text: text, style: .body).accessibilityIdentifier("memory.manage.recoveredText")
            case .failure: MemoryRowText(text: language.text("Original input could not be decoded. The action is retained.", "无法解析原输入，原操作仍保留。"), style: .body)
            case .success(.none): EmptyView()
            }
            MemoryRowText(text: message.label(language), style: .body).accessibilityIdentifier("memory.manage.recoveryStatus." + pending.actionID)
            if !client.managementAvailable { Text(language.text("Action receipt queries are not available yet.", "管理操作回执查询尚未开放。")) }
            MemoryLifecycleButton(title: language.text("Query original action", "查询原操作"), identifier: "memory.manage.recoveryQuery." + pending.actionID,
                                  enabled: !busy && client.managementAvailable) {
                guard !busy, client.managementPresentationIsCurrent(binding) else { return }
                busy = true;message = .querying
                Task {
                    do {
                        let result = try await client.queryManagement(actionID: pending.actionID, binding: binding)
                        guard client.managementPresentationIsCurrent(binding), !Task.isCancelled else { return }
                        switch result {
                        case .historicalReceipt, .historicalStopUseReceipt: message = .confirmed
                        case .rejected(let code, let reason): message = .rejected(code, reason)
                        case .notObserved:
                            if let failure = try client.managementFailure(actionID: pending.actionID, binding: binding) {
                                message = .rejected(failure.status, failure.code)
                            } else { message = .notObserved }
                        }
                    } catch {
                        guard client.managementPresentationIsCurrent(binding) else { return }
                        message = .unknown
                    }
                    busy = false
                }
            }
        }
    }
}
