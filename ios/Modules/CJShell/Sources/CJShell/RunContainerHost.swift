import Foundation
import Observation
import CJRunClient
import CJSession

@MainActor public struct RunContainerConfiguration {
    fileprivate let id = UUID()
    let model: RunDisplayModel
    let session: SessionLifecycle
    let operation: SessionOperation
    let generation: ShellGeneration
    let synthetic: Bool
    let followAcceptedMessages: Bool
    let isCurrent: @MainActor () -> Bool
    /// Model credentials must use this same original session operation and the existing trusted bridge.
    public init(model: RunDisplayModel, session: SessionLifecycle, operation: SessionOperation,
                generation: ShellGeneration, synthetic: Bool, followAcceptedMessages: Bool = false, isCurrent: @escaping @MainActor () -> Bool) {
        self.model = model; self.session = session; self.operation = operation
        self.generation = generation; self.synthetic = synthetic; self.followAcceptedMessages = followAcceptedMessages; self.isCurrent = isCurrent
    }
}
@MainActor @Observable public final class RunContainerHost {
    private let shell: ShellState
    private var configuration: RunContainerConfiguration?
    private var origin: AcceptedMessageRunReceipt?
    private var selection = UUID()
    public private(set) var foreground = false
    public private(set) var sourceUnavailable = false
    public var displayModel: RunDisplayModel? {
        guard foreground, let configuration, configurationIsCurrent(configuration) else { return nil }
        return configuration.model
    }
    public var followsAcceptedMessages: Bool { displayModel != nil && configuration?.followAcceptedMessages == true }
    public var isShowingOriginal: Bool { origin != nil || sourceUnavailable }
    public var isSynthetic: Bool { displayModel != nil && configuration?.synthetic == true }
    public init(shell: ShellState) {
        self.shell = shell
        shell.runContainerHost?.invalidate()
        shell.runContainerHost = self
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    private func ownsConfiguration(_ value: RunContainerConfiguration) -> Bool {
        configuration?.id == value.id && shell.generation == value.generation && !shell.messageBindingBlocked
    }
    private func configurationIsCurrent(_ value: RunContainerConfiguration) -> Bool {
        guard ownsConfiguration(value), value.session.isCurrent(value.operation) else { return false }
        let current = value.isCurrent()
        return current && ownsConfiguration(value) && value.session.isCurrent(value.operation)
    }
    @discardableResult public func configure(_ value: RunContainerConfiguration) -> Bool {
        guard configuration == nil, value.generation == shell.generation, !shell.messageBindingBlocked,
              value.session.isCurrent(value.operation), value.isCurrent(),
              configuration == nil, value.generation == shell.generation, !shell.messageBindingBlocked,
              value.session.isCurrent(value.operation) else { return false }
        value.model.invalidate()
        configuration = value; origin = nil; selection = UUID(); sourceUnavailable = false
        return true // no source, read, credentials or new session is created here
    }
    public func setForeground(_ active: Bool) {
        foreground = active
        if !active { retireSelection() }
    }
    public func retireSelection() {
        let model = configuration?.model
        origin = nil; selection = UUID(); sourceUnavailable = false
        model?.invalidate() // callback-free canonical local fence; no host writes afterward
    }
    public func invalidate() {
        let model = configuration?.model
        configuration = nil; origin = nil; selection = UUID(); sourceUnavailable = false
        model?.invalidate()
    }
    private func sourceIsCurrent(_ original: AcceptedMessageRunReceipt, configurationID: UUID, token: UUID) -> Bool {
        guard foreground, let configuration, configuration.id == configurationID,
              origin === original, selection == token, configurationIsCurrent(configuration) else { return false }
        // MESSAGE validation may revoke admission. The last admission callback may in
        // turn replace the source. Finish with callback-free canonical/local checks.
        guard original.isCurrent(), configurationIsCurrent(configuration) else { return false }
        return original.isStillOwned() && foreground && ownsConfiguration(configuration) && origin === original && selection == token
            && configuration.session.isCurrent(configuration.operation)
    }
    /// Explicit selection only; staged/unknown/malformed receipts are never upgraded here.
    @discardableResult public func selectAcceptedMessage(from messages: AssistantMessageHost) -> Bool {
        guard messages.belongs(to: shell), foreground, let configuration else { return false }
        // Retire the previous source before any callback may prepare work against it.
        retireSelection()
        let originalSelection = selection
        guard configurationIsCurrent(configuration), selection == originalSelection,
              let source = messages.captureAcceptedRunReceipt(),
              source.isCurrent(), ownsConfiguration(configuration), selection == originalSelection, foreground else {
            if ownsConfiguration(configuration), selection == originalSelection {
                retireSelection(); sourceUnavailable = true
            }
            return false
        }
        let token = UUID(); selection = token; origin = source; sourceUnavailable = false
        do {
            let configurationID = configuration.id
            let runSource = try RunDisplaySource(receipt: source.receipt, session: configuration.session, operation: configuration.operation,
                isCurrent: { [weak self] in self?.sourceIsCurrent(source, configurationID: configurationID, token: token) == true })
            let accepted = configuration.model.select(runSource)
            guard ownsConfiguration(configuration), origin === source, selection == token else { return false }
            // Canonical select owns its cleanup. A false return can mean a newer
            // prepare won inside its callback; the old host must not clear that work.
            return accepted
        } catch {
            guard ownsConfiguration(configuration), origin === source, selection == token else { return false }
            retireSelection(); sourceUnavailable = true; return false
        }
    }
}
