import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMemoryClient

private actor TypedMemoryWire: ClientTransport {
    enum FirstPost: Sendable { case accepted, lostACK, failed, unknown }
    let firstPost: FirstPost
    let nullReceipt: Bool
    let deniedQuery: Bool
    var posts: [Data] = []
    var queries = 0
    var committed: Data?
    init(_ firstPost: FirstPost = .accepted,nullReceipt: Bool = false,deniedQuery: Bool = false) {
        self.firstPost = firstPost;self.nullReceipt = nullReceipt;self.deniedQuery = deniedQuery
    }
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        let json: String
        let status: HTTPResponse.Status
        if operationID == "saveTypedMemory" {
            #expect(request.method == .post && request.path == "/v2/memories")
            let raw = try await Data(collecting:body!,upTo:32768);posts.append(raw)
            if posts.count == 1,firstPost == .failed || firstPost == .unknown {
                status = .forbidden
                json = "{\"request_id\":\"\(trace)\",\"error\":{\"code\":\"MEMORY_SOURCE_DENIED\",\"category\":\"access\",\"message_en\":\"Denied\",\"message_zh\":\"拒绝\",\"outcome\":\"\(firstPost == .failed ? "failed" : "unknown")\",\"recovery\":\"do_not_retry\"}}"
            } else {
                committed = raw
                if firstPost == .lostACK && posts.count == 1 { throw URLError(.networkConnectionLost) }
                status = .ok;json = try receipt(raw)
            }
        } else {
            #expect(operationID == "getTypedMemoryReceipt" && request.method == .get)
            queries += 1
            if deniedQuery {
                status = .forbidden
                json = "{\"request_id\":\"\(trace)\",\"error\":{\"code\":\"MEMORY_SOURCE_DENIED\",\"category\":\"access\",\"message_en\":\"Denied\",\"message_zh\":\"拒绝\",\"outcome\":\"failed\",\"recovery\":\"do_not_retry\"}}"
            } else {
                status = .ok
                json = try committed.flatMap { nullReceipt ? nil : try receipt($0) } ?? "{\"version\":\"MEMORY-result.2\",\"request_id\":\"\(trace)\",\"receipt\":null}"
            }
        }
        var response = HTTPResponse(status:status);response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        return (response,HTTPBody(json.utf8))
    }
    private func receipt(_ raw: Data) throws -> String {
        let command = try TypedMemoryCommand(originalUTF8:raw)
        return "{\"version\":\"MEMORY-result.2\",\"request_id\":\"\(trace)\",\"receipt\":{\"operation_id\":\"\(command.operationID)\",\"item_id\":\"\(command.itemID)\",\"version\":1,\"status\":\"\(command.kind == .inference ? "candidate" : "active")\",\"input_sha256\":\"\(digest(raw))\"}}"
    }
}

@MainActor extension Fixture {
    func typedStore() throws -> TypedMemoryPendingStore {
        try TypedMemoryPendingStore(directory:root,maximumBytes:100_000,maximumRecords:100,
            namespace:.init(environment:binding.environment,account:binding.account,purpose:.localMemoryPendingV1),keyID:keyID,key:{ self.secret })
    }
    func typedClient(_ wire: any ClientTransport,credentials: MemoryCredentialCallback? = nil) throws -> TypedMemoryClient {
        try TypedMemoryClient(endpoint:endpoint,credentials:credentials ?? { _ in "synthetic-only" },
            currentBinding:{ self.current },pendingStore:typedStore(),interceptedTransport:wire)
    }
}

