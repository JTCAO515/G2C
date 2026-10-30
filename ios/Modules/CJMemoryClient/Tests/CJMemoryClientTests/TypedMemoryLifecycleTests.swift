import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMemoryClient

private actor TypedLifecycleWire: ClientTransport {
    var posts: [Data] = []
    var receipts: [String:[String:Any]] = [:]
    var version = 1
    var sourceVersion = 1
    var status = "active"
    var text = "original / 原文"
    var firstPost = ""
    var denyQuery = false
    var contextVersion = 7
    func configure(_ firstPost: String = "",denyQuery: Bool = false) { self.firstPost = firstPost;self.denyQuery = denyQuery }
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        let object: [String:Any]
        var responseStatus = 200
        if operationID == "getTypedMemoryItem" {
            object = ["request_id":trace,"version":"MEMORY-result.2","item":["version":version,"status":status,"recorded_at":"2026-10-30T11:12:13.123456Z",
                "command":["operation_id":"saved-original","item_id":"item","subject":"traveller","slot":"preference","text":text,"occurred_at":"去年",
                    "source_id":"source-\(sourceVersion)","source_version":sourceVersion,"kind":"preference","extent":"current",
                    "context":["kind":"travel","id":String(repeating:"a",count:32),"expected_version":contextVersion]]]]
        } else if operationID == "getTypedMemoryManagementReceipt" {
            if denyQuery { responseStatus = 403;object = error("failed") }
            else {
                let id = URLComponents(string:request.path!)!.queryItems!.first!.value!
                object = ["request_id":trace,"version":"MEMORY-result.2","receipt":receipts[id] ?? NSNull()]
            }
        } else {
            #expect(["applyTypedMemoryManagement","applyTypedMemoryStopUse"].contains(operationID))
            #expect(request.method == .post && request.path?.hasPrefix("/v2/memory-") == true)
            let raw = try await Data(collecting:body!,upTo:32768);posts.append(raw)
            let input = try JSONSerialization.jsonObject(with:raw) as! [String:Any]
            let first = posts.count == 1
            if first && ["failed","unknown"].contains(firstPost) {
                responseStatus = 403;object = error(firstPost)
            } else {
                let expectedVersion = input["expected_version"] as? Int,expectedSource = input["expected_source_version"] as? Int
                #expect(expectedVersion == version && expectedSource == sourceVersion)
                version += 1
                switch input["operation"] as! String {
                case "pause":status = "disabled"
                case "resume":status = "active"
                case "edit":
                    text = input["text"] as! String;sourceVersion += 1
                    contextVersion = (input["context"] as! [String:Any])["expected_version"] as! Int
                case "withdraw":status = "withdrawn"
                default:Issue.record("unexpected frozen operation")
                }
                let receipt: [String:Any] = ["action_id":input["action_id"]!,"item_id":"item","version":version,"status":status,"input_sha256":digest(raw)]
                receipts[input["action_id"] as! String] = receipt
                if first && firstPost == "lostACK" { throw URLError(.networkConnectionLost) }
                object = ["request_id":trace,"version":"MEMORY-result.2","receipt":receipt]
            }
        }
        var response = HTTPResponse(status:.init(code:responseStatus));response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        return (response,HTTPBody(try JSONSerialization.data(withJSONObject:object)))
    }
    private func error(_ outcome: String) -> [String:Any] {
        ["request_id":trace,"error":["code":"MEMORY_SOURCE_DENIED","category":"access","message_en":"Denied","message_zh":"拒绝","outcome":outcome,"recovery":"do_not_retry"]]
    }
}

