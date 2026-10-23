import Foundation
import Testing
import CryptoKit
import CJAPI
import OpenAPIRuntime
import HTTPTypes
import CJMessageHTTP
@testable import CJMemoryClient

actor ManagementServer: ClientTransport {
    let id = "e\u{301} /+%"
    var version = 1
    var status = "active"
    var sourceVersion = 1
    var rejectResume = false
    var calls: [(String, Data)] = []
    var receipts: [String: String] = [:]
    var loseApplyReply = false
    var queryPayload: String?
    var corruptHash = false
    func setSourceVersion(_ value: Int) { sourceVersion = value }
    func setRejectResume(_ value: Bool) { rejectResume = value }
    func configure(loseApplyReply: Bool = false, queryPayload: String? = nil, corruptHash: Bool = false) {
        self.loseApplyReply = loseApplyReply; self.queryPayload = queryPayload; self.corruptHash = corruptHash
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data
        if let body { bytes = try await Data(collecting: body, upTo: 32768) } else { bytes = Data() }
        calls.append((operationID, bytes))
        let json: String
        switch operationID {
        case "getMemoryItem", "listMemories":
            let item = itemJSON(id: id, timestamp: "2026-10-23T01:00:00.123456Z")
                .replacingOccurrences(of: "\"version\":1", with: "\"version\":\(version)")
                .replacingOccurrences(of: "\"status\":\"active\"", with: "\"status\":\"\(status)\"")
                .replacingOccurrences(of: "\"source_version\":1", with: "\"source_version\":\(sourceVersion)")
            if operationID == "getMemoryItem" { json = "{\"request_id\":\"\(trace)\",\"item\":\(item)}" }
            else { json = "{\"request_id\":\"\(trace)\",\"items\":[\(item)],\"next_after\":\"\(id)\"}" }
        case "applyMemoryManagementAction":
            let c = try JSONDecoder().decode(Components.Schemas.MemoryManagementAction.self, from: bytes)
            guard c.expected_version == version, c.expected_source_version == sourceVersion, same(c.item_id, id) else { throw MemoryFailure.invalidInput }
            if c.operation == .resume && rejectResume {
                var denied = HTTPResponse(status: .conflict)
                denied.headerFields[.contentType] = "application/json"; denied.headerFields[.cacheControl] = "no-store"
                denied.headerFields[HTTPField.Name("X-Request-ID")!] = trace
                let error = "{\"request_id\":\"\(trace)\",\"error\":{\"code\":\"SOURCE_NOT_RESUMABLE\",\"category\":\"conflict\",\"message_en\":\"Source unavailable\",\"message_zh\":\"来源不可用\",\"outcome\":\"failed\",\"recovery\":\"reconcile_original\"}}"
                return (denied, HTTPBody(error.utf8))
            }
            version += 1; status = c.operation == .pause ? "disabled" : "active"
            let hash = corruptHash ? String(repeating: "0", count: 64) : digest(bytes)
            let receipt = "{\"action_id\":\"\(c.action_id)\",\"item_id\":\"\(id)\",\"version\":\(version),\"status\":\"\(status)\",\"input_sha256\":\"\(hash)\"}"
            receipts[c.action_id] = receipt
            if loseApplyReply { throw MemoryFailure.exchangeUnknown }
            json = "{\"request_id\":\"\(trace)\",\"receipt\":\(receipt)}"
        case "queryMemoryManagementReceipt":
            let observed = receipts.first { request.path?.contains($0.key) == true }?.value ?? "null"
            json = "{\"request_id\":\"\(trace)\",\"receipt\":\(queryPayload ?? observed)}"
        default: throw MemoryFailure.invalidInput
        }
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[.cacheControl] = "no-store"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        return (response, HTTPBody(json.utf8))
    }
}
@MainActor final class ManagementFixture {
    let base: Fixture
    let journalURL: URL
    let endpoint: MemoryEndpoint
    init() throws {
        base = try Fixture(); journalURL = base.root.appendingPathComponent("lifecycle")
        try FileManager.default.createDirectory(at: journalURL, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        endpoint = try MemoryEndpoint(url: base.endpoint.url, maximumRequestBytes: 32768, maximumResponseBytes: 65536)
    }
    func store() throws -> MemoryManagementPendingStore {
        let secret = base.secret
        return try MemoryManagementPendingStore(directory: journalURL, maximumBytes: 100_000, maximumRecords: 100,
            namespace: .init(environment: base.binding.environment, account: base.binding.account, purpose: .localMemoryPendingV1), keyID: base.keyID) { secret }
    }
    func client(_ server: any ClientTransport, credentials: MemoryCredentialCallback? = nil) throws -> MemoryClient {
        MemoryClient(endpoint: endpoint, credentials: credentials ?? { _ in "synthetic-only" }, currentBinding: { [self] in base.current },
            pendingStore: nil, interceptedTransport: server, managementPendingStore: try store())
    }
    func selection(_ client: MemoryClient, id: String) async throws -> MemoryManagementSelection {
        _ = try await client.detail(itemID: id, binding: base.binding)
        return try client.managementSelection(itemID: id, binding: base.binding)
    }
    func cleanup() { base.cleanup() }
}
@Suite @MainActor struct MemoryManagementTests {
    @Test func pauseResumeAndHistoricalQueryNeverRollbackCurrentRead() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer(); let client = try f.client(server)
        let id = await server.id; let selection = try await f.selection(client, id: id)
        #expect(selection.expectedVersion == 1 && selection.expectedSourceVersion == 1)
        guard case .historicalReceipt(let paused) = try await client.applyManagement(.pause, selection: selection, binding: f.base.binding) else { Issue.record("missing receipt"); return }
        #expect(paused.status == .disabled && paused.version == 2)
        let resumeSelection = try await f.selection(client, id: id)
        guard case .historicalReceipt(let resumed) = try await client.applyManagement(.resume, selection: resumeSelection, binding: f.base.binding) else { Issue.record("missing receipt"); return }
        #expect(resumed.status == .active && resumed.version == 3)
        let current = try await f.selection(client, id: id)
        guard case .historicalReceipt(let historical) = try await client.queryManagement(actionID: paused.action_id, binding: f.base.binding) else { Issue.record("missing historical receipt"); return }
        #expect(historical.version == 2 && historical.status == .disabled)
        let stillCurrent = try client.managementSelection(itemID: id, binding: f.base.binding)
        #expect(current.expectedVersion == 3 && stillCurrent.expectedVersion == 3)
        let originals = try f.store().pending(); let calls = await server.calls.filter { $0.0 == "applyMemoryManagementAction" }
        #expect(originals.count == 2 && calls.count == 2)
        for original in originals {
            let json = try #require(JSONSerialization.jsonObject(with: original.originalUTF8) as? [String: Any])
            #expect(Set(json.keys) == ["action_id", "operation", "item_id", "expected_version", "expected_source_version"])
            #expect(calls.contains { $0.1 == original.originalUTF8 })
            #expect(digest(original.originalUTF8) == original.expectedSHA256)
            #expect(Data(try original.command.item_id.utf8) == Data(id.utf8))
        }
    }
    @Test func unknownReopenAndNullQueryDoNotAuthorizeResend() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer(); await server.configure(loseApplyReply: true)
        let client = try f.client(server); let id = await server.id; let selection = try await f.selection(client, id: id)
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await client.applyManagement(.pause, selection: selection, binding: f.base.binding) }
        let original = try #require(f.store().pending().first)
        let reopened = try f.client(server); await server.configure(queryPayload: "null")
        guard case .notObserved = try await reopened.queryManagement(actionID: original.actionID, binding: f.base.binding) else { Issue.record("not null"); return }
        let read = try await f.selection(reopened, id: id)
        await #expect(throws: MemoryFailure.pendingRequiresQuery) { try await reopened.applyManagement(.resume, selection: read, binding: f.base.binding) }
        #expect(await server.calls.filter { $0.0 == "applyMemoryManagementAction" }.count == 1)
        await server.configure()
        guard case .historicalReceipt = try await reopened.queryManagement(actionID: original.actionID, binding: f.base.binding) else { Issue.record("original not recovered"); return }
    }
    @Test func cannotCaptureUnacceptedOrCrossClientSelection() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer(); let client = try f.client(server); let id = await server.id
        #expect(throws: MemoryFailure.staleBinding) { try client.managementSelection(itemID: id, binding: f.base.binding) }
        let selection = try await f.selection(client, id: id); let other = try f.client(server)
        await #expect(throws: MemoryFailure.staleBinding) { try await other.applyManagement(.pause, selection: selection, binding: f.base.binding) }
        let newerRead = try await f.selection(client, id: id)
        await #expect(throws: MemoryFailure.staleBinding) { try await client.applyManagement(.pause, selection: selection, binding: f.base.binding) }
        #expect(newerRead.expectedVersion == selection.expectedVersion)
        #expect(try f.store().pending().isEmpty)
    }
    @Test func wrongHashAndMalformedNonNullNeverSettle() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer(); await server.configure(corruptHash: true)
        let client = try f.client(server); let id = await server.id; let selection = try await f.selection(client, id: id)
        await #expect(throws: MemoryFailure.invalidResponse) { try await client.applyManagement(.pause, selection: selection, binding: f.base.binding) }
        let original = try #require(f.store().pending().first); await server.configure(queryPayload: "{}")
        await #expect(throws: MemoryFailure.invalidResponse) { try await client.queryManagement(actionID: original.actionID, binding: f.base.binding) }
    }
    @Test func credentialSwitchKeepsOriginalWithoutDispatch() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer(); var switchNow = false
        let client = try f.client(server, credentials: { _ in if switchNow { f.base.current = nil }; return "synthetic-only" })
        let id = await server.id; let selection = try await f.selection(client, id: id); switchNow = true
        await #expect(throws: MemoryFailure.staleBinding) { try await client.applyManagement(.pause, selection: selection, binding: f.base.binding) }
        #expect(try f.store().pending().count == 1)
        #expect(await server.calls.filter { $0.0 == "applyMemoryManagementAction" }.isEmpty)
    }
    @Test func defaultPublicManagementIsUnavailableBeforeCredentialsOrJournal() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer(); let testClient = try f.client(server)
        let id = await server.id; let selection = try await f.selection(testClient, id: id)
        let live = MemoryClient(endpoint: f.endpoint, credentials: { _ in Issue.record("Unexpected credential access"); return nil },
            currentBinding: { f.base.current }, pendingStore: nil, liveReadTransport: try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1), managementPendingStore: try f.store())
        #expect(!live.managementAvailable)
        await #expect(throws: MemoryFailure.unconfigured) { try await live.applyManagement(.pause, selection: selection, binding: f.base.binding) }
        await #expect(throws: MemoryFailure.unconfigured) { try await live.queryManagement(actionID: "original", binding: f.base.binding) }
        #expect(try f.store().pending().isEmpty)
    }
    @Test func lifecycleCiphertextCannotBeReadAsManualSaveLedger() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer(); let client = try f.client(server)
        let id = await server.id; let selection = try await f.selection(client, id: id)
        _ = try await client.applyManagement(.pause, selection: selection, binding: f.base.binding)
        let secret = f.base.secret
        let manual = try MemoryPendingStore(directory: f.journalURL, maximumBytes: 100_000, maximumRecords: 100,
            namespace: .init(environment: f.base.binding.environment, account: f.base.binding.account, purpose: .localMemoryPendingV1), keyID: f.base.keyID) { secret }
        #expect(throws: CryptoKitError.self) { try manual.pending() }
    }
}
actor ManagementBarrierTransport: ClientTransport {
    let server: ManagementServer
    let barrier: Barrier
    init(server: ManagementServer, barrier: Barrier) { self.server = server; self.barrier = barrier }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let response = try await server.send(request, body: body, baseURL: baseURL, operationID: operationID)
        if operationID == "applyMemoryManagementAction" { await barrier.stop() }
        return response
    }
}
extension MemoryManagementTests {
    @Test func actualCancelledPostKeepsOriginalAndOnlyFreshQuerySettles() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer(); let barrier = Barrier()
        let client = try f.client(ManagementBarrierTransport(server: server, barrier: barrier)); let id = await server.id
        let selection = try await f.selection(client, id: id)
        let task = Task { try await client.applyManagement(.pause, selection: selection, binding: f.base.binding) }
        await barrier.waitUntilArrived(); task.cancel(); await barrier.release()
        await #expect(throws: CancellationError.self) { try await task.value }
        let pending = try #require(f.store().pending().first)
        guard case .historicalReceipt = try await client.queryManagement(actionID: pending.actionID, binding: f.base.binding) else { Issue.record("original query failed"); return }
        #expect(await server.calls.filter { $0.0 == "applyMemoryManagementAction" }.count == 1)
        await #expect(throws: MemoryFailure.pendingRequiresQuery) { try await client.applyManagement(.pause, selection: selection, binding: f.base.binding) }
    }
    @Test func selectionChangedAtCredentialAwaitRejectsBeforePost() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer(); var change = false
        let client = try f.client(server, credentials: { _ in
            if change {
                let b = f.base.binding
                f.base.current = MemoryBinding(environment: b.environment, account: b.account, generation: b.generation, selection: UUID())
            }
            return "synthetic-only"
        })
        let id = await server.id; let selection = try await f.selection(client, id: id); change = true
        await #expect(throws: MemoryFailure.staleBinding) { try await client.applyManagement(.pause, selection: selection, binding: f.base.binding) }
        #expect(await server.calls.filter { $0.0 == "applyMemoryManagementAction" }.isEmpty)
        #expect(try f.store().pending().count == 1)
    }
    @Test func directoryReplacementAtManagementKeyLookupNeverDispatches() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer()
        let moved = f.journalURL.appendingPathExtension("retired"); var swapped = false
        let store = try MemoryManagementPendingStore(directory: f.journalURL, maximumBytes: 100_000, maximumRecords: 100,
            namespace: .init(environment: f.base.binding.environment, account: f.base.binding.account, purpose: .localMemoryPendingV1), keyID: f.base.keyID) {
                if !swapped {
                    swapped = true; try FileManager.default.moveItem(at: f.journalURL, to: moved)
                    try FileManager.default.createDirectory(at: f.journalURL, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
                }
                return f.base.secret
            }
        let client = MemoryClient(endpoint: f.endpoint, credentials: { _ in "synthetic-only" }, currentBinding: { f.base.current },
            pendingStore: nil, interceptedTransport: server, managementPendingStore: store)
        let id = await server.id; let selection = try await f.selection(client, id: id)
        await #expect(throws: MemoryFailure.storageUnavailable) { try await client.applyManagement(.pause, selection: selection, binding: f.base.binding) }
        #expect(await server.calls.filter { $0.0 == "applyMemoryManagementAction" }.isEmpty)
    }
    @Test func capturedSourceVersionIsNotDefaultedAndDisabledDoesNotAuthorizeResume() async throws {
        let f = try ManagementFixture(); defer { f.cleanup() }; let server = ManagementServer(); await server.setSourceVersion(7)
        let client = try f.client(server); let id = await server.id; let selection = try await f.selection(client, id: id)
        #expect(selection.expectedSourceVersion == 7)
        _ = try await client.applyManagement(.pause, selection: selection, binding: f.base.binding)
        let paused = try await f.selection(client, id: id); #expect(paused.expectedVersion == 2 && paused.expectedSourceVersion == 7)
        await server.setRejectResume(true)
        await #expect(throws: MemoryFailure.rejected(409, "SOURCE_NOT_RESUMABLE")) { try await client.applyManagement(.resume, selection: paused, binding: f.base.binding) }
        #expect(await server.version == 2)
        let records = try f.store().pending()
        #expect(records.count == 2)
        let resumedAction = try #require(records.first { (try? $0.command.operation) == .resume })
        guard case .notObserved = try await client.queryManagement(actionID: resumedAction.actionID, binding: f.base.binding) else { Issue.record("unexpected receipt"); return }
    }
}
