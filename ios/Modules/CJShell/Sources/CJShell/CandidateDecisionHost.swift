import Foundation
import Observation
import CJManualPreviewClient
import CJMessageHTTP
import CJTripClient

public enum CandidateActivity: Equatable { case idle, reading, deciding, ready, unknown, conflict, unavailable }
public typealias NeedsPlanningActivity = CandidateActivity
public typealias ScopedCandidateActivity = CandidateActivity
public typealias NeedsPlanningHost = CandidateDecisionHost<NeedsPlanningClient>
public typealias ScopedCandidateHost = CandidateDecisionHost<ScopedTripClient>

@MainActor public protocol CandidateAction { var actionID: String { get } }
public protocol CandidateReceipt: Sendable { var isAcceptance: Bool { get } }

/// The surface one candidate flow exposes to its host: protected read, one
/// explicit decision, original-only recovery and the formal read after accept.
@MainActor public protocol CandidateDecisionClient: AnyObject {
    associatedtype Source: Sendable
    associatedtype Read: AnyObject
    associatedtype Kind
    associatedtype Work: CandidateAction
    associatedtype Display: CandidateAction
    associatedtype Receipt: CandidateReceipt
    static func source(of original: AcceptedMessageRunReceipt) -> Source?
    func discover(original: Source, validateOriginal: @escaping @MainActor () throws -> Void) async throws -> Read
    func validateRead(_ read: Read) throws
    func originalActions() throws -> [Display]
    func stage(_ kind: Kind, read: Read) throws -> Work
    func perform(_ work: Work) async throws -> CandidateDecision<Receipt>
    func queryOriginal(_ id: String) async throws -> CandidateDecision<Receipt>
    func readFormal(for receipt: Receipt) async throws -> StructuredTripRecord?
}

extension NeedsPlanningWork: CandidateAction {}
extension NeedsPlanningOriginalDisplay: CandidateAction {}
extension NeedsPlanningReceipt: CandidateReceipt { public var isAcceptance: Bool { kind == .accept } }
extension NeedsPlanningClient: CandidateDecisionClient {
    public static func source(of original: AcceptedMessageRunReceipt) -> AcceptedTravelMessageSource? { original.planningSource }
}
extension ScopedDecisionWork: CandidateAction {}
extension ScopedOriginalDisplay: CandidateAction {}
extension ScopedActionReceipt: CandidateReceipt { public var isAcceptance: Bool { kind == .accept } }
extension ScopedTripClient: CandidateDecisionClient {
    public static func source(of original: AcceptedMessageRunReceipt) -> MessageEditReference? { original.editReference }
}

@MainActor @Observable public final class CandidateDecisionHost<Client: CandidateDecisionClient> {
    @ObservationIgnored private weak var messages: AssistantMessageHost?
    @ObservationIgnored private let client: Client
    private var revision = UUID()
    private var storedRead: Client.Read?
    private var original: AcceptedMessageRunReceipt?
    public private(set) var activity: CandidateActivity = .idle
    public private(set) var actions: [Client.Display] = []
    public private(set) var actionID: String?
    public private(set) var receipt: Client.Receipt?
    public private(set) var formal: StructuredTripRecord?
    public private(set) var formalUnavailable = false
    public var busy: Bool { activity == .reading || activity == .deciding }
    init(messages: AssistantMessageHost, client: Client) { self.messages = messages; self.client = client }
    public var read: Client.Read? {
        guard let captured = storedRead, let original, original.isCurrent(),
              (try? client.validateRead(captured)) != nil, original.isStillOwned(), storedRead === captured else { return nil }
        return captured
    }
    public func clearSelection() { revision = UUID(); storedRead = nil; original = nil; actionID = nil; receipt = nil; formal = nil; formalUnavailable = false; activity = .idle }
    public func invalidate() { clearSelection(); actions = []; actionID = nil; receipt = nil; formal = nil }
    public func prepareDiscovery() -> (@MainActor () async -> Void)? {
        guard !busy, let original = messages?.captureAcceptedRunReceipt(), let reference = Client.source(of: original) else { return nil }
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
    public func prepareDecision(_ kind: Client.Kind, read: Client.Read) -> (@MainActor () async -> Void)? {
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
    private func apply(_ result: CandidateDecision<Client.Receipt>, token: UUID) async {
        switch result {
        case .unknown: activity = .unknown
        case .rejected(let status): activity = status == 409 ? .conflict : .unavailable
        case .confirmed(let value):
            receipt = value; activity = .ready; formalUnavailable = false
            if value.isAcceptance {
                do {
                    let current = try await client.readFormal(for: value)
                    guard revision == token else { return }
                    formal = current
                } catch { guard revision == token else { return }; formalUnavailable = true }
            }
        }
    }
}
