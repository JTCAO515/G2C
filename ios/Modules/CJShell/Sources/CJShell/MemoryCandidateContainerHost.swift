import Foundation
import Observation
import CJMemoryClient
import CJSession

public struct MemoryCandidateConversationReadContext: Sendable {
    fileprivate let core: UUID
    fileprivate let conversation: String
}

@MainActor public struct MemoryCandidateContainerBinding {
    fileprivate let id = UUID()
    let client: MemoryCandidateClient
    let memory: MemoryBinding
    let generation: ShellGeneration
    let messages: AssistantMessageHost
    let session: SessionLifecycle
    let operation: SessionOperation
    let current: @MainActor () -> MemoryBinding?
    public init(client: MemoryCandidateClient, memory: MemoryBinding, shellGeneration: ShellGeneration,
                messages: AssistantMessageHost, session: SessionLifecycle, sessionOperation: SessionOperation,
                currentBinding: @escaping @MainActor () -> MemoryBinding?) {
        self.client = client; self.memory = memory; generation = shellGeneration; self.messages = messages
        self.session = session; operation = sessionOperation; current = currentBinding
    }
}

/// Root owns this host and retires it with its business writers. Reading a
/// presentation additionally requires the actual Shell, SDK and MESSAGE leases.
@MainActor @Observable public final class MemoryCandidateContainerHost {
    private struct Core {
        let id = UUID()
        let binding: MemoryCandidateContainerBinding
        let model: MemoryCandidatePresentation
    }
    private let shell: ShellState
    @ObservationIgnored private var core: Core?
    @ObservationIgnored private var notifying = false
    private var signal = UUID()
    public init(shell: ShellState) {
        self.shell = shell
        let original = shell.memoryCandidateContainerHost, generation = shell.generation
        original?.invalidate()
        if shell.memoryCandidateContainerHost === original, shell.generation == generation {
            shell.memoryCandidateContainerHost = self
        }
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    private func notify() {
        guard !notifying else { return }
        notifying = true; defer { notifying = false }; signal = UUID()
    }
    private func owns(_ binding: MemoryCandidateContainerBinding) -> Bool {
        shell.memoryCandidateContainerHost === self && core?.binding.id == binding.id && !shell.messageBindingBlocked
            && shell.generation == binding.generation && binding.session.isCurrent(binding.operation)
    }
    private func owns(_ captured: Core) -> Bool { core?.id == captured.id && owns(captured.binding) }
    private func validCore() -> Core? {
        guard let captured = core, owns(captured) else { return nil }
        let observed = captured.binding.current()
        guard observed == captured.binding.memory, owns(captured) else { return nil }
        return captured
    }
    public var selectedConversation: String? {
        _ = signal
        guard let captured = validCore() else { return nil }
        let selected = captured.binding.messages.selectedConversation
        return owns(captured) ? selected : nil
    }
    public var presentation: MemoryCandidatePresentation? {
        _ = signal
        guard let captured = validCore() else { return nil }
        let selected = captured.binding.messages.selectedConversation
        guard owns(captured), captured.model.conversationID.map({ Data($0.utf8) }) == selected.map({ Data($0.utf8) }) else { return nil }
        return captured.model
    }
    @discardableResult public func bind(_ value: MemoryCandidateContainerBinding) -> Bool {
        guard core == nil, shell.memoryCandidateContainerHost === self, value.messages.belongs(to: shell), shell.generation == value.generation,
              !shell.messageBindingBlocked, value.session.isCurrent(value.operation), value.current() == value.memory,
              core == nil, shell.memoryCandidateContainerHost === self, shell.generation == value.generation, !shell.messageBindingBlocked,
              value.session.isCurrent(value.operation) else { return false }
        let model = MemoryCandidatePresentation(client: value.client)
        model.replace(binding: value.memory, conversationID: nil)
        core = Core(binding: value, model: model); notify(); return true
    }
    public func synchronizeConversation() {
        guard let captured = validCore() else { return }
        let selected = captured.binding.messages.selectedConversation
        guard owns(captured) else { return }
        if captured.model.conversationID.map({ Data($0.utf8) }) != selected.map({ Data($0.utf8) }) {
            captured.model.replace(binding: captured.binding.memory, conversationID: selected)
        }
    }
    /// The visible conversation is captured before creating a Task. A delayed
    /// button or lifecycle callback cannot silently read a replacement source.
    public func captureConversationRead() -> MemoryCandidateConversationReadContext? {
        guard let captured = validCore(), let conversation = captured.binding.messages.selectedConversation,
              owns(captured) else { return nil }
        return .init(core: captured.id, conversation: conversation)
    }
    public func isCurrent(_ context: MemoryCandidateConversationReadContext?) -> Bool {
        guard let context, let captured = validCore(), captured.id == context.core else { return false }
        let selected = captured.binding.messages.selectedConversation
        return selected.map({ Data($0.utf8) }) == Data(context.conversation.utf8) && owns(captured)
    }
    public func loadSuggestions(context: MemoryCandidateConversationReadContext?, onlyIfUnread: Bool = false) async {
        guard let context, let captured = validCore(), captured.id == context.core, isCurrent(context) else { return }
        synchronizeConversation()
        guard owns(captured), let model = presentation,
              model === captured.model, model.conversationID.map({ Data($0.utf8) }) == Data(context.conversation.utf8),
              !onlyIfUnread || model.state == .unread,
              let work = model.prepareDiscovery(), isCurrent(context) else { return }
        await model.perform(work)
    }
    public func retirePresentation() {
        guard let captured = core else { return }
        captured.model.replace(binding: captured.binding.memory, conversationID: nil)
    }
    public func invalidate() {
        let original = core?.model; core = nil
        original?.replace(binding: nil, conversationID: nil)
        notify()
    }
}
