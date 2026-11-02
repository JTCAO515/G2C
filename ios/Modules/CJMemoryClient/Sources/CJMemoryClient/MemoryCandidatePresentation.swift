import Foundation
import Observation

public enum MemoryCandidateState: Sendable, Equatable {
    case unconfigured, unselected, unread, loading, ready, invalidReview, changing, reconciling, unknown, conflict, unavailable, recoveryUnavailable
    public var isBusy: Bool { self == .loading || self == .changing || self == .reconciling }
}
public struct MemoryCandidateEditorEntry: Identifiable, Sendable {
    public let id: UUID
    public let candidate: MemoryCandidate
    fileprivate let slot: UUID
    fileprivate let request: UUID
}
public struct MemoryCandidatePresentationWork: Sendable {
    fileprivate enum Kind: Sendable {
        case discover(MemoryCandidateJobsRead?), candidates(MemoryCandidateJobsRead, MemoryCandidateJob)
        case review(MemoryCandidateWork), query(MemoryCandidateOriginal), originals
    }
    fileprivate let slot: UUID
    fileprivate let request: UUID
    fileprivate let kind: Kind
}

/// Installs a complete original scope before notifying Observation. A result from
/// an old account/conversation cannot write the replacement presentation slot.
@MainActor @Observable public final class MemoryCandidatePresentation {
    private final class Slot {
        let id = UUID()
        let binding: MemoryBinding?
        let conversation: String?
        var request = UUID(), started: UUID?
        var state: MemoryCandidateState
        var pages: [MemoryCandidateJobsRead] = []
        var source: MemoryCandidateJobsRead?
        var selectedProducer: MemoryCandidateJob?
        var read: MemoryCandidatesRead?
        var original: MemoryCandidateOriginal?
        var receipt: MemoryCandidateReceipt?
        var rejection: (Int, String)?
        var originals: [MemoryCandidateOriginal] = []
        init(binding: MemoryBinding?, conversation: String?, configured: Bool) {
            self.binding = binding; self.conversation = conversation
            state = !configured || binding == nil ? .unconfigured : conversation == nil ? .unselected : .unread
        }
    }
    private let client: MemoryCandidateClient?
    @ObservationIgnored private var slot: Slot
    @ObservationIgnored private var notifying = false
    private var signal = UUID()
    public init(client: MemoryCandidateClient?) { self.client = client; slot = Slot(binding: nil, conversation: nil, configured: client != nil) }
    private func notify() {
        guard !notifying else { return }; notifying = true; defer { notifying = false }; signal = UUID()
    }
    public var state: MemoryCandidateState { _ = signal; return slot.state }
    public var conversationID: String? { _ = signal; return slot.conversation }
    public var jobs: [MemoryCandidateJob] { _ = signal; return slot.pages.flatMap(\.page.jobs) }
    public var candidates: [MemoryCandidate] { _ = signal; return slot.read?.page.candidates ?? [] }
    public var producer: MemoryCandidateJob? { _ = signal; return slot.selectedProducer }
    public var original: MemoryCandidateOriginal? { _ = signal; return slot.original }
    public var historicalReceipt: MemoryCandidateReceipt? { _ = signal; return slot.receipt }
    public var rejectionStatus: Int? { _ = signal; return slot.rejection?.0 }
    public var pendingActions: [MemoryCandidateOriginal] { _ = signal; return slot.originals }
    public var canRead: Bool { _ = signal; return client != nil && slot.binding != nil && slot.conversation != nil && !slot.state.isBusy }
    public var hasMore: Bool { _ = signal; return canRead && slot.pages.last?.page.nextAfterJobID != nil }
    public func canReview(candidateID: String) -> Bool {
        _ = signal
        return (slot.state == .ready || slot.state == .invalidReview) && slot.read?.page.candidates.contains(where: { same($0.id, candidateID) && $0.status == .candidate }) == true
    }
    public func replace(binding: MemoryBinding?, conversationID: String?) {
        client?.invalidate(); slot = Slot(binding: binding, conversation: conversationID, configured: client != nil); notify()
    }
    private func matches(_ work: MemoryCandidatePresentationWork) -> Bool { slot.id == work.slot && slot.request == work.request }
    private func current(_ work: MemoryCandidatePresentationWork) -> Bool {
        guard matches(work), let binding = slot.binding, let client else { return false }
        return client.isCurrent(binding: binding, conversation: slot.conversation) && matches(work)
    }
    private func prepare() -> Slot? {
        let captured = slot
        guard let binding = captured.binding, let client, !captured.state.isBusy else { return nil }
        let request = UUID(); captured.request = request; captured.started = nil
        guard client.isCurrent(binding: binding, conversation: captured.conversation), slot === captured,
              captured.request == request, !captured.state.isBusy else { return nil }
        return captured
    }
    public func prepareDiscovery(more: Bool = false) -> MemoryCandidatePresentationWork? {
        guard canRead, !more || hasMore, let captured = prepare() else { return nil }
        let after = more ? captured.pages.last : nil
        if !more { captured.pages = []; captured.read = nil; captured.source = nil; captured.selectedProducer = nil }
        captured.state = .loading
        let work = MemoryCandidatePresentationWork(slot: captured.id, request: captured.request, kind: .discover(after))
        notify(); return work
    }
    public func prepareCandidates(producer: MemoryCandidateJob) -> MemoryCandidatePresentationWork? {
        guard canRead, let captured = prepare(), let source = captured.pages.first(where: { $0.page.jobs.contains(producer) }) else { return nil }
        captured.read = nil; captured.state = .loading
        let work = MemoryCandidatePresentationWork(slot: captured.id, request: captured.request, kind: .candidates(source, producer))
        notify(); return work
    }
    public func captureReview(candidateID: String) -> MemoryCandidateEditorEntry? {
        let captured = slot, request = captured.request
        guard canReview(candidateID: candidateID), let client, let binding = captured.binding,
              client.isCurrent(binding: binding, conversation: captured.conversation), slot === captured, captured.request == request,
              let candidate = captured.read?.page.candidates.first(where: { same($0.id, candidateID) }) else { return nil }
        return .init(id: UUID(), candidate: candidate, slot: captured.id, request: request)
    }
    public func canReview(entry: MemoryCandidateEditorEntry) -> Bool {
        entry.slot == slot.id && entry.request == slot.request && canReview(candidateID: entry.candidate.id)
    }
    public func prepareReview(entry: MemoryCandidateEditorEntry, review: MemoryCandidateReview) -> MemoryCandidatePresentationWork? {
        guard canReview(entry: entry) else { return nil }
        return prepareReview(candidateID: entry.candidate.id, review: review)
    }
    public func prepareReview(candidateID: String, review: MemoryCandidateReview) -> MemoryCandidatePresentationWork? {
        let originalRequest = slot.request
        guard canReview(candidateID: candidateID), let captured = prepare(), let read = captured.read, let client else { return nil }
        let request = captured.request
        do {
            let action = try client.prepareReview(read: read, candidateID: candidateID, review: review)
            guard slot === captured, captured.request == request else { return nil }
            captured.original = action.original; captured.receipt = nil; captured.rejection = nil
            captured.read = nil; captured.state = .changing
            let work = MemoryCandidatePresentationWork(slot: captured.id, request: captured.request, kind: .review(action))
            notify(); return work
        } catch {
            guard slot === captured, captured.request == request else { return nil }
            if error as? MemoryFailure == .invalidInput {
                captured.request = originalRequest; captured.state = .invalidReview
            } else {
                captured.read = nil
                captured.state = error as? MemoryFailure == .pendingRequiresQuery ? .unknown : .recoveryUnavailable
            }
            notify(); return nil
        }
    }
    public func prepareOriginals() -> MemoryCandidatePresentationWork? {
        guard let captured = prepare() else { return nil }
        captured.state = .loading
        let work = MemoryCandidatePresentationWork(slot: captured.id, request: captured.request, kind: .originals)
        notify(); return work
    }
    public func selectOriginal(actionID: String) {
        let captured = slot
        guard !captured.state.isBusy, let original = captured.originals.first(where: { same($0.actionID, actionID) }) else { return }
        client?.retireReads(); captured.request = UUID(); captured.started = nil
        captured.pages = []; captured.source = nil; captured.read = nil; captured.selectedProducer = nil
        captured.original = original; captured.receipt = nil; captured.rejection = nil; captured.state = .unknown
        notify()
    }
    public func prepareQuery() -> MemoryCandidatePresentationWork? {
        guard let original = slot.original, let captured = prepare() else { return nil }
        captured.state = .reconciling
        let work = MemoryCandidatePresentationWork(slot: captured.id, request: captured.request, kind: .query(original))
        notify(); return work
    }
    public func perform(_ work: MemoryCandidatePresentationWork) async {
        guard current(work), let client else { return }
        let captured = slot
        guard captured.started != work.request, let binding = captured.binding else { return }
        captured.started = work.request
        do {
            switch work.kind {
            case .discover(let after):
                guard let conversation = captured.conversation else { throw MemoryFailure.staleBinding }
                let page = try await client.discover(binding: binding, conversation: conversation, after: after)
                guard current(work) else { return }
                captured.pages.append(page); captured.state = .ready
            case .candidates(let source, let producer):
                let read = try await client.candidates(from: source, producer: producer)
                guard current(work) else { return }
                captured.source = source; captured.selectedProducer = producer; captured.read = read; captured.state = .ready
            case .originals:
                let records = try client.originals(binding: binding)
                guard current(work) else { return }
                captured.originals = records; captured.state = captured.original == nil ? .unread : .unknown
            case .review(let action):
                let result = try await client.perform(action)
                try await apply(result, work: work, client: client)
                return
            case .query(let original):
                let result = try await client.query(original)
                try await apply(result, work: work, client: client)
                return
            }
            notify()
        } catch {
            guard current(work) else { return }
            captured.read = nil
            if captured.receipt != nil { captured.state = .unavailable }
            else if case MemoryFailure.rejected(let status, let code) = error {
                captured.rejection = (status, code); captured.state = status == 409 ? .conflict : .unavailable
            } else {
                switch work.kind {
                case .review, .query: captured.state = .unknown
                case .originals: captured.state = .recoveryUnavailable
                case .discover, .candidates: captured.state = .unavailable
                }
            }
            notify()
        }
    }
    private func apply(_ result: MemoryCandidateResult, work: MemoryCandidatePresentationWork, client: MemoryCandidateClient) async throws {
        guard current(work) else { return }
        let captured = slot
        switch result {
        case .recorded(let receipt):
            captured.receipt = receipt; captured.rejection = nil
            // The receipt is historical. Only this fresh protected read installs
            // a current candidate projection; failure preserves the known result.
            if let source = captured.source, let producer = captured.selectedProducer {
                let read = try await client.candidates(from: source, producer: producer)
                guard current(work) else { return }
                captured.read = read; captured.state = .ready
            } else { captured.state = .unread }
        case .notObserved: captured.read = nil; captured.state = .unknown
        case .rejected(let status, let code):
            captured.read = nil; captured.rejection = (status, code); captured.state = status == 409 ? .conflict : .unavailable
        }
        notify()
    }
}
