import Foundation
import Observation
import CJUsageClient
import CJSession
import CJMessageHTTP

/// Existing trusted read resources and source admission. No attempt, actor or URL is defaulted.
@MainActor public struct UsageContainerConfiguration {
    let id = UUID()
    let session: SessionLifecycle
    let endpoint: MessageEndpoint
    let credentials: UsageCredentialCallback
    let transport: NoRedirectTransport
    let generation: ShellGeneration
    let isCurrent: @MainActor (UsageBinding) -> Bool
    public init(session: SessionLifecycle, endpoint: MessageEndpoint, credentials: @escaping UsageCredentialCallback,
                transport: NoRedirectTransport, generation: ShellGeneration,
                isCurrent: @escaping @MainActor (UsageBinding) -> Bool) {
        self.session = session; self.endpoint = endpoint; self.credentials = credentials
        self.transport = transport; self.generation = generation; self.isCurrent = isCurrent
    }
}
typealias UsageModelFactory = @MainActor (UsageContainerConfiguration, @escaping @MainActor () -> UsageBinding?) -> UsageViewModel

/// Conditional read-only integration. A real production original-attempt source is not wired yet.
@MainActor @Observable public final class UsageContainerHost {
    private let shell: ShellState
    private var configuration: UsageContainerConfiguration?
    private var selected: UsageBinding?
    private var model: UsageViewModel?
    private var request: UUID?
    private var foreground = false
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private let makeModel: UsageModelFactory
    public var selectionGeneration: UUID? { selected?.selectionGeneration }
    public var hasOriginalSource: Bool { selected != nil }
    public var canRead: Bool {
        guard foreground, let configuration, let selected, model != nil else { return false }
        return shell.generation == configuration.generation && !shell.messageBindingBlocked
            && configuration.session.isCurrent(selected.sessionOperation)
    }
    public var state: UsageState { canRead ? model?.state ?? .unavailable : .unavailable }
    public convenience init(shell: ShellState) {
        self.init(shell: shell, makeModel: { config, current in
            UsageViewModel(session: config.session, endpoint: config.endpoint, credentials: config.credentials,
                           currentBinding: current, liveReadTransport: config.transport)
        })
    }
    init(shell: ShellState, makeModel: @escaping UsageModelFactory) {
        self.shell = shell; self.makeModel = makeModel
        shell.usageContainerHost?.invalidate(); shell.usageContainerHost = self
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    @discardableResult public func configure(_ config: UsageContainerConfiguration) -> Bool {
        guard configuration == nil, shell.generation == config.generation, !shell.messageBindingBlocked else { return false }
        configuration = config
        return true // resource construction never queries or fabricates a source
    }
    private func currentBinding(configurationID: UUID) -> UsageBinding? {
        guard foreground, let config = configuration, config.id == configurationID, let original = selected,
              shell.generation == config.generation, !shell.messageBindingBlocked,
              config.session.isCurrent(original.sessionOperation) else { return nil }
        let allowed = config.isCurrent(original)
        guard allowed, foreground, configuration?.id == configurationID, selected == original,
              shell.generation == config.generation, !shell.messageBindingBlocked,
              config.session.isCurrent(original.sessionOperation) else { return nil }
        return original // no callback after the original source/actor/generation checks
    }
    /// Only the trusted root may supply this original evidence. No UI text field or
    /// message/run inference calls this. Supplied generation is replaced by a new local
    /// selection generation on EVERY switch; original source/revision/actor/op are retained.
    public func selectOriginal(_ original: UsageBinding?) {
        let oldModel = model, oldTask = task
        task = nil; model = nil; selected = nil; request = nil
        if foreground, let config = configuration, shell.generation == config.generation, !shell.messageBindingBlocked,
           let original, !original.actorIdentity.isEmpty, !original.source.attemptID.isEmpty,
           config.session.isCurrent(original.sessionOperation) {
            let binding = UsageBinding(source: original.source, sessionOperation: original.sessionOperation,
                actorIdentity: original.actorIdentity, selectionGeneration: UUID(), revision: original.revision)
            selected = binding
            let id = config.id
            let candidate = makeModel(config, { [weak self] in self?.currentBinding(configurationID: id) })
            if configuration?.id == id, selected == binding { model = candidate }
            else { candidate.invalidate() }
        }
        oldModel?.invalidate(); oldTask?.cancel() // captured old objects only; no host writes afterward
    }
    public func setForeground(_ active: Bool) {
        foreground = active
        if !active { selectOriginal(nil) } // no automatic reselection or GET on foreground
    }
    public func invalidate() {
        let oldModel = model, oldTask = task
        configuration = nil; model = nil; selected = nil; request = nil; task = nil
        oldModel?.invalidate(); oldTask?.cancel()
    }
    private func ownsRequest(_ token: UUID, model originalModel: UsageViewModel, config: UsageContainerConfiguration, binding: UsageBinding) -> Bool {
        request == token && model === originalModel && configuration?.id == config.id && selected == binding
            && foreground && shell.generation == config.generation && !shell.messageBindingBlocked
    }
    /// Explicit button event: reserve host ownership, then model.prepare BEFORE Task.
    public func readOriginal() {
        guard canRead, let config = configuration, let model, let binding = selected else { return }
        let oldTask = task; task = nil
        let token = UUID(); request = token
        do {
            let prepared = try model.prepare(binding) // its own owner is installed before admission callbacks
            guard ownsRequest(token, model: model, config: config, binding: binding) else { oldTask?.cancel(); return }
            task = Task { [weak self] in
                await model.read(prepared)
                guard let self, self.ownsRequest(token, model: model, config: config, binding: binding) else { return }
                self.task = nil; self.request = nil
            }
            oldTask?.cancel() // no old-lifetime write after cancellation callbacks
        } catch {
            if ownsRequest(token, model: model, config: config, binding: binding) { request = nil }
            oldTask?.cancel() // a stale outer preparation must not invalidate the newer model/work
        }
    }
}
