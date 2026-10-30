import Foundation
import Testing
import HTTPTypes
@testable import CJMessageHTTP
@testable import CJMemoryClient

@MainActor private final class PriorOriginalGate { var blocked = false }

/// L0 non-network interceptors only. These cases do not claim signed API/PG L1.
@MainActor struct LegacyTypedReconciliationTests {
    private func manualStore(_ f: ManagementFixture) throws -> MemoryPendingStore {
        let directory = f.base.root.appendingPathComponent("manual-v1")
        if !FileManager.default.fileExists(atPath:directory.path) {
            try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        }
        let secret = f.base.secret
        return try MemoryPendingStore(directory:directory,maximumBytes:100_000,maximumRecords:20,
            namespace:.init(environment:f.base.binding.environment,account:f.base.binding.account,purpose:.localMemoryPendingV1),
            keyID:f.base.keyID,key:{secret})
    }
    private func readOnly(_ f: ManagementFixture,wire: Interceptor) throws -> MemoryClient {
        let transport = try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:nil,validatePreview:nil)
        return MemoryClient(endpoint:f.base.endpoint,credentials:{_ in "synthetic-only"},currentBinding:{f.base.current},
            pendingStore:try manualStore(f),liveReadTransport:transport,managementPendingStore:try f.store(),managementReadEndpoint:f.endpoint)
    }
    private func typed(_ f: ManagementFixture,legacy: MemoryClient,wire: Interceptor) throws -> TypedMemoryClient {
        let root = f.base.root.appendingPathComponent("typed-v2")
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        let secret = f.base.secret
        let store = try TypedMemoryPendingStore(directory:root,maximumBytes:100_000,maximumRecords:20,
            namespace:.init(environment:f.base.binding.environment,account:f.base.binding.account,purpose:.localMemoryPendingV1),
            keyID:f.base.keyID,key:{secret})
        return TypedMemoryClient(endpoint:f.base.endpoint,credentials:{_ in "synthetic-only"},currentBinding:{f.base.current},
            pendingStore:store,interceptedTransport:wire,validatePriorOriginals:{
                if try legacy.requiresOriginalReconciliation(binding:f.base.binding) { throw MemoryFailure.pendingRequiresQuery }
            })
    }
    private func typedCommand() throws -> TypedMemoryCommand {
        try TypedMemoryCommand(operationID:"typed-original",itemID:"typed-item",subject:"self",slot:"test",text:"explicit new input",
            occurredAt:"date unknown",kind:.preference,travelContext:nil)
    }
    private func typedReceipt(_ bytes: Data) throws -> String {
        let c = try TypedMemoryCommand(originalUTF8:bytes)
        return "{\"version\":\"MEMORY-result.2\",\"request_id\":\"\(trace)\",\"receipt\":{\"operation_id\":\"\(c.operationID)\",\"item_id\":\"\(c.itemID)\",\"version\":1,\"status\":\"active\",\"input_sha256\":\"\(digest(bytes))\"}}"
    }
    @Test(arguments:["receipt","null","denied","bad_hash"])
    func oldUnknownCannotBeBypassedByANewWireVersion(_ result: String) async throws {
        let f = try ManagementFixture();defer {f.cleanup()}
        let old = command(),original = try MemoryPending(old)
        let lostACK = Interceptor {_,_,operation in
            #expect(operation == "saveMemory");throw URLError(.networkConnectionLost)
        }
        let writer = MemoryClient(endpoint:f.base.endpoint,credentials:{_ in "synthetic-only"},currentBinding:{f.base.current},
            pendingStore:try manualStore(f),interceptedTransport:lostACK)
        await #expect(throws:MemoryFailure.exchangeUnknown) { try await writer.save(old,binding:f.base.binding) }
        let readerWire = Interceptor(status:result == "denied" ? .forbidden : .ok) {_,_,operation in
            #expect(operation == "queryMemoryReceipt")
            switch result {
            case "null":return "{\"request_id\":\"\(trace)\",\"receipt\":null}"
            case "denied":return "{\"request_id\":\"\(trace)\",\"error\":{\"code\":\"MEMORY_SOURCE_DENIED\",\"category\":\"access\",\"message_en\":\"Denied\",\"message_zh\":\"拒绝\",\"outcome\":\"failed\",\"recovery\":\"do_not_retry\"}}"
            default:return try receipt(original.originalUTF8,badHash:result == "bad_hash")
            }
        }
        let reader = try readOnly(f,wire:readerWire)
        #expect(!reader.manualWritesAvailable && !reader.managementAvailable)
        #expect(try reader.requiresOriginalReconciliation(binding:f.base.binding))
        let reply = try typedReceipt(typedCommand().originalUTF8)
        let typedWire = Interceptor {_,_,operation in #expect(operation == "saveTypedMemory");return reply }
        let client = try typed(f,legacy:reader,wire:typedWire)
        await #expect(throws:MemoryFailure.pendingRequiresQuery) { try await client.save(typedCommand(),binding:f.base.binding) }
        #expect(await typedWire.calls.isEmpty)
        #expect(try client.pending(binding:f.base.binding).isEmpty)
        await #expect(throws:MemoryFailure.liveWriteUnavailable) { try await reader.save(command(),binding:f.base.binding) }
        #expect(await readerWire.calls.isEmpty)
        if result == "receipt" {
            guard case .saved = try await reader.query(operationID:old.operation_id,binding:f.base.binding) else { Issue.record("original receipt not found");return }
            #expect(try !reader.requiresOriginalReconciliation(binding:f.base.binding))
            guard case .saved = try await client.save(typedCommand(),binding:f.base.binding) else { Issue.record("reconciled originals blocked a new save");return }
            #expect(await typedWire.calls.count == 1)
        } else {
            if result == "null" {
                guard case .notObserved = try await reader.query(operationID:old.operation_id,binding:f.base.binding) else { Issue.record("null changed meaning");return }
            } else { await #expect(throws:(any Error).self) { try await reader.query(operationID:old.operation_id,binding:f.base.binding) } }
            #expect(try reader.requiresOriginalReconciliation(binding:f.base.binding))
            await #expect(throws:MemoryFailure.pendingRequiresQuery) { try await client.save(typedCommand(),binding:f.base.binding) }
            #expect(await typedWire.calls.isEmpty)
        }
        #expect(try reader.pending(binding:f.base.binding).map(\.originalUTF8) == [original.originalUTF8])
        #expect(await readerWire.calls.map(\.0) == ["queryMemoryReceipt"])
    }
    @Test func completeOldJournalsAreRequiredBeforeDeclaringReconciliation() throws {
        let f = try Fixture();defer {f.cleanup()}
        let client = try f.client(Interceptor {_,_,_ in Issue.record("unexpected request");return ""})
        #expect(throws:MemoryFailure.unconfigured) { try client.requiresOriginalReconciliation(binding:f.binding) }
    }
    @Test func priorOriginalGateIsRecheckedBeforePOSTButNeverBlocksOriginalQueries() async throws {
        let f = try Fixture();defer {f.cleanup()}
        let gate = PriorOriginalGate()
        let wire = Interceptor {request,_,operation in
            #expect(request.method == .get && operation == "getTypedMemoryReceipt")
            return "{\"version\":\"MEMORY-result.2\",\"request_id\":\"\(trace)\",\"receipt\":null}"
        }
        let client = TypedMemoryClient(endpoint:f.endpoint,credentials:{_ in gate.blocked = true;return "synthetic-only"},
            currentBinding:{f.current},pendingStore:try f.typedStore(),interceptedTransport:wire,
            validatePriorOriginals:{ if gate.blocked { throw MemoryFailure.pendingRequiresQuery } })
        await #expect(throws:MemoryFailure.exchangeUnknown) { try await client.save(typedCommand(),binding:f.binding) }
        #expect(await wire.calls.isEmpty)
        #expect(try client.pending(binding:f.binding).count == 1)
        guard case .notObserved = try await client.query(operationID:"typed-original",binding:f.binding) else { Issue.record("original query blocked by write gate");return }
        #expect(await wire.calls.map(\.0) == ["getTypedMemoryReceipt"])
    }
    @Test func readOnlyLifecycleQueryPreservesOriginalBytesAndCannotApply() async throws {
        let f = try ManagementFixture();defer {f.cleanup()}
        let server = ManagementServer();await server.configure(loseApplyReply:true)
        let writer = try f.client(server)
        let selection = try await f.selection(writer,id:await server.id)
        await #expect(throws:MemoryFailure.exchangeUnknown) { try await writer.applyManagement(.pause,selection:selection,binding:f.base.binding) }
        let original = try #require(try f.store().pending().first)
        let transport = try NoRedirectTransport(interceptedTransport:server,previewEndpoint:nil,validatePreview:nil)
        let unconfigured = MemoryClient(endpoint:f.endpoint,credentials:{_ in "synthetic-only"},currentBinding:{f.base.current},
            pendingStore:try manualStore(f),liveReadTransport:transport,managementPendingStore:try f.store())
        await #expect(throws:MemoryFailure.unconfigured) { try await unconfigured.queryManagement(actionID:original.actionID,binding:f.base.binding) }
        let reader = MemoryClient(endpoint:f.base.endpoint,credentials:{_ in "synthetic-only"},currentBinding:{f.base.current},
            pendingStore:try manualStore(f),liveReadTransport:transport,managementPendingStore:try f.store(),managementReadEndpoint:f.endpoint)
        #expect(try reader.requiresOriginalReconciliation(binding:f.base.binding))
        guard case .historicalReceipt = try await reader.queryManagement(actionID:original.actionID,binding:f.base.binding) else { Issue.record("read-only original receipt unavailable");return }
        #expect(try !reader.requiresOriginalReconciliation(binding:f.base.binding))
        #expect(!reader.managementAvailable && !reader.manualWritesAvailable)
        await #expect(throws:MemoryFailure.unconfigured) { try await reader.applyManagement(.pause,selection:selection,binding:f.base.binding) }
        #expect(try f.store().pending().first?.originalUTF8 == original.originalUTF8)
        #expect(await server.calls.filter({$0.0 == "applyMemoryManagementAction"}).count == 1)
    }
}
