import Foundation
import Observation
import CJRunClient
import CJSession
import CJTripClient
import CJNeedsClient

public enum RunAnswerFormat: Sendable { case plainText,placeToolV1,factToolV1,needsPreviewV1 }
public enum PlaceRunProjection: Sendable { case waiting,unavailable,loaded(PlaceToolTranscriptV1) }
public enum FactRunProjection: Sendable { case waiting,unavailable,loaded(FactToolTranscriptV1) }
public enum NeedsPreviewRunProjection: Sendable { case waiting,unavailable,loaded(NeedsPreviewV1) }

@MainActor public struct RunContainerConfiguration {
    fileprivate let id = UUID()
    let model: RunDisplayModel
    let session: SessionLifecycle
    let operation: SessionOperation
    let generation: ShellGeneration
    let synthetic: Bool
    let followAcceptedMessages: Bool
    let answerFormat: RunAnswerFormat
    let isCurrent: @MainActor () -> Bool
    /// Model credentials must use this same original session operation and the existing trusted bridge.
    public init(model: RunDisplayModel, session: SessionLifecycle, operation: SessionOperation,
                generation: ShellGeneration, synthetic: Bool, followAcceptedMessages: Bool = false,answerFormat: RunAnswerFormat = .plainText, isCurrent: @escaping @MainActor () -> Bool) {
        self.model = model; self.session = session; self.operation = operation
        self.generation = generation; self.synthetic = synthetic; self.followAcceptedMessages = followAcceptedMessages;self.answerFormat = answerFormat; self.isCurrent = isCurrent
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
    public var answerFormat: RunAnswerFormat? { displayModel != nil ? configuration?.answerFormat : nil }
    /// Presentation association only. The panel must still obtain its data
    /// through the current protected projection, never retain an old copy.
    public var originalPresentationID: UUID? {
        guard let configuration,let original = origin else { return nil }
        let token = selection
        return sourceIsCurrent(original,configurationID:configuration.id,token:token) ? token : nil
    }
    /// Cross-component copy requires the actual same session operation, not
    /// merely a shared window, matching caller IDs or a source hash.
    func currentOriginalUses(session: SessionLifecycle, operation: SessionOperation, generation: ShellGeneration) -> Bool {
        guard let configured = configuration, configured.session === session, configured.operation == operation,
              configured.generation == generation, originalPresentationID != nil else { return false }
        return configuration?.id == configured.id && configured.session.isCurrent(operation)
    }
    /// Final local ownership fence after the last peer callback. Canonical
    /// recovery/lease reads only; this does not replace the earlier admission.
    func stillOwnsOriginal(_ expected: UUID) -> Bool {
        guard foreground, selection == expected, let configured = configuration, let original = origin,
              shell.generation == configured.generation, !shell.messageBindingBlocked,
              configured.session.isCurrent(configured.operation) else { return false }
        return original.isStillOwned() && selection == expected && configuration?.id == configured.id && origin === original
    }
    private struct ToolRead {
        let original: AcceptedMessageRunReceipt
        let configurationID: UUID
        let token: UUID
        let text: String
        let completed: Bool
    }
    private enum ToolInput { case waiting, unavailable, ready(ToolRead) }
    /// One shared source acquisition path; each decoder still performs the
    /// callback-bearing final original-source fence after parsing its own ABI.
    private func toolInput(for format: RunAnswerFormat) -> ToolInput {
        guard let configuration, configuration.answerFormat == format, let original = origin else { return .unavailable }
        let token = selection
        guard sourceIsCurrent(original, configurationID: configuration.id, token: token) else { return .unavailable }
        let state = configuration.model.state, progress = configuration.model.streamProgress
        let text: String, completed: Bool
        if let progress { text = progress.text; completed = false }
        else {
            switch state {
            case .loaded(let value): text = value.snapshot.text; completed = value.snapshot.status == .completed
            case .ready, .loading: return .waiting
            case .unselected, .unavailable: return .unavailable
            }
        }
        return .ready(ToolRead(original: original, configurationID: configuration.id, token: token, text: text, completed: completed))
    }
    public var placeProjection: PlaceRunProjection {
        switch toolInput(for: .placeToolV1) {
        case .waiting: return .waiting
        case .unavailable: return .unavailable
        case .ready(let read):
            let result: PlaceRunProjection
            do { result = .loaded(try PlaceToolTranscriptV1.decode(Data(read.text.utf8), runID: read.original.receipt.run_id, completed: read.completed)) }
            catch { result = .unavailable }
            guard sourceIsCurrent(read.original, configurationID: read.configurationID, token: read.token) else { return .unavailable }
            return result
        }
    }
    public var followsAcceptedMessages: Bool { displayModel != nil && configuration?.followAcceptedMessages == true }
    public var factProjection: FactRunProjection {
        switch toolInput(for: .factToolV1) {
        case .waiting: return .waiting
        case .unavailable: return .unavailable
        case .ready(let read):
            let result: FactRunProjection
            do { result = .loaded(try FactToolTranscriptV1.decode(Data(read.text.utf8), runID: read.original.receipt.run_id, completed: read.completed)) }
            catch { result = .unavailable }
            guard sourceIsCurrent(read.original, configurationID: read.configurationID, token: read.token) else { return .unavailable }
            return result
        }
    }
    public var needsPreviewProjection: NeedsPreviewRunProjection {
        switch toolInput(for: .needsPreviewV1) {
        case .waiting: return .waiting
        case .unavailable: return .unavailable
        case .ready(let read):
            guard read.completed else { return .waiting }
            guard let text = read.original.originalTextUTF8 else { return .unavailable }
            let result: NeedsPreviewRunProjection
            do {
                result = .loaded(try NeedsPreviewV1.decode(Data(read.text.utf8), messageID: read.original.receipt.message_id,
                    runID: read.original.receipt.run_id, sourceTextUTF8: text))
            } catch { result = .unavailable }
            guard sourceIsCurrent(read.original, configurationID: read.configurationID, token: read.token) else { return .unavailable }
            return result
        }
    }
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
            let runSource = try RunDisplaySource(receipt: source.receipt,travelReference:source.travelReference, session: configuration.session, operation: configuration.operation,
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