@MainActor struct TypedMemoryClientTests {
    private func store(_ f: Fixture) throws -> TypedMemoryPendingStore { try f.typedStore() }
    private func client(_ f: Fixture,_ wire: TypedMemoryWire,credentials: MemoryCredentialCallback? = nil) throws -> TypedMemoryClient {
        try f.typedClient(wire,credentials:credentials)
    }
    private func command(_ id: String = "original") throws -> TypedMemoryCommand {
        try TypedMemoryCommand(operationID:id,itemID:"item-" + id,subject:"traveller",slot:"preference",text:"保持原文",occurredAt:"去年",kind:.preference,
            travelContext:MemoryTravelSelection(id:String(repeating:"a",count:32),expectedVersion:2))
    }
    @Test(arguments:[TypedMemoryWire.FirstPost.accepted,.failed,.unknown,.lostACK])
    fileprivate func presentationRetirementPreservesKnownCompletionsButNeverUpgradesUnknown(_ mode: TypedMemoryWire.FirstPost) async throws {
        let f = try Fixture();defer { f.cleanup() }
        let wire = TypedMemoryWire(mode),client = try client(f,wire),first = try command()
        switch mode {
        case .accepted:_ = try await client.save(first,binding:f.binding)
        case .failed:await #expect(throws:MemoryFailure.rejected(403,"MEMORY_SOURCE_DENIED")) { try await client.save(first,binding:f.binding) }
        case .unknown,.lostACK:await #expect(throws:MemoryFailure.exchangeUnknown) { try await client.save(first,binding:f.binding) }
        }
        client.retirePresentation()
        #expect(await wire.posts == [first.originalUTF8])
        if mode == .unknown || mode == .lostACK {
            await #expect(throws:MemoryFailure.pendingRequiresQuery) { try await client.save(command("fresh"),binding:f.binding) }
            if mode == .unknown {
                guard case .notObserved = try await client.query(operationID:first.operationID,binding:f.binding) else { Issue.record("missing receipt changed meaning");return }
                await #expect(throws:MemoryFailure.pendingRequiresQuery) { try await client.save(command("fresh"),binding:f.binding) }
                #expect(await wire.posts == [first.originalUTF8]);return
            }
            guard case .saved = try await client.query(operationID:first.operationID,binding:f.binding) else { Issue.record("original receipt missing");return }
        }
        guard case .saved = try await client.save(command("fresh"),binding:f.binding) else { Issue.record("known original blocked a fresh save");return }
        #expect(await wire.posts.count == 2)
        #expect(try client.pending(binding:f.binding).first?.originalUTF8 == first.originalUTF8)
    }
    @Test func presentationRetirementDuringCredentialsCannotDispatch() async throws {
        let f = try Fixture();defer { f.cleanup() }
        let wire = TypedMemoryWire()
        var retire: () -> Void = {}
        let client = try client(f,wire,credentials:{ _ in retire();return "synthetic-only" })
        retire = { client.retirePresentation() }
        await #expect(throws:MemoryFailure.staleBinding) { try await client.save(command(),binding:f.binding) }
        #expect(await wire.posts.isEmpty)
        #expect(try client.pending(binding:f.binding).count == 1)
    }
    @Test func lostACKReopenOnlyQueriesOriginalReceiptAndNeverRepeatsPOST() async throws {
        let f = try Fixture();defer { f.cleanup() }
        let wire = TypedMemoryWire(.lostACK),client = try client(f,wire),command = try command()
        await #expect(throws:MemoryFailure.exchangeUnknown) { try await client.save(command,binding:f.binding) }
        let restored = try self.client(f,wire)
        await #expect(throws:MemoryFailure.pendingRequiresQuery) { try await restored.save(self.command("new"),binding:f.binding) }
        guard case .saved(let receipt) = try await restored.query(operationID:command.operationID,binding:f.binding) else { Issue.record("lost original receipt");return }
        #expect(receipt.input_sha256 == digest(command.originalUTF8))
        #expect(await wire.posts == [command.originalUTF8]);#expect(await wire.queries == 1)
        #expect(try restored.pending(binding:f.binding).map(\.originalUTF8) == [command.originalUTF8])
    }
    @Test(arguments:[false,true]) func nullAndDeniedGETRemainUnknown(denied: Bool) async throws {
        let f = try Fixture();defer { f.cleanup() }
        let wire = TypedMemoryWire(.unknown,nullReceipt:true,deniedQuery:denied),client = try client(f,wire)
        await #expect(throws:MemoryFailure.exchangeUnknown) { try await client.save(command(),binding:f.binding) }
        if denied { await #expect(throws:MemoryFailure.exchangeUnknown) { try await client.query(operationID:"original",binding:f.binding) } }
        else { guard case .notObserved = try await client.query(operationID:"original",binding:f.binding) else { Issue.record("null claimed failure");return } }
        await #expect(throws:MemoryFailure.pendingRequiresQuery) { try await client.save(command("new"),binding:f.binding) }
        #expect(await wire.posts.count == 1)
    }
    @Test func explicitFailureSurvivesReopenAndPermitsOnlyNewOriginal() async throws {
        let f = try Fixture();defer {
            f.cleanup()
            try? FileManager.default.removeItem(at:f.root.appendingPathExtension("CJMemoryTypedRejectionsV2"))
        }
        let wire = TypedMemoryWire(.failed),client = try client(f,wire),original = try command()
        await #expect(throws:MemoryFailure.rejected(403,"MEMORY_SOURCE_DENIED")) { try await client.save(original,binding:f.binding) }
        let reopened = try self.client(f,wire)
        guard case .rejected(403,"MEMORY_SOURCE_DENIED") = try await reopened.query(operationID:original.operationID,binding:f.binding) else { Issue.record("lost durable failure");return }
        let next = try command("fresh")
        guard case .saved = try await reopened.save(next,binding:f.binding) else { Issue.record("fresh original blocked");return }
        #expect(await wire.posts == [original.originalUTF8,next.originalUTF8])
        #expect(try reopened.pending(binding:f.binding).count == 2)
    }
    @Test func originalIsDurableBeforeCredentialAwaitAndLateIdentityCannotDispatch() async throws {
        let f = try Fixture();defer { f.cleanup() }
        let wire = TypedMemoryWire(),command = try command()
        let store = try store(f)
        let client = try client(f,wire,credentials:{ binding in
            #expect(binding == f.binding)
            let records = try store.pending()
            #expect(records.map(\.originalUTF8) == [command.originalUTF8])
            f.current = nil
            return "synthetic-only"
        })
        await #expect(throws:MemoryFailure.staleBinding) { try await client.save(command,binding:f.binding) }
        #expect(await wire.posts.isEmpty)
        #expect(try store.pending().map(\.originalUTF8) == [command.originalUTF8])
    }
}
