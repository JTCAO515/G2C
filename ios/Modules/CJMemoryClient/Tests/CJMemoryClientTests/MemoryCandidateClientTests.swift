import Foundation
import Observation
import CryptoKit
import Testing
import CJSession
import CJMessageKeys
import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime
@testable import CJMemoryClient

private let ccTrace = "11111111-1111-4111-8111-111111111461"
@MainActor private final class CandidateSDKStore: SessionPersistence {
    var material: SessionMaterial?
    func load() throws -> SessionMaterial? { material }
    func save(_ material: SessionMaterial) throws { self.material = material }
    func clearAndBlock() throws { material = nil }
}
@MainActor private final class CandidateServer {
    var requests: [(String, String, Data?)] = []
    var receipt: [String: Any]?
    var conversation = "chat-A", jobID = "producer-job", attemptID = "original-attempt"
    var loseACK = false, nullReceipt = false, nullAction = false
    var status = "candidate", wrongProducer = false, serviceUnavailable = false, conflict = false
    var beforePost: ((Data) throws -> Void)?
    var after: (() -> Void)?
    func respond(_ request: HTTPRequest, raw: Data?, operation: String) throws -> (HTTPResponse, HTTPBody?) {
        requests.append((operation, request.path!, raw))
        #expect(request.headerFields[.authorization] == "Bearer SYNTHETIC.CANDIDATE.SDK")
        var code = 200
        let value: [String: Any]
        if serviceUnavailable {
            code = 503
            value = ["request_id": ccTrace, "error": ["code":"DEPENDENCY_UNAVAILABLE","category":"dependency","message_en":"Unknown","message_zh":"未知","outcome":"unknown","recovery":"reconcile_original"]]
        } else {
            switch operation {
            case "readMemoryCandidateJobsV1":
                value = ["version":"MEMORY-CANDIDATE-JOBS@1","request_id":ccTrace,"result":["conversation_id":conversation,"jobs":[["job_id":jobID,"attempt_id":attemptID]],"next_after_job_id":NSNull()]]
            case "readMemoryCandidatesV1":
                value = ["version":"MEMORY-CANDIDATE-list@1","request_id":ccTrace,"result":["job_id":wrongProducer ? "other-job" : jobID,"attempt_id":attemptID,"memory_epoch":2,"candidates":[[
                    "candidate_id":"candidate-中文","version":1,"status":status,"subject":"traveler","slot":"food","kind":status == "active" ? "preference" : "inference","text":"不吃辣","extent":"long_term","occurred_at":"时间不详","context":NSNull()]]]]
            case "applyMemoryCandidateActionV1":
                let bytes = try #require(raw); try beforePost?(bytes)
                if conflict {
                    code = 409
                    value = ["request_id":ccTrace,"error":["code":"MEMORY_CONFLICT","category":"conflict","message_en":"Conflict","message_zh":"冲突","outcome":"failed","recovery":"do_not_retry"]]
                } else {
                    let fields = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
                    let confirmed = fields["operation"] as? String == "confirm"
                    var result: [String: Any] = ["item_id":fields["candidate_id"]!,"version":2,"status":confirmed ? "active" : "rejected"]
                    if confirmed { result["source_id"] = "candidate-confirm-v1:" + digest(bytes); result["source_version"] = 1 }
                    receipt = ["version":"MEMORY-CANDIDATE-result@1","action_id":fields["action_id"]!,"candidate_id":fields["candidate_id"]!,"input_sha256":digest(bytes),"receipt":result]
                    status = confirmed ? "active" : "withdrawn"
                    if loseACK { throw MemoryFailure.exchangeUnknown }
                    value = ["version":"MEMORY-CANDIDATE-response@1","request_id":ccTrace,"result":nullAction ? NSNull() : receipt!]
                }
            case "queryMemoryCandidateReceiptV1":
                value = ["version":"MEMORY-CANDIDATE-response@1","request_id":ccTrace,"result":nullReceipt ? NSNull() : receipt as Any? ?? NSNull()]
            default: throw MemoryFailure.invalidInput
            }
        }
        let callback = after; after = nil; callback?()
        let body = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
        var headers = HTTPFields(); headers[.contentType] = "application/json"; headers[.cacheControl] = "no-store"
        headers[HTTPField.Name("X-Request-ID")!] = ccTrace
        return (HTTPResponse(status: .init(code: code), headerFields: headers), HTTPBody(body))
    }
}
private struct CandidateWire: ClientTransport {
    let server: CandidateServer
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 32768) } else { bytes = nil }
        return try await server.respond(request, raw: bytes, operation: operationID)
    }
}
@MainActor private final class CandidateClientFixture {
    let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cc-" + UUID().uuidString)
    let binding = MemoryBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    let key = SymmetricKey(size: .bits256), keyID = UUID()
    let sdk = CandidateSDKStore(), server = CandidateServer()
    let session: SessionLifecycle
    let operation: SessionOperation
    var selected = "chat-A", current = true
    var credentialCallback: (() -> Void)?
    var store: MemoryCandidatePendingStore!
    var client: MemoryCandidateClient!
    init() throws {
        session = SessionLifecycle(persistence: sdk, restorePolicy: .userInitiatedOnly)
        operation = try session.beginTrustedSDKSave(); try session.save(SessionMaterial(trustedSDKBytes: Data("synthetic-candidate-sdk".utf8)), for: operation)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions:0o700])
        store = try makeStore(); client = try makeClient()
    }
    func makeStore() throws -> MemoryCandidatePendingStore {
        let material = key
        return try MemoryCandidatePendingStore(directory: root, maximumBytes:100000,maximumRecords:100,
            namespace:.init(environment:binding.environment,account:binding.account,purpose:.localMemoryPendingV1),keyID:keyID,key:{material})
    }
    func makeClient() throws -> MemoryCandidateClient {
        let endpoint = try MemoryEndpoint(url: URL(string:"https://candidate-unit.invalid")!,maximumRequestBytes:32768,maximumResponseBytes:524288)
        return MemoryCandidateClient(endpoint:endpoint,credentials:{ [self] captured in
            #expect(captured == binding);let callback=credentialCallback;credentialCallback=nil;callback?();return "SYNTHETIC.CANDIDATE.SDK"
        },currentBinding:{[self] in current ? binding : nil},currentConversation:{[self] in selected},session:session,sessionOperation:operation,pendingStore:store,interceptedTransport:CandidateWire(server:server))
    }
    func read() async throws -> MemoryCandidatesRead {
        let jobs = try await client.discover(binding:binding,conversation:selected)
        return try await client.candidates(from:jobs,producer: #require(jobs.page.jobs.first))
    }
    func dispose() { try? FileManager.default.removeItem(at:root) }
}
@MainActor struct MemoryCandidateClientTests {
    @Test func queryIDsKeepLiteralPlusAndUnicodeThroughTheCanonicalQueryParser() async throws {
        let f = try CandidateClientFixture(); defer { f.dispose() }
        f.selected = "chat+中文"; f.server.conversation = f.selected
        f.server.jobID = "job+e\u{301}"; f.server.attemptID = "attempt+中文"
        let read = try await f.read()
        #expect(read.page.producer.jobID == f.server.jobID)
        let requests = f.server.requests
        #expect(requests.count == 2)
        for (_, path, _) in requests {
            #expect(!path.contains("+")); #expect(path.contains("%2B"))
        }
        let first = try #require(URLComponents(string: requests[0].1)?.queryItems)
        let second = try #require(URLComponents(string: requests[1].1)?.queryItems)
        #expect(first.first(where: { $0.name == "conversation_id" })?.value == f.selected)
        #expect(second.first(where: { $0.name == "job_id" })?.value.map { Data($0.utf8) } == Data(f.server.jobID.utf8))
        #expect(second.first(where: { $0.name == "attempt_id" })?.value == f.server.attemptID)
        #expect(try f.store.records().isEmpty)
    }
    @Test func publicFactoryIsUnavailableOutsideExplicitDebugSimulator() throws {
        #if !DEBUG || !targetEnvironment(simulator)
        let f = try CandidateClientFixture(); defer { f.dispose() }
        let endpoint = try MemoryEndpoint(url: #require(URL(string: "http://127.0.0.1:9000")), maximumRequestBytes: 32768, maximumResponseBytes: 524288, allowLoopbackHTTP: true)
        #expect(throws: MemoryFailure.liveWriteUnavailable) {
            try MemoryCandidateClient(development: endpoint, credentials: { _ in "SYNTHETIC" }, currentBinding: { f.binding },
                currentConversation: { f.selected }, session: f.session, sessionOperation: f.operation, pendingStore: f.store,
                requestTimeout: 1, resourceTimeout: 1)
        }
        #endif
    }
    @Test func genuineDiscoveryPrecedesReviewAndExactOriginalIsDurableBeforePost() async throws {
        let f=try CandidateClientFixture();defer{f.dispose()}
        let read=try await f.read()
        let work=try f.client.prepareReview(read:read,candidateID:"candidate-中文",review:.confirm(kind:.preference,text:"少辣",occurredAt:"时间不详",travel:nil))
        let original=try #require(try f.store.records().first)
        f.server.beforePost={bytes in
            let persisted = try f.store.records()
            #expect(persisted.first?.originalUTF8 == bytes);#expect(bytes == original.originalUTF8)
        }
        guard case .recorded(let receipt)=try await f.client.perform(work) else {Issue.record("No actual original result");return}
        #expect(receipt.active && receipt.inputSHA256 == original.expectedSHA256)
        #expect(f.server.requests.map(\.0)==["readMemoryCandidateJobsV1","readMemoryCandidatesV1","applyMemoryCandidateActionV1"])
        await #expect(throws:MemoryFailure.staleBinding){try await f.client.perform(work)}
        #expect(throws:MemoryFailure.staleBinding){try f.client.prepareReview(read:read,candidateID:"candidate-中文",review:.reject)}
    }
    @Test func lostACKReconstructionAndNullUseOriginalGETWithoutAnotherPost() async throws {
        let f=try CandidateClientFixture();defer{f.dispose()}
        let read=try await f.read(),work=try f.client.prepareReview(read:read,candidateID:"candidate-中文",review:.reject)
        let bytes=try #require(try f.store.records().first?.originalUTF8)
        f.server.loseACK=true
        await #expect(throws:MemoryFailure.exchangeUnknown){try await f.client.perform(work)}
        f.store=try f.makeStore();f.client=try f.makeClient()
        let original=try #require(try f.client.originals(binding:f.binding).first)
        f.server.nullReceipt=true
        guard case .notObserved=try await f.client.query(original) else {Issue.record("Null fabricated a result");return}
        f.server.status="candidate"
        let current=try await f.read()
        #expect(throws:MemoryFailure.pendingRequiresQuery){try f.client.prepareReview(read:current,candidateID:"candidate-中文",review:.reject)}
        f.server.nullReceipt=false
        guard case .recorded(let result)=try await f.client.query(original) else {Issue.record("Original not recovered");return}
        #expect(!result.active)
        #expect(try f.store.records().first?.originalUTF8 == bytes)
        #expect(f.server.requests.filter{$0.0=="applyMemoryCandidateActionV1"}.count==1)
    }
    @Test func callerCannotUseAnotherClientOrInventedProducerReference() async throws {
        let f=try CandidateClientFixture();defer{f.dispose()}
        let jobs=try await f.client.discover(binding:f.binding,conversation:f.selected)
        let other=try f.makeClient()
        await #expect(throws:MemoryFailure.staleBinding){try await other.candidates(from:jobs,producer:#require(jobs.page.jobs.first))}
        let invented=try MemoryCandidateJob(.object(["job_id":.string("invented"),"attempt_id":.string("attempt")]))
        await #expect(throws:MemoryFailure.staleBinding){try await f.client.candidates(from:jobs,producer:invented)}
        #expect(f.server.requests.count==1)
    }
    @Test func credentialsSwitchAndLateResponseCannotPublishOrPrepareForNewSelection() async throws {
        let f=try CandidateClientFixture();defer{f.dispose()}
        f.credentialCallback={f.selected="chat-B"}
        await #expect(throws:MemoryFailure.staleBinding){try await f.client.discover(binding:f.binding,conversation:"chat-A")}
        #expect(f.server.requests.isEmpty)
        f.selected="chat-A";f.server.after={f.client.invalidate()}
        await #expect(throws:MemoryFailure.staleBinding){try await f.client.discover(binding:f.binding,conversation:"chat-A")}
        #expect(f.server.requests.count==1)
        let read=try await f.read();f.selected="chat-B"
        #expect(throws:MemoryFailure.staleBinding){try f.client.prepareReview(read:read,candidateID:"candidate-中文",review:.reject)}
        #expect(try f.store.records().isEmpty)
    }
    @Test func serviceUnknownIsNotEmptyDiscoveryAndWrongOriginalProducerRejects() async throws {
        let f=try CandidateClientFixture();defer{f.dispose()}
        f.server.serviceUnavailable=true
        await #expect(throws:MemoryFailure.exchangeUnknown){try await f.client.discover(binding:f.binding,conversation:f.selected)}
        f.server.serviceUnavailable=false;f.server.wrongProducer=true
        await #expect(throws:MemoryFailure.invalidResponse){try await f.read()}
    }
    @Test func postNullIsInvalidAndDefiniteConflictKeepsOriginalDeclineAfterReopen() async throws {
        let f=try CandidateClientFixture();defer{f.dispose()}
        let read=try await f.read(),work=try f.client.prepareReview(read:read,candidateID:"candidate-中文",review:.reject)
        f.server.conflict=true
        await #expect(throws:MemoryFailure.rejected(409,"MEMORY_CONFLICT")){try await f.client.perform(work)}
        f.client=try f.makeClient();f.server.nullReceipt=true
        let original=try #require(try f.client.originals(binding:f.binding).first)
        guard case .rejected(let code,_)=try await f.client.query(original) else {Issue.record("Definite decline vanished");return}
        #expect(code==409)
        let next=try await f.read(),again=try f.client.prepareReview(read:next,candidateID:"candidate-中文",review:.reject)
        f.server.conflict=false;f.server.nullAction=true
        await #expect(throws:MemoryFailure.invalidResponse){try await f.client.perform(again)}
        #expect(f.server.requests.filter{$0.0=="applyMemoryCandidateActionV1"}.count==2)
    }
}

