import Foundation
import Observation

public enum MemoryErasureState: Sendable {
    case unconfigured, unselected, ready, preparing, submitting, loading, reconciling, known, unknown, conflict, unavailable, recoveryUnavailable
    public var isBusy: Bool { self == .preparing || self == .submitting || self == .loading || self == .reconciling }
}
public struct MemoryErasurePresentationWork: Sendable {
    fileprivate enum Kind: Sendable { case submit(MemoryErasureWork), query(MemoryErasureOriginal), originals }
    fileprivate let slot: UUID
    fileprivate let request: UUID
    fileprivate let kind: Kind
}

/// Last protected progress and known original stop are separate. An unavailable
/// GET retains a prior stop without presenting old physical progress as current.
@MainActor @Observable public final class MemoryErasurePresentation {
    private final class Slot {
        let id = UUID()
        let binding: MemoryBinding?
        var entry: MemoryErasureEntry?
        var request = UUID(), started: UUID?
        var state: MemoryErasureState
        var original: MemoryErasureOriginal?
        var originals: [MemoryErasureOriginal] = []
        var progress: MemoryErasureProgress?
        var progressIsCurrent = false
        init(binding: MemoryBinding?, entry: MemoryErasureEntry?, configured: Bool) {
            self.binding = binding; self.entry = entry
            state = !configured || binding == nil ? .unconfigured : entry == nil ? .unselected : .ready
        }
    }
    private let client: MemoryErasureClient?
    @ObservationIgnored private var slot: Slot
    @ObservationIgnored private var notifying = false
    private var signal = UUID()
    public init(client: MemoryErasureClient?) { self.client = client; slot = .init(binding: nil, entry: nil, configured: client != nil) }
    private func notify() {
        guard !notifying else { return }; notifying = true; defer { notifying = false }; signal = UUID()
    }
    public var state: MemoryErasureState { _ = signal; return slot.state }
    public var entry: MemoryErasureEntry? { _ = signal; return slot.entry }
    public var original: MemoryErasureOriginal? { _ = signal; return slot.original }
    public var originals: [MemoryErasureOriginal] { _ = signal; return slot.originals }
    public var progress: MemoryErasureProgress? { _ = signal; return slot.progress }
    public var progressIsCurrent: Bool { _ = signal; return slot.progressIsCurrent }
    public var knownStopped: Bool { _ = signal; return slot.progress?.stopped == true || slot.original?.knownStopped == true }
    public var canSubmit: Bool { _ = signal; return slot.state == .ready && slot.entry != nil }
    public var canRecover: Bool { _ = signal; return client != nil && slot.binding != nil && !slot.state.isBusy }
    public func replace(binding: MemoryBinding?, entry: MemoryErasureEntry? = nil) {
        let next = Slot(binding: binding, entry: entry, configured: client != nil)
        slot = next
        if let binding, let client {
            let current = client.isCurrent(binding: binding, entry: entry)
            guard slot === next else { return }
            if !current { next.entry = nil; next.state = .unavailable }
        }
        notify()
    }
    public func invalidate() {
        slot = .init(binding: nil, entry: nil, configured: client != nil)
        client?.invalidate(); notify()
    }
    public func prepareSubmission(acknowledged: Bool) -> MemoryErasurePresentationWork? {
        guard acknowledged, canSubmit, let entry = slot.entry, let client else { return nil }
        let captured = slot, request = UUID()
        // Reserve before any source/key callback can synchronously reenter.
        captured.request = request; captured.started = nil; captured.state = .preparing
        do {
            let work = try client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope)
            guard slot === captured, captured.request == request else { return nil }
            captured.original = work.original; captured.entry = nil
            captured.progress = nil; captured.progressIsCurrent = false; captured.state = .submitting
            let result = MemoryErasurePresentationWork(slot: captured.id, request: request, kind: .submit(work))
            notify(); return result
        } catch {
            guard slot === captured, captured.request == request else { return nil }
            captured.entry = nil
            captured.state = error as? MemoryFailure == .pendingRequiresQuery ? .unknown : .recoveryUnavailable
            notify(); return nil
        }
    }
    private func prepare() -> Slot? {
        guard canRecover, let client, let binding = slot.binding else { return nil }
        let captured = slot, request = UUID()
        captured.request = request; captured.started = nil
        guard client.isCurrent(binding: binding), slot === captured, captured.request == request, !captured.state.isBusy else { return nil }
        return captured
    }
    public func prepareOriginals() -> MemoryErasurePresentationWork? {
        guard let captured = prepare() else { return nil }
        captured.state = .loading; captured.progressIsCurrent = false
        let result = MemoryErasurePresentationWork(slot: captured.id, request: captured.request, kind: .originals)
        notify(); return result
    }
    public func selectOriginal(actionID: String) {
        guard !slot.state.isBusy, let selected = slot.originals.first(where: { same($0.actionID, actionID) }) else { return }
        slot.request = UUID(); slot.started = nil; slot.entry = nil
        slot.original = selected; slot.progress = nil; slot.progressIsCurrent = false; slot.state = .unknown
        notify()
    }
    public func prepareQuery() -> MemoryErasurePresentationWork? {
        guard let original = slot.original, let captured = prepare() else { return nil }
        captured.state = .reconciling; captured.progressIsCurrent = false
        let result = MemoryErasurePresentationWork(slot: captured.id, request: captured.request, kind: .query(original))
        notify(); return result
    }
    private func current(_ work: MemoryErasurePresentationWork) -> Bool {
        guard slot.id == work.slot, slot.request == work.request, let binding = slot.binding, let client else { return false }
        return client.isCurrent(binding: binding) && slot.id == work.slot && slot.request == work.request
    }
    public func perform(_ work: MemoryErasurePresentationWork) async {
        guard current(work), let client, let binding = slot.binding else { return }
        let captured = slot
        guard captured.started != work.request else { return }; captured.started = work.request
        do {
            switch work.kind {
            case .originals:
                let originals = try client.originals(binding: binding)
                guard current(work) else { return }
                captured.originals = originals
                captured.state = captured.original == nil ? .unselected : .unknown
            case .submit(let action):
                let progress = try await client.perform(action)
                guard current(work) else { return }
                captured.progress = progress; captured.progressIsCurrent = true; captured.state = .known
            case .query(let original):
                let progress = try await client.query(original)
                guard current(work) else { return }
                captured.progress = progress; captured.progressIsCurrent = true; captured.state = .known
            }
            notify()
        } catch {
            guard current(work) else { return }
            captured.progressIsCurrent = false
            if case MemoryFailure.rejected(let status, _) = error { captured.state = status == 409 ? .conflict : .unavailable }
            else {
                switch work.kind {
                case .originals: captured.state = .recoveryUnavailable
                case .submit, .query: captured.state = .unknown
                }
            }
            notify()
        }
    }
}
