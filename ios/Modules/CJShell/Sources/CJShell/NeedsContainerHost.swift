import Foundation
import Observation
import CJNeedsClient
import CJSession
import CJFeasibilityClient
import CryptoKit

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
    @ObservationIgnored private var epoch = UUID()
    @ObservationIgnored private var draftEditRevision = UUID()
    @ObservationIgnored private var executing = false
    @ObservationIgnored private var operationTask: Task<Void, Never>?
    @ObservationIgnored private var evaluation: FeasibilityHostPresentation?
    private var evaluationEpoch = UUID()
    public private(set) var busy = false
    public var presentation: NeedsPresentation? { current ? value : nil }
    public var viewIdentity: UUID? { current ? binding?.id : nil }
    public var isConfigured: Bool { current }
    public var isSynthetic: Bool { current && binding?.synthetic == true }
    public var canSave: Bool { current && !busy && value?.canSave == true }
    public enum ManualIssue: Sendable { case reconcileOriginals, storageUnavailable }
    public private(set) var manualIssue: ManualIssue?
    public var originalActions: [NeedsPending] {
        guard current, let value, value.pendingState == .loaded else { return [] }
        return value.canSave ? value.pendingActions : pendingActions
    }
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
        operationTask?.cancel(); operationTask = nil
        invalidateFeasibility()
        let original = value
        binding = nil; value = nil; epoch = UUID(); draftEditRevision = UUID(); busy = false; executing = false; manualIssue = nil
        original?.replace(binding: nil) // canonical invalidation; no callback or later host mutation
    }
    public func suspendForBackground() { invalidate() }
    public func leaveContainer(id: UUID) {
        guard binding?.id == id else { return }
        invalidateFeasibility()
    }
    private func reserve(_ work: NeedsPresentationWork?, context: NeedsContainerAction, editRevision: UUID? = nil) -> NeedsContainerWork? {
        guard let work, accepts(context), editRevision == nil || editRevision == draftEditRevision else { return nil }
        invalidateFeasibility()
        let token = UUID(); epoch = token; executing = false; busy = true
        guard owns(context, token), busy else { return nil }
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
                  $0.actionID == actionID && (context.presentation.canSave || $0.needsID == context.binding.selectedNeedsID)
              }) else { return nil }
        return reserve(context.presentation.prepareQuery(actionID: actionID, preservingEditor: context.presentation.canSave), context: context)
    }
    public func perform(_ prepared: NeedsContainerWork?) async {
        guard let prepared, owns(prepared.context, prepared.token), busy, !executing else { return }
        executing = true
        let model = prepared.context.presentation, work = prepared.work
        let task = Task { await model.perform(work) }
        operationTask = task
        await withTaskCancellationHandler(operation: { await task.value }, onCancel: { task.cancel() })
        guard owns(prepared.context, prepared.token) else { return }
        operationTask = nil; executing = false
        busy = false // Last observed host write; old cleanup cannot retire newer work.
    }
    public func loadPending(context: NeedsContainerAction?) {
        guard let context, accepts(context) else { return }
        let token = UUID(); epoch = token; busy = true
        context.presentation.loadPending()
        guard owns(context, token) else { return }; busy = false
    }
    @discardableResult public func beginNew(context: NeedsContainerAction?) -> Bool {
        guard let context, accepts(context), context.presentation.canSave, context.presentation.snapshot == nil else { return false }
        invalidateFeasibility(); draftEditRevision = UUID()
        context.presentation.beginNew(id: context.binding.selectedNeedsID)
        return true
    }
    @discardableResult public func beginCorrection(context: NeedsContainerAction?) -> Bool {
        guard let context, accepts(context), context.presentation.canSave,
              let snapshot = context.presentation.snapshot, snapshot.needs_id == context.binding.selectedNeedsID else { return false }
        invalidateFeasibility(); draftEditRevision = UUID()
        return context.presentation.beginCorrectionFromSnapshot()
    }
    @discardableResult public func applyPreview(from runs: RunContainerHost, expectedSource: UUID,
                                                context: NeedsContainerAction?) -> Bool {
        let revision = draftEditRevision
        guard let context, accepts(context), runs.belongs(to: shell),
              runs.originalPresentationID == expectedSource,
              case .loaded(let preview) = preview(from: runs),
              var draft = context.presentation.draft else { return false }
        draft.applyUnconfirmedPreview(preview) // Pure local copy; original expected_version stays fixed.
        guard runs.originalPresentationID == expectedSource, accepts(context), runs.stillOwnsOriginal(expectedSource), draftEditRevision == revision,
              context.presentation.draft?.editorID == draft.editorID else { return false }
        draftEditRevision = UUID()
        context.presentation.draft = draft
        return true
    }
    public func preview(from runs: RunContainerHost) -> NeedsPreviewRunProjection {
        guard current, let original = binding, runs.belongs(to: shell),
              runs.currentOriginalUses(session: original.session, operation: original.operation, generation: original.shellGeneration),
              let source = runs.originalPresentationID else { return .unavailable }
        let result = runs.needsPreviewProjection
        guard current, binding?.id == original.id,
              runs.currentOriginalUses(session: original.session, operation: original.operation, generation: original.shellGeneration),
              binding?.id == original.id, runs.stillOwnsOriginal(source) else { return .unavailable }
        return result
    }
    public func prepareSave(context: NeedsContainerAction?) -> NeedsContainerWork? {
        let revision = draftEditRevision
        guard let context, accepts(context), context.presentation.canSave, context.presentation.draft != nil else { return nil }
        do {
            let blocked = try context.binding.client.requiresOriginalReconciliation(binding: context.binding.needs)
            guard accepts(context), revision == draftEditRevision else { return nil }
            if blocked { manualIssue = .reconcileOriginals; return nil }
            manualIssue = nil
            guard accepts(context), revision == draftEditRevision else { return nil }
            // The one new ID is created only after the complete original journal
            // permits a distinct user action. No ID is minted to bypass unknown.
            let work = context.presentation.prepareSave(actionID: UUID().uuidString)
            return reserve(work, context: context, editRevision: revision)
        } catch {
            guard accepts(context), revision == draftEditRevision else { return nil }
            manualIssue = .storageUnavailable
            return nil
        }
    }
    public func prepareReplay(_ actionID: String, context: NeedsContainerAction?) -> NeedsContainerWork? {
        guard let context, accepts(context), context.presentation.canSave,
              context.presentation.pendingActions.contains(where: { $0.actionID == actionID }) else { return nil }
        return reserve(context.presentation.prepareReplay(actionID: actionID, preservingEditor: true), context: context)
    }
    public struct Cancellation {
        fileprivate let binding: UUID
        fileprivate let token: UUID
    }
    public func captureCancellation() -> Cancellation? {
        guard current, busy, operationTask != nil, let binding else { return nil }
        return Cancellation(binding: binding.id, token: epoch)
    }
    public func cancel(_ work: Cancellation?) {
        guard let work, current, work.binding == binding?.id, work.token == epoch, busy else { return }
        operationTask?.cancel() // Stop waiting; a possible POST remains original-only unknown.
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
    /// A frozen accepted current snapshot only; drafts, historical revisions and receipts are not sources.
    public var feasibilityPresentation: FeasibilityHostPresentation? {
        access(keyPath: \.feasibilityPresentation)
        guard let original = evaluation else { return nil }
        return currentFeasibilityBinding(for: original.id) == original.binding ? original : nil
    }
    public func openFeasibility(context: NeedsContainerAction?) -> Bool {
        let attempt = UUID(); evaluationEpoch = attempt
        guard let context, accepts(context), evaluationEpoch == attempt,
              context.presentation.state == .loaded,
              let snapshot = context.presentation.snapshot,
              snapshot.needs_id == context.binding.selectedNeedsID, snapshot.version > 0,
              let bytes = Data(base64Encoded: snapshot.content_utf8_base64), !bytes.isEmpty else { return false }
        let accepted = FeasibilityBinding(environment: context.binding.needs.environment,
            account: context.binding.needs.account, generation: context.binding.needs.generation,
            selection: context.binding.needs.selection, sessionOperation: context.binding.operation,
            needsID: snapshot.needs_id, acceptedRevision: snapshot.version,
            acceptedContentSHA256: SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined())
        let id = UUID()
        let model = FeasibilityModel(session: context.binding.session, currentBinding: { [weak self] in
            self?.currentFeasibilityBinding(for: id)
        })
        // Snapshot bytes are retained exactly; never serialize fields to establish identity.
        let next = FeasibilityHostPresentation(id: id, model: model, binding: accepted,
            snapshot: snapshot, sourceEpoch: epoch, containerID: context.binding.id)
        guard evaluationEpoch == attempt, accepts(context), evaluationEpoch == attempt,
              context.presentation.snapshot == snapshot, context.presentation.state == .loaded else { return false }
        let old = evaluation
        // Observation sends willSet before executing this closure. Recheck ownership
        // INSIDE the actual mutation boundary after synchronous observers have run.
        withMutation(keyPath: \.feasibilityPresentation) {
            guard evaluationEpoch == attempt else { return }
            evaluation = next
        }
        old?.model.invalidate()
        return true
    }
    private func currentFeasibilityBinding(for id: UUID) -> FeasibilityBinding? {
        guard let original = evaluation, original.id == id, original.sourceEpoch == epoch,
              original.containerID == binding?.id, current,
              evaluation === original, original.sourceEpoch == epoch,
              value?.state == .loaded, value?.snapshot == original.snapshot,
              !busy else { return nil }
        return original.binding
    }
    public func dismissFeasibility(id: UUID) {
        // Old A's disappear/cancel callback must never clear a newly opened B (including ABA).
        guard evaluation?.id == id else { return }
        invalidateFeasibility()
    }
    private func invalidateFeasibility() {
        let attempt = UUID(); evaluationEpoch = attempt
        let old = evaluation
        withMutation(keyPath: \.feasibilityPresentation) {
            guard evaluationEpoch == attempt else { return }
            evaluation = nil
        }
        old?.model.invalidate()
    }
}