@MainActor struct TypedMemoryLifecycleTests {
    private func read(_ client: TypedMemoryClient,_ f: Fixture) async throws -> TypedMemoryRead {
        let value = try await client.detail(itemID:"item",binding:f.binding)
        return try #require(value)
    }
    private func cleanup(_ f: Fixture) {
        f.cleanup()
        let root = f.root.appendingPathExtension("CJMemoryTypedManagementV2")
        try? FileManager.default.removeItem(at:root)
        try? FileManager.default.removeItem(at:root.appendingPathExtension("CJMemoryTypedManagementRejectionsV2"))
    }
    @Test func travelPauseEditDisabledResumeAndStopRequireFreshSourceReads() async throws {
        let f = try Fixture();defer { cleanup(f) }
        let wire = TypedLifecycleWire(),client = try f.typedClient(wire)
        let first = try await read(client,f)
        guard case .historicalReceipt(let paused) = try await client.manage(.pause,read:first,binding:f.binding) else { Issue.record("pause missing");return }
        #expect(paused.status == .disabled)
        await #expect(throws:(any Error).self) { try await client.manage(.resume,read:first,binding:f.binding) }
        let disabled = try await read(client,f)
        _ = try await client.manage(.edit,read:disabled,text:"new / 新原文",travelContext:MemoryTravelSelection(id:String(repeating:"a",count:32),expectedVersion:9),binding:f.binding)
        let edited = try await read(client,f)
        #expect(edited.item.value.status == .disabled && edited.item.value.command.source_version == 2 && edited.item.value.command.source_id == "source-2")
        #expect(edited.item.scope == .travel(try MemoryTravelSelection(id:String(repeating:"a",count:32),expectedVersion:9)))
        _ = try await client.manage(.resume,read:edited,binding:f.binding)
        let active = try await read(client,f)
        _ = try await client.manage(.stopUse,read:active,binding:f.binding)
        let stopped = try await read(client,f)
        #expect(stopped.item.value.status == .withdrawn && stopped.item.value.command.text == "new / 新原文")
        #expect(await wire.posts.count == 4)
        let originals = try client.managementPending(binding:f.binding)
        #expect(originals.count == 4)
        for original in originals { #expect(original.expectedSHA256 == digest(original.originalUTF8)) }
    }
    @Test func lostACKReopenOnlyQueriesOriginalAndDoesNotRepeatAction() async throws {
        let f = try Fixture();defer { cleanup(f) }
        let wire = TypedLifecycleWire();await wire.configure("lostACK")
        let client = try f.typedClient(wire),initial = try await read(client,f)
        await #expect(throws:MemoryFailure.exchangeUnknown) { try await client.manage(.pause,read:initial,binding:f.binding) }
        client.invalidate()
        let reopened = try f.typedClient(wire),current = try await read(reopened,f)
        await #expect(throws:MemoryFailure.pendingRequiresQuery) { try await reopened.manage(.resume,read:current,binding:f.binding) }
        let originals = try reopened.managementPending(binding:f.binding),original = try #require(originals.first)
        guard case .historicalReceipt(let receipt) = try await reopened.queryManagement(actionID:original.actionID,binding:f.binding) else { Issue.record("original receipt missing");return }
        #expect(receipt.input_sha256 == original.expectedSHA256)
        _ = try await reopened.manage(.resume,read:current,binding:f.binding)
        #expect(await wire.posts.count == 2)
        #expect(await wire.posts.first == original.originalUTF8)
    }
    @Test func unresolvedManagementCannotBeBypassedByFreshManualSave() async throws {
        let f = try Fixture();defer { cleanup(f) }
        let wire = TypedLifecycleWire();await wire.configure("lostACK")
        let client = try f.typedClient(wire)
        await #expect(throws:MemoryFailure.exchangeUnknown) { try await client.manage(.pause,read:read(client,f),binding:f.binding) }
        client.invalidate()
        let reopened = try f.typedClient(wire)
        let fresh = try TypedMemoryCommand(operationID:"fresh",itemID:"new",subject:"traveller",slot:"preference",text:"new",occurredAt:"unknown",kind:.preference,travelContext:nil)
        await #expect(throws:MemoryFailure.pendingRequiresQuery) { try await reopened.save(fresh,binding:f.binding) }
        #expect(try reopened.pending(binding:f.binding).isEmpty)
        #expect(await wire.posts.count == 1)
    }
    @Test func unresolvedManualCannotBeBypassedByFreshManagement() async throws {
        let f = try Fixture();defer { cleanup(f) }
        let store = try f.typedStore()
        let original = try TypedMemoryCommand(operationID:"unknown-save",itemID:"new",subject:"traveller",slot:"preference",text:"original",occurredAt:"unknown",kind:.preference,travelContext:nil)
        try store.append(TypedMemoryPending(original)) {}
        let wire = TypedLifecycleWire(),client = try f.typedClient(wire)
        await #expect(throws:MemoryFailure.pendingRequiresQuery) { try await client.manage(.pause,read:read(client,f),binding:f.binding) }
        #expect(try client.managementPending(binding:f.binding).isEmpty)
        #expect(await wire.posts.isEmpty)
        #expect(try client.pending(binding:f.binding).map(\.originalUTF8) == [original.originalUTF8])
    }
    @Test func confirmedCompletionSurvivesPresentationRetirementButReadDoesNot() async throws {
        let f = try Fixture();defer { cleanup(f) }
        let wire = TypedLifecycleWire(),client = try f.typedClient(wire),initial = try await read(client,f)
        _ = try await client.manage(.pause,read:initial,binding:f.binding)
        client.invalidate()
        #expect(throws:MemoryFailure.staleBinding) { try client.validateRead(initial,binding:f.binding) }
        let current = try await read(client,f)
        _ = try await client.manage(.resume,read:current,binding:f.binding)
        #expect(await wire.posts.count == 2)
    }
    @Test func failedPostReleasesFreshReviewAfterReopenAndNeverResendsOldAction() async throws {
        let f = try Fixture();defer { cleanup(f) }
        let wire = TypedLifecycleWire();await wire.configure("failed")
        let client = try f.typedClient(wire),initial = try await read(client,f)
        guard case .rejected(403,"MEMORY_SOURCE_DENIED") = try await client.manage(.pause,read:initial,binding:f.binding) else { Issue.record("failed outcome missing");return }
        let reopened = try f.typedClient(wire),current = try await read(reopened,f)
        _ = try await reopened.manage(.pause,read:current,binding:f.binding)
        let posted = await wire.posts
        #expect(posted.count == 2 && posted[0] != posted[1])
        #expect(try reopened.managementPending(binding:f.binding).count == 2)
    }
    @Test(arguments:[false,true]) func unknownAndReceiptDenialDoNotReleaseNewOperation(denied: Bool) async throws {
        let f = try Fixture();defer { cleanup(f) }
        let wire = TypedLifecycleWire();await wire.configure("unknown",denyQuery:denied)
        let client = try f.typedClient(wire),initial = try await read(client,f)
        await #expect(throws:MemoryFailure.exchangeUnknown) { try await client.manage(.pause,read:initial,binding:f.binding) }
        let originals = try client.managementPending(binding:f.binding),original = try #require(originals.first)
        if denied { await #expect(throws:MemoryFailure.exchangeUnknown) { try await client.queryManagement(actionID:original.actionID,binding:f.binding) } }
        else { guard case .notObserved = try await client.queryManagement(actionID:original.actionID,binding:f.binding) else { Issue.record("absence claimed terminal");return } }
        let current = try await read(client,f)
        await #expect(throws:MemoryFailure.pendingRequiresQuery) { try await client.manage(.pause,read:current,binding:f.binding) }
        #expect(await wire.posts.count == 1)
    }
    @Test func rereadOrAnotherClientCannotReuseOldReadAndEditCannotChangeTravel() async throws {
        let f = try Fixture();defer { cleanup(f) }
        let wire = TypedLifecycleWire(),client = try f.typedClient(wire),old = try await read(client,f)
        let current = try await read(client,f)
        await #expect(throws:MemoryFailure.staleBinding) { try await client.manage(.pause,read:old,binding:f.binding) }
        let other = try f.typedClient(wire)
        await #expect(throws:MemoryFailure.staleBinding) { try await other.manage(.pause,read:current,binding:f.binding) }
        await #expect(throws:MemoryFailure.invalidInput) { try await client.manage(.edit,read:current,text:"new",travelContext:MemoryTravelSelection(id:String(repeating:"b",count:32),expectedVersion:9),binding:f.binding) }
        #expect(await wire.posts.isEmpty)
    }
}
