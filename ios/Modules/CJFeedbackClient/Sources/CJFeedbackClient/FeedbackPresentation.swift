import Foundation
import Observation
import CJAPI

public enum FeedbackState: Equatable, Sendable {
    case unavailable, editing, loading, submitting, reconciling, unknown, conflict, submitted, invalidInput, recoveryUnavailable
    public var isBusy: Bool { self == .loading || self == .submitting || self == .reconciling }
}

/// Opaque one-use work, captured in the button/lifecycle callback before its Task is queued.
public struct FeedbackWork: Sendable {
    fileprivate enum Kind: Sendable { case reload, submit(FeedbackPending), query(FeedbackPending) }
    fileprivate let owner: UUID
    fileprivate let lifetime: UUID
    fileprivate let request: UUID
    fileprivate let operation: FeedbackOperation
    fileprivate let kind: Kind
}

@MainActor @Observable public final class FeedbackPresentation {
    public private(set) var binding: FeedbackBinding?
    public private(set) var context: FeedbackContext?
    public private(set) var problem = ""
    public private(set) var expectation = ""
    public private(set) var includeContext = false
    public private(set) var state: FeedbackState = .unavailable
    public private(set) var original: FeedbackPending?
    public private(set) var receipt: Components.Schemas.FeedbackReceipt?
    public private(set) var pendingActions: [FeedbackPending] = []
    private let client: FeedbackClient?
    private let owner = UUID()
    private var lifetime = UUID()
    private var request = UUID()
    private var started: UUID?
    public init(client: FeedbackClient?) { self.client = client }
    public var submissionAvailable: Bool { client?.acceptsSubmissions == true && binding != nil }
    public var canEdit: Bool { original == nil && !state.isBusy }

    /// Host must synchronously replace on account/environment/selection change, before queued work.
    public func replace(binding: FeedbackBinding?, context: FeedbackContext? = nil) {
        lifetime = UUID(); request = UUID(); started = nil; client?.invalidate()
        self.binding = binding; self.context = context
        problem = ""; expectation = ""; includeContext = false; original = nil; receipt = nil; pendingActions = []
        state = submissionAvailable ? .editing : .unavailable
    }
    public func edit(problem: String, expectation: String) {
        guard canEdit else { return }
        // Accepted edits retire any frozen preparation still inside a host callback.
        request = UUID(); started = nil; client?.invalidate()
        self.problem = problem; self.expectation = expectation
        state = submissionAvailable ? .editing : .unavailable
    }
    public func associateContext(_ include: Bool) {
        guard canEdit else { return }
        // Association is part of the original action, just like problem/expectation.
        request = UUID(); started = nil; client?.invalidate()
        includeContext = include && context != nil
    }
    private func prepare(_ kind: FeedbackWork.Kind) -> FeedbackWork? {
        guard let binding, let client, !state.isBusy else { return nil }
        let savedLifetime = lifetime
        let savedRequest = UUID(); request = savedRequest; started = nil
        client.invalidate()
        do {
            let operation = try client.begin(binding: binding)
            guard lifetime == savedLifetime, request == savedRequest, self.binding == binding else { return nil }
            return FeedbackWork(owner: owner, lifetime: savedLifetime, request: savedRequest, operation: operation, kind: kind)
        } catch {
            guard lifetime == savedLifetime, request == savedRequest else { return nil }
            state = original == nil ? .unavailable : .recoveryUnavailable; return nil
        }
    }
    public func prepareSubmit() -> FeedbackWork? {
        guard canEdit, submissionAvailable else { return nil }
        do {
            let frozen = try FeedbackPending(problem: problem, expectation: expectation, context: includeContext ? context : nil)
            guard let work = prepare(.submit(frozen)) else { return nil }
            original = frozen; receipt = nil; state = .submitting
            return work
        } catch { state = .invalidInput; return nil }
    }
    public func prepareReload() -> FeedbackWork? {
        guard let work = prepare(.reload) else { return nil }; state = .loading; return work
    }
    public func selectPending(actionID: String) {
        guard let pending = pendingActions.first(where: { same($0.actionID, actionID) }), let action = try? pending.action() else { return }
        // No external callbacks. Invalidate running/queued old selection even if host binding is unchanged.
        request = UUID(); started = nil; client?.invalidate()
        original = pending; receipt = nil; problem = action.problem; expectation = action.expectation
        includeContext = !action.references.isEmpty; state = .unknown
    }
    public func prepareQuery() -> FeedbackWork? {
        guard let original, let work = prepare(.query(original)) else { return nil }
        state = .reconciling; return work
    }
    private func matches(_ work: FeedbackWork) -> Bool {
        work.owner == owner && work.lifetime == lifetime && work.request == request
    }
    private func current(_ work: FeedbackWork) -> Bool {
        matches(work) && client?.owns(work.operation) == true && matches(work)
    }
    public func perform(_ work: FeedbackWork) async {
        guard current(work) else {
            if matches(work) { state = original == nil ? .unavailable : .recoveryUnavailable }; return
        }
        guard started != work.request, let client else { return }
        started = work.request
        do {
            switch work.kind {
            case .reload:
                let records = try client.pending(operation: work.operation)
                guard current(work) else { return }
                // The binding callback above can mutate resources; fence again before publishing them.
                let final = try client.pending(operation: work.operation)
                guard matches(work) else { return }
                guard records.map(\.inputSHA256) == final.map(\.inputSHA256) else { throw FeedbackFailure.storageUnavailable }
                pendingActions = final
                state = original == nil ? (submissionAvailable ? .editing : .unavailable) : .unknown
            case .submit(let original):
                let result = try await client.submit(original, operation: work.operation)
                try publish(result, original: original, work: work)
            case .query(let original):
                let result = try await client.queryOriginal(actionID: original.actionID, operation: work.operation)
                try publish(result, original: original, work: work)
            }
        } catch {
            guard current(work) else {
                // Cancellation and a vanished credential/binding must not strand this selection busy.
                if matches(work) { state = original == nil ? .unavailable : .recoveryUnavailable }
                return
            }
            if case FeedbackFailure.rejected(409) = error { state = .conflict }
            else if case .reload = work.kind { state = .recoveryUnavailable }
            else { state = .unknown }
        }
    }
    private func publish(_ result: FeedbackResult, original: FeedbackPending, work: FeedbackWork) throws {
        guard current(work), let client else { return }
        try client.verify(original, operation: work.operation)
        guard matches(work) else { return }
        switch result {
        case .submitted(let receipt): self.receipt = receipt; state = .submitted
        case .notObserved: receipt = nil; state = .unknown
        }
    }
}
