#if os(iOS)
import CJLioUser
import CJMemoryClient
import SwiftUI

public struct LioSavedMemoryView: View {
    let host: TypedMemoryContainerHost
    let language: ShellLanguage
    @State private var surface: TypedMemorySurface?
    @State private var path: [Data] = []
    @State private var reload = 0
    @State private var deletion: LioMemoryDeletionRoute?
    @State private var stoppedMemory = false

    public init(host: TypedMemoryContainerHost, language: ShellLanguage) {
        self.host = host
        self.language = language
    }

    public var body: some View {
        let listSurface = path.isEmpty ? surface : nil
        NavigationStack(path: $path) {
            List {
                Group {
                    switch host.items {
                    case .unconfigured, .loading:
                        ProgressView()
                    case .failed:
                        Text(language.text("Couldn’t show your memories. Pull down to try again.",
                                           "暂时看不到你的记忆，下拉再试一次。"))
                    case .loaded(let items):
                        let saved = items.filter { isSaved($0) }
                        if saved.isEmpty && !host.hasMore {
                            Text(language.text("Things you ask Lio to remember appear here.", "你让 Lio 记住的内容会出现在这里。"))
                        }
                        ForEach(saved.indices, id: \.self) { index in
                            let item = saved[index].item.value
                            NavigationLink(value: Data(item.command.item_id.utf8)) {
                                Text(item.command.text)
                            }
                        }
                        if host.hasMore {
                            Button(language.text("More memories", "更多记忆")) {
                                let current = surface
                                Task { await host.loadItems(surface: current, more: true) }
                            }
                        }
                    }
                    if let model = host.erasurePresentation, model.original != nil || !model.originals.isEmpty {
                        Button(language.text("Memory deletions", "记忆删除记录")) { deletion = .history }
                            .disabled(model.state.isBusy)
                    }
                }
                .lioRow()
            }
            .lioPage()
            .navigationTitle(language.text("Memory", "记忆"))
            .refreshable { await host.loadItems(surface: surface) }
            .navigationDestination(for: Data.self) { id in
                if let surface {
                    LioSavedMemoryDetail(host: host, surface: surface, itemID: String(decoding: id, as: UTF8.self),
                                         language: language) { deletion = .memory(id) }
                }
            }
        }
        .onAppear {
            surface = host.enterSurface()
            reload += 1
        }
        .onDisappear {
            host.leaveSurface(surface)
            surface = nil
        }
        .onChange(of: path) { _, newPath in
            if newPath.isEmpty { reload += 1 }
        }
        // Use the same snapshot to identify and start the task. The initial
        // task must not pick up the surface created by onAppear and race its replacement.
        .task(id: listSurface.map { _ in reload }) {
            guard let listSurface, !Task.isCancelled else { return }
            await host.loadItems(surface: listSurface)
            if !Task.isCancelled, deletion == nil, path.isEmpty, let model = host.erasurePresentation, model.original == nil,
               let work = model.prepareOriginals() {
                await model.perform(work)
            }
        }
        .sheet(item: $deletion, onDismiss: closeDeletion) { route in
            if let model = host.erasurePresentation {
                LioMemoryDeletionView(host: host, model: model, route: route, language: language) {
                    stoppedMemory = true
                }
            }
        }
    }

    private func closeDeletion() {
        guard stoppedMemory || host.erasurePresentation?.knownStopped == true else { return }
        stoppedMemory = false
        surface = host.enterSurface()
        path.removeAll()
        reload += 1
    }
}

private func isSaved(_ read: TypedMemoryRead) -> Bool {
    let item = read.item.value
    return item.status == .active || item.status == .disabled
}

private struct LioSavedMemoryDetail: View {
    let host: TypedMemoryContainerHost
    let surface: TypedMemorySurface
    let itemID: String
    let language: ShellLanguage
    let showDeletion: () -> Void
    @State private var draft: String?
    @State private var saving = false
    @State private var notice: String?

