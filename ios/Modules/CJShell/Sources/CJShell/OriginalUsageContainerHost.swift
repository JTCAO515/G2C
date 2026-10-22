import Foundation
import Observation
import CJUsageClient
import CJSession
import CJMessageHTTP

/// Actor/session evidence comes from the existing trusted identity root. No actor,
/// receipt, attempt or operation association is derived from MESSAGE text/IDs here.
@MainActor public struct OriginalUsageContainerConfiguration {
    let id = UUID()
    let session: SessionLifecycle
    let operation: SessionOperation
    let actorIdentity: Data
    let revision: UInt64
    let endpoint: MessageEndpoint
    let credentials: OriginalUsageCredentialCallback
    let transport: NoRedirectTransport
    let generation: ShellGeneration
    let isCurrent: @MainActor (OriginalUsageBinding) -> Bool
    public init(session: SessionLifecycle, operation: SessionOperation, actorIdentity: Data, revision: UInt64,
                endpoint: MessageEndpoint, credentials: @escaping OriginalUsageCredentialCallback,
                transport: NoRedirectTransport, generation: ShellGeneration,
                isCurrent: @escaping @MainActor (OriginalUsageBinding) -> Bool) throws {
        guard !actorIdentity.isEmpty else { throw UsageFailure.unavailable }
        self.session = session; self.operation = operation; self.actorIdentity = actorIdentity; self.revision = revision
        self.endpoint = endpoint; self.credentials = credentials; self.transport = transport
        self.generation = generation; self.isCurrent = isCurrent
    }
}
typealias OriginalUsageModelFactory = @MainActor (OriginalUsageContainerConfiguration, AcceptedMessageUsageInput,
    @escaping @MainActor () -> OriginalUsageBinding?) -> OriginalUsageViewModel

