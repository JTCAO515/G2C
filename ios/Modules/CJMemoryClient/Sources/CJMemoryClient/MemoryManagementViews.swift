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
private struct MemoryManagementControlsContent: View {
    let client: MemoryClient
    let selection: MemoryManagementSelection
    let binding: MemoryBinding
    let language: MemoryLanguage
    @State private var confirming: Components.Schemas.MemoryManagementAction.operationPayload?
    @State private var started = false
    @State private var status = ""
    @State private var originalActionID: String?
    @State private var request = UUID()
    private func perform(_ action: @escaping () async throws -> MemoryManagementResult) {
        guard client.managementPresentationIsCurrent(binding) else { return }
        let token = UUID(); request = token
        status = language.text("Checking original action…", "正在核对原操作…")
        Task {
            do {
                guard client.managementPresentationIsCurrent(binding), token == request else { return }
                let result = try await action()
                guard client.managementPresentationIsCurrent(binding), token == request, !Task.isCancelled else { return }
                switch result {
                case .historicalReceipt:
                    status = language.text("Original action confirmed. Refresh the item for its current state.", "原操作已确认；请刷新条目查看当前状态。")
                case .notObserved:
                    status = language.text("Original receipt not observed. Do not resend.", "尚未查到原回执，不可重新发送。")
                }
            } catch {
                guard client.managementPresentationIsCurrent(binding), token == request else { return }
                status = language.text("Action not confirmed. Query the original action only.", "操作尚未确认，请仅查询原操作。")
            }
            originalActionID = client.managementActionID(for: selection, binding: binding)
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(language.text("The service verifies source permission and whether this action is allowed. A disabled label alone does not grant resume.", "服务端会核验来源权限与操作条件；“已停用”不代表一定可恢复。"))
                .font(.footnote)
            if !client.managementAvailable {
                Text(language.text("Pause and resume are not available yet.", "逐条暂停与恢复尚未开放。"))
            }
            HStack {
                Button(language.text("Request pause", "请求暂停")) { confirming = .pause }
                Button(language.text("Request resume", "请求恢复")) { confirming = .resume }
            }.disabled(!client.managementAvailable || started)
            Text(status)
            if let originalActionID {
                Button(language.text("Query original action", "查询原操作")) {
                    perform { try await client.queryManagement(actionID: originalActionID, binding: binding) }
                }.disabled(!client.managementAvailable)
            }
        }
        .confirmationDialog(language.text("Confirm the requested memory action", "确认本次记忆操作"), isPresented: Binding(
            get: { confirming != nil }, set: { if !$0 { confirming = nil } })) {
                if let operation = confirming {
                    Button(operation == .pause ? language.text("Confirm pause", "确认暂停") : language.text("Confirm resume", "确认恢复")) {
                        guard !started, client.managementPresentationIsCurrent(binding) else { return }
                        started = true; confirming = nil
                        perform { try await client.applyManagement(operation, selection: selection, binding: binding) }
                    }
                }
                Button(language.text("Cancel", "取消"), role: .cancel) { confirming = nil }
            }
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
    @State private var message = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(language.text("Original memory action · query only", "原记忆操作 · 仅查询"))
            Text(message)
            if !client.managementAvailable { Text(language.text("Action receipt queries are not available yet.", "管理操作回执查询尚未开放。")) }
            Button(language.text("Query original action", "查询原操作")) {
                guard !busy, client.managementPresentationIsCurrent(binding) else { return }
                busy = true
                Task {
                    do {
                        let result = try await client.queryManagement(actionID: pending.actionID, binding: binding)
                        guard client.managementPresentationIsCurrent(binding), !Task.isCancelled else { return }
                        switch result {
                        case .historicalReceipt: message = language.text("Original action confirmed; refresh for current state.", "原操作已确认；请刷新查看当前状态。")
                        case .notObserved: message = language.text("Receipt not observed; this does not allow resending.", "尚未查到回执；这不允许重新发送。")
                        }
                    } catch {
                        guard client.managementPresentationIsCurrent(binding) else { return }
                        message = language.text("Query failed; original action is retained.", "查询失败，原操作仍保留。")
                    }
                    busy = false
                }
            }.disabled(busy || !client.managementAvailable)
        }
    }
}
