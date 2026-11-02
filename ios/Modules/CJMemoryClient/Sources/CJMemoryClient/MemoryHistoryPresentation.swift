import Foundation
import Observation

public enum MemoryHistoryState: Equatable, Sendable {
    case unconfigured, unselected, unread, loading, ready, changing, reconciling, unknown, conflict, unavailable, recoveryUnavailable
    public var isBusy: Bool { self == .loading || self == .changing || self == .reconciling }
}
public struct MemoryHistoryWork: Sendable {
    fileprivate enum Kind: Sendable { case read, reload, change(MemoryHistoryPending), query(MemoryHistoryPending) }
    fileprivate let scope: UUID
    fileprivate let request: UUID
    fileprivate let operation: MemoryHistoryOperation
    fileprivate let kind: Kind
}

/// One conversation presentation. Publish a complete slot before notifying observers;
/// old work never writes the new account/conversation slot during synchronous reentry.
@MainActor @Observable public final class MemoryHistoryPresentation {
    private final class Slot {
        let id = UUID()
        let binding: MemoryBinding?
        let conversation: String?
        var request = UUID()
        var started: UUID?
        var state: MemoryHistoryState
        var read: MemoryHistoryRead?
        var original: MemoryHistoryPending?
        var receipt: MemoryHistoryReceipt?
        var rejection: (Int, String)?
        var records: [MemoryHistoryPending] = []
        var unresolved: Set<Data> = []
        init(binding: MemoryBinding?, conversation: String?, configured: Bool) {
            self.binding = binding; self.conversation = conversation
            state = !configured || binding == nil ? .unconfigured : conversation == nil ? .unselected : .unread
        }
    }
    private let client: MemoryHistoryClient?
    @ObservationIgnored private var slot: Slot
    private var signal = UUID()
    @ObservationIgnored private var notifying = false
    private func notify() {
        guard !notifying else { return }
        notifying = true
        defer { notifying = false }
        signal = UUID()
    }
    public init(client: MemoryHistoryClient?) {
        self.client = client; slot = Slot(binding: nil, conversation: nil, configured: client != nil)
    }
    public var state: MemoryHistoryState { _ = signal; return slot.state }
    public var conversationID: String? { _ = signal; return slot.conversation }
    public var settings: MemoryHistorySettings? { _ = signal; return slot.read?.settings }
    public var original: MemoryHistoryPending? { _ = signal; return slot.original }
    public var receipt: MemoryHistoryReceipt? { _ = signal; return slot.receipt }
    public var rejectionStatus: Int? { _ = signal; return slot.rejection?.0 }
    public var pendingActions: [MemoryHistoryPending] { _ = signal; return slot.records }
    public var canRead: Bool { _ = signal; return client != nil && slot.binding != nil && slot.conversation != nil && !slot.state.isBusy }
    public var hasUnresolved: Bool { _ = signal; return !slot.unresolved.isEmpty }
    public var canChange: Bool { _ = signal; return canRead && slot.state == .ready && slot.read != nil && slot.unresolved.isEmpty }

