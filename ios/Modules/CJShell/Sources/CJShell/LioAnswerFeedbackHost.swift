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
    /// Lines confirmed by the server this session (a confirmed line is removed from the device, so this is the memory).
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
        await send(Key(message: Data(messageID.utf8), step: .notHelpful), messageID: messageID, problem: problem, userRetry: false)
    }

    public func addDetails(messageID: String, text: String) async -> LioAnswerFeedbackOutcome {
        await send(Key(message: Data(messageID.utf8), step: .details), messageID: messageID, problem: text, userRetry: false)
    }

    /// A host made after the app came back has no attempts yet: the text from `LioHome` lets it find the line
    /// already saved for this message and step instead of leaving the retry dead or making a second line.
    public func retry(_ step: LioAnswerFeedbackStep, messageID: String, text: String) async -> LioAnswerFeedbackOutcome {
        await send(Key(message: Data(messageID.utf8), step: step), messageID: messageID, problem: text, userRetry: true)
    }

    /// Callback-free: retires queued work when the session ends.
    public func invalidate() { presentation.replace(binding: nil) }

    /// `userRetry` is true only for the traveller's own tap on "try again": then a saved line the server says it has no
    /// record of is sent again under its own ID and exact bytes (#1855, once per such answer); a first tap never does.
    private func send(_ key: Key, messageID: String, problem: String, userRetry: Bool) async -> LioAnswerFeedbackOutcome {
        guard !busy else { return .notSent }
        busy = true
        defer { busy = false }
        // The first text for a step is the one kept; a repeat call for the same step reuses its line.
        var attempt = attempts[key] ?? Attempt(messageID: messageID, problem: problem)
        attempts[key] = attempt
        if let id = attempt.actionID, arrived.contains(Data(id.utf8)) { return .sent }
        guard open(messageID: messageID) else { return .unavailable }
        guard let saved = await savedLines() else { return .notSent }
        for id in saved.map(\.id) where !arrived.contains(Data(id.utf8)) {
            switch await lookUp(id) {
            case .arrived: break
            case .noSuchLine:
                guard userRetry, await resend(id) else { return .notSent }
            case .unknown: return .notSent
            }
            arrived.insert(Data(id.utf8))
        }
        if attempt.actionID == nil, let id = saved.first(where: { $0.matches(messageID: messageID, problem: attempt.problem) })?.id {
            // Made by an earlier host for this message and text (the app went to the background, or reconnected).
            attempt.actionID = id
            attempts[key] = attempt
        }
        if let id = attempt.actionID {
            if arrived.contains(Data(id.utf8)) { return .sent }
            // Saving comes before sending, so a line that never reached this device's store never left it.
            attempt.actionID = nil
            attempts[key] = attempt
        }
        // Lines the server confirmed were removed from this device, so the cap is counted again (#1855).
        guard open(messageID: messageID), let remaining = await savedLines() else { return .notSent }
        guard remaining.count < maximumRecords else { return .full }
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

    private struct SavedLine {
        let id: String
        /// Every reference, as kind and ID; Lio's lines carry exactly one, the message.
        let references: [Data]
        let problem: Data
        let expectationIsEmpty: Bool

        /// Only a line shaped like Lio's own: this message alone, this exact text, no expectation.
        func matches(messageID: String, problem: String) -> Bool {
            references == [Data("message:\(messageID)".utf8)] && self.problem == Data(problem.utf8) && expectationIsEmpty
        }
    }

    /// Every line saved on this device for the account (in the store's own order), or nil when it can't be read.
    private func savedLines() async -> [SavedLine]? {
        guard let work = presentation.prepareReload() else { return nil }
        await presentation.perform(work)
        guard presentation.state == .editing, presentation.original == nil else { return nil }
        return presentation.pendingActions.map { pending in
            let action = try? pending.action()
            return SavedLine(id: pending.actionID,
                             references: action?.references.map { Data("\($0.kind.rawValue):\($0.id)".utf8) } ?? [],
                             problem: Data((action?.problem ?? "").utf8),
                             expectationIsEmpty: action?.expectation.isEmpty ?? false)
        }
    }

    private enum LookUp { case arrived, noSuchLine, unknown }

    /// `arrived` only when the server returns this exact line; `noSuchLine` only when it answers that it has none.
    private func lookUp(_ id: String) async -> LookUp {
        presentation.selectPending(actionID: id)
        guard presentation.original.map({ Data($0.actionID.utf8) == Data(id.utf8) }) == true,
              let work = presentation.prepareQuery() else { return .unknown }
        await presentation.perform(work)
        guard presentation.original.map({ Data($0.actionID.utf8) == Data(id.utf8) }) == true else { return .unknown }
        if presentation.state == .submitted { return .arrived }
        return presentation.state == .unknown && presentation.receipt == nil && presentation.canResendSelected ? .noSuchLine : .unknown
    }

    /// Sends the selected line again, same ID and bytes. True only when its receipt came back.
    private func resend(_ id: String) async -> Bool {
        guard presentation.original.map({ Data($0.actionID.utf8) == Data(id.utf8) }) == true,
              let work = presentation.prepareResend() else { return false }
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
