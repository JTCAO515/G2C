#if os(iOS)
import CJLioUser
import CJMemoryClient
import SwiftUI
import UIKit

public struct LioSavedMemoryView: View {
    let host: TypedMemoryContainerHost
    let language: ShellLanguage
    @State private var surface: TypedMemorySurface?
    @State private var path: [Data] = []
    @State private var reload = 0
    @State private var deletion: LioMemoryDeletionRoute?
    @State private var stoppedMemory = false
    @ScaledMetric(relativeTo: .headline) private var previewHeight = previewLineHeight * 3
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.colorScheme) private var colorScheme

    public init(host: TypedMemoryContainerHost, language: ShellLanguage) {
        self.host = host
        self.language = language
    }

    public var body: some View {
        let listSurface = path.isEmpty ? surface : nil
        NavigationStack(path: $path) {
            GeometryReader { page in
                VStack(alignment: .leading, spacing: 0) {
                    Text(language.text("Memory", "记忆"))
                        .font(LioTheme.display(.largeTitle))
                        .foregroundStyle(LioTheme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                        .padding(.horizontal, 16)
                        .padding(.top, 12)
                        .padding(.bottom, 8)
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            switch host.items {
                            case .unconfigured, .loading:
                                ProgressView()
                            case .failed:
                                Text(
                                    language.text(
                                        "Couldn’t show your memories. Pull down to try again.",
                                        "暂时看不到你的记忆，下拉再试一次。"))
                            case .loaded(let items):
                                let saved = items.filter { isSaved($0) }
                                if saved.isEmpty && !host.hasMore {
                                    VStack(spacing: 16) {
                                        LioPortrait(size: 80)
                                        Text(
                                            language.text(
                                                "Things you ask Lio to remember appear here.", "你让 Lio 记住的内容会出现在这里。"
                                            )
                                        )
                                        .font(LioTheme.display(.title3))
                                        .multilineTextAlignment(.center)
                                    }
                                    .padding(.vertical, 40)
                                    .frame(maxWidth: .infinity)
                                }
                                LazyVGrid(
                                    columns: Array(
                                        repeating: GridItem(.flexible(), spacing: 12, alignment: .top),
                                        count: typeSize.isAccessibilitySize ? 1 : 2),
                                    spacing: typeSize.isAccessibilitySize ? 0 : 12
                                ) {
                                    memoryCards(saved, pageHeight: page.size.height)
                                }
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, typeSize.isAccessibilitySize ? 0 : 16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .clipped()
                    .refreshable { await host.loadItems(surface: surface) }
                    if case .loaded = host.items, host.hasMore {
                        Button {
                            let current = surface
                            Task { await host.loadItems(surface: current, more: true) }
                        } label: {
                            Text(language.text("More memories", "更多记忆"))
                                .foregroundStyle(LioTheme.ink)
                                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                                .contentShape(Rectangle())
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                    }
                    if let model = host.erasurePresentation, model.original != nil || !model.originals.isEmpty {
                        Button {
                            deletion = .history
                        } label: {
                            Text(language.text("Memory deletions", "记忆删除记录"))
                                .foregroundStyle(LioTheme.ink)
                                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                                .contentShape(Rectangle())
                        }
                        .disabled(model.state.isBusy)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                    }
                }
            }
            .lioPage()
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(LioTheme.paper, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(colorScheme, for: .navigationBar)
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

    private func memoryCards(_ saved: [TypedMemoryRead], pageHeight: CGFloat) -> some View {
        ForEach(saved.indices, id: \.self) { index in
            let item = saved[index].item.value
            let id = Data(item.command.item_id.utf8)
            let deactivated = item.status == .disabled
            let card = NavigationLink(value: id) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 4) {
                        Image(systemName: memorySymbol(saved[index]))
                            .font(.title3)
                            .foregroundStyle(LioTheme.gold)
                        Spacer(minLength: 4)
                        if deactivated {
                            Text(language.text("Deactivated", "已停用"))
                                .font(.subheadline.weight(.semibold))
                                .fixedSize(horizontal: false, vertical: true)
                                .foregroundStyle(LioTheme.inkSecondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                        }
                    }
                    ScrollView(.vertical) {
                        Text(item.command.text)
                            .font(LioTheme.display(.headline))
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .scrollIndicators(.hidden)
                    .scrollDisabled(true)
                    .frame(height: previewHeight)
                    .clipped()
                    .allowsHitTesting(false)
                    Spacer(minLength: 0)
                }
                .foregroundStyle(LioTheme.ink)
                .padding(12)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                .overlay { RoundedRectangle(cornerRadius: LioTheme.Radius.card).stroke(LioTheme.hairline, lineWidth: 1) }
                .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            }
            .buttonStyle(.plain)
            .aspectRatio(1, contentMode: .fit)
            .accessibilityLabel(memoryCategory(saved[index]) + (deactivated ? " · " + language.text("Deactivated", "已停用") : ""))
            .accessibilityValue(item.command.text)
            .accessibilityIdentifier("lio.memory.card.\(item.command.item_id)")
            VStack(spacing: 0) {
                card
                Spacer(minLength: 0)
            }
            .padding(.vertical, typeSize.isAccessibilitySize ? 16 : 0)
            .frame(height: typeSize.isAccessibilitySize ? pageHeight : nil)
        }
    }

    private func memoryCategory(_ read: TypedMemoryRead) -> String {
        switch read.item.value.command.kind {
        case .fact: language.text("About you", "关于你")
        case .experience: language.text("Experience", "经历")
        case .preference: language.text("Preference", "偏好")
        case .inference: language.text("Suggestion", "小提示")
        }
    }

    private func memorySymbol(_ read: TypedMemoryRead) -> String {
        switch read.item.value.command.kind {
        case .fact: "info.circle"
        case .experience: "sparkles"
        case .preference: "heart"
        case .inference: "lightbulb"
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

private let previewLineHeight: CGFloat = {
    let font = UIFont.preferredFont(forTextStyle: .headline,
                                   compatibleWith: UITraitCollection(preferredContentSizeCategory: .large))
    return UIFont(descriptor: font.fontDescriptor.withDesign(.serif)!, size: 0).lineHeight
}()

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
    @FocusState private var editing: Bool
    @Environment(\.scenePhase) private var phase

    var body: some View {
        Form {
            Group {
                if let draft {
                    TextField(language.text("Memory", "记忆"),
                              text: Binding(get: { self.draft ?? draft }, set: { self.draft = $0 }), axis: .vertical)
                        .lineLimit(3...8)
                        .disabled(saving)
                        .focused($editing)
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
        .onChange(of: phase) { _, phase in
            if phase != .active { editing = false }
        }
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
