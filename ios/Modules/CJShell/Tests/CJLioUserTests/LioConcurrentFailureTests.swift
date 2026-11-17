import CJMessageClient
@testable import CJMessageHTTP
import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJLioUser

@MainActor private final class FailureScope: MessageCredentialsProvider, SecureMessageStorage {
    var active = true
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {}
    func validate() throws { if !active { throw RecoveryError.inactive } }
}
private actor FailureBodyGate {
    private var arrival: Bool?
    private var arrivalWaiter: CheckedContinuation<Bool, Never>?
    private var continuation: CheckedContinuation<Void, Never>?

    func waitForBody() async -> Bool {
        if let arrival { return arrival }
        return await withCheckedContinuation { arrivalWaiter = $0 }
    }

    func wait() async {
        arrival = true
        arrivalWaiter?.resume(returning: true); arrivalWaiter = nil
        await withCheckedContinuation { continuation = $0 }
    }

    func requestFinished() {
        guard arrival == nil else { return }
        arrival = false
        arrivalWaiter?.resume(returning: false); arrivalWaiter = nil
    }

    func release() { continuation?.resume(); continuation = nil }
}

private struct DelayedFailureBody: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let gate: FailureBodyGate
    struct AsyncIterator: AsyncIteratorProtocol {
        let gate: FailureBodyGate
        var sent = false
        mutating func next() async throws -> ArraySlice<UInt8>? {
            guard !sent else { return nil }; sent = true
            await gate.wait()
            return Array("{}".utf8)[...]
        }
    }
    func makeAsyncIterator() -> AsyncIterator { .init(gate: gate) }
}
private actor ConcurrentFailureTransport: ClientTransport {
    let gate: FailureBodyGate
    let secondStatus: HTTPResponse.Status
    let secondReferences: [String]
    let secondBody: Data
    private(set) var methods: [HTTPRequest.Method] = []
    init(gate: FailureBodyGate, secondStatus: HTTPResponse.Status = .serviceUnavailable,
         secondReferences: [String] = ["C95744FC-F460-4ED1-B21B-A64D5D34896C"],
         secondBody: Data = Data("{}".utf8)) {
        self.gate = gate
        self.secondStatus = secondStatus
        self.secondReferences = secondReferences
        self.secondBody = secondBody
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        methods.append(request.method)
        let first = request.path?.contains("before=first") == true
        var response = HTTPResponse(status: first ? .ok : secondStatus)
        response.headerFields[.contentType] = "application/json"
        let references = first ? ["B95744FC-F460-4ED1-B21B-A64D5D34896C"] : secondReferences
        for reference in references {
            response.headerFields.append(.init(name: HTTPField.Name("X-Request-ID")!, value: reference))
        }
        return (response, first ? HTTPBody(DelayedFailureBody(gate: gate), length: .unknown, iterationBehavior: .single) : HTTPBody(secondBody))
    }
}

@MainActor private struct RecordedFailureFixture {
    let defaults: UserDefaults
    let notes: LioDiagnosticLog
    let service: LioService

    init(response: ConcurrentFailureTransport) throws {
        let scope = try StorageScope(environment: "synthetic-diagnostic-records", account: "synthetic-owner")
        let boundary = FailureScope()
        let recovery = MessageRecovery(storage: boundary), lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16384, maximumResponseBytes: 65536)
        let transport = try NoRedirectTransport(interceptedTransport: response, messageEndpoint: endpoint,
                                                validateMessage: { try boundary.validate() }, lio: true)
        let client = LioTimelineHTTP(scope: scope, lease: lease, credentials: boundary, transport: transport)
        let defaults = try #require(UserDefaults(suiteName: "synthetic-problem-notes-" + UUID().uuidString))
        let notes = LioDiagnosticLog(defaults: defaults, build: "47")
        self.defaults = defaults
        self.notes = notes
        service = LioService.signedTimeline(client, readFailed: { notes.record(error: $0, stage: .timeline) })
    }
}

@MainActor struct LioConcurrentFailureTests {
    enum TraceShape: Sendable, CaseIterable { case valid, malformed, duplicate }

