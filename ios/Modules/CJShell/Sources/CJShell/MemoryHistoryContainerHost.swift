import Foundation
import Observation
import CJMemoryClient
import CJSession

@MainActor public struct MemoryHistoryContainerBinding {
    fileprivate let id = UUID()
    let client: MemoryHistoryClient
    let memory: MemoryBinding
    let generation: ShellGeneration
    let messages: AssistantMessageHost
    let session: SessionLifecycle
    let operation: SessionOperation
    let current: @MainActor () -> MemoryBinding?
    public init(client: MemoryHistoryClient, memory: MemoryBinding, shellGeneration: ShellGeneration,
                messages: AssistantMessageHost, session: SessionLifecycle, sessionOperation: SessionOperation,
                currentBinding: @escaping @MainActor () -> MemoryBinding?) {
        self.client = client; self.memory = memory; generation = shellGeneration; self.messages = messages
        self.session = session; operation = sessionOperation; current = currentBinding
    }
}

/// A current conversation comes from the canonical MESSAGE host, never ShellContext or a UI text ID.
@MainActor @Observable public final class MemoryHistoryContainerHost {
    private struct Core {
        let binding: MemoryHistoryContainerBinding
        let model: MemoryHistoryPresentation
    }
    private let shell: ShellState
    @ObservationIgnored private var core: Core?
    @ObservationIgnored private var notifying = false
    private var signal = UUID()
    public init(shell: ShellState) {
        self.shell = shell
        let original = shell.memoryHistoryContainerHost, generation = shell.generation
        original?.invalidate()
        if shell.memoryHistoryContainerHost === original, shell.generation == generation {
            shell.memoryHistoryContainerHost = self
        }
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    private func notify() {
        guard !notifying else { return }
        notifying = true; defer { notifying = false }
        signal = UUID()
    }
    private func owns(_ binding: MemoryHistoryContainerBinding) -> Bool {
        shell.memoryHistoryContainerHost === self && core?.binding.id == binding.id
            && !shell.messageBindingBlocked && shell.generation == binding.generation
            && binding.session.isCurrent(binding.operation)
    }
    private func validCore() -> Core? {
        guard let captured = core, owns(captured.binding) else { return nil }
        let observed = captured.binding.current()
        guard observed == captured.binding.memory, owns(captured.binding) else { return nil }
        return captured
    }
    public var selectedConversation: String? {
        _ = signal
        guard let captured = validCore() else { return nil }
        let selected = captured.binding.messages.selectedConversation
        return owns(captured.binding) ? selected : nil
    }
    public var presentation: MemoryHistoryPresentation? {
        _ = signal
        guard let captured = validCore() else { return nil }
        // This MESSAGE getter checks its own lease first, then reads the current
        // selection. Finish without another caller callback after that source read.
        let selected = captured.binding.messages.selectedConversation
        guard owns(captured.binding), captured.model.conversationID.map({Data($0.utf8)}) == selected.map({Data($0.utf8)}) else { return nil }
        return captured.model
    }
    @discardableResult public func bind(_ value: MemoryHistoryContainerBinding) -> Bool {
        guard core == nil, shell.memoryHistoryContainerHost === self, value.messages.belongs(to: shell),
              shell.generation == value.generation, !shell.messageBindingBlocked,
              value.session.isCurrent(value.operation), value.current() == value.memory,
              core == nil, shell.memoryHistoryContainerHost === self, shell.generation == value.generation,
              !shell.messageBindingBlocked, value.session.isCurrent(value.operation) else { return false }
        let model = MemoryHistoryPresentation(client: value.client)
        model.replace(binding: value.memory, conversationID: nil)
        core = Core(binding: value, model: model)
        notify(); return true
    }
    public func synchronizeConversation() {
        guard let captured = validCore() else { return }
        let selected = captured.binding.messages.selectedConversation
        guard owns(captured.binding) else { return }
        if captured.model.conversationID.map({Data($0.utf8)}) != selected.map({Data($0.utf8)}) {
            captured.model.replace(binding: captured.binding.memory, conversationID: selected)
        }
    }
    public func retirePresentation() {
        guard let captured = core else { return }
        captured.model.replace(binding: captured.binding.memory, conversationID: nil)
    }
    public func invalidate() {
        let original = core?.model; core = nil
        original?.replace(binding: nil, conversationID: nil)
        notify() // no old-client or source mutation after notifying observers
    }
}