@MainActor @Observable public final class OriginalUsageContainerHost {
    private let shell: ShellState
    private var configuration: OriginalUsageContainerConfiguration?
    private var origin: AcceptedMessageUsageInput?
    private var binding: OriginalUsageBinding?
    private var model: OriginalUsageViewModel?
    private var resolved: ResolvedUsageSource?
    private var request: UUID?
    private var selection = UUID()
    private var foreground = false
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private let makeModel: OriginalUsageModelFactory
    public var selectionGeneration: UUID? { binding?.selectionGeneration }
    public var canResolve: Bool {
        guard foreground, let cfg = configuration else { return false }
        return shell.generation == cfg.generation && !shell.messageBindingBlocked && cfg.session.isCurrent(cfg.operation)
    }
    public var canReadStatus: Bool { canResolve && resolved != nil && origin?.isStillOwned() == true }
    public var state: OriginalUsageState {
        guard canResolve, let cfg = configuration, let originalModel = model, let original = binding,
              let originalOrigin = origin else { return .unavailable }
        let token = selection
        let observed = originalModel.state
        guard matches(cfg, originalModel, original, originalOrigin, token), originalOrigin.isStillOwned() else { return .unavailable }
        return observed
    }
    public convenience init(shell: ShellState) {
        self.init(shell: shell, makeModel: { cfg, input, current in
            OriginalUsageViewModel(session: cfg.session, recovery: input.recovery, scope: input.scope, endpoint: cfg.endpoint,
                credentials: cfg.credentials, currentBinding: current, liveReadTransport: cfg.transport)
        })
    }
    init(shell: ShellState, makeModel: @escaping OriginalUsageModelFactory) {
        self.shell = shell; self.makeModel = makeModel
        shell.originalUsageContainerHost?.invalidate(); shell.originalUsageContainerHost = self
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    @discardableResult public func configure(_ cfg: OriginalUsageContainerConfiguration) -> Bool {
        guard configuration == nil, shell.generation == cfg.generation, !shell.messageBindingBlocked,
              cfg.session.isCurrent(cfg.operation) else { return false }
        configuration = cfg; return true
    }
    private func matches(_ cfg: OriginalUsageContainerConfiguration, _ originalModel: OriginalUsageViewModel,
                         _ original: OriginalUsageBinding, _ originalOrigin: AcceptedMessageUsageInput, _ token: UUID) -> Bool {
        foreground && configuration?.id == cfg.id && model === originalModel && binding == original && origin === originalOrigin
            && selection == token && shell.generation == cfg.generation && !shell.messageBindingBlocked
            && cfg.session.isCurrent(original.sessionOperation)
    }
    private func currentBinding(configurationID: UUID, selection token: UUID) -> OriginalUsageBinding? {
        guard let cfg = configuration, cfg.id == configurationID, let original = binding,
              let originalModel = model, let originalOrigin = origin,
              matches(cfg, originalModel, original, originalOrigin, token), cfg.isCurrent(original) else { return nil }
        guard originalOrigin.isCurrent(), cfg.isCurrent(original) else { return nil }
        guard matches(cfg, originalModel, original, originalOrigin, token), originalOrigin.isStillOwned() else { return nil }
        return original // no external callback after final canonical MESSAGE/session/selection fence
    }
    private func detachSelection(reserving nextSelection: UUID = UUID(), request nextRequest: UUID? = nil) -> Task<Void, Never>? {
        let oldModel = model, oldTask = task
        model = nil; origin = nil; binding = nil; resolved = nil; request = nextRequest; task = nil; selection = nextSelection
        oldModel?.invalidate()
        return oldTask
    }
    /// Called inside synchronous MESSAGE selection mutation. Invalidation is immediate;
    /// cancellation of the captured task is deferred so cancellation callbacks cannot
    /// overwrite that MESSAGE selection or a newer source in the same call stack.
    public func retireSelection() {
        let oldTask = detachSelection()
        if let oldTask { Task { oldTask.cancel() } }
    }
    public func setForeground(_ active: Bool) { foreground = active; if !active { retireSelection() } }
    public func invalidate() {
        configuration = nil
        retireSelection()
    }
    private func ownsRequest(_ cfg: OriginalUsageContainerConfiguration, _ originalModel: OriginalUsageViewModel,
                             _ original: OriginalUsageBinding, _ input: AcceptedMessageUsageInput, _ token: UUID,
                             request operation: UUID) -> Bool {
        request == operation && matches(cfg, originalModel, original, input, token)
    }
    private func start(_ prepared: PreparedOriginalUsageRead, cfg: OriginalUsageContainerConfiguration,
                       model originalModel: OriginalUsageViewModel, binding original: OriginalUsageBinding,
                       input: AcceptedMessageUsageInput, selection token: UUID, request operation: UUID,
                       association: Bool) {
        task = Task { [weak self] in
            await originalModel.read(prepared)
            guard let self, self.ownsRequest(cfg, originalModel, original, input, token, request: operation) else { return }
            let observed = originalModel.state
            guard self.ownsRequest(cfg, originalModel, original, input, token, request: operation) else { return }
            if association, input.isStillOwned(), case .sourceReady(let source) = observed { self.resolved = source }
            self.task = nil; self.request = nil
        }
    }
    /// Explicit action 1. Uses only the current canonical accepted MESSAGE record.
    public func resolveCurrentMessage(from messages: AssistantMessageHost) {
        guard canResolve, messages.belongs(to: shell), let cfg = configuration else { return }
        let token = UUID(), operation = UUID()
        let oldTask = detachSelection(reserving: token, request: operation); defer { oldTask?.cancel() }
        guard request == operation, selection == token, configuration?.id == cfg.id, canResolve else { return }
        guard let input = messages.captureAcceptedUsageInput(), request == operation, selection == token,
              configuration?.id == cfg.id, canResolve else { return }
        let candidate = makeModel(cfg, input, { [weak self] in self?.currentBinding(configurationID: cfg.id, selection: token) })
        do {
            let accepted = try candidate.captureAcceptedMessage(input.record, lease: input.lease)
            guard request == operation, selection == token, configuration?.id == cfg.id, canResolve,
                  input.isCurrent(), request == operation, selection == token, input.isStillOwned() else { candidate.invalidate(); return }
            let original = OriginalUsageBinding(acceptedMessage: accepted, sessionOperation: cfg.operation,
                actorIdentity: cfg.actorIdentity, selectionGeneration: token, revision: cfg.revision)
            model = candidate; origin = input; binding = original
            let prepared = try candidate.prepareAssociation(original)
            guard ownsRequest(cfg, candidate, original, input, token, request: operation) else { return }
            start(prepared, cfg: cfg, model: candidate, binding: original, input: input, selection: token, request: operation, association: true)
        } catch {
            // Only captured old candidate is touched. A nested resolve may already own a new model.
            if model !== candidate { candidate.invalidate() }
            if request == operation, selection == token { request = nil }
        }
    }
    /// Explicit action 2. The closed association source cannot be replaced by legacy UsageSource.
    public func readResolvedStatus() {
        guard canReadStatus, let cfg = configuration, let originalModel = model, let original = binding,
              let input = origin, let source = resolved else { return }
        let token = selection, operation = UUID(), oldTask = task
        task = nil; request = operation; defer { oldTask?.cancel() }
        do {
            let prepared = try originalModel.prepareStatus(source)
            guard ownsRequest(cfg, originalModel, original, input, token, request: operation) else { return }
            start(prepared, cfg: cfg, model: originalModel, binding: original, input: input, selection: token, request: operation, association: false)
        } catch {
            if ownsRequest(cfg, originalModel, original, input, token, request: operation) { request = nil }
        }
    }
}
