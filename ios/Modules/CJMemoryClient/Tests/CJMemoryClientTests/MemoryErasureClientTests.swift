import Foundation
import Observation
import Testing
import CJSession
import CJMessageKeys
import HTTPTypes
import OpenAPIRuntime
@testable import CJMemoryClient

@MainActor private final class ErasureSDKStore: SessionPersistence {
    var material: SessionMaterial?
    func load() throws -> SessionMaterial? { material }
    func save(_ material: SessionMaterial) throws { self.material = material }
    func clearAndBlock() throws { material = nil }
}
@MainActor private final class ErasureServer {
    var requests: [(String, Data?)] = []
    var original: MemoryErasureAction?
    var lostACK = false, missing = false, changedOperation = false, failed = false, nullResult = false
    var phase = "unknown"
    var beforePost: ((Data) throws -> Void)?
    var after: (() -> Void)?
    func respond(_ request: HTTPRequest, raw: Data?, operation: String) throws -> (HTTPResponse, HTTPBody?) {
        requests.append((operation, raw))
        #expect(request.headerFields[.authorization] == "Bearer SYNTHETIC.ERASURE.SDK")
        let post = operation == "eraseMemoryV1"
        if post {
            #expect(request.path == "/v1/memory-erasures")
            let raw = try #require(raw); try beforePost?(raw)
            if let original { #expect(original.originalUTF8 == raw) }
            original = try MemoryErasureAction(originalUTF8: raw)
            if lostACK { throw MemoryFailure.exchangeUnknown }
        } else {
            #expect(operation == "readMemoryErasureProgressV1")
            let parameters = try #require(URLComponents(string: request.path!)?.queryItems)
            #expect(parameters.count == 1 && parameters[0].name == "action_id" && parameters[0].value == original?.actionID)
        }
        let status: Int, value: [String: Any]
        if missing || failed {
            status = failed ? 409 : 503
            value = ["request_id": erasureTrace, "error": ["code": failed ? "ERASURE_CONFLICT" : "ERASURE_UNAVAILABLE",
                "category": failed ? "conflict" : "dependency", "message_en": "Unavailable", "message_zh": "尚未核实",
                "outcome": failed ? "failed" : "unknown", "recovery": "reconcile_original"]]
        } else {
            status = 200
            let original = try #require(original)
            var response = erasureResponse(original, post: post, phase: phase)
            if nullResult { response["result"] = NSNull() }
            if changedOperation {
                var result = response["result"] as! [String: Any]
                result["operation_id"] = "memory-erasure-v1:" + String(repeating: "b", count: 64)
                response["result"] = result
            }
            value = response
        }
        let callback = after; after = nil; callback?()
        var headers = HTTPFields(); headers[.contentType] = "application/json"; headers[.cacheControl] = "no-store"
        headers[HTTPField.Name("X-Request-ID")!] = erasureTrace
        return (HTTPResponse(status: .init(code: status), headerFields: headers), HTTPBody(try erasureBytes(value)))
    }
}
private struct ErasureWire: ClientTransport {
    let server: ErasureServer
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let raw: Data?
        if let body { raw = try await Data(collecting: body, upTo: 32768) } else { raw = nil }
        return try await server.respond(request, raw: raw, operation: operationID)
    }
}
@MainActor private final class ErasureClientFixture {
    let f: Fixture
    let sdk = ErasureSDKStore(), server = ErasureServer()
    let session: SessionLifecycle
    let operation: SessionOperation
    let reader: TypedMemoryClient
    var store: MemoryErasurePendingStore!
    var client: MemoryErasureClient!
    var credentialCallback: (() -> Void)?
    var currentCallback: (() -> Void)?
    var directory: URL { f.root.appendingPathExtension("erasure") }
    var storeNamespace: MessageKeyNamespace { .init(environment: f.binding.environment, account: f.binding.account, purpose: .localMemoryPendingV1) }
    init() throws {
        f = try Fixture()
        session = SessionLifecycle(persistence: sdk, restorePolicy: .userInitiatedOnly)
        operation = try session.beginTrustedSDKSave()
        try session.save(SessionMaterial(trustedSDKBytes: Data("synthetic-erasure-sdk".utf8)), for: operation)
        reader = try f.typedClient(Interceptor { _, _, operation in
            #expect(operation == "getTypedMemoryItem")
            return "{\"version\":\"MEMORY-result.2\",\"request_id\":\"\(trace)\",\"item\":{\"command\":{\"operation_id\":\"save\",\"item_id\":\"item+中文\",\"subject\":\"self\",\"slot\":\"pace\",\"text\":\"轻松行程\",\"occurred_at\":\"时间不详\",\"source_id\":\"source\",\"source_version\":2,\"kind\":\"preference\",\"extent\":\"long_term\",\"context\":null},\"version\":4,\"status\":\"active\",\"recorded_at\":\"2026-11-03T00:00:00Z\"}}"
        })
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        store = try makeStore(); client = makeClient()
    }
    func makeStore() throws -> MemoryErasurePendingStore {
        try MemoryErasurePendingStore(directory: directory, maximumBytes: 100000, maximumRecords: 100,
            namespace: .init(environment: f.binding.environment, account: f.binding.account, purpose: .localMemoryPendingV1), keyID: f.keyID, key: { self.f.secret })
    }
    func makeClient() -> MemoryErasureClient {
        MemoryErasureClient(endpoint: f.endpoint, credentials: { [self] _ in
            let callback = credentialCallback; credentialCallback = nil; callback?(); return "SYNTHETIC.ERASURE.SDK"
        }, currentBinding: { [self] in
            let callback = currentCallback; currentCallback = nil; callback?(); return f.current
        }, session: session, sessionOperation: operation, pendingStore: store, interceptedTransport: ErasureWire(server: server))
    }
    func entry() async throws -> MemoryErasureEntry {
        let read = try #require(try await reader.detail(itemID: "item+中文", binding: f.binding))
        return try client.capture(read: read, reader: reader, binding: f.binding)
    }
    func dispose() {
        f.cleanup()
        for root in [directory, directory.appendingPathExtension("CJMemoryErasureObservationsV1")] { try? FileManager.default.removeItem(at: root) }
    }
}
@MainActor struct MemoryErasureClientTests {
    @Test func localAuthorizationNeedsOriginalProtectedStopAndRetiresWithSDK() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let work = try f.client.prepare(entry: await f.entry(), acknowledgement: .ownedTripDerivedScope)
        #expect(throws: (any Error).self) { try f.client.localAuthorization(for: work.original) }
        _ = try await f.client.perform(work)
        let grant = try f.client.localAuthorization(for: work.original)
        #expect(grant.itemID == "item+中文" && grant.binding == f.f.binding)
        try grant.validate()
        f.reader.invalidate()
        // Local erasure recovery is tied to the original stop, not a fresh detail.
        try grant.validate()
        try f.session.clear()
        #expect(throws: (any Error).self) { try grant.validate() }
    }
    @Test func protectedStopClearsOnlyOwnItemJournalsAndRetainsOriginalRecovery() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let work = try f.client.prepare(entry: await f.entry(), acknowledgement: .ownedTripDerivedScope)
        _ = try await f.client.perform(work)
        let grant = try f.client.localAuthorization(for: work.original)
        let namespace = f.storeNamespace
        let manualRoot = f.f.root.appendingPathComponent("manual"), typedRoot = f.f.root.appendingPathComponent("typed"), managementRoot = f.f.root.appendingPathComponent("management")
        for root in [manualRoot, typedRoot, managementRoot] {
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        }
        let manual = try MemoryPendingStore(directory: manualRoot, maximumBytes: 100000, maximumRecords: 100, namespace: namespace, keyID: f.f.keyID, key: { f.f.secret })
        let typed = try TypedMemoryPendingStore(directory: typedRoot, maximumBytes: 100000, maximumRecords: 100, namespace: namespace, keyID: f.f.keyID, key: { f.f.secret })
        let management = try MemoryManagementPendingStore(directory: managementRoot, maximumBytes: 100000, maximumRecords: 100, namespace: namespace, keyID: f.f.keyID, key: { f.f.secret })
        var target = command("已删除的中文"); target.item_id = "item+中文"
        let removed = try MemoryPending(target), other = try MemoryPending(command("另一条记忆"))
        try manual.append(removed); try manual.append(other)
        try manual.recordRejection(removed, status: 409, code: "ORIGINAL_CONFLICT", validateBinding: {})
        let typedRecord = TypedMemoryPending(try TypedMemoryCommand(operationID: "typed-save", itemID: "item+中文", subject: "self", slot: "pace", text: "已删除的中文", occurredAt: "时间不详", kind: .preference, travelContext: nil))
        try typed.append(typedRecord, validateBinding: {})
        try typed.recordRejection(typedRecord, status: 409, code: "ORIGINAL_CONFLICT", validateBinding: {})
        let otherFile = manualRoot.appendingPathComponent(digest(Data(other.operationID.utf8)) + ".memory")
        let otherBytes = try Data(contentsOf: otherFile)
        let cleaner = MemoryItemLocalCleanup(manual: manual, management: management, typed: typed)
        #expect(throws: MemoryFailure.staleBinding) { try cleaner.clear(grant, validateCurrent: { throw MemoryFailure.staleBinding }) }
        #expect(try manual.pending().count == 2)
        try cleaner.clear(grant, validateCurrent: {})
        #expect(try manual.pending().map(\.operationID) == [other.operationID])
        #expect(try typed.pending().isEmpty)
        #expect(try Data(contentsOf: otherFile) == otherBytes)
        #expect(try FileManager.default.contentsOfDirectory(atPath: manualRoot.appendingPathExtension("CJMemoryRejections").path).isEmpty)
        #expect(try FileManager.default.contentsOfDirectory(atPath: typedRoot.appendingPathExtension("CJMemoryTypedRejectionsV2").path).isEmpty)
        #expect(try f.store.records().count == 1)
        try grant.validate()
        // A fresh original-stop authorization can explicitly verify an empty retry.
        try cleaner.clear(grant, validateCurrent: {})
    }
    @Test func originalIsDurableBeforePOSTAndTheWorkCannotBeSentTwice() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let entry = try await f.entry(), work = try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope)
        let pending = try #require(try f.store.records().first)
        f.server.beforePost = { raw in
            let current = try f.store.records()
            #expect(current.first?.originalUTF8 == raw && raw == pending.originalUTF8)
        }
        let result = try await f.client.perform(work)
        #expect(result.stopped && result.phase == .unknown && !result.onlineComplete)
        #expect(try f.store.observation(for: pending)?.value.operationID == result.operationID)
        await #expect(throws: MemoryFailure.staleBinding) { try await f.client.perform(work) }
        #expect(f.server.requests.filter { $0.0 == "eraseMemoryV1" }.count == 1)
    }
    @Test func lostACKAndMissingGETPreserveExactOriginalAcrossReconstruction() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let entry = try await f.entry(), work = try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope)
        let raw = try #require(try f.store.records().first?.originalUTF8)
        f.server.lostACK = true
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await f.client.perform(work) }
        f.store = try f.makeStore(); f.client = f.makeClient()
        let original = try #require(try f.client.originals(binding: f.f.binding).first)
        f.server.missing = true
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await f.client.query(original) }
        let fresh = try await f.entry()
        #expect(throws: MemoryFailure.pendingRequiresQuery) { try f.client.prepare(entry: fresh, acknowledgement: .ownedTripDerivedScope) }
        f.server.missing = false; f.server.phase = "complete"
        #expect(try await f.client.query(original).onlineComplete)
        #expect(try f.store.records().first?.originalUTF8 == raw)
        #expect(f.server.requests.filter { $0.0 == "eraseMemoryV1" }.count == 1)
    }
    @Test func oldReadDifferentClientSDKSwitchAndCredentialReentryCannotDispatch() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let entry = try await f.entry(), other = f.makeClient()
        #expect(throws: MemoryFailure.staleBinding) { try other.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope) }
        _ = try await f.reader.detail(itemID: "item+中文", binding: f.f.binding)
        #expect(throws: MemoryFailure.staleBinding) { try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope) }
        let fresh = try await f.entry(), work = try f.client.prepare(entry: fresh, acknowledgement: .ownedTripDerivedScope)
        f.credentialCallback = { f.client.invalidate() }
        await #expect(throws: MemoryFailure.staleBinding) { try await f.client.perform(work) }
        #expect(f.server.requests.isEmpty)
        let originals = try f.client.originals(binding: f.f.binding)
        #expect(originals.count == 1)
        f.f.current = nil
        await #expect(throws: MemoryFailure.staleBinding) { try await f.client.query(originals[0]) }
        #expect(f.server.requests.isEmpty)
    }
    @Test func laterSourceRetirementWithholdsPOSTProjectionButOriginalGETStillRecovers() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let entry = try await f.entry(), work = try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope)
        f.server.after = { f.reader.invalidate() }
        await #expect(throws: MemoryFailure.staleBinding) { try await f.client.perform(work) }
        #expect(f.server.requests.count == 1)
        let original = try #require(try f.client.originals(binding: f.f.binding).first)
        #expect(try await f.client.query(original).stopped)
        f.server.changedOperation = true
        await #expect(throws: MemoryFailure.invalidResponse) { try await f.client.query(original) }
        #expect(f.server.requests.filter { $0.0 == "eraseMemoryV1" }.count == 1)
    }
    @Test func conflictAndNullCannotCreateAStopGrantOrReleaseANewOriginal() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let entry = try await f.entry(), work = try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope)
        f.server.failed = true
        await #expect(throws: MemoryFailure.rejected(409, "ERASURE_CONFLICT")) { try await f.client.perform(work) }
        let record = try #require(try f.store.records().first)
        #expect(try f.store.observation(for: record) == nil)
        f.server.failed = false; f.server.nullResult = true
        let original = try #require(try f.client.originals(binding: f.f.binding).first)
        await #expect(throws: MemoryFailure.invalidResponse) { try await f.client.query(original) }
        let fresh = try await f.entry()
        #expect(throws: MemoryFailure.pendingRequiresQuery) { try f.client.prepare(entry: fresh, acknowledgement: .ownedTripDerivedScope) }
        #expect(f.server.requests.filter { $0.0 == "eraseMemoryV1" }.count == 1)
    }
    @Test func sourceCallbackCannotPrepareASecondOriginalDuringTheFirstPreparation() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let entry = try await f.entry()
        var refused = false
        f.currentCallback = {
            do { _ = try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope); Issue.record("Reentrant preparation admitted") }
            catch { #expect(error as? MemoryFailure == .pendingRequiresQuery); refused = true }
        }
        let work = try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope)
        let records = try f.store.records()
        #expect(refused && records.count == 1)
        _ = try await f.client.perform(work)
        #expect(f.server.requests.filter { $0.0 == "eraseMemoryV1" }.count == 1)
    }
    @Test func orphanObservationCannotBecomeAnEmptyUnresolvedInventory() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let entry = try await f.entry(), work = try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope)
        _ = try await f.client.perform(work)
        let file = try #require(FileManager.default.contentsOfDirectory(at: f.directory, includingPropertiesForKeys: nil).first)
        try FileManager.default.removeItem(at: file)
        f.store = try f.makeStore(); f.client = f.makeClient()
        #expect(throws: MemoryFailure.storageUnavailable) { try f.client.originals(binding: f.f.binding) }
    }
    @Test func legacySelectionUsesItsOriginalReaderAndRetirementAlsoFencesErasure() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let server = ManagementServer()
        let legacy = try MemoryClient(endpoint: f.f.endpoint, credentials: { _ in "synthetic-legacy" },
            currentBinding: { f.f.current }, pendingStore: f.f.store(), interceptedTransport: server)
        let itemID = await server.id
        _ = try await legacy.detail(itemID: itemID, binding: f.f.binding)
        let selected = try legacy.managementSelection(itemID: itemID, binding: f.f.binding)
        let other = try MemoryClient(endpoint: f.f.endpoint, credentials: { _ in "synthetic-legacy" },
            currentBinding: { f.f.current }, pendingStore: f.f.store(), interceptedTransport: server)
        #expect(throws: MemoryFailure.staleBinding) { try f.client.capture(read: selected, reader: other, binding: f.f.binding) }
        let entry = try f.client.capture(read: selected, reader: legacy, binding: f.f.binding)
        #expect(Data(entry.itemID.utf8) == Data(itemID.utf8))
        let work = try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope)
        legacy.invalidate()
        await #expect(throws: MemoryFailure.staleBinding) { try await f.client.perform(work) }
        #expect(f.server.requests.isEmpty)
    }
    @Test func explicitReconciliationRequiresOwnedGETAndKeepsExactOriginalBytesAndOperation() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let entry = try await f.entry(), initial = try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope)
        f.server.lostACK = true
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await f.client.perform(initial) }
        let original = try #require(try f.client.originals(binding: f.f.binding).first)
        let read = try await f.client.queryRead(original)
        let reconciled = try f.client.prepareReconciliation(original, after: read)
        #expect(throws: MemoryFailure.staleBinding) { try f.client.prepareReconciliation(original, after: read) }
        f.server.lostACK = false; f.server.phase = "complete"
        let result = try await f.client.perform(reconciled)
        #expect(result.onlineComplete && result.operationID == read.progress.operationID)
        let posts = f.server.requests.filter { $0.0 == "eraseMemoryV1" }
        #expect(posts.count == 2 && posts[0].1 == posts[1].1)
        let completed = try await f.client.queryRead(original)
        #expect(throws: MemoryFailure.staleBinding) { try f.client.prepareReconciliation(original, after: completed) }
        await #expect(throws: MemoryFailure.staleBinding) { try await f.client.perform(reconciled) }
    }
    @Test func unavailableNewGETRetiresOldPermissionAndAnotherClientCannotUseIt() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let entry = try await f.entry(), initial = try f.client.prepare(entry: entry, acknowledgement: .ownedTripDerivedScope)
        _ = try await f.client.perform(initial)
        let original = try #require(try f.client.originals(binding: f.f.binding).first)
        let read = try await f.client.queryRead(original)
        let other = f.makeClient(), otherOriginal = try #require(try other.originals(binding: f.f.binding).first)
        #expect(throws: MemoryFailure.staleBinding) { try other.prepareReconciliation(otherOriginal, after: read) }
        let prepared = try f.client.prepareReconciliation(original, after: read)
        f.server.missing = true
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await f.client.queryRead(original) }
        await #expect(throws: MemoryFailure.staleBinding) { try await f.client.perform(prepared) }
        #expect(throws: MemoryFailure.staleBinding) { try f.client.prepareReconciliation(original, after: read) }
        #expect(f.server.requests.filter { $0.0 == "eraseMemoryV1" }.count == 1)
    }
}