@MainActor struct MemoryCandidatePresentationTests {
    private func loaded(_ f: CandidateClientFixture) async throws -> MemoryCandidatePresentation {
        let model = MemoryCandidatePresentation(client: f.client)
        model.replace(binding: f.binding, conversationID: f.selected)
        await model.perform(try #require(model.prepareDiscovery()))
        let producer = try #require(model.jobs.first)
        let selection = try #require(model.prepareCandidates(producer: producer))
        await model.perform(selection)
        #expect(model.state == .ready && model.candidates.first?.status == .candidate)
        return model
    }
    @Test func originalReceiptAndFreshCurrentStateAreSeparate() async throws {
        let f = try CandidateClientFixture(); defer { f.dispose() }
        let model = try await loaded(f)
        let work = try #require(model.prepareReview(candidateID: "candidate-中文", review: .confirm(kind: .preference, text: "少辣", occurredAt: "时间不详", travel: nil)))
        #expect(model.original != nil && model.candidates.isEmpty && model.state == .changing)
        await model.perform(work)
        #expect(model.historicalReceipt?.active == true)
        #expect(model.candidates.first?.status == .active && model.state == .ready)
        #expect(!model.canReview(candidateID: "candidate-中文"))
        #expect(f.server.requests.filter { $0.0 == "readMemoryCandidatesV1" }.count == 2)
        #expect(f.server.requests.filter { $0.0 == "applyMemoryCandidateActionV1" }.count == 1)
    }
    @Test func successfulOriginalIsNotErasedByLaterCurrentReadFailure() async throws {
        let f = try CandidateClientFixture(); defer { f.dispose() }
        let model = try await loaded(f)
        f.server.after = { f.server.serviceUnavailable = true }
        let work = try #require(model.prepareReview(candidateID: "candidate-中文", review: .reject))
        await model.perform(work)
        #expect(model.historicalReceipt != nil && model.historicalReceipt?.active == false)
        #expect(model.candidates.isEmpty && model.state == .unavailable && model.rejectionStatus == nil)
        #expect(f.server.requests.filter { $0.0 == "applyMemoryCandidateActionV1" }.count == 1)
    }
    @Test func unknownOriginalQueriesWithoutPostingAgain() async throws {
        let f = try CandidateClientFixture(); defer { f.dispose() }
        let model = try await loaded(f); f.server.loseACK = true
        await model.perform(try #require(model.prepareReview(candidateID: "candidate-中文", review: .reject)))
        #expect(model.state == .unknown && model.original != nil && model.historicalReceipt == nil)
        f.server.nullReceipt = true
        await model.perform(try #require(model.prepareQuery()))
        #expect(model.state == .unknown && !model.canReview(candidateID: "candidate-中文"))
        f.server.nullReceipt = false
        await model.perform(try #require(model.prepareQuery()))
        #expect(model.historicalReceipt?.active == false && model.candidates.first?.status == .withdrawn)
        #expect(f.server.requests.filter { $0.0 == "applyMemoryCandidateActionV1" }.count == 1)
    }
    @Test func replacementBeforeDispatchRetiresOldWorkAndLateResponseCannotOverwriteNewSlot() async throws {
        let f = try CandidateClientFixture(); defer { f.dispose() }
        let model = MemoryCandidatePresentation(client: f.client)
        model.replace(binding: f.binding, conversationID: "chat-A")
        let old = try #require(model.prepareDiscovery())
        f.selected = "chat-B"; model.replace(binding: f.binding, conversationID: "chat-B")
        await model.perform(old)
        #expect(f.server.requests.isEmpty && model.conversationID == "chat-B" && model.state == .unread)
        f.selected = "chat-A"; model.replace(binding: f.binding, conversationID: "chat-A")
        let pending = try #require(model.prepareDiscovery())
        f.server.after = { f.selected = "chat-B"; model.replace(binding: f.binding, conversationID: "chat-B") }
        await model.perform(pending)
        #expect(model.conversationID == "chat-B" && model.jobs.isEmpty && model.state == .unread)
    }
    @Test func synchronousObservationReplacementOwnsTheCompleteNewSlot() async throws {
        let f = try CandidateClientFixture(); defer { f.dispose() }
        let model = MemoryCandidatePresentation(client: f.client)
        model.replace(binding: f.binding, conversationID: "chat-A")
        var replaced = false
        withObservationTracking { _ = model.state } onChange: {
            MainActor.assumeIsolated {
                guard !replaced else { return }; replaced = true
                f.selected = "chat-B"; model.replace(binding: f.binding, conversationID: "chat-B")
            }
        }
        let work = try #require(model.prepareDiscovery())
        #expect(replaced && model.state == .unread && model.conversationID == "chat-B")
        await model.perform(work)
        #expect(f.server.requests.isEmpty && model.jobs.isEmpty && model.state == .unread)
    }
    @Test func editorEntryCannotSilentlyRetargetAfterFreshReadOrConversationChange() async throws {
        let f = try CandidateClientFixture(); defer { f.dispose() }
        let model = try await loaded(f)
        let entry = try #require(model.captureReview(candidateID: "candidate-中文"))
        let producer = try #require(model.jobs.first)
        await model.perform(try #require(model.prepareCandidates(producer: producer)))
        #expect(model.prepareReview(entry: entry, review: .reject) == nil)
        #expect(try f.store.records().isEmpty)
        let current = try #require(model.captureReview(candidateID: "candidate-中文"))
        f.selected = "chat-B"; model.replace(binding: f.binding, conversationID: "chat-B")
        #expect(model.prepareReview(entry: current, review: .reject) == nil)
        #expect(try f.store.records().isEmpty)
    }
    @Test func invalidUserEditCanBeCorrectedWithoutLosingTheOriginalRead() async throws {
        let f = try CandidateClientFixture(); defer { f.dispose() }
        let model = try await loaded(f)
        let entry = try #require(model.captureReview(candidateID: "candidate-中文"))
        #expect(model.prepareReview(entry: entry, review: .confirm(kind: .preference, text: " ", occurredAt: "时间不详", travel: nil)) == nil)
        #expect(model.state == .invalidReview && model.canReview(candidateID: "candidate-中文"))
        #expect(try f.store.records().isEmpty)
        let work = try #require(model.prepareReview(entry: entry, review: .confirm(kind: .preference, text: "少辣", occurredAt: "时间不详", travel: nil)))
        await model.perform(work)
        #expect(model.historicalReceipt?.active == true)
    }

}
