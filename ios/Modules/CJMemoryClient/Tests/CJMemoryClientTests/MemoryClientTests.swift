import Testing
import Foundation
import CryptoKit
import CJAPI
@testable import CJMessageKeys
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJMemoryClient

actor Interceptor: ClientTransport {
    var calls: [(String, Data)] = []
    let status: HTTPResponse.Status
    let handler: @Sendable (HTTPRequest, Data, String) async throws -> String
    init(status: HTTPResponse.Status = .ok, _ handler: @escaping @Sendable (HTTPRequest, Data, String) async throws -> String) { self.status = status; self.handler = handler }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data
        if let body { bytes = try await awaitData(body) } else { bytes = Data() }
        calls.append((operationID, bytes))
        let json = try await handler(request, bytes, operationID)
        var response = HTTPResponse(status: status)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(json.utf8))
    }
    private func awaitData(_ body: HTTPBody) async throws -> Data { try await Data(collecting: body, upTo: 100_000) }
}
let trace = "00000000-0000-0000-0000-000000000001"
@MainActor final class Fixture {
    let binding = MemoryBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    var current: MemoryBinding?
    let root: URL
    let secret = SymmetricKey(size: .bits256)
    let keyID = UUID()
    let endpoint = try! MemoryEndpoint(url: URL(string: "https://memory.invalid")!, maximumRequestBytes: 100_000, maximumResponseBytes: 100_000)
    init() throws {
        root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        current = binding
    }
    func store(key: SymmetricKey? = nil, keyID: UUID? = nil) throws -> MemoryPendingStore {
        let secret = key ?? secret
        return try MemoryPendingStore(directory: root, maximumBytes: 100_000, maximumRecords: 100,
            namespace: .init(environment: binding.environment, account: binding.account, purpose: .localMemoryPendingV1), keyID: keyID ?? self.keyID) { secret }
    }
    func client(_ transport: Interceptor, credentials: MemoryCredentialCallback? = nil) throws -> MemoryClient {
        try MemoryClient(endpoint: endpoint, credentials: credentials ?? { _ in "test-credential" },
            currentBinding: { [self] in current }, pendingStore: store(), interceptedTransport: transport)
    }
    func cleanup() {
        try? FileManager.default.removeItem(at: root)
        try? FileManager.default.removeItem(at: root.appendingPathExtension("CJMemoryRejections"))
    }
}
func command(_ text: String = "cafe\u{301}", inference: Bool = false) -> Components.Schemas.MemoryManualSaveCommand {
    .init(operation_id: UUID().uuidString.lowercased(), item_id: UUID().uuidString.lowercased(), subject: "self", slot: "test",
          text: text, occurred_at: "date unknown", kind: inference ? .inference : .preference, extent: .long_term, context_id: .case2(nil))
}
func receipt(_ bytes: Data, badHash: Bool = false) throws -> String {
    let c = try JSONDecoder().decode(Components.Schemas.MemoryManualSaveCommand.self, from: bytes)
    return "{\"request_id\":\"\(trace)\",\"receipt\":{\"operation_id\":\"\(c.operation_id)\",\"item_id\":\"\(c.item_id)\",\"version\":1,\"status\":\"\(c.kind == .inference ? "candidate" : "active")\",\"input_sha256\":\"\(badHash ? String(repeating: "0", count: 64) : digest(bytes))\"}}"
}
@Suite @MainActor struct MemoryClientTests {
    @Test func originalBytesPersistBeforeCredentialAwaitAndSurviveReopen() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let transport = Interceptor { _, bytes, _ in try receipt(bytes) }
        let store = try f.store()
        let client = try f.client(transport, credentials: { _ in
            let pendingCount = try store.pending().count
            #expect(pendingCount == 1)
            return "test-credential"
        })
        let c = command()
        guard case .saved = try await client.save(c, binding: f.binding) else { Issue.record("not saved"); return }
        let reopened = try f.store().pending()
        let sent = await transport.calls
        #expect(reopened.count == 1)
        #expect(reopened[0].originalUTF8 == sent[0].1)
        #expect(reopened[0].expectedSHA256 == digest(sent[0].1))
        let decoded = try JSONDecoder().decode(Components.Schemas.MemoryManualSaveCommand.self, from: sent[0].1)
        #expect(Data(decoded.text.utf8) == Data(c.text.utf8))
        #expect(Data(decoded.text.utf8) != Data("café".utf8))
        let disk = try Data(contentsOf: f.root.appendingPathComponent(digest(Data(c.operation_id.utf8)) + ".memory"))
        #expect(disk.range(of: Data(c.text.utf8)) == nil)
    }
    @Test func nullAfterUnknownAndReopenNeverResends() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let transport = Interceptor { _, _, op in
            if op == "saveMemory" { throw MemoryFailure.exchangeUnknown }
            return "{\"request_id\":\"\(trace)\",\"receipt\":null}"
        }
        let c = command(); let client = try f.client(transport)
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await client.save(c, binding: f.binding) }
        let reopened = try f.client(transport)
        guard case .notObserved = try await reopened.query(operationID: c.operation_id, binding: f.binding) else { Issue.record("not null"); return }
        await #expect(throws: MemoryFailure.pendingRequiresQuery) { try await reopened.save(command(), binding: f.binding) }
        #expect(await transport.calls.map(\.0) == ["saveMemory", "queryMemoryReceipt"])
    }
    @Test func badHashCannotSettleAndCandidateIsDistinct() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let bad = Interceptor { _, bytes, _ in try receipt(bytes, badHash: true) }
        let client = try f.client(bad)
        await #expect(throws: MemoryFailure.invalidResponse) { try await client.save(command(), binding: f.binding) }
        #expect(try f.store().pending().count == 1)
        let g = try Fixture(); defer { g.cleanup() }
        let good = try g.client(Interceptor { _, bytes, _ in try receipt(bytes) })
        guard case .candidate = try await good.save(command(inference: true), binding: g.binding) else { Issue.record("candidate became fact"); return }
    }
    @Test func credentialAccountSwitchDoesNotSend() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let transport = Interceptor { _, _, _ in "{}" }
        let client = try f.client(transport, credentials: { _ in f.current = nil; return "test-credential" })
        await #expect(throws: MemoryFailure.staleBinding) { try await client.save(command(), binding: f.binding) }
        #expect(await transport.calls.isEmpty)
        #expect(try f.store().pending().count == 1)
    }
    @Test func lateResponseFromOldBindingIsRejected() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let transport = Interceptor { _, bytes, _ in
            await MainActor.run { f.current = nil }
            return try receipt(bytes)
        }
        let client = try f.client(transport)
        await #expect(throws: MemoryFailure.staleBinding) { try await client.save(command(), binding: f.binding) }
        #expect(try f.store().pending().count == 1)
    }
    @Test func cancellationRetainsOriginal() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let transport = Interceptor { _, _, _ in throw CancellationError() }
        let client = try f.client(transport)
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await client.save(command(), binding: f.binding) }
        #expect(try f.store().pending().count == 1)
    }
    @Test func encryptedReopenRejectsWrongKeyIDCorruptionAndUnknownFiles() throws {
        let f = try Fixture(); defer { f.cleanup() }
        let store = try f.store(); let record = try MemoryPending(command())
        try store.append(record)
        #expect(throws: (any Error).self) { try f.store(key: SymmetricKey(size: .bits256)).pending() }
        #expect(throws: (any Error).self) { try f.store(keyID: UUID()).pending() }
        #expect(throws: MemoryFailure.storageUnavailable) { try store.append(record) }
        let path = f.root.appendingPathComponent(digest(Data(record.operationID.utf8)) + ".memory")
        var bytes = try Data(contentsOf: path); bytes[0] ^= 1; try bytes.write(to: path)
        #expect(throws: (any Error).self) { try store.pending() }
        #expect(throws: CryptoKitError.self) { try store.append(record) }
        #expect(try Data(contentsOf: path) == bytes)
    }
    @Test func liveWriteIsUnavailableBeforeStorageAndCredentials() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let client = MemoryClient(endpoint: f.endpoint, credentials: { _ in Issue.record("credential called"); return nil },
            currentBinding: { f.current }, pendingStore: try f.store(),
            liveReadTransport: try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1))
        await #expect(throws: MemoryFailure.liveWriteUnavailable) { try await client.save(command(), binding: f.binding) }
        #expect(try f.store().pending().isEmpty)
    }
    @Test func nonNullMalformedReceiptIsNotAbsence() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let c = command(); try f.store().append(MemoryPending(c))
        let client = try f.client(Interceptor { _, _, _ in "{\"request_id\":\"\(trace)\",\"receipt\":{}}" })
        await #expect(throws: MemoryFailure.invalidResponse) { try await client.query(operationID: c.operation_id, binding: f.binding) }
    }
    @Test func groupsAndEmptyListUseOfficialClient() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let client = try f.client(Interceptor { _, _, op in
            if op == "listMemoryGroups" { return "{\"request_id\":\"\(trace)\",\"groups\":[{\"subject\":\"self\",\"status\":\"candidate\",\"count\":1}]}" }
            return "{\"request_id\":\"\(trace)\",\"items\":[],\"next_after\":null}"
        })
        #expect(try await client.groups(binding: f.binding).first?.status == .candidate)
        let page = try await client.list(limit: 10, binding: f.binding)
        #expect(page.items.isEmpty && page.next == nil)
    }
}