    public func replace(binding: MemoryBinding?, conversationID: String?) {
        client?.invalidate()
        slot = Slot(binding: binding, conversation: conversationID, configured: client != nil)
        notify() // Last publication; reentrant replacement owns its new slot.
    }
    private func matches(_ work: MemoryHistoryWork) -> Bool { slot.id == work.scope && slot.request == work.request }
    private func current(_ work: MemoryHistoryWork) -> Bool { matches(work) && client?.owns(work.operation) == true && matches(work) }
    private func prepared() -> (Slot, UUID, MemoryHistoryOperation)? {
        let captured = slot
        guard let binding = captured.binding, let conversation = captured.conversation, let client, !captured.state.isBusy else { return nil }
        let request = UUID(); captured.request = request; captured.started = nil
        do {
            let op = try client.begin(binding: binding, conversation: conversation)
            guard slot === captured, captured.request == request else { return nil }
            return (captured, request, op)
        } catch {
            guard slot === captured, captured.request == request else { return nil }
            captured.read = nil; captured.state = captured.original == nil ? .unavailable : .recoveryUnavailable
            notify(); return nil
        }
    }
    public func prepareRead() -> MemoryHistoryWork? {
        guard let (captured, request, op) = prepared() else { return nil }
        captured.read = nil; captured.state = .loading
        let work = MemoryHistoryWork(scope: captured.id, request: request, operation: op, kind: .read)
        notify(); return work
    }
    public func prepareReload() -> MemoryHistoryWork? {
        guard let (captured, request, op) = prepared() else { return nil }
        captured.state = .loading
        let work = MemoryHistoryWork(scope: captured.id, request: request, operation: op, kind: .reload)
        notify(); return work
    }
    public func prepareChange(_ change: MemoryHistoryChange) -> MemoryHistoryWork? {
        guard canChange, let read = slot.read, let client,
              let (captured, request, op) = prepared() else { return nil }
        do {
            let original = try client.prepare(change: change, read: read, operation: op)
            guard slot === captured, captured.request == request else { return nil }
            captured.original = original; captured.receipt = nil; captured.rejection = nil
            captured.read = nil; captured.state = .changing
            let work = MemoryHistoryWork(scope: captured.id, request: request, operation: op, kind: .change(original))
            notify(); return work
        } catch {
            guard slot === captured, captured.request == request else { return nil }
            captured.read = nil; captured.state = .unavailable
            notify(); return nil
        }
    }
    public func selectPending(actionID: String) {
        let captured = slot
        guard !captured.state.isBusy, let original = captured.records.first(where: { same($0.actionID, actionID) }) else { return }
        client?.invalidate(); captured.request = UUID(); captured.started = nil
        captured.original = original; captured.receipt = nil; captured.rejection = nil
        captured.read = nil; captured.state = .unknown
        notify()
    }
    public func prepareQuery() -> MemoryHistoryWork? {
        guard let original = slot.original, let (captured, request, op) = prepared() else { return nil }
        captured.state = .reconciling
        let work = MemoryHistoryWork(scope: captured.id, request: request, operation: op, kind: .query(original))
        notify(); return work
    }
    private func refresh(_ work: MemoryHistoryWork, client: MemoryHistoryClient) async throws {
        let read = try await client.read(work.operation)
        let pending = try client.pendingInfo(work.operation)
        guard current(work) else { return }
        let captured = slot
        captured.read = read; captured.records = pending.records; captured.unresolved = pending.unresolved
        captured.state = .ready
        notify()
    }
    public func perform(_ work: MemoryHistoryWork) async {
        guard current(work), let client else {
            if matches(work) {
                let captured = slot; captured.read = nil
                captured.state = captured.original == nil ? .unavailable : .recoveryUnavailable
                notify()
            }
            return
        }
        let captured = slot
        guard captured.started != work.request else { return }
        captured.started = work.request
        do {
            switch work.kind {
            case .read:
                try await refresh(work, client: client)
            case .reload:
                let pending = try client.pendingInfo(work.operation)
                guard current(work) else { return }
                captured.records = pending.records; captured.unresolved = pending.unresolved
                captured.state = captured.read == nil ? (captured.original == nil ? .unread : .unknown) : .ready
                notify()
            case .change(let original):
                let result = try await client.submit(original, operation: work.operation)
                try await apply(result, work: work, client: client)
            case .query(let original):
                let result = try await client.query(original, operation: work.operation)
                try await apply(result, work: work, client: client)
            }
        } catch {
            guard current(work) else {
                if matches(work) {
                    captured.read = nil; captured.state = captured.original == nil ? .unavailable : .recoveryUnavailable
                    notify()
                }
                return
            }
            captured.read = nil
            if captured.receipt != nil {
                // The action succeeded; a later settings GET failure cannot become
                // a rejected/uncommitted action or an inferred current enabled value.
                captured.state = .unavailable
            } else if case MemoryFailure.rejected(let status, let code) = error, [400,401,403,409].contains(status),
               case .change = work.kind {
                captured.rejection = (status, code); captured.state = status == 409 ? .conflict : .unavailable
            } else {
                switch work.kind {
                case .read: captured.state = .unavailable
                case .reload: captured.state = .recoveryUnavailable
                case .change, .query: captured.state = .unknown
                }
            }
            notify()
        }
    }
    private func apply(_ result: MemoryHistoryResult, work: MemoryHistoryWork, client: MemoryHistoryClient) async throws {
        guard current(work) else { return }
        let captured = slot
        switch result {
        case .recorded(let receipt):
            captured.receipt = receipt; captured.rejection = nil
            // Do not install receipt.historical as the current switch value.
            try await refresh(work, client: client)
        case .notObserved:
            captured.read = nil; captured.state = .unknown
            notify()
        case .rejected(let status, let code):
            captured.read = nil; captured.rejection = (status, code)
            captured.state = status == 409 ? .conflict : .unavailable
            notify()
        }
    }
}