    var body: some View {
        Form {
            Group {
                if let draft {
                    TextField(language.text("Memory", "记忆"),
                              text: Binding(get: { self.draft ?? draft }, set: { self.draft = $0 }), axis: .vertical)
                        .lineLimit(3...8)
                        .disabled(saving)
                        .accessibilityIdentifier("lio.memory.editor")
                    Button(language.text("Save", "保存")) { Task { await save(draft) } }
                        .disabled(saving || !(1...4096).contains(draft.unicodeScalars.count) ||
                                  draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        .accessibilityIdentifier("lio.memory.save")
                    Button(language.text("Cancel", "取消")) { self.draft = nil }
                        .disabled(saving)
                } else {
                    switch host.detail {
                    case .unconfigured, .loading:
                        ProgressView()
                    case .loaded(let entry):
                        if let entry, isSaved(entry) {
                            let item = entry.item.value
                            Text(item.command.text)
                            if item.status == .disabled {
                                Text(language.text("Lio isn’t using this memory.", "Lio 暂时不用这条记忆。"))
                                    .foregroundStyle(LioTheme.inkSecondary)
                            }
                            if entry.item.scope == .longTerm, item.command.kind != .inference {
                                Button(language.text("Edit", "编辑")) {
                                    notice = nil
                                    draft = item.command.text
                                }
                                .accessibilityIdentifier("lio.memory.edit")
                            }
                            if let model = host.erasurePresentation {
                                Button(language.text("Delete memory", "删除记忆"), role: .destructive) {
                                    do {
                                        try host.prepareErasure(surface: surface)
                                        showDeletion()
                                    } catch {
                                        notice = language.text("Couldn’t open memory deletion.", "暂时无法删除这条记忆。")
                                    }
                                }
                                .disabled(model.state.isBusy || host.busy)
                                .accessibilityIdentifier("lio.memory.delete")
                            }
                        } else {
                            Text(language.text("This memory is no longer available.", "这条记忆已不可用。"))
                        }
                    case .failed:
                        Text(language.text("Couldn’t show this memory. Pull down to try again.", "暂时看不到这条记忆，下拉再试一次。"))
                    }
                }
                if let notice { Text(notice).font(.footnote) }
                if saving { ProgressView() }
            }
            .lioRow()
        }
        .lioPage()
        .navigationTitle(language.text("Memory", "记忆"))
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(saving)
        .task(id: Data(itemID.utf8)) { await load() }
        .refreshable {
            if !saving && draft == nil { await load() }
        }
    }

    private func load() async {
        await host.loadDetail(itemID: itemID, surface: surface)
    }

    private func save(_ text: String) async {
        guard !saving else { return }
        saving = true
        defer { saving = false }
        notice = nil
        host.loadOriginals(surface: surface)
        guard case .loaded(let before) = host.managementOriginals else {
            notice = language.text("Couldn’t save this change.", "暂时无法保存这次修改。")
            return
        }
        do {
            let work = try host.prepareManagement(.edit, text: text, surface: surface)
            await host.performManagement(work)
        } catch MemoryFailure.pendingRequiresQuery {
            await recoverAndReload()
            return
        } catch {
            notice = language.text("Couldn’t save this change.", "暂时无法保存这次修改。")
            return
        }

        if case .needsOriginalQuery = host.managementState {
            await recoverAndReload()
            return
        }
        if case .unknown = host.managementState {
            host.loadOriginals(surface: surface)
            let earlier = Set(before.map { Data($0.actionID.utf8) })
            if case .loaded(let after) = host.managementOriginals {
                let added = after.filter { !earlier.contains(Data($0.actionID.utf8)) }
                if added.count == 1, let action = added.first {
                    await host.queryManagement(actionID: action.actionID, surface: surface)
                }
            }
        }
        draft = nil
        switch host.managementState {
        case .historical:
            notice = language.text("Saved.", "已保存。")
        case .rejected:
            notice = language.text("Couldn’t save this change.", "暂时无法保存这次修改。")
        default:
            notice = language.text("Your change may still be pending.", "这次修改可能还没完成。")
        }
        await load()
    }

    private func recoverAndReload() async {
        if case .loaded(let records) = host.originals {
            for record in records {
                await host.querySave(operationID: record.operationID, surface: surface)
            }
        }
        if case .loaded(let records) = host.managementOriginals {
            for record in records {
                await host.queryManagement(actionID: record.actionID, surface: surface)
            }
        }
        if case .requiresQuery = host.legacyRecoveryState {
            if case .loaded(let records) = host.legacyOriginals {
                for record in records {
                    await host.queryLegacySave(operationID: record.operationID, surface: surface)
                }
            }
            if case .loaded(let records) = host.legacyManagementOriginals {
                for record in records {
                    await host.queryLegacyManagement(actionID: record.actionID, surface: surface)
                }
            }
        }
        draft = nil
        await load()
        notice = language.text("An earlier change may still be pending.", "上次修改可能还没完成。")
    }
}
#endif
