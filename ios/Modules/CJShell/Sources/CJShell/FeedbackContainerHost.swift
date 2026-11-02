import Foundation
import Observation
import CJFeedbackClient
import CJSession

public enum FeedbackSurface: String, Hashable, Sendable { case answer, general }
/// UI lifetime only, not a message ID, session or permission. Frozen when opening a surface.
public struct FeedbackContainerEntry: Hashable, Sendable {
    fileprivate let bindingID: UUID
    fileprivate let surface: FeedbackSurface
}
@MainActor public struct FeedbackContainerBinding {
    fileprivate let id = UUID()
    let client: FeedbackClient
    let feedback: FeedbackBinding
    let shellGeneration: ShellGeneration
    let session: SessionLifecycle
    let operation: SessionOperation
    let context: FeedbackContext?
    let answerRevision: UUID?
    let runSource: FeedbackAnswerSource?
    let synthetic: Bool
    let current: @MainActor () -> FeedbackBinding?
    public init(client: FeedbackClient, feedback: FeedbackBinding, shellGeneration: ShellGeneration,
                session: SessionLifecycle, sessionOperation: SessionOperation,
                context: FeedbackContext? = nil, answerRevision: UUID? = nil, runSource: FeedbackAnswerSource? = nil, synthetic: Bool,
                currentBinding: @escaping @MainActor () -> FeedbackBinding?) {
        self.client = client; self.feedback = feedback; self.shellGeneration = shellGeneration
        self.session = session; operation = sessionOperation; self.context = context
        self.answerRevision = answerRevision; self.runSource = runSource; self.synthetic = synthetic; current = currentBinding
    }
}

/// Both surfaces consume one public module, with distinct clients/models so cleanup cannot
/// turn a general draft into answer feedback or invalidate another surface's queued work.
@MainActor @Observable public final class FeedbackContainerHost {
    public let surface: FeedbackSurface
    private let shell: ShellState
    private var binding: FeedbackContainerBinding?
    private var model: FeedbackPresentation?
    private let answerBinding: (@MainActor (FeedbackAnswerSource) throws -> FeedbackContainerBinding)?
    public var isConfigured: Bool { current }
    public init(shell: ShellState, surface: FeedbackSurface,
                answerBinding: (@MainActor (FeedbackAnswerSource) throws -> FeedbackContainerBinding)? = nil) {
        self.shell = shell; self.surface = surface; self.answerBinding = answerBinding
        switch surface {
        case .answer: shell.answerFeedbackHost?.invalidate(); shell.answerFeedbackHost = self
        case .general: shell.generalFeedbackHost?.invalidate(); shell.generalFeedbackHost = self
        }
    }
    func belongs(to shell: ShellState, surface: FeedbackSurface) -> Bool { self.shell === shell && self.surface == surface }
    private func sourceMatches(_ binding: FeedbackContainerBinding) -> Bool {
        switch surface {
        case .general: return binding.context == nil && binding.answerRevision == nil && binding.runSource == nil
        case .answer:
            if let source = binding.runSource {
                guard binding.answerRevision == nil, let context = binding.context,
                      Data(context.messageID.utf8) == Data(source.context.messageID.utf8),
                      context.runID.map({Data($0.utf8)}) == source.context.runID.map({Data($0.utf8)}) else { return false }
                return source.isCurrent(session: binding.session, operation: binding.operation, generation: binding.shellGeneration)
            }
            return binding.context != nil && binding.answerRevision == shell.assistantContentRevision && shell.assistantBody != nil
        }
    }
    private var current: Bool {
        guard let binding, !shell.messageBindingBlocked, shell.generation == binding.shellGeneration,
              sourceMatches(binding), binding.session.isCurrent(binding.operation) else { return false }
        let observed = binding.current()
        return self.binding?.id == binding.id && observed == binding.feedback
            && !shell.messageBindingBlocked && shell.generation == binding.shellGeneration
            && sourceMatches(binding) && binding.session.isCurrent(binding.operation)
            && self.binding?.id == binding.id && !shell.messageBindingBlocked && shell.generation == binding.shellGeneration
    }
    private func sharesOtherClient(_ value: FeedbackContainerBinding) -> Bool {
        let other = surface == .answer ? shell.generalFeedbackHost : shell.answerFeedbackHost
        return other?.binding?.client === value.client
    }
    @discardableResult public func bind(_ value: FeedbackContainerBinding) -> Bool {
        guard binding == nil, !shell.messageBindingBlocked, shell.generation == value.shellGeneration,
              sourceMatches(value), !sharesOtherClient(value), value.session.isCurrent(value.operation),
              value.current() == value.feedback,
              binding == nil, !shell.messageBindingBlocked, shell.generation == value.shellGeneration,
              sourceMatches(value), !sharesOtherClient(value), value.session.isCurrent(value.operation), binding == nil else { return false }
        let model = FeedbackPresentation(client: value.client)
        model.replace(binding: value.feedback, context: value.context)
        binding = value; self.model = model
        return true
    }
    /// Called only by an explicit answer feedback action, never while rendering.
    public func prepareAnswer(from runs: RunContainerHost) throws -> FeedbackContainerEntry? {
        guard surface == .answer, runs.belongs(to: shell), let answerBinding else { return nil }
        if let entry = captureEntry() { return entry }
        invalidate()
        guard let source = try runs.captureFeedbackSource() else { return nil }
        let value = try answerBinding(source)
        guard bind(value) else { return nil }
        return captureEntry()
    }
    public func captureEntry() -> FeedbackContainerEntry? {
        guard current, let binding else { return nil }
        return FeedbackContainerEntry(bindingID: binding.id, surface: surface)
    }
    public func presentation(for entry: FeedbackContainerEntry?) -> FeedbackPresentation? {
        guard let entry, current, entry.surface == surface, entry.bindingID == binding?.id else { return nil }
        return model
    }
    public func isSynthetic(for entry: FeedbackContainerEntry?) -> Bool {
        presentation(for: entry) != nil && binding?.synthetic == true
    }
    public func invalidate() {
        let original = model
        binding = nil; model = nil
        original?.replace(binding: nil) // canonical invalidate is callback-free; no old host writes afterward
    }
    public func suspendForBackground() { invalidate() }
}