actor Barrier {
    private var arrived = false
    private var observer: CheckedContinuation<Void, Never>?
    private var releaseWaiter: CheckedContinuation<Void, Never>?
    func stop() async {
        arrived = true; observer?.resume(); observer = nil
        await withCheckedContinuation { releaseWaiter = $0 }
    }
    func waitUntilArrived() async {
        if arrived { return }
        await withCheckedContinuation { observer = $0 }
    }
    func release() { releaseWaiter?.resume(); releaseWaiter = nil }
}
func itemJSON(id: String, timestamp: String) -> String {
    """
    {"command":{"operation_id":"00000000-0000-0000-0000-000000000010","item_id":"\(id)","subject":"self","slot":"test","text":"synthetic","source_id":"source-test","occurred_at":"date unknown","kind":"preference","extent":"long_term","context_id":null,"source_version":1},"version":1,"status":"active","recorded_at":"\(timestamp)"}
    """
}
extension MemoryClientTests {
    @Test(arguments: ["2026-10-22T01:00:00Z", "2026-10-22T01:00:00.123456Z"])
    func officialDateDecoderAndKeysetPage(timestamp: String) async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let id = "00000000-0000-0000-0000-000000000002"
        let item = itemJSON(id: id, timestamp: timestamp)
        let transport = Interceptor { request, _, op in
            if op == "getMemoryItem" { return "{\"request_id\":\"\(trace)\",\"item\":\(item)}" }
            if request.path?.contains("after=") == true { return "{\"request_id\":\"\(trace)\",\"items\":[],\"next_after\":null}" }
            return "{\"request_id\":\"\(trace)\",\"items\":[\(item)],\"next_after\":\"\(id)\"}"
        }
        let client = try f.client(transport)
        let detail = try await client.detail(itemID: id, binding: f.binding)
        #expect(detail?.command.item_id == id)
        let page = try await client.list(limit: 1, binding: f.binding)
        #expect(page.next != nil)
        let last = try await client.list(limit: 1, after: page.next, binding: f.binding)
        #expect(last.items.isEmpty && last.next == nil)
        let other = try f.client(transport)
        await #expect(throws: MemoryFailure.staleBinding) { try await other.list(limit: 1, after: page.next, binding: f.binding) }
    }
    @Test func credentialReentryInvalidatesOlderRead() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let barrier = Barrier()
        let transport = Interceptor { _, _, _ in "{\"request_id\":\"\(trace)\",\"groups\":[]}" }
        var requests = 0
        let client = try f.client(transport, credentials: { _ in
            requests += 1
            if requests == 1 { await barrier.stop() }
            return "test-credential"
        })
        let old = Task { try await client.groups(binding: f.binding) }
        await barrier.waitUntilArrived()
        #expect(try await client.groups(binding: f.binding).isEmpty)
        await barrier.release()
        await #expect(throws: MemoryFailure.staleBinding) { try await old.value }
        #expect(await transport.calls.count == 1)
    }
    @Test func actualCancellationAfterDispatchDoesNotConfirm() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let barrier = Barrier()
        let transport = Interceptor { _, bytes, _ in await barrier.stop(); return try receipt(bytes) }
        let client = try f.client(transport)
        let task = Task { try await client.save(command(), binding: f.binding) }
        await barrier.waitUntilArrived()
        task.cancel(); await barrier.release()
        await #expect(throws: CancellationError.self) { try await task.value }
        #expect(try f.store().pending().count == 1)
        await #expect(throws: MemoryFailure.pendingRequiresQuery) { try await client.save(command(), binding: f.binding) }
    }
    @Test func malformedDuplicateResponseAndWrongItemDoNotPublish() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let bad = try f.client(Interceptor { _, _, _ in "{\"request_id\":\"\(trace)\",\"groups\":[],\"groups\":[]}" })
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await bad.groups(binding: f.binding) }
        let wrongID = "00000000-0000-0000-0000-000000000003"
        let wrong = try f.client(Interceptor { _, _, _ in
            "{\"request_id\":\"\(trace)\",\"item\":\(itemJSON(id: wrongID, timestamp: "2026-10-22T01:00:00Z"))}"
        })
        await #expect(throws: MemoryFailure.invalidResponse) { try await wrong.detail(itemID: trace, binding: f.binding) }
    }
    @Test func storageMissingKeyAndBindingChangeBeforeAppendFailClosed() throws {
        let f = try Fixture(); defer { f.cleanup() }
        let store = try MemoryPendingStore(directory: f.root, maximumBytes: 100_000, maximumRecords: 100,
            namespace: .init(environment: f.binding.environment, account: f.binding.account, purpose: .localMemoryPendingV1), keyID: f.keyID) {
                throw MemoryFailure.keyUnavailable
            }
        let record = try MemoryPending(command())
        #expect(throws: MemoryFailure.keyUnavailable) { try store.append(record) }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
        let valid = try f.store()
        #expect(throws: MemoryFailure.staleBinding) {
            try valid.append(record) { throw MemoryFailure.staleBinding }
        }
        #expect(try valid.pending().isEmpty)
    }
}

