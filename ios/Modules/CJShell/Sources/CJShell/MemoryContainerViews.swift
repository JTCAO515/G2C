#if os(iOS)
import SwiftUI
import CJMemoryClient
import CJRunClient

private extension ShellLanguage {
    var memoryLanguage: MemoryLanguage { self == .english ? .english : .chinese }
}

private struct MemoryActionButton: View {
    let title: String
    let enabled: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            RunReadableText(text: title)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
        }.buttonStyle(ShellReadableButtonStyle()).accessibilityLabel(title).disabled(!enabled)
    }
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
                Section {
                    MemoryItemsView(state: host.items, language: state.language.memoryLanguage) { itemID in
                        if host.selectItem(itemID, context: action) { state.memoryPath.append(.memoryDetail) }
                    }.disabled(host.busy)
                } header: {
                    RunReadableText(text: group.subject, style: .caption).textCase(nil)
                }
                Section {
                    MemoryActionButton(title: state.language.text("Load from start", "从头读取"), enabled: action != nil) {
                        Task { await host.loadItems(context: action) }
                    }
                    if host.hasMore {
                        MemoryActionButton(title: state.language.text("Load next page", "读取下一页"), enabled: action != nil) {
                            Task { await host.loadItems(context: action, more: true) }
                        }
                        RunReadableText(text: state.language.text("More records may follow, even when this page has no matching memories.", "即使本页没有匹配记忆，后续仍可能有记录。"), style: .caption)
                    }
                }
            } else {
                Text(state.language.text("Select a current memory group first.", "请先选择当前记忆分组。"))
            }
        }
            .navigationTitle(state.language.text("Memories", "记忆列表")).navigationBarTitleDisplayMode(.inline)
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
            if host.managementAvailable {
                MemoryManagementHostControls(host: host, language: language).id(host.managementIdentity)
            }
            MemoryActionButton(title: language.text("Load current detail", "读取当前详情"), enabled: action != nil) {
                Task { await host.loadDetail(context: action) }
            }
        }
            .navigationTitle(language.text("Memory detail", "记忆详情")).navigationBarTitleDisplayMode(.inline)
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
    @State private var recovering = false
    var body: some View {
        let action = host.captureAction()
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if !host.canSubmitManual {
                    Text(language.text("Saving new memories is not available yet.", "暂不支持保存新记忆。"))
                }
                Text(language.text("Before a new save, previous operations are checked. An unknown receipt keeps new saves blocked; previous operations are never resent.", "新增保存前会核查此前的原操作。回执未查明时不提交新的保存，也不会重发旧操作。"))
                    .font(.footnote)
                if recovering {
                    MemoryActionButton(title: language.text("New memory", "新增一条记忆"), enabled: action != nil) { recovering = false }
                } else {
                    if let binding = host.manualBinding {
                        MemoryManualForm(binding: binding, currentBinding: { host.manualBinding },
                            options: host.manualOptions, language: language.memoryLanguage,
                            submit: { command in try await host.submitManual(command, context: action) },
                            queryOriginal: { operationID in try await host.queryManual(operationID, context: host.captureAction()) })
                            .id(host.formIdentity)
                            .disabled(!host.canSubmitManual)
                    } else {
                        Text(language.text("Memory is not configured.", "记忆尚未配置。"))
                    }
                }
                if host.managementAvailable {
                    MemoryManagementHostRecovery(host: host, language: language).id(host.managementIdentity)
                }
                Divider()
                Text(language.text("Previous save operations", "此前的保存操作")).font(.headline)
                MemoryActionButton(title: language.text("Read original operations", "读取原操作"), enabled: action != nil) { recovering = true; host.loadPending(context: action) }
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
                            RunSelectableText(text: record.operationID, minimumHeight: 44)
                            MemoryActionButton(title: language.text("Query this original operation", "查询此原操作"), enabled: action != nil) {
                                Task { await host.queryOriginal(record.operationID, context: action) }
                            }
                        }
                    }
                }
                if let operationID = host.queriedOperationID {
                    Text(language.text("Result for operation: ", "操作结果：") + operationID).font(.caption)
                    if host.busy { ProgressView(language.text("Querying…", "查询中…")) }
                    else { MemorySaveStatusView(state: host.saveState, language: language.memoryLanguage, queryOriginal: nil, statusIdentifier: "memory.original.status") }
                }
                Text(language.text("A past receipt does not establish current use. An unknown or missing receipt does not permit resending.", "历史回执不代表当前仍在使用；结果未知或未查到回执时，不可重新发送。"))
                    .font(.caption)
            }.frame(maxWidth: .infinity, alignment: .leading).padding()
        }
            .navigationTitle(language.text("Add memory", "新增记忆")).navigationBarTitleDisplayMode(.inline)
            .onAppear { presentation = host.beginManagementPresentation() }
            .onDisappear {
                host.leaveManagementPresentation(presentation)
                presentation = nil
            }
    }
}
#endif

