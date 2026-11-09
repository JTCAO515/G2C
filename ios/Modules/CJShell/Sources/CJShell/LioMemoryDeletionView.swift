#if os(iOS)
import CJMemoryClient
import SwiftUI

enum LioMemoryDeletionRoute: Hashable, Identifiable {
    case memory(Data)
    case history

    var id: Self { self }
}

struct LioMemoryDeletionView: View {
    let host: TypedMemoryContainerHost
    let model: MemoryErasurePresentation
    let route: LioMemoryDeletionRoute
    let language: ShellLanguage
    let onStopped: () -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var phase
    @State private var inventoryLoaded = false
    @State private var inventoryLoading = true
    @State private var attemptedCleanup: Set<Data> = []

    private var activeDeletion: Data? {
        guard inventoryLoaded, phase == .active, let original = model.original else { return nil }
        return Data(original.actionID.utf8)
    }

    private var stoppedDeletion: Data? {
        guard model.knownStopped, !model.state.isBusy else { return nil }
        return activeDeletion
    }

    var body: some View {
        NavigationStack {
            Form {
                if route == .history, model.originals.count > 1 { deletions }
                if inventoryLoading || model.state.isBusy {
                    ProgressView()
                }
                if route != .history, inventoryLoaded, model.canSubmit, let entry = model.entry {
                    Text(entry.text)
                    Text(language.text(
                        "Deleting this memory also clears trip suggestions and unsaved drafts for this account. Your chats and saved trips stay. Other services may still have their own copies.",
                        "删除这条记忆也会清理此账号的行程建议和未保存草稿。聊天和已保存行程会保留，其他服务可能仍保有各自的副本。"))
                    Button(language.text("Delete memory", "删除记忆"), role: .destructive) {
                        perform(model.prepareSubmission(acknowledged: true))
                    }
                } else if model.original != nil {
                    status
                } else if !inventoryLoading {
                    Text(language.text("Couldn’t open memory deletion.", "暂时无法打开记忆删除。"))
                }
            }
            .navigationTitle(language.text("Delete memory", "删除记忆"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(language.text("Done", "完成")) { dismiss() }
                        .disabled(model.state.isBusy)
                }
            }
        }
        .interactiveDismissDisabled(model.state.isBusy)
        .task { await loadDeletions() }
        .task(id: activeDeletion) {
            if let activeDeletion { await observeDeletion(activeDeletion) }
        }
        .onChange(of: stoppedDeletion, initial: true) { _, stopped in
            guard let stopped, host.erasurePresentation === model, attemptedCleanup.insert(stopped).inserted else { return }
            if host.localCleanupState != .complete { host.clearErasedLocalContent() }
            onStopped()
        }
    }

    private var deletions: some View {
        Picker(language.text("Memory deletion", "记忆删除"), selection: Binding(
            get: { model.original.map { Data($0.actionID.utf8) } },
            set: { selected in
                guard let original = model.originals.first(where: { Data($0.actionID.utf8) == selected }) else { return }
                model.selectOriginal(actionID: original.actionID)
            }
        )) {
            ForEach(Array(model.originals.enumerated()), id: \.offset) { index, record in
                Text(language.text("Deletion \(index + 1)", "第 \(index + 1) 次删除"))
                    .tag(Optional(Data(record.actionID.utf8)))
            }
        }
        .disabled(!inventoryLoaded || model.state.isBusy)
    }

    @ViewBuilder
    private var status: some View {
        if model.knownStopped {
            Text(language.text("Lio has stopped using this memory.", "Lio 已停止使用这条记忆。"))
            if model.progressIsCurrent && model.progress?.onlineComplete == true {
                Text(language.text("Online cleanup is complete.", "线上清理已完成。"))
            } else if model.progressIsCurrent && model.progress?.phase == .inProgress {
                Text(language.text("Online cleanup is in progress.", "正在清理线上副本。"))
            } else {
                Text(language.text("Online cleanup hasn’t been confirmed as complete.", "暂时无法确认线上清理已完成。"))
            }
            switch host.localCleanupState {
            case .complete:
                Text(language.text("This device’s records of saving and editing this memory were cleared.", "本机已清理这条记忆的保存和编辑记录。"))
            case .unknown:
                Text(language.text("This device may still have records of saving or editing this memory.", "本机可能仍保有这条记忆的保存或编辑记录。"))
            case .notChecked, .clearing:
                EmptyView()
            }
            if model.canReconcile {
                Button(language.text("Continue deleting", "继续删除"), role: .destructive) {
                    perform(model.prepareReconciliation())
                }
            }
        } else {
            Text(language.text("We couldn’t confirm that Lio stopped using this memory yet.", "暂时无法确认 Lio 已停止使用这条记忆。"))
        }
    }

    private func loadDeletions() async {
        defer { inventoryLoading = false }
        guard let work = model.prepareOriginals() else { return }
        await model.perform(work)
        guard !Task.isCancelled, host.erasurePresentation === model else { return }
        guard model.state != .recoveryUnavailable else { return }
        let record: MemoryErasureOriginal?
        switch route {
        case .memory(let item):
            record = model.originals.first { Data($0.itemID.utf8) == item }
        case .history:
            record = model.originals.first { !$0.knownStopped } ?? model.originals.first
        }
        if let record { model.selectOriginal(actionID: record.actionID) }
        inventoryLoaded = true
    }

    private func observeDeletion(_ actionID: Data) async {
        while !Task.isCancelled, host.erasurePresentation === model, activeDeletion == actionID {
            if !model.state.isBusy {
                if model.progressIsCurrent, let progress = model.progress,
                   progress.onlineComplete || progress.phase == .blocked || progress.phase == .failed { return }
                if let work = model.prepareQuery() { await model.perform(work) }
            }
            do { try await Task.sleep(for: .seconds(12)) } catch { return }
        }
    }

    private func perform(_ work: MemoryErasurePresentationWork?) {
        guard let work else { return }
        Task { await model.perform(work) }
    }
}
#endif
