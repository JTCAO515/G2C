import Foundation
import Observation
import CJManualPreviewClient
import CJTripClient

public enum NeedsPlanningActivity: Equatable { case idle, reading, deciding, ready, unknown, conflict, unavailable }
@MainActor @Observable public final class NeedsPlanningHost {
    @ObservationIgnored private weak var messages: AssistantMessageHost?
    @ObservationIgnored private let client: NeedsPlanningClient
    private var revision = UUID()
    private var storedRead: NeedsPlanningRead?
    private var original: AcceptedMessageRunReceipt?
    public private(set) var activity: NeedsPlanningActivity = .idle
    public private(set) var actions: [NeedsPlanningOriginalDisplay] = []
    public private(set) var actionID: String?
    public private(set) var receipt: NeedsPlanningReceipt?
    public private(set) var formal: StructuredTripRecord?
    public private(set) var formalUnavailable = false
    public var busy: Bool { activity == .reading || activity == .deciding }
    init(messages: AssistantMessageHost, client: NeedsPlanningClient) { self.messages = messages; self.client = client }
    public var read: NeedsPlanningRead? {
        guard let captured = storedRead, let original, original.isCurrent(),
              (try? client.validateRead(captured)) != nil, original.isStillOwned(), storedRead === captured else { return nil }
        return captured
    }
    public func clearSelection() { revision = UUID(); storedRead = nil; original = nil; actionID = nil; receipt = nil; formal = nil; formalUnavailable = false; activity = .idle }
    public func invalidate() { clearSelection(); actions = []; actionID = nil; receipt = nil; formal = nil }
    public func prepareDiscovery() -> (@MainActor () async -> Void)? {
        guard !busy, let original = messages?.captureAcceptedRunReceipt(), let reference = original.planningSource else { return nil }
        let token = UUID(); revision = token; self.original = original; storedRead = nil; activity = .reading
        return { [weak self] in
            guard let self else { return }
            do {
                let read = try await client.discover(original: reference) { [weak self] in
                    guard let self, self.revision == token, original.isCurrent(), original.isStillOwned(), self.revision == token else { throw PreviewFailure.retired }
                }
                guard revision == token, original.isStillOwned() else { return }
                storedRead = read; activity = .ready
            } catch {
                guard revision == token, original.isStillOwned() else { return }
                activity = .unavailable
            }
        }
    }
    public func prepareDecision(_ kind: NeedsPlanningAction.Kind, read: NeedsPlanningRead) -> (@MainActor () async -> Void)? {
        guard !busy, self.read === read else { return nil }
        do {
            let work = try client.stage(kind, read: read)
            let token = revision
            actionID = work.actionID; receipt = nil; formal = nil; activity = .deciding
            actions = try client.originalActions()
            return { [weak self] in
                guard let self else { return }
                do {
                    let result = try await client.perform(work)
                    guard revision == token else { return }
                    await apply(result, token: token)
                } catch {
                    guard revision == token else { return }
                    activity = (error as? PreviewFailure) == .conflict ? .conflict : .unknown
                }
            }
        } catch { activity = (error as? PreviewFailure) == .conflict ? .conflict : .unknown; return nil }
    }
    public func loadOriginals() {
        guard !busy else { return }
        do { actions = try client.originalActions() }
        catch { actions = []; activity = .unavailable }
    }
    public func prepareQuery(_ id: String) -> (@MainActor () async -> Void)? {
        guard !busy, actions.contains(where: { $0.actionID == id }) else { return nil }
        let token = UUID(); revision = token; storedRead = nil; original = nil
        actionID = id; receipt = nil; formal = nil; activity = .reading
        return { [weak self] in
            guard let self else { return }
            do {
                let result = try await client.queryOriginal(id)
                guard revision == token else { return }
                await apply(result, token: token)
            } catch { guard revision == token else { return }; activity = .unknown }
        }
    }
    private func apply(_ result: NeedsPlanningResult, token: UUID) async {
        switch result {
        case .unknown: activity = .unknown
        case .rejected(let status): activity = status == 409 ? .conflict : .unavailable
        case .confirmed(let value):
            receipt = value; activity = .ready; formalUnavailable = false
            if value.kind == .accept {
                do {
                    let current = try await client.readFormal(for: value)
                    guard revision == token else { return }
                    formal = current
                } catch { guard revision == token else { return }; formalUnavailable = true }
            }
        }
    }
}