@MainActor final class TestKeyPersistence: MessageKeyPersistence {
    var record: MessageKeyRecord?
    func read() throws -> MessageKeyRecord? { record }
    func add(_ record: MessageKeyRecord) throws { self.record = record }
    func remove(expectedID: UUID) throws { record = nil }
}
extension MemoryClientTests {
    @Test func officialProviderPurposeExpectedIDAndInvalidation() throws {
        let f = try Fixture(); defer { f.cleanup() }
        let namespace = MessageKeyNamespace(environment: f.binding.environment, account: f.binding.account, purpose: .localMemoryPendingV1)
        let provider = ScopedMessageKeyProvider(namespace: namespace, persistence: TestKeyPersistence(), randomBytes: { Data(repeating: 42, count: 32) })
        let key = try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create))
        let store = try MemoryPendingStore(directory: f.root, maximumBytes: 100_000, maximumRecords: 100,
            binding: f.binding, expectedKeyID: key.id, provider: provider)
        try store.append(MemoryPending(command()))
        #expect(try store.pending().count == 1)
        let wrong = try MemoryPendingStore(directory: f.root, maximumBytes: 100_000, maximumRecords: 100,
            binding: f.binding, expectedKeyID: UUID(), provider: provider)
        #expect(throws: MessageKeyFailure.keyMismatch) { try wrong.pending() }
        let messageProvider = ScopedMessageKeyProvider(namespace: .init(environment: f.binding.environment, account: f.binding.account, purpose: .localMessageStorageV1), persistence: TestKeyPersistence())
        #expect(throws: MemoryFailure.keyUnavailable) {
            try MemoryPendingStore(directory: f.root, maximumBytes: 100_000, maximumRecords: 100,
                binding: f.binding, expectedKeyID: key.id, provider: messageProvider)
        }
        provider.invalidate()
        #expect(throws: MessageKeyFailure.inactiveNamespace) { try store.pending() }
    }
    @Test func originalQuerySettlesPersistedHashOnly() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let c = command(); let record = try MemoryPending(c)
        try f.store().append(record)
        let transport = Interceptor { request, _, op in
            #expect(op == "queryMemoryReceipt")
            #expect(request.path?.contains(c.operation_id) == true)
            return try receipt(record.originalUTF8)
        }
        let client = try f.client(transport)
        guard case .saved(let r) = try await client.query(operationID: c.operation_id, binding: f.binding) else { Issue.record("not saved"); return }
        #expect(r.input_sha256 == record.expectedSHA256)
        #expect(await transport.calls.count == 1)
    }
}
extension MemoryClientTests {
    @Test func expiredCredentialsAreNotEmptyGroups() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let client = try f.client(Interceptor(status: .unauthorized) { _, _, _ in
            """
            {"request_id":"\(trace)","error":{"code":"AUTH_EXPIRED","category":"auth","message_en":"Expired","message_zh":"已过期","outcome":"failed","recovery":"do_not_retry"}}
            """
        })
        await #expect(throws: MemoryFailure.rejected(401, "AUTH_EXPIRED")) { try await client.groups(binding: f.binding) }
    }
    @Test func unknownFileAndDirectoryReplacementFailClosed() throws {
        let f = try Fixture(); defer { f.cleanup() }
        let store = try f.store()
        let unknown = f.root.appendingPathComponent("unknown")
        try Data().write(to: unknown)
        #expect(throws: MemoryFailure.storageUnavailable) { try store.pending() }
        try FileManager.default.removeItem(at: unknown)
        let moved = f.root.appendingPathExtension("retired")
        try FileManager.default.moveItem(at: f.root, to: moved)
        defer { try? FileManager.default.removeItem(at: moved) }
        try FileManager.default.createDirectory(at: f.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        #expect(throws: MemoryFailure.storageUnavailable) { try store.pending() }
        #expect(throws: MemoryFailure.storageUnavailable) { try store.append(MemoryPending(command())) }
    }
}
extension MemoryClientTests {
    @Test func sameKeyCannotDecryptAnotherAccountAssociatedData() throws {
        let f = try Fixture(); defer { f.cleanup() }
        try f.store().append(MemoryPending(command()))
        let wrong = try MemoryPendingStore(directory: f.root, maximumBytes: 100_000, maximumRecords: 100,
            namespace: .init(environment: f.binding.environment, account: UUID(), purpose: .localMemoryPendingV1), keyID: f.keyID) { f.secret }
        #expect(throws: CryptoKitError.self) { try wrong.pending() }
    }
}