    @Test(arguments: TraceShape.allCases)
    func unreadableRepliesKeepSafeNotesWithoutCopyingPrivateErrorData(trace: TraceShape) async throws {
        let reference = "C95744FC-F460-4ED1-B21B-A64D5D34896C"
        let references: [String]
        switch trace {
        case .valid: references = [reference]
        case .malformed: references = ["SYNTHETIC-PRIVATE-HEADER"]
        case .duplicate: references = [reference, "B95744FC-F460-4ED1-B21B-A64D5D34896C"]
        }
        let privateValues = ["SYNTHETIC-PRIVATE-TEXT", "SYNTHETIC-PRIVATE-TOKEN",
                             "https://synthetic.invalid/SYNTHETIC-PRIVATE-URL",
                             "SYNTHETIC-ORIGINAL-CID", "SYNTHETIC-ORIGINAL-MID", "SYNTHETIC-PRIVATE-HEADER"]
        let body = try JSONSerialization.data(withJSONObject: ["answer": privateValues[0], "token": privateValues[1],
            "url": privateValues[2], "conversation_id": privateValues[3], "message_id": privateValues[4]])
        let response = ConcurrentFailureTransport(gate: FailureBodyGate(), secondStatus: .ok,
                                                   secondReferences: references, secondBody: body)
        let fixture = try RecordedFailureFixture(response: response)
        let defaults = fixture.defaults, notes = fixture.notes
        let earlier = try #require(fixture.service.earlier)
        do {
            _ = try await earlier("private-response")
            Issue.record("An unreadable response must not become an empty successful history")
        } catch {
            let problem = try #require(error as? LioRequestProblem)
            #expect(problem.cause == .responseFormat && problem.diagnosis.category == .unclear)
            #expect(problem.diagnosis.httpStatus == 200)
        }
        #expect(await response.methods == [.get])
        #expect(notes.entries.count == 1)
        let reply = try #require(notes.entries.first)
        #expect(reply.cause == .responseFormat && reply.stage == .timeline && reply.origin == .timeline)
        #expect(reply.reference == (trace == .valid ? reference : nil))

        notes.record(error: URLError(.cannotConnectToHost, userInfo: [NSLocalizedDescriptionKey: privateValues[0],
            NSURLErrorFailingURLStringErrorKey: privateValues[2], "token": privateValues[1],
            "conversation_id": privateValues[3], "message_id": privateValues[4]]), stage: .history)
        #expect(notes.entries.count == 2)
        #expect(notes.entries.first?.cause == .network && notes.entries.first?.origin == .history)
        #expect(notes.entries.first?.errorCode == -1004)
        let stored = try #require(defaults.data(forKey: "g2c.lio.problem-notes.v1"))
        let entries = try #require(JSONSerialization.jsonObject(with: stored) as? [[String: Any]])
        let allowed: Set<String> = ["category", "stage", "request", "httpStatus", "reference", "time", "build",
                                   "origin", "cause", "errorCode"]
        for entry in entries { #expect(Set(entry.keys).isSubset(of: allowed)) }
        let texts = [try #require(String(data: stored, encoding: .utf8)), notes.text(.english), notes.text(.chinese)]
        for text in texts {
            for value in privateValues { #expect(!text.contains(value)) }
        }
        #expect(LioDiagnosticLog(defaults: defaults, build: "47").entries == notes.entries)
    }

    @Test func aConflictingReadKeepsItsOwnStatusAndReferenceInProblemNotes() async throws {
        let response = ConcurrentFailureTransport(gate: FailureBodyGate(), secondStatus: .conflict)
        let fixture = try RecordedFailureFixture(response: response)
        let defaults = fixture.defaults, notes = fixture.notes
        let earlier = try #require(fixture.service.earlier)
        do {
            _ = try await earlier("conflict")
            Issue.record("A conflicting read must not become a successful or empty history")
        } catch {
            let problem = try #require(error as? LioRequestProblem)
            #expect(problem.cause == .http && problem.diagnosis.category == .unclear)
        }
        #expect(await response.methods == [.get])
        let entry = try #require(notes.entries.first)
        #expect(notes.entries.count == 1)
        #expect(entry.stage == .timeline && entry.origin == .timeline && entry.request == "timeline")
        #expect(entry.httpStatus == 409 && entry.cause == .http)
        #expect(entry.reference == "C95744FC-F460-4ED1-B21B-A64D5D34896C")
        #expect(LioDiagnosticLog(defaults: defaults, build: "47").entries == notes.entries)
        for language in [LioLanguage.english, .chinese] {
            let copied = notes.text(language)
            #expect(copied.contains("HTTP 409") && copied.contains("origin=timeline") && copied.contains("cause=http"))
            #expect(copied.contains("ref C95744FC-F460-4ED1-B21B-A64D5D34896C"))
        }
    }

    @Test func overlappingReadsKeepTheirOwnResponseReference() async throws {
        let scope = try StorageScope(environment: "synthetic-overlap", account: "synthetic-owner")
        let boundary = FailureScope(), gate = FailureBodyGate()
        let recovery = MessageRecovery(storage: boundary), lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16384, maximumResponseBytes: 65536)
        let transport = try NoRedirectTransport(interceptedTransport: ConcurrentFailureTransport(gate: gate),
            messageEndpoint: endpoint, validateMessage: { try boundary.validate() }, lio: true)
        let client = LioTimelineHTTP(scope: scope, lease: lease, credentials: boundary, transport: transport)
        let service = LioService.signedTimeline(client)
        let earlier = try #require(service.earlier)
        let first = Task { () -> LioRequestProblem? in
            let problem: LioRequestProblem?
            do { _ = try await earlier("first"); Issue.record("Expected local revocation"); problem = nil }
            catch { problem = error as? LioRequestProblem }
            await gate.requestFinished()
            return problem
        }
        guard await gate.waitForBody() else {
            _ = await first.value
            Issue.record("First request finished before its response body arrived")
            return
        }
        do { _ = try await earlier("second"); Issue.record("Expected HTTP 503") }
        catch {
            let problem = try #require(error as? LioRequestProblem)
            #expect(problem.diagnosis.httpStatus == 503)
            #expect(problem.diagnosis.serverReference == "C95744FC-F460-4ED1-B21B-A64D5D34896C")
        }
        boundary.active = false
        await gate.release()
        let problem = try #require(await first.value)
        #expect(problem.cause == .inactiveSession)
        #expect(problem.diagnosis.httpStatus == 200)
        #expect(problem.diagnosis.serverReference == "B95744FC-F460-4ED1-B21B-A64D5D34896C")
    }
}