@MainActor struct MemoryErasurePresentationTests {
    private func model(_ f: ErasureClientFixture) async throws -> MemoryErasurePresentation {
        let entry = try await f.entry(), model = MemoryErasurePresentation(client: f.client)
        model.replace(binding: f.f.binding, entry: entry); return model
    }
    @Test func noSubmissionWithoutExplicitRangeAcknowledgement() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let model = try await model(f)
        #expect(model.canSubmit && model.prepareSubmission(acknowledged: false) == nil)
        #expect(try f.store.records().isEmpty && f.server.requests.isEmpty)
        let work = try #require(model.prepareSubmission(acknowledged: true))
        #expect(model.original != nil && model.entry == nil && model.state == .submitting)
        await model.perform(work)
        #expect(model.knownStopped && model.progress?.phase == .unknown && model.progressIsCurrent)
        #expect(model.progress?.onlineComplete == false)
    }
    @Test func failedRefreshKeepsKnownStopButRetiresTheOldPhysicalProjection() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let model = try await model(f)
        await model.perform(try #require(model.prepareSubmission(acknowledged: true)))
        #expect(model.knownStopped && model.progressIsCurrent)
        f.server.missing = true
        await model.perform(try #require(model.prepareQuery()))
        #expect(model.knownStopped && !model.progressIsCurrent && model.state == .unknown)
        f.store = try f.makeStore(); f.client = f.makeClient()
        let restored = MemoryErasurePresentation(client: f.client)
        restored.replace(binding: f.f.binding)
        await restored.perform(try #require(restored.prepareOriginals()))
        let original = try #require(restored.originals.first)
        restored.selectOriginal(actionID: original.actionID)
        #expect(restored.knownStopped && restored.progress == nil && !restored.progressIsCurrent)
    }
    @Test func accountReplacementFencesPreparedAndLateWorkWithoutPublishingIntoNewScope() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let model = try await model(f), work = try #require(model.prepareSubmission(acknowledged: true))
        model.replace(binding: nil)
        await model.perform(work)
        #expect(f.server.requests.isEmpty && model.original == nil && model.state == .unconfigured)
        let second = try ErasureClientFixture(); defer { second.dispose() }
        let lateModel = try await self.model(second)
        let late = try #require(lateModel.prepareSubmission(acknowledged: true))
        second.server.after = { second.f.current = nil; lateModel.replace(binding: nil) }
        await lateModel.perform(late)
        #expect(second.server.requests.count == 1)
        #expect(lateModel.progress == nil && lateModel.original == nil && lateModel.state == .unconfigured)
    }
    @Test func synchronousObservationReplacementOwnsTheWholeNewSlot() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let model = try await model(f)
        var replaced = false
        withObservationTracking { _ = model.state } onChange: {
            MainActor.assumeIsolated {
                guard !replaced else { return }; replaced = true; model.replace(binding: nil)
            }
        }
        let work = try #require(model.prepareSubmission(acknowledged: true))
        await model.perform(work)
        #expect(replaced && model.state == .unconfigured && model.original == nil && f.server.requests.isEmpty)
        #expect(try f.store.records().count == 1)
    }
    @Test func originalInventoryReadPreservesSelectionAndContinueNeedsFreshSuccessfulGET() async throws {
        let f = try ErasureClientFixture(); defer { f.dispose() }
        let model = try await model(f)
        await model.perform(try #require(model.prepareOriginals()))
        #expect(model.canSubmit && model.entry != nil)
        await model.perform(try #require(model.prepareSubmission(acknowledged: true)))
        #expect(!model.canReconcile && model.prepareReconciliation() == nil)
        await model.perform(try #require(model.prepareQuery()))
        #expect(model.canReconcile)
        f.server.phase = "complete"
        await model.perform(try #require(model.prepareReconciliation()))
        #expect(model.knownStopped && model.progress?.onlineComplete == true && !model.canReconcile)
        let bodies = f.server.requests.filter { $0.0 == "eraseMemoryV1" }.compactMap(\.1)
        #expect(bodies.count == 2 && bodies[0] == bodies[1])
    }
}
