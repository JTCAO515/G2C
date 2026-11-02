import Foundation
import Testing
import CJAuth
import CJSession
import CJManualPreviewClient
import CJMessageClient
import CJTripClient
@testable import CJShell

@MainActor private final class StubRead {}
private struct StubAction: CandidateAction, Sendable { let actionID: String }
private struct StubReceipt: CandidateReceipt { let isAcceptance: Bool }
private struct StubFailure: Error {}

@MainActor private final class StubClient: CandidateDecisionClient {
    typealias Decision = CandidateDecision<StubReceipt>
    var originals = [StubAction(actionID: "original")]
    var originalsFail = false
    var result: Decision = .unknown
    var queryFails = false
    var formalFails = false
    var formalReads = 0
    var pause: (@MainActor () -> Void)?
    static func source(of original: AcceptedMessageRunReceipt) -> String? { nil }
    func discover(original: String, validateOriginal: @escaping @MainActor () throws -> Void) async throws -> StubRead { StubRead() }
    func validateRead(_ read: StubRead) throws {}
    func originalActions() throws -> [StubAction] {
        if originalsFail { throw StubFailure() }
        return originals
    }
    func stage(_ kind: Bool, read: StubRead) throws -> StubAction { StubAction(actionID: "staged") }
    func perform(_ work: StubAction) async throws -> Decision { result }
    func queryOriginal(_ id: String) async throws -> Decision {
        pause?()
        if queryFails { throw StubFailure() }
        return result
    }
    func readFormal(for receipt: StubReceipt) async throws -> StructuredTripRecord? {
        formalReads += 1
        if formalFails { throw StubFailure() }
        return nil
    }
}

@Suite @MainActor struct CandidateDecisionHostTests {
    private func make() throws -> (AssistantMessageHost, StubClient, CandidateDecisionHost<StubClient>) {
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: "candidate-host-" + UUID().uuidString)))
        let messages = AssistantMessageHost(shell: shell), client = StubClient()
        return (messages, client, CandidateDecisionHost(messages: messages, client: client))
    }
    private func query(_ host: CandidateDecisionHost<StubClient>) async throws {
        host.loadOriginals()
        let work = try #require(host.prepareQuery("original"))
        #expect(host.activity == .reading && host.busy && host.actionID == "original")
        await work()
    }

    @Test func acceptedOriginalReadsFormalOnce() async throws {
        let (messages, client, host) = try make()
        client.result = .confirmed(StubReceipt(isAcceptance: true))
        try await query(host)
        #expect(host.activity == .ready && host.receipt?.isAcceptance == true && client.formalReads == 1 && !host.formalUnavailable)
        withExtendedLifetime(messages) {}
    }

    @Test func rejectedOriginalNeverReadsFormal() async throws {
        let (messages, client, host) = try make()
        client.result = .confirmed(StubReceipt(isAcceptance: false))
        try await query(host)
        #expect(host.activity == .ready && host.receipt?.isAcceptance == false && client.formalReads == 0)
        withExtendedLifetime(messages) {}
    }

    @Test func formalFailureKeepsTheConfirmedReceipt() async throws {
        let (messages, client, host) = try make()
        client.result = .confirmed(StubReceipt(isAcceptance: true)); client.formalFails = true
        try await query(host)
        #expect(host.activity == .ready && host.receipt != nil && host.formalUnavailable)
        withExtendedLifetime(messages) {}
    }

    @Test func rejectionMapsConflictSeparately() async throws {
        for (status, expected) in [(409, CandidateActivity.conflict), (503, .unavailable)] {
            let (messages, client, host) = try make()
            client.result = .rejected(status)
            try await query(host)
            #expect(host.activity == expected && host.receipt == nil)
            withExtendedLifetime(messages) {}
        }
    }

    @Test func unknownAndFailedQueriesStayUnknown() async throws {
        for fails in [false, true] {
            let (messages, client, host) = try make()
            client.result = .unknown; client.queryFails = fails
            try await query(host)
            #expect(host.activity == .unknown && host.receipt == nil && client.formalReads == 0)
            withExtendedLifetime(messages) {}
        }
    }

    @Test func onlyListedIdleOriginalsCanBeQueried() throws {
        let (messages, _, host) = try make()
        #expect(host.prepareQuery("original") == nil)
        host.loadOriginals()
        #expect(host.prepareQuery("other") == nil)
        #expect(host.prepareQuery("original") != nil)
        #expect(host.prepareQuery("original") == nil, "A busy host admits no second query")
        withExtendedLifetime(messages) {}
    }

    @Test func clearedSelectionDiscardsTheLateResult() async throws {
        let (messages, client, host) = try make()
        client.result = .confirmed(StubReceipt(isAcceptance: true))
        client.pause = { host.clearSelection() }
        try await query(host)
        #expect(host.activity == .idle && host.receipt == nil && client.formalReads == 0)
        withExtendedLifetime(messages) {}
    }

    @Test func originalsFailureClearsTheList() throws {
        let (messages, client, host) = try make()
        host.loadOriginals()
        #expect(host.actions.count == 1)
        client.originalsFail = true
        host.loadOriginals()
        #expect(host.actions.isEmpty && host.activity == .unavailable)
        withExtendedLifetime(messages) {}
    }

    @Test func discoveryNeedsAnAcceptedOriginal() throws {
        let (messages, _, host) = try make()
        #expect(host.prepareDiscovery() == nil && host.activity == .idle && host.read == nil)
        withExtendedLifetime(messages) {}
    }
}