#if os(iOS)
/// Optional entry beside chat. Every answer uses the same reviewed manual-save
/// form and original-operation journal; merely viewing/skipping writes nothing.
struct MemoryCollectionView: View {
    let host: MemoryContainerHost
    @Bindable var shell: ShellState
    @Environment(\.dismiss) private var dismiss
    @State private var index = 0
    private var language: ShellLanguage { shell.language }
    private func question(_ option: MemoryManualOption) -> String {
        switch option.kind {
        case .fact: language.text("What would you like us to know for your travels?", "关于你的旅行，有哪些希望我们记住的情况？")
        case .experience: language.text("Which travel experience would you like to keep?", "有哪些旅行经历希望记下来？")
        case .preference: language.text("What travel preference would you like to save?", "你有哪些希望保存的旅行偏好？")
        case .inference: language.text("Which suggestion still needs your confirmation?", "哪些推断仍需要你确认？")
        }
    }
    var body: some View {
        let questions = host.collectionOptions
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(language.text("A few things to remember", "逐步了解你的旅行习惯")).font(.title2)
                Text(language.text("These questions are optional. You can chat at any time. Only content you choose to save is submitted; guesses stay unconfirmed.", "这些问题均可跳过，随时可以聊天。只有你选择保存的内容才会提交，推断仍待确认。"))
                if questions.indices.contains(index), let binding = host.manualBinding {
                    Text(language.text("Question ", "问题 ") + "\(index + 1)/\(questions.count)")
                        .accessibilityIdentifier("memory.collection.progress")
                    RunReadableText(text: question(questions[index]))
                        .accessibilityIdentifier("memory.collection.question")
                    MemoryManualForm(binding: binding, currentBinding: { host.manualBinding },
                        options: [questions[index]], language: language.memoryLanguage,
                        submit: { command in try await host.submitManual(command, context: host.captureAction()) },
                        queryOriginal: { operationID in try await host.queryManual(operationID, context: host.captureAction()) })
                        .id(questions[index].id)
                    Button(language.text("Next question (optional)", "继续下一问（可跳过）")) {
                        if index + 1 < questions.count { index += 1 }
                        else { dismiss() }
                    }.disabled(host.busy).accessibilityIdentifier("memory.collection.next")
                } else {
                    Text(language.text("Memory collection is unavailable.", "暂不能收集记忆。"))
                }
                Button(language.text("Skip for now and chat", "暂时跳过，开始聊天")) {
                    dismiss(); shell.selectedTab = .assistant
                }.accessibilityIdentifier("memory.collection.skip")
                Text(language.text("If a save is unknown, check its original operation from Add memory. Skipping does not cancel or resend it.", "保存结果未知时，请在新增记忆页查询原操作。跳过不会取消或重发保存。"))
                    .font(.footnote)
            }.frame(maxWidth: .infinity, alignment: .leading).padding()
        }
            .navigationTitle(language.text("Optional questions", "可选问题")).navigationBarTitleDisplayMode(.inline)
    }
}
#endif
