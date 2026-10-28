#if os(iOS)
import SwiftUI
import CJMemoryClient

private extension ShellLanguage {
    var memoryLanguage: MemoryLanguage { self == .english ? .english : .chinese }
}

struct MemoryContainerGroups: View {
    let host: MemoryContainerHost
    @Bindable var state: ShellState
    var body: some View {
        let action = host.captureAction()
        MemoryGroupsView(state: host.groups, language: state.language.memoryLanguage) { group in
            if host.selectGroup(group, context: action) { state.memoryPath.append(.memoryItems) }
        }
        .disabled(host.busy)
        Button {
            Task { await host.loadGroups(context: action) }
        } label: {
            Text(host.isConfigured ? state.language.text("Load groups", "读取分组")
                 : state.language.text("Load groups — unavailable", "读取分组——不可用"))
                .foregroundStyle(Color(uiColor: .label)).fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
        }.buttonStyle(ShellReadableButtonStyle()).disabled(action == nil)
        if host.isSynthetic {
            Text(state.language.text("Synthetic test data", "合成测试数据")).font(.caption)
        }
    }
}

struct MemoryContainerItems: View {
    let host: MemoryContainerHost
    @Bindable var state: ShellState
    var body: some View {
        let action = host.captureAction()
        List {
            if let group = host.selectedGroup {
                Section(group.subject) {
                    MemoryItemsView(state: host.items, language: state.language.memoryLanguage) { itemID in
                        if host.selectItem(itemID, context: action) { state.memoryPath.append(.memoryDetail) }
                    }.disabled(host.busy)
                }
                Section {
                    Button(state.language.text("Load from start", "从头读取")) {
                        Task { await host.loadItems(context: action) }
                    }.disabled(action == nil)
                    if host.hasMore {
                        Button(state.language.text("Load next page", "读取下一页")) {
                            Task { await host.loadItems(context: action, more: true) }
                        }.disabled(action == nil)
                        Text(state.language.text("More records may follow, even when this page has no matching memories.", "即使本页没有匹配记忆，后续仍可能有记录。"))
                            .font(.caption)
                    }
                }
            } else {
                Text(state.language.text("Select a current memory group first.", "请先选择当前记忆分组。"))
            }
        }.navigationTitle(state.language.text("Memories", "记忆列表"))
    }
}

struct MemoryContainerDetail: View {
    let host: MemoryContainerHost
    let language: ShellLanguage
    @State private var presentation: MemoryManagementPresentationLifetime?
    var body: some View {
        let action = host.captureAction()
        List {
            MemoryDetailView(state: host.detail, language: language.memoryLanguage)
            MemoryManagementHostControls(host: host, language: language)
                .id(host.managementIdentity)
            Button(language.text("Load current detail", "读取当前详情")) {
                Task { await host.loadDetail(context: action) }
            }.disabled(action == nil)
        }.navigationTitle(language.text("Memory detail", "记忆详情"))
            .onAppear { presentation = host.beginManagementPresentation() }
            .onDisappear {
                host.leaveManagementPresentation(presentation)
                presentation = nil
            }
    }
}

struct MemoryContainerManual: View {
    let host: MemoryContainerHost
    let language: ShellLanguage
    @State private var presentation: MemoryManagementPresentationLifetime?
    var body: some View {
        let action = host.captureAction()
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(language.text("Saving new memories is not available yet.", "暂不支持保存新记忆。"))
                if let binding = host.manualBinding {
                    MemoryManualForm(binding: binding, currentBinding: { host.manualBinding },
                        options: host.manualOptions, language: language.memoryLanguage,
                        submit: { command in try await host.submitManual(command, context: action) },
                        queryOriginal: { _ in throw MemoryFailure.liveWriteUnavailable })
                        .id(host.formIdentity)
                        .disabled(!host.canSubmitManual)
                } else {
                    Text(language.text("Memory is not configured.", "记忆尚未配置。"))
                }
                MemoryManagementHostRecovery(host: host, language: language)
                    .id(host.managementIdentity)
                Divider()
                Text(language.text("Previous save operations", "此前的保存操作")).font(.headline)
                Button(language.text("Read original operations", "读取原操作")) { host.loadPending(context: action) }
                    .disabled(action == nil)
                switch host.pending {
                case .unconfigured:
                    Text(language.text("Original operations have not been loaded.", "尚未读取原操作。"))
                case .loading:
                    ProgressView()
                case .failed:
                    Text(language.text("Could not read original operations. Recovery is unavailable.", "无法读取原操作，暂不能恢复查询。"))
                case .loaded(let records):
                    if records.isEmpty { Text(language.text("No original operations found.", "未发现原操作。")) }
                    ForEach(records, id: \.originalUTF8) { record in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(record.operationID).font(.caption).textSelection(.enabled)
                            Button(language.text("Query this original operation", "查询此原操作")) {
                                Task { await host.queryOriginal(record.operationID, context: action) }
                            }.disabled(action == nil)
                        }
                    }
                }
                if let operationID = host.queriedOperationID {
                    Text(language.text("Result for operation: ", "操作结果：") + operationID).font(.caption)
                    if host.busy { ProgressView(language.text("Querying…", "查询中…")) }
                    else { MemorySaveStatusView(state: host.saveState, language: language.memoryLanguage, queryOriginal: nil) }
                }
                Text(language.text("A past receipt does not establish current use. An unknown or missing receipt does not permit resending.", "历史回执不代表当前仍在使用；结果未知或未查到回执时，不可重新发送。"))
                    .font(.caption)
            }.frame(maxWidth: .infinity, alignment: .leading).padding()
        }.navigationTitle(language.text("Add memory", "新增记忆"))
            .onAppear { presentation = host.beginManagementPresentation() }
            .onDisappear {
                host.leaveManagementPresentation(presentation)
                presentation = nil
            }
    }
}
#endif
