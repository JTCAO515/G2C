#if os(iOS)
import CJLioUser
import CJMemoryClient
import CJRunClient
import SwiftUI

public struct LioSavedMemoryView: View {
    let host: TypedMemoryContainerHost
    let language: ShellLanguage
    @State private var surface: TypedMemorySurface?
    @State private var path: [Data] = []
    @State private var deletion: LioMemoryDeletionRoute?
    @State private var stoppedMemory = false
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.lioMemorySuggestions) private var suggestions
    @Environment(\.lioCloseMemory) private var close

    public init(host: TypedMemoryContainerHost, language: ShellLanguage) {
        self.host = host
        self.language = language
    }

    public var body: some View {
        let listSurface = path.isEmpty ? surface : nil
        NavigationStack(path: $path) {
            VStack(alignment: .leading, spacing: 0) {
                Text(LioMemoryCopy.pageTitle(language))
                    .font(LioTheme.display(.largeTitle))
                    .foregroundStyle(LioTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("lio.memory.title")
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 8)
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        switch host.items {
                        case .unconfigured, .loading:
                            if !suggestions.isEmpty { memorySuggestions }
                            ProgressView()
                        case .failed:
                            if !suggestions.isEmpty { memorySuggestions }
                            Text(
                                language.text(
                                    "Couldn’t show your memories. Pull down to try again.",
                                    "暂时看不到你的记忆，下拉再试一次。"))
                        case .loaded(let items):
                            let saved = items.filter { isSaved($0) }
                            if !saved.isEmpty || host.hasMore { memoryIntro }
                            if !suggestions.isEmpty { memorySuggestions }
                            if saved.isEmpty && !host.hasMore { emptyMemory }
                            ForEach(LioMemoryGrouping.groups(saved) { $0.item.value.command.slot }) { group in
                                memoryGroup(group)
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, typeSize.isAccessibilitySize ? 8 : 16)
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
                            .font(.headline)
                            .foregroundStyle(LioTheme.ink)
                            .padding(.horizontal, LioTheme.Spacing.sm)
                            .frame(minHeight: 44)
                            .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .frame(maxWidth: .infinity, alignment: .leading)
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
            .lioPage()
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(LioTheme.paper, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(colorScheme, for: .navigationBar)
            .toolbar {
                if let close {
                    ToolbarItem(placement: .confirmationAction) {
                        // Same as the chat menu's Done: text that follows Dynamic Type in the navigation bar.
                        Button { close() } label: {
                            RunReadableText(text: language.text("Done", "完成"), color: LioTheme.vermilion)
                                .fixedSize()
                                .frame(minHeight: 44)
                        }
                        .accessibilityLabel(language.text("Done", "完成"))
                        .accessibilityIdentifier("lio.me.memory.done")
                    }
                }
            }
            .navigationDestination(for: Data.self) { id in
                if let surface {
                    LioSavedMemoryDetail(host: host, surface: surface, itemID: String(decoding: id, as: UTF8.self),
                                         language: language) { deletion = .memory(id) }
                }
            }
        }
        .onAppear {
            surface = host.enterSurface()
        }
        .onDisappear {
            host.leaveSurface(surface)
            surface = nil
        }
        .task(id: listSurface) {
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

    /// What the page is for, and the note that answers say when they use a memory. Text only.
    private var memoryIntro: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            Text(LioMemoryCopy.pageDescription(language))
                .accessibilityIdentifier("lio.memory.intro")
            Text(LioMemoryCopy.usageNote(language))
                .accessibilityIdentifier("lio.memory.usage-note")
        }
        .font(.subheadline)
        .foregroundStyle(LioTheme.inkSecondary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Nothing saved yet: say what Lio remembers and how to make it happen, with sentences the service accepts.
    private var emptyMemory: some View {
        let shape = RoundedRectangle(cornerRadius: LioTheme.Radius.card)
        let examples = LioMemoryCopy.examples(language)
        return VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
            VStack(spacing: LioTheme.Spacing.sm) {
                LioPortrait(size: 80)
                Text(LioMemoryCopy.emptyTitle(language))
                    .font(LioTheme.display(.title3))
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("lio.memory.empty.title")
                Text(LioMemoryCopy.emptyDescription(language))
                    .font(.body)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .multilineTextAlignment(.center)
                    .accessibilityIdentifier("lio.memory.empty.description")
            }
            .frame(maxWidth: .infinity)
            .fixedSize(horizontal: false, vertical: true)
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                Text(LioMemoryCopy.remembersHeading(language))
                    .font(.headline)
                    .accessibilityAddTraits(.isHeader)
                Text(LioMemoryCopy.remembers(language))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.memory.empty.remembers")
            }
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                Text(LioMemoryCopy.examplesHeading(language))
                    .font(.headline)
                    .accessibilityAddTraits(.isHeader)
                ForEach(examples.indices, id: \.self) { index in
                    Text(verbatim: "“\(examples[index])”")
                        .font(LioTheme.display(.body))
                        .padding(LioTheme.Spacing.sm)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                        .accessibilityIdentifier("lio.memory.empty.example.\(index)")
                }
                Text(LioMemoryCopy.examplesTip(language))
                    .font(.subheadline)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.memory.empty.tip")
            }
            Text(LioMemoryCopy.usageNote(language))
                .font(.subheadline)
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.memory.usage-note")
        }
        .foregroundStyle(LioTheme.ink)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(LioTheme.Spacing.md)
        .background(LioTheme.surface, in: shape)
        .overlay { shape.stroke(LioTheme.hairline, lineWidth: 1).allowsHitTesting(false) }
        .accessibilityIdentifier("lio.memory.empty")
    }

    private var memorySuggestions: some View {
        let shape = RoundedRectangle(cornerRadius: LioTheme.Radius.card)
        return VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text(language.text("Suggestions from this chat", "当前对话的记忆建议"))
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("lio.memory.suggestions")
            ForEach(suggestions.indices, id: \.self) { index in
                Text(verbatim: suggestions[index])
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("lio.memory.suggestion.\(index)")
            }
            Text(language.text("Choose what to remember in Chat.", "在聊天里选择要记住的内容。"))
                .font(.subheadline)
                .foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(LioTheme.ink)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(LioTheme.Spacing.md)
        .background(LioTheme.surface, in: shape)
        .overlay { shape.stroke(LioTheme.hairline, lineWidth: 1).allowsHitTesting(false) }
    }

    private func memoryGroup(_ group: LioMemoryGroup<TypedMemoryRead>) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            HStack(spacing: LioTheme.Spacing.xs) {
                Image(systemName: group.category.symbol)
                    .foregroundStyle(LioTheme.gold)
                    .accessibilityHidden(true)
                Text(group.category.title(language))
                    .font(LioTheme.display(.title3))
                    .foregroundStyle(LioTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.isHeader)
            .accessibilityIdentifier("lio.memory.group.\(group.category.rawValue)")
            ForEach(group.items.indices, id: \.self) { index in
                memoryRow(group.items[index])
            }
        }
    }

    private func memoryRow(_ read: TypedMemoryRead) -> some View {
        let item = read.item.value
        let summary = LioMemoryCopy.summary(recordedAt: item.recorded_at, longTerm: read.item.scope == .longTerm,
                                            language: language)
        return NavigationLink(value: Data(item.command.item_id.utf8)) {
            LioMemoryRowLabel(symbol: memorySymbol(read), heading: read.item.title ?? item.command.text,
                              text: item.command.text, summary: summary, itemID: item.command.item_id,
                              deactivated: item.status == .disabled, language: language)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(memoryAccessibilityLabel(read))
        .accessibilityValue(item.command.text)
        .accessibilityHint(summary)
        .accessibilityIdentifier("lio.memory.card.\(item.command.item_id)")
    }

    private func memoryAccessibilityLabel(_ read: TypedMemoryRead) -> String {
        var parts: [String] = []
        if let title = read.item.title { parts.append(title) }
        parts.append(memoryCategory(read))
        if read.item.value.status == .disabled { parts.append(language.text("Deactivated", "已停用")) }
        return parts.joined(separator: " · ")
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
    }
}

/// One saved memory in the list: its short title (or the whole text), the text, where it came from, and whether
/// Lio is using it. The row is at least 44 pt tall and grows with Dynamic Type.
private struct LioMemoryRowLabel: View {
    let symbol: String
    let heading: String
    let text: String
    let summary: String
    let itemID: String
    let deactivated: Bool
    let language: ShellLanguage

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: LioTheme.Radius.card)
        HStack(alignment: .top, spacing: LioTheme.Spacing.sm) {
            Image(systemName: symbol)
                .font(.title3)
                .foregroundStyle(LioTheme.gold)
                .accessibilityHidden(true)
            texts
            Image(systemName: "chevron.forward")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityHidden(true)
                .frame(minHeight: 44)
        }
        .foregroundStyle(LioTheme.ink)
        .padding(LioTheme.Spacing.sm)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .topLeading)
        .background(LioTheme.surface, in: shape)
        .overlay { shape.stroke(LioTheme.hairline, lineWidth: 1) }
        .contentShape(shape)
    }

    private var texts: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            Text(heading)
                .font(LioTheme.display(.headline))
                .frame(maxWidth: .infinity, alignment: .leading)
            if heading != text {
                Text(text)
                    .font(.subheadline)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .lineLimit(3)
            }
            Text(summary)
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.memory.source.\(itemID)")
            if deactivated { deactivatedBadge }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private var deactivatedBadge: some View {
        Text(language.text("Deactivated", "已停用"))
            .accessibilityIdentifier("lio.memory.deactivated.\(itemID)")
            .font(.subheadline)
            .fontWeight(.semibold)
            .foregroundStyle(LioTheme.inkSecondary)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
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
    @FocusState private var editing: Bool
    @Environment(\.scenePhase) private var phase
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Form {
            Section {
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
                            if item.status == .disabled {
                                Text(language.text("Lio isn’t using this memory.", "Lio 暂时不用这条记忆。"))
                                    .foregroundStyle(LioTheme.inkSecondary)
                            }
                            Text(item.command.text)
                            if entry.item.scope == .longTerm, item.command.kind != .inference {
                                Button(language.text("Edit", "编辑")) {
                                    notice = nil
                                    draft = item.command.text
                                }
                                .disabled(saving || host.busy)
                                .accessibilityIdentifier("lio.memory.edit")
                                Button(language.text(item.status == .disabled ? "Reactivate" : "Deactivate",
                                                     item.status == .disabled ? "继续使用" : "暂停使用")) {
                                    Task { await change(item.status == .disabled ? .resume : .pause) }
                                }
                                .disabled(saving || host.busy)
                                .accessibilityIdentifier(item.status == .disabled ? "lio.memory.resume" : "lio.memory.pause")
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
                                .disabled(saving || model.state.isBusy || host.busy)
                                .foregroundStyle(LioTheme.vermilion)
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
            } header: {
                Text(language.text("Memory", "记忆"))
                    .font(LioTheme.display(.title2))
                    .foregroundStyle(LioTheme.ink)
                    .textCase(nil)
                    .accessibilityAddTraits(.isHeader)
            }
            provenance
        }
        .scrollDismissesKeyboard(.interactively)
        .lioPage()
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .navigationBarBackButtonHidden(saving)
        .toolbar {
            ToolbarItem(placement: .principal) { Color.clear.frame(width: 1, height: 1).accessibilityHidden(true) }
            if editing {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(language.text("Done", "完成")) { editing = false }
                        .accessibilityIdentifier("lio.memory.keyboard-done")
                }
            }
        }
        .onChange(of: phase) { _, phase in
            if phase != .active { editing = false }
        }
        .task(id: Data(itemID.utf8)) { await load() }
        .refreshable {
            if !saving && draft == nil { await load() }
        }
    }

    /// Where this memory came from and how answers mention it. Text only; nothing is read from the service.
    @ViewBuilder private var provenance: some View {
        if draft == nil, case .loaded(let entry) = host.detail, let entry, isSaved(entry) {
            Section {
                provenanceLines(entry)
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .lioRow()
            }
        }
    }

    private func provenanceLines(_ entry: TypedMemoryRead) -> some View {
        Group {
            Text(LioMemoryCopy.summary(recordedAt: entry.item.value.recorded_at,
                                       longTerm: entry.item.scope == .longTerm, language: language))
                .accessibilityIdentifier("lio.memory.detail.source")
            Text(LioMemoryCopy.usageNote(language))
                .accessibilityIdentifier("lio.memory.detail.usage-note")
        }
    }

    private func load() async {
        await host.loadDetail(itemID: itemID, surface: surface)
    }

    private func save(_ text: String) async {
        await change(.edit, text: text)
    }

    private func change(_ operation: TypedMemoryOperation, text: String? = nil) async {
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
            let work = try host.prepareManagement(operation, text: text, surface: surface)
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
            switch operation {
            case .pause, .resume: notice = nil
            default: notice = language.text("Saved.", "已保存。")
            }
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
