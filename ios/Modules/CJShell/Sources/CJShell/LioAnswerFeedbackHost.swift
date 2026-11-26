import Foundation
import CJFeedbackClient
import CJLioUser

/// #1753 (W4-9): Lio's "Not helpful" through the canonical feedback model. The host keeps one client and one
/// `FeedbackPresentation` for the signed-in session, and handles one answer at a time.
///
/// Every line is saved on this device before it is sent. A line whose arrival is not known is only looked up by
/// its own ID afterwards; it is never sent again under a new one. Before anything new is sent, every line still
/// saved on this device is looked up one by one until each has arrived. What arrived is remembered only for this
/// session (#1855 changes how the device keeps them).
@MainActor public final class LioAnswerFeedbackHost: LioAnswerFeedbackSending {
    private struct Key: Hashable {
        let message: Data
        let step: LioAnswerFeedbackStep
    }
    private struct Attempt {
        let messageID: String
        let problem: String
        var actionID: String?
    }

    private let presentation: FeedbackPresentation
    private let currentBinding: @MainActor () -> FeedbackBinding?
    private let maximumRecords: Int
    private var arrived: Set<Data> = []
    private var attempts: [Key: Attempt] = [:]
    private var busy = false

    /// `client` must be Lio's own: never the engineering answer surface's (see `FeedbackContainerHost`).
    /// `maximumRecords` is the limit its pending store was made with.
    public init(client: FeedbackClient, currentBinding: @escaping @MainActor () -> FeedbackBinding?, maximumRecords: Int) {
        presentation = FeedbackPresentation(client: client)
        self.currentBinding = currentBinding
        self.maximumRecords = maximumRecords
    }

    public func notHelpful(messageID: String, problem: String) async -> LioAnswerFeedbackOutcome {
        await send(Key(message: Data(messageID.utf8), step: .notHelpful), messageID: messageID, problem: problem)
    }

    public func addDetails(messageID: String, text: String) async -> LioAnswerFeedbackOutcome {
        await send(Key(message: Data(messageID.utf8), step: .details), messageID: messageID, problem: text)
    }

    public func retry(_ step: LioAnswerFeedbackStep, messageID: String) async -> LioAnswerFeedbackOutcome {
        let key = Key(message: Data(messageID.utf8), step: step)
        guard let attempt = attempts[key] else { return .notSent }
        return await send(key, messageID: attempt.messageID, problem: attempt.problem)
    }

    /// Callback-free: retires queued work when the session ends.
    public func invalidate() { presentation.replace(binding: nil) }

    private func send(_ key: Key, messageID: String, problem: String) async -> LioAnswerFeedbackOutcome {
        guard !busy else { return .notSent }
        busy = true
        defer { busy = false }
        // The first text for a step is the one kept; a repeat call for the same step reuses its line.
        var attempt = attempts[key] ?? Attempt(messageID: messageID, problem: problem)
        attempts[key] = attempt
        if let id = attempt.actionID, arrived.contains(Data(id.utf8)) { return .sent }
        guard open(messageID: messageID) else { return .unavailable }
        guard let saved = await savedLines() else { return .notSent }
        for id in saved where !arrived.contains(Data(id.utf8)) {
            guard await lookUp(id) else { return .notSent }
            arrived.insert(Data(id.utf8))
        }
        if let id = attempt.actionID {
            if arrived.contains(Data(id.utf8)) { return .sent }
            // Saving comes before sending, so a line that never reached this device's store never left it.
            attempt.actionID = nil
            attempts[key] = attempt
        }
        guard saved.count < maximumRecords else { return .full }
        let (id, didArrive) = await submit(problem: attempt.problem)
        attempt.actionID = id
        attempts[key] = attempt
        guard didArrive, let id else { return .notSent }
        arrived.insert(Data(id.utf8))
        return .sent
    }

    /// Points the shared presentation at this answer's message (message only, no run).
    private func open(messageID: String) -> Bool {
        guard let binding = currentBinding(), let context = try? FeedbackContext(messageID: messageID) else {
            presentation.replace(binding: nil)
            return false
        }
        presentation.replace(binding: binding, context: context)
        return presentation.state == .editing
    }

    /// Every line saved on this device for the account, or nil when the store can't be read.
    private func savedLines() async -> [String]? {
        guard let work = presentation.prepareReload() else { return nil }
        await presentation.perform(work)
        guard presentation.state == .editing, presentation.original == nil else { return nil }
        return presentation.pendingActions.map(\.actionID)
    }

    /// True only when the server returns this exact line.
    private func lookUp(_ id: String) async -> Bool {
        presentation.selectPending(actionID: id)
        guard presentation.original.map({ Data($0.actionID.utf8) == Data(id.utf8) }) == true,
              let work = presentation.prepareQuery() else { return false }
        await presentation.perform(work)
        return presentation.state == .submitted
            && presentation.original.map({ Data($0.actionID.utf8) == Data(id.utf8) }) == true
    }

    /// Saves and sends one new line. Returns its ID when one was made, and whether it is known to have arrived.
    private func submit(problem: String) async -> (String?, Bool) {
        if presentation.state == .submitted { presentation.startAnother() }
        guard presentation.state == .editing, presentation.canEdit else { return (nil, false) }
        presentation.edit(problem: problem, expectation: "")
        presentation.associateContext(true)
        guard presentation.includeContext, let work = presentation.prepareSubmit(),
              let id = presentation.original?.actionID else { return (nil, false) }
        await presentation.perform(work)
        let didArrive = presentation.state == .submitted
            && presentation.original.map({ Data($0.actionID.utf8) == Data(id.utf8) }) == true
        return (id, didArrive)
    }
}
