import Foundation
import SwiftUI
import CJAPI

public enum MemoryLanguage: Sendable {
    case english, chinese
    func text(_ english: String, _ chinese: String) -> String { self == .english ? english : chinese }
}
public enum MemoryLoad<Value> {
    case unconfigured, loading, loaded(Value), failed
}
public enum MemorySaveState {
    case unconfigured, ready, saving, saved, candidate, unknown, notObserved, failed
    public func label(_ language: MemoryLanguage) -> String {
        switch self {
        case .unconfigured: language.text("Saving is not configured", "保存尚未配置")
        case .ready: language.text("Review the content and scope before saving", "保存前请核对内容与范围")
        case .saving: language.text("Saving…", "保存中…")
        case .saved: language.text("Saved. Current use depends on its current status.", "已保存；当前是否使用取决于条目当前状态。")
        case .candidate: language.text("Saved as a candidate, not a confirmed fact", "已保存为待确认候选，尚非确认事实")
        case .unknown: language.text("Result unknown. Query the original operation.", "结果未知，请查询原操作。")
        case .notObserved: language.text("Original receipt not observed. Do not resend.", "尚未查到原回执，不可重新发送。")
        case .failed: language.text("Save not confirmed. Check the original operation.", "尚未确认保存，请核查原操作。")
        }
    }
}
func statusLabel(_ status: String, _ language: MemoryLanguage) -> String {
    switch status {
    case "active": language.text("Active", "已启用")
    case "candidate": language.text("Candidate · unconfirmed", "候选 · 待确认")
    case "disabled": language.text("Disabled", "已停用")
    case "withdrawn": language.text("Withdrawn", "已撤回")
    default: language.text("Unknown", "未知")
    }
}
/// Embeddable sections only: account/language/navigation remain owned by CJShell.
public struct MemoryGroupsView: View {
    let state: MemoryLoad<[Components.Schemas.MemoryGroup]>
    let language: MemoryLanguage
    let select: (Components.Schemas.MemoryGroup) -> Void
    public init(state: MemoryLoad<[Components.Schemas.MemoryGroup]>, language: MemoryLanguage,
                select: @escaping (Components.Schemas.MemoryGroup) -> Void) {
        self.state = state; self.language = language; self.select = select
    }
    public var body: some View {
        switch state {
        case .unconfigured: Text(language.text("Memory is not configured", "记忆尚未配置"))
        case .loading: ProgressView(language.text("Loading memories", "正在读取记忆"))
        case .failed: Text(language.text("Could not load groups", "无法读取分组"))
        case .loaded(let groups):
            if groups.isEmpty { Text(language.text("No memory groups", "暂无记忆分组")) }
            ForEach(groups.indices, id: \.self) { index in
                let group = groups[index]
                Button { select(group) } label: {
                    VStack(alignment: .leading) {
                        Text(group.subject)
                        Text("\(statusLabel(group.status.rawValue, language)) · \(group.count)").font(.subheadline)
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityIdentifier("memory.group." + String(index))
            }
        }
    }
}
extension Components.Schemas.MemoryItem {
    // Swift String equality normalizes canonical equivalents; wire IDs do not.
    var memoryRowIdentity: Data { Data(command.item_id.utf8) }
}
public struct MemoryItemsView: View {
    let state: MemoryLoad<[Components.Schemas.MemoryItem]>
    let language: MemoryLanguage
    let select: (String) -> Void
    public init(state: MemoryLoad<[Components.Schemas.MemoryItem]>, language: MemoryLanguage, select: @escaping (String) -> Void) {
        self.state = state; self.language = language; self.select = select
    }
    public var body: some View {
        switch state {
        case .unconfigured: Text(language.text("Memory is not configured", "记忆尚未配置"))
        case .loading: ProgressView()
        case .failed: Text(language.text("Could not load memories", "无法读取记忆"))
        case .loaded(let items):
            if items.isEmpty { Text(language.text("No memories in this page", "本页暂无记忆")) }
            ForEach(items, id: \.memoryRowIdentity) { item in
                Button { select(item.command.item_id) } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        MemoryRowText(text: item.command.text, style: .body)
                        MemoryRowText(text: statusLabel(item.status.rawValue, language), style: .caption)
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .accessibilityLabel(item.command.text + ", " + statusLabel(item.status.rawValue, language))
                    .accessibilityIdentifier("memory.item." + item.command.item_id)
            }
        }
    }
}
public struct MemoryDetailView: View {
    let state: MemoryLoad<Components.Schemas.MemoryItem?>
    let language: MemoryLanguage
    public init(state: MemoryLoad<Components.Schemas.MemoryItem?>, language: MemoryLanguage) { self.state = state; self.language = language }
    public var body: some View {
        switch state {
        case .unconfigured: Text(language.text("Memory is not configured", "记忆尚未配置"))
        case .loading: ProgressView()
        case .failed: Text(language.text("Could not load memory", "无法读取记忆详情"))
        case .loaded(let item):
            if let item {
                VStack(alignment: .leading, spacing: 12) {
                    Text(item.command.text).textSelection(.enabled)
                    Text(statusLabel(item.status.rawValue, language))
                    LabeledContent(language.text("Subject", "对象"), value: item.command.subject)
                    LabeledContent(language.text("Field", "字段"), value: item.command.slot)
                    LabeledContent(language.text("Kind", "类型"), value: item.command.kind.rawValue)
                    LabeledContent { Text(item.command.extent.rawValue).accessibilityIdentifier("memory.detail.scope.value") } label: {
                        MemoryRowText(text: language.text("Scope", "范围"), style: .body)
                    }
                    if case .case1(let context) = item.command.context_id {
                        LabeledContent(language.text("Context", "适用上下文"), value: context)
                    }
                    LabeledContent(language.text("Source", "来源"), value: item.command.source_id)
                    LabeledContent(language.text("Source version", "来源版本"), value: String(item.command.source_version))
                    LabeledContent(language.text("Approximate time", "大致时间"), value: item.command.occurred_at)
                    LabeledContent(language.text("Recorded", "记录时间")) { Text(item.recorded_at, format: .dateTime) }
                    LabeledContent(language.text("Version", "版本"), value: String(item.version))
                }
            } else { Text(language.text("Memory not found", "未找到该记忆")) }
        }
    }
}
public struct MemorySaveStatusView: View {
    let state: MemorySaveState
    let language: MemoryLanguage
    let query: (() -> Void)?
    let statusIdentifier: String
    public init(state: MemorySaveState, language: MemoryLanguage, queryOriginal: (() -> Void)?, statusIdentifier: String = "memory.save.status") {
        self.state = state; self.language = language; query = queryOriginal; self.statusIdentifier = statusIdentifier
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            MemoryRowText(text: state.label(language), style: .body).accessibilityIdentifier(statusIdentifier)
            if case .saving = state { ProgressView() }
            if let query {
                Button(action: query) {
                    MemoryRowText(text: language.text("Query original operation", "查询原操作"), style: .body)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityIdentifier("memory.save.query")
            }
        }
    }
}
/// Host supplies each permitted combination and understandable scope disclosure.
/// These UI options do not grant server policy or network write authorization.
public struct MemoryManualOption: Identifiable {
    public let id: UUID
    public let label: String
    public let disclosure: String
    public let subject: String
    public let slot: String
    public let kind: Components.Schemas.MemoryManualSaveCommand.kindPayload
    public let extent: Components.Schemas.MemoryManualSaveCommand.extentPayload
    public let contextID: String?
    public init(id: UUID, label: String, disclosure: String, subject: String, slot: String,
                kind: Components.Schemas.MemoryManualSaveCommand.kindPayload,
                extent: Components.Schemas.MemoryManualSaveCommand.extentPayload, contextID: String?) {
        self.id = id; self.label = label; self.disclosure = disclosure; self.subject = subject; self.slot = slot
        self.kind = kind; self.extent = extent; self.contextID = contextID
    }
    func command(text: String, occurredAt: String) throws -> Components.Schemas.MemoryManualSaveCommand {
        guard !label.isEmpty, !disclosure.isEmpty, !subject.isEmpty, !slot.isEmpty, memoryText(text), memoryText(occurredAt),
              extent == .current ? contextID?.isEmpty == false : contextID == nil else { throw MemoryFailure.unconfigured }
        return .init(operation_id: UUID().uuidString.lowercased(), item_id: UUID().uuidString.lowercased(),
                     subject: subject, slot: slot, text: text, occurred_at: occurredAt, kind: kind, extent: extent,
                     context_id: contextID.map { .case1($0) } ?? .case2(nil))
    }
}
public struct MemoryManualForm: View {
    let binding: MemoryBinding
    let current: @MainActor () -> MemoryBinding?
    let options: [MemoryManualOption]
    let language: MemoryLanguage
    let submit: (Components.Schemas.MemoryManualSaveCommand) async throws -> MemorySaveResult
    let query: (String) async throws -> MemorySaveResult
    public init(binding: MemoryBinding, currentBinding: @escaping @MainActor () -> MemoryBinding?,
                options: [MemoryManualOption], language: MemoryLanguage,
                submit: @escaping (Components.Schemas.MemoryManualSaveCommand) async throws -> MemorySaveResult,
                queryOriginal: @escaping (String) async throws -> MemorySaveResult) {
        self.binding = binding; current = currentBinding; self.options = options
        self.language = language; self.submit = submit; query = queryOriginal
    }
    public var body: some View {
        MemoryManualFormContent(binding: binding, current: current, options: options, language: language, submit: submit, query: query)
            .id(binding)
    }
}
private struct MemoryManualFormContent: View {
    let binding: MemoryBinding
    let current: @MainActor () -> MemoryBinding?
    let query: (String) async throws -> MemorySaveResult
    let options: [MemoryManualOption]
    let language: MemoryLanguage
    let submit: (Components.Schemas.MemoryManualSaveCommand) async throws -> MemorySaveResult
    private enum Input: Hashable { case memory, time }
    @FocusState private var focusedInput: Input?
    @State private var selection: UUID?
    @State private var text = ""
    @State private var occurredAt = ""
    @State private var state: MemorySaveState = .ready
    @State private var started = false
    @State private var originalID: String?
    @State private var requestGeneration = UUID()
    init(binding: MemoryBinding, current: @escaping @MainActor () -> MemoryBinding?, options: [MemoryManualOption], language: MemoryLanguage,
         submit: @escaping (Components.Schemas.MemoryManualSaveCommand) async throws -> MemorySaveResult,
         query: @escaping (String) async throws -> MemorySaveResult) {
        self.binding = binding; self.current = current; self.options = options; self.language = language; self.submit = submit; self.query = query
        _selection = State(initialValue: options.count == 1 ? options[0].id : nil)
    }
    private func run(_ action: @escaping () async throws -> MemorySaveResult) {
        guard current() == binding else { return }
        let token = UUID(); requestGeneration = token
        Task {
            do {
                guard current() == binding, requestGeneration == token, !Task.isCancelled else { return }
                let result = try await action()
                guard current() == binding, requestGeneration == token, !Task.isCancelled else { return }
                switch result {
                case .saved: state = .saved
                case .candidate: state = .candidate
                case .notObserved: state = .notObserved
                }
            } catch {
                guard current() == binding, requestGeneration == token else { return }
                switch error {
                case MemoryFailure.pendingRequiresQuery:
                    originalID = nil; state = .failed
                case MemoryFailure.rejected: state = .failed
                default: state = .unknown
                }
            }
        }
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if options.isEmpty { Text(MemorySaveState.unconfigured.label(language)) }
            else {
                if started {
                    if let option = options.first(where: { $0.id == selection }) {
                        MemoryRowText(text: option.label, style: .body)
                        MemoryRowText(text: option.disclosure, style: .caption)
                    }
                    MemoryRowText(text: text, style: .body)
                    MemoryRowText(text: occurredAt, style: .body)
                } else {
                Picker(language.text("Save scope", "保存范围"), selection: $selection) {
                    Text(language.text("Choose a scope", "请选择范围")).tag(Optional<UUID>.none)
                    ForEach(options) { option in Text(option.label).tag(Optional(option.id)) }
                }.disabled(started).accessibilityIdentifier("memory.manual.scope")
                if let option = options.first(where: { $0.id == selection }) { Text(option.disclosure).font(.subheadline) }
                TextField(language.text("Memory", "记忆内容"), text: $text, axis: .vertical)
                    .textFieldStyle(.roundedBorder).frame(minHeight: 44)
                    .focused($focusedInput, equals: .memory)
                    .contentShape(Rectangle()).onTapGesture { focusedInput = .memory }
                    .disabled(started).accessibilityIdentifier("memory.manual.text")
                TextField(language.text("Approximate time (required; describe if unknown)", "大致时间（必填，不清楚请明确说明）"), text: $occurredAt)
                    .textFieldStyle(.roundedBorder).frame(minHeight: 44)
                    .focused($focusedInput, equals: .time).submitLabel(.done)
                    .onSubmit { focusedInput = nil }
                    .contentShape(Rectangle()).onTapGesture { focusedInput = .time }
                    .disabled(started).accessibilityIdentifier("memory.manual.time")
                Button(language.text("Save memory", "保存记忆")) {
                    guard !started, let option = options.first(where: { $0.id == selection }) else { return }
                    do {
                        let command = try option.command(text: text, occurredAt: occurredAt)
                        guard current() == binding else { return }
                        focusedInput = nil; started = true; state = .saving; originalID = command.operation_id
                        run { try await submit(command) }
                    } catch { state = .unconfigured }
                }.disabled(started || selection == nil || !memoryText(text) || !memoryText(occurredAt)).accessibilityIdentifier("memory.manual.save")
                }
                MemorySaveStatusView(state: state, language: language, queryOriginal: originalID.map { id in
                    { run { try await query(id) } }
                })
            }
        }
        #if os(iOS)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button(language.text("Done", "完成")) { focusedInput = nil }
                    .accessibilityIdentifier("memory.keyboard.done")
            }
        }
        #endif
    }
}
