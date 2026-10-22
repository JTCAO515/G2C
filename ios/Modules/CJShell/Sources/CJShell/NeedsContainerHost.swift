import Foundation
import Observation
import CJNeedsClient
import CJSession

/// One existing journey selection, supplied by the trusted root; never authentication or extraction.
@MainActor public struct NeedsContainerBinding {
    fileprivate let id = UUID()
    let client: NeedsClient
    let needs: NeedsBinding
    let selectedNeedsID: String
    let shellGeneration: ShellGeneration
    let session: SessionLifecycle
    let operation: SessionOperation
    let synthetic: Bool
    let current: @MainActor () -> NeedsBinding?
    public init(client: NeedsClient, needs: NeedsBinding, selectedNeedsID: String, shellGeneration: ShellGeneration,
                session: SessionLifecycle, sessionOperation: SessionOperation, synthetic: Bool,
                currentBinding: @escaping @MainActor () -> NeedsBinding?) {
        self.client = client; self.needs = needs; self.selectedNeedsID = selectedNeedsID
        self.shellGeneration = shellGeneration; self.session = session; operation = sessionOperation
        self.synthetic = synthetic; current = currentBinding
    }
}
@MainActor public struct NeedsContainerAction {
    fileprivate let binding: NeedsContainerBinding
    fileprivate let presentation: NeedsPresentation
    fileprivate let epoch: UUID
}
@MainActor public struct NeedsContainerWork {
    fileprivate let context: NeedsContainerAction
    fileprivate let work: NeedsPresentationWork
    fileprivate let token: UUID
}

@MainActor @Observable public final class NeedsContainerHost {
    private let shell: ShellState
    private var binding: NeedsContainerBinding?
    private var value: NeedsPresentation?
    private var epoch = UUID()
    @ObservationIgnored private var draftEditRevision = UUID()
    private var executing = false
    public private(set) var busy = false
    public var presentation: NeedsPresentation? { current ? value : nil }
    public var viewIdentity: UUID? { current ? binding?.id : nil }
    public var isConfigured: Bool { current }
    public var isSynthetic: Bool { current && binding?.synthetic == true }
    public var canSave: Bool { false }
    public var pendingActions: [NeedsPending] {
        guard current, let binding, let value, value.pendingState == .loaded else { return [] }
        return value.pendingActions.filter { $0.needsID == binding.selectedNeedsID }
    }
    public init(shell: ShellState) {
        self.shell = shell
        shell.needsContainerHost?.invalidate()
        shell.needsContainerHost = self
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    private var current: Bool {
        guard let binding, !shell.messageBindingBlocked, shell.generation == binding.shellGeneration,
              binding.session.isCurrent(binding.operation) else { return false }
        let observed = binding.current()
        return self.binding?.id == binding.id && observed == binding.needs
            && shell.generation == binding.shellGeneration && !shell.messageBindingBlocked
            && binding.session.isCurrent(binding.operation)
    }
    @discardableResult public func bind(_ binding: NeedsContainerBinding) -> Bool {
        guard self.binding == nil, !binding.selectedNeedsID.isEmpty,
              shell.generation == binding.shellGeneration, !shell.messageBindingBlocked,
              binding.session.isCurrent(binding.operation), binding.current() == binding.needs,
              self.binding == nil, shell.generation == binding.shellGeneration,
              !shell.messageBindingBlocked, binding.session.isCurrent(binding.operation) else { return false }
        let presentation = NeedsPresentation(client: binding.client)
        presentation.replace(binding: binding.needs)
        self.binding = binding; value = presentation; epoch = UUID(); draftEditRevision = UUID()
        return true
    }
    public func captureAction() -> NeedsContainerAction? {
        guard current, !busy, let binding, let value else { return nil }
        return NeedsContainerAction(binding: binding, presentation: value, epoch: epoch)
    }
    private func accepts(_ action: NeedsContainerAction) -> Bool {
        current && !busy && binding?.id == action.binding.id && value === action.presentation && epoch == action.epoch
    }
    private func owns(_ action: NeedsContainerAction, _ token: UUID) -> Bool {
        current && binding?.id == action.binding.id && value === action.presentation && epoch == token
    }
    public func invalidate() {
        let original = value
        binding = nil; value = nil; epoch = UUID(); draftEditRevision = UUID(); busy = false; executing = false
        original?.replace(binding: nil) // canonical invalidation; no callback or later host mutation
    }
    public func suspendForBackground() { invalidate() }
    private func reserve(_ work: NeedsPresentationWork?, context: NeedsContainerAction) -> NeedsContainerWork? {
        guard let work else { return nil }
        let token = UUID(); epoch = token; busy = true; executing = false
        return NeedsContainerWork(context: context, work: work, token: token)
    }
    public func prepareDetail(context: NeedsContainerAction?) -> NeedsContainerWork? {
        guard let context, accepts(context) else { return nil }
        return reserve(context.presentation.prepareDetail(id: context.binding.selectedNeedsID), context: context)
    }
    public func prepareRevision(_ version: Int, context: NeedsContainerAction?) -> NeedsContainerWork? {
        guard let context, accepts(context), version > 0 else { return nil }
        return reserve(context.presentation.prepareRevision(id: context.binding.selectedNeedsID, version: version), context: context)
    }
    public func prepareQuery(_ actionID: String, context: NeedsContainerAction?) -> NeedsContainerWork? {
        guard let context, accepts(context), context.presentation.pendingState == .loaded,
              context.presentation.pendingActions.contains(where: {
                  $0.actionID == actionID && $0.needsID == context.binding.selectedNeedsID
              }) else { return nil }
        return reserve(context.presentation.prepareQuery(actionID: actionID), context: context)
    }
    public func perform(_ prepared: NeedsContainerWork?) async {
        guard let prepared, owns(prepared.context, prepared.token), busy, !executing else { return }
        executing = true
        await prepared.context.presentation.perform(prepared.work)
        guard owns(prepared.context, prepared.token) else { return }
        busy = false; executing = false
    }
    public func loadPending(context: NeedsContainerAction?) {
        guard let context, accepts(context) else { return }
        let token = UUID(); epoch = token; busy = true
        context.presentation.loadPending()
        guard owns(context, token) else { return }; busy = false
    }
    @discardableResult public func updateDraft(_ draft: NeedsDraft, context: NeedsContainerAction?) -> Bool {
        // accepts invokes the trusted binding callback, which may accept a newer edit
        // of this same editor. Capture local ownership before entering that callback.
        let originalEditRevision = draftEditRevision
        guard let context, accepts(context), draftEditRevision == originalEditRevision,
              let original = context.presentation.draft,
              original.editorID == draft.editorID, original.needsID == context.binding.selectedNeedsID,
              draft.needsID == original.needsID, draft.expectedVersion == original.expectedVersion else { return false }
        draftEditRevision = UUID() // local edit order only, never the server expectedVersion
        context.presentation.draft = draft
        return true // local editing only; no action ID, command, persistence or POST is created
    }
}
