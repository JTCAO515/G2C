import Foundation
import Observation
import CJMemoryClient
import CJAPI

/// A trusted root supplies the SAME canonical binding callback used by this client.
/// No identity, endpoint, key, storage, field policy or write capability is defaulted here.
@MainActor public struct MemoryContainerBinding {
    fileprivate let id = UUID()
    let client: MemoryClient
    let memory: MemoryBinding
    let shellGeneration: ShellGeneration
    let pageSize: Int
    let options: [MemoryManualOption]
    let synthetic: Bool
    let current: @MainActor () -> MemoryBinding?
    public init(client: MemoryClient, memory: MemoryBinding, shellGeneration: ShellGeneration,
                pageSize: Int, manualOptions: [MemoryManualOption] = [], synthetic: Bool,
                currentBinding: @escaping @MainActor () -> MemoryBinding?) {
        self.client = client; self.memory = memory; self.shellGeneration = shellGeneration
        self.pageSize = pageSize; options = manualOptions; self.synthetic = synthetic; current = currentBinding
    }
}
@MainActor public struct MemoryContainerAction {
    fileprivate let binding: MemoryContainerBinding
    fileprivate let epoch: UUID
}

@MainActor @Observable public final class MemoryContainerHost {
    private let shell: ShellState
    private var binding: MemoryContainerBinding?
    private var epoch = UUID()
    public private(set) var busy = false
    private var groupsValue: MemoryLoad<[Components.Schemas.MemoryGroup]> = .unconfigured
    private var itemsValue: MemoryLoad<[Components.Schemas.MemoryItem]> = .unconfigured
    private var detailValue: MemoryLoad<Components.Schemas.MemoryItem?> = .unconfigured
    private var pendingValue: MemoryLoad<[MemoryPending]> = .unconfigured
    private var saveValue: MemorySaveState = .unconfigured
    private var pages: [MemoryPage] = []
    private var group: Components.Schemas.MemoryGroup?
    private var itemID: String?
    private var queriedID: String?
    public var isConfigured: Bool { current }
    public var isSynthetic: Bool { current && binding?.synthetic == true }
    public var groups: MemoryLoad<[Components.Schemas.MemoryGroup]> { current ? groupsValue : .unconfigured }
    public var items: MemoryLoad<[Components.Schemas.MemoryItem]> { current ? itemsValue : .unconfigured }
    public var detail: MemoryLoad<Components.Schemas.MemoryItem?> { current ? detailValue : .unconfigured }
    public var pending: MemoryLoad<[MemoryPending]> { current ? pendingValue : .unconfigured }
    public var saveState: MemorySaveState { current ? saveValue : .unconfigured }
    public var selectedGroup: Components.Schemas.MemoryGroup? { current ? group : nil }
    public var manualBinding: MemoryBinding? { current ? binding?.memory : nil }
    public var formIdentity: UUID? { current ? binding?.id : nil }
    public var queriedOperationID: String? { current ? queriedID : nil }
    public var manualOptions: [MemoryManualOption] { current ? binding?.options ?? [] : [] }
    public var canSubmitManual: Bool { false } // canonical public client has no production POST capability
    public var hasMore: Bool { current && !busy && pages.last?.next != nil }
    public init(shell: ShellState) {
        self.shell = shell
        shell.memoryContainerHost?.invalidate()
        shell.memoryContainerHost = self
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    private var current: Bool {
        guard let binding, !shell.messageBindingBlocked, binding.shellGeneration == shell.generation else { return false }
        let observed = binding.current()
        return self.binding?.id == binding.id && observed == binding.memory
            && binding.shellGeneration == shell.generation && !shell.messageBindingBlocked
    }
    @discardableResult public func bind(_ value: MemoryContainerBinding) -> Bool {
        guard binding == nil, (1...100).contains(value.pageSize), !shell.messageBindingBlocked,
              value.shellGeneration == shell.generation, value.current() == value.memory,
              binding == nil, !shell.messageBindingBlocked, value.shellGeneration == shell.generation else { return false }
        binding = value; epoch = UUID()
        return true
    }
    public func captureAction() -> MemoryContainerAction? {
        guard current, !busy, let binding else { return nil }
        return MemoryContainerAction(binding: binding, epoch: epoch)
    }
    private func accepts(_ context: MemoryContainerAction) -> Bool {
        current && binding?.id == context.binding.id && epoch == context.epoch && !busy
    }
    private func owns(_ original: MemoryContainerBinding, _ token: UUID) -> Bool {
        current && binding?.id == original.id && epoch == token
    }
    public func invalidate() {
        let previous = binding?.client
        binding = nil; epoch = UUID(); busy = false
        groupsValue = .unconfigured; itemsValue = .unconfigured; detailValue = .unconfigured
        pendingValue = .unconfigured; saveValue = .unconfigured
        pages = []; group = nil; itemID = nil; queriedID = nil
        previous?.invalidate() // canonical method only rotates local generation; no resource callback
    }
    public func suspendForBackground() { invalidate() } // no automatic rebind/GET on foreground
    public func loadGroups(context: MemoryContainerAction?) async {
        guard let context, accepts(context) else { return }
        let token = UUID(); epoch = token; busy = true; groupsValue = .loading
        group = nil; itemID = nil; pages = []; itemsValue = .unconfigured; detailValue = .unconfigured
        do {
            let rows = try await context.binding.client.groups(binding: context.binding.memory)
            guard owns(context.binding,token) else { return }
            groupsValue = .loaded(rows); busy = false
        } catch { if owns(context.binding,token) { groupsValue = .failed; busy = false } }
    }
    @discardableResult public func selectGroup(_ value: Components.Schemas.MemoryGroup, context: MemoryContainerAction?) -> Bool {
        guard let context, accepts(context), case .loaded(let rows) = groupsValue,
              let selected = rows.first(where: { Data($0.subject.utf8) == Data(value.subject.utf8) && $0.status == value.status }) else { return false }
        epoch = UUID(); group = selected; pages = []; itemID = nil; itemsValue = .unconfigured; detailValue = .unconfigured
        return true
    }
    public func loadItems(context: MemoryContainerAction?, more: Bool = false) async {
        // hasMore invokes the trusted binding callback; it may synchronously select a
        // newer item/group. Recheck the original epoch before claiming pagination.
        guard let context, accepts(context), let group, !more || hasMore, accepts(context) else { return }
        let after = more ? pages.last?.next : nil
        if !more { pages = [] }
        let token = UUID(); epoch = token; busy = true; itemsValue = .loading
        itemID = nil; detailValue = .unconfigured
        do {
            let page = try await context.binding.client.list(limit: context.binding.pageSize,after:after,binding:context.binding.memory)
            guard owns(context.binding,token) else { return }
            pages.append(page)
            itemsValue = .loaded(pages.flatMap(\.items).filter {
                Data($0.command.subject.utf8) == Data(group.subject.utf8) && $0.status.rawValue == group.status.rawValue
            })
            busy = false
        } catch { if owns(context.binding,token) { pages = []; itemsValue = .failed; busy = false } }
    }
    @discardableResult public func selectItem(_ value: String, context: MemoryContainerAction?) -> Bool {
        guard let context, accepts(context), case .loaded(let rows) = itemsValue,
              rows.contains(where: { Data($0.command.item_id.utf8) == Data(value.utf8) }) else { return false }
        epoch = UUID(); itemID = value; detailValue = .unconfigured; return true
    }
    public func loadDetail(context: MemoryContainerAction?) async {
        guard let context, accepts(context), let itemID else { return }
        let token = UUID(); epoch = token; busy = true; detailValue = .loading
        do {
            let value = try await context.binding.client.detail(itemID:itemID,binding:context.binding.memory)
            guard owns(context.binding,token) else { return }
            detailValue = .loaded(value); busy = false
        } catch { if owns(context.binding,token) { detailValue = .failed; busy = false } }
    }
    public func loadPending(context: MemoryContainerAction?) {
        guard let context, accepts(context) else { return }
        let token = UUID(); epoch = token; busy = true; pendingValue = .loading
        queriedID = nil; saveValue = .unconfigured
        do {
            let records = try context.binding.client.pending(binding:context.binding.memory)
            guard owns(context.binding,token) else { return }
            pendingValue = .loaded(records); busy = false
        } catch { if owns(context.binding,token) { pendingValue = .failed; busy = false } }
    }
    public func queryOriginal(_ operationID: String, context: MemoryContainerAction?) async {
        guard let context, accepts(context), case .loaded(let records) = pendingValue,
              records.contains(where: { Data($0.operationID.utf8) == Data(operationID.utf8) }) else { return }
        let token = UUID(); epoch = token; busy = true
        queriedID = operationID; saveValue = .unconfigured
        do {
            let result = try await context.binding.client.query(operationID:operationID,binding:context.binding.memory)
            guard owns(context.binding,token) else { return }
            switch result { case .saved: saveValue = .saved; case .candidate: saveValue = .candidate; case .notObserved: saveValue = .notObserved }
            busy = false
        } catch { if owns(context.binding,token) { saveValue = .unknown; busy = false } }
    }
    public func submitManual(_ command: Components.Schemas.MemoryManualSaveCommand, context: MemoryContainerAction?) async throws -> MemorySaveResult {
        // No public producer write capability exists. Do not substitute GET permission or an app Boolean.
        throw MemoryFailure.liveWriteUnavailable
    }
}
