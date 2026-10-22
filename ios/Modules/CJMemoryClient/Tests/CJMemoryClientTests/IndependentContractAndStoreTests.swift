import Testing
import Foundation
import CJAPI
import CryptoKit
@testable import CJMemoryClient

@Suite @MainActor struct IndependentContractAndStoreTests {
    @Test func semanticCandidateForExplicitPreferenceIsAValidReceipt() async throws {
        let f=try Fixture();defer{f.cleanup()}
        var c=command();c.occurred_at="date unknown"
        let expected=try MemoryPending(c)
        let transport=Interceptor { _,bytes,op in
            let original=op=="saveMemory" ? bytes : expected.originalUTF8
            return try receipt(original).replacingOccurrences(of:"\"status\":\"active\"",with:"\"status\":\"candidate\"")
        }
        let client=try f.client(transport)
        do {
            guard case .candidate=try await client.save(c,binding:f.binding) else {Issue.record("Candidate was not surfaced distinctly");return}
        } catch {Issue.record("Valid semantic-unresolved preference candidate receipt rejected")}
        do {
            guard case .candidate=try await client.query(operationID:c.operation_id,binding:f.binding) else {Issue.record("Original candidate query did not settle");return}
        } catch {Issue.record("Valid original candidate query remains unresolvable")}
    }
    @Test func serverOpaqueIDsAreReadableWithoutUUIDNarrowing() async throws {
        let f=try Fixture();defer{f.cleanup()}
        let opaque="e\u{301}"
        let item=itemJSON(id:opaque,timestamp:"2026-10-22T01:00:00.123456Z")
            .replacingOccurrences(of:"00000000-0000-0000-0000-000000000010",with:"original +/%&é")
        let client=try f.client(Interceptor { _,_,op in
            if op=="getMemoryItem" {return "{\"request_id\":\"\(trace)\",\"item\":\(item)}"}
            return "{\"request_id\":\"\(trace)\",\"items\":[\(item)],\"next_after\":\"\(opaque)\"}"
        })
        do {#expect(try await client.detail(itemID:opaque,binding:f.binding) != nil)}
        catch {Issue.record("Contract-valid opaque item ID rejected by detail")}
        do {#expect(try await client.list(limit:1,binding:f.binding).items.count==1)}
        catch {Issue.record("Contract-valid opaque IDs rejected by list validation")}
    }
    @Test func directoryReplacementInsideKeyCallbackCannotLoseDurableOriginalBeforePOST() async throws {
        let f=try Fixture();defer{f.cleanup()}
        let moved=f.root.appendingPathExtension("independent-retired")
        defer{try? FileManager.default.removeItem(at:moved)}
        var swapped=false
        let store=try MemoryPendingStore(directory:f.root,maximumBytes:100_000,maximumRecords:100,
            namespace:.init(environment:f.binding.environment,account:f.binding.account,purpose:.localMemoryPendingV1),keyID:f.keyID) {
                if !swapped {
                    swapped=true
                    try FileManager.default.moveItem(at:f.root,to:moved)
                    try FileManager.default.createDirectory(at:f.root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
                }
                return f.secret
            }
        let transport=Interceptor { _,bytes,_ in try receipt(bytes) }
        let client=MemoryClient(endpoint:f.endpoint,credentials:{_ in "synthetic-only"},currentBinding:{f.current},pendingStore:store,interceptedTransport:transport)
        var c=command();c.occurred_at="date unknown"
        do {_=try await client.save(c,binding:f.binding)} catch {}
        let calls=await transport.calls
        #expect(calls.isEmpty,"POST escaped after canonical pending directory was replaced")
        if !calls.isEmpty {
            #expect(try !f.store().pending().isEmpty,"Reopening canonical directory lost original after POST")
        }
    }
    @Test func optionalOccurrenceCannotEmitServerRejectedBlankValue() throws {
        let option=MemoryManualOption(id:UUID(),label:"Synthetic",disclosure:"Synthetic scope only",subject:"self",slot:"test",kind:.preference,extent:.long_term,contextID:nil)
        // Chosen fix: reject blank input before staging, rather than inventing unknown time.
        #expect(throws: MemoryFailure.unconfigured) { try option.command(text:"synthetic",occurredAt:"") }
        #expect(throws: MemoryFailure.unconfigured) { try option.command(text:"synthetic",occurredAt:" \n") }
        let c = try option.command(text:"synthetic",occurredAt:"date unknown")
        #expect(c.occurred_at == "date unknown")
    }
}

extension IndependentContractAndStoreTests {
    @Test func credentialCallbackReplacementRejectsDispatchAndRetainsOriginalCiphertext() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let moved = f.root.appendingPathExtension("retained-original")
        defer { try? FileManager.default.removeItem(at: moved) }
        let c = command()
        let transport = Interceptor { _, bytes, _ in try receipt(bytes) }
        let client = try f.client(transport, credentials: { _ in
            try FileManager.default.moveItem(at: f.root, to: moved)
            try FileManager.default.createDirectory(at: f.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
            return "synthetic-only"
        })
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await client.save(c, binding: f.binding) }
        #expect(await transport.calls.isEmpty)
        #expect(try FileManager.default.contentsOfDirectory(atPath: moved.path).count == 1)
        // Restore the original directory in this synthetic test only; production never auto-restores.
        try FileManager.default.removeItem(at: f.root)
        try FileManager.default.moveItem(at: moved, to: f.root)
        let original = try f.store().pending()
        #expect(original.count == 1)
        let expected = try MemoryPending(c)
        #expect(original.first?.originalUTF8 == expected.originalUTF8)
    }
    @Test func inferenceStillCannotSettleAsActive() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let client = try f.client(Interceptor { _, bytes, _ in
            try receipt(bytes).replacingOccurrences(of: "\"status\":\"candidate\"", with: "\"status\":\"active\"")
        })
        await #expect(throws: MemoryFailure.invalidResponse) { try await client.save(command(inference: true), binding: f.binding) }
        #expect(try f.store().pending().count == 1)
    }
    @Test func blankManualFieldsFailBeforePersistenceOrCredentials() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let transport = Interceptor { _, _, _ in Issue.record("Unexpected dispatch"); return "{}" }
        let client = try f.client(transport, credentials: { _ in Issue.record("Unexpected credentials"); return nil })
        for occurrence in ["", " \n", String(repeating: "x", count: 4097)] {
            var c = command(); c.occurred_at = occurrence
            await #expect(throws: MemoryFailure.invalidInput) { try await client.save(c, binding: f.binding) }
        }
        #expect(try f.store().pending().isEmpty)
        #expect(await transport.calls.isEmpty)
    }
    @Test func opaquePendingIDsPreserveNFDAndReadLegacyUUIDFiles() throws {
        let f = try Fixture(); defer { f.cleanup() }
        var nfd = command(); nfd.operation_id = "op-e\u{301}/%"; nfd.item_id = "resource /+%"
        var nfc = nfd; nfc.operation_id = "op-é/%"
        let store = try f.store()
        try store.append(MemoryPending(nfd)); try store.append(MemoryPending(nfc))
        let originals = try store.pending()
        #expect(Set(originals.map { Data($0.operationID.utf8) }).count == 2)
        let c = command(); let record = try MemoryPending(c); try store.append(record)
        let hashPath = f.root.appendingPathComponent(digest(Data(c.operation_id.utf8)) + ".memory")
        let legacyPath = f.root.appendingPathComponent(UUID(uuidString: c.operation_id)!.uuidString + ".memory")
        try FileManager.default.moveItem(at: hashPath, to: legacyPath)
        #expect(try store.pending().count == 3)
        #expect(throws: MemoryFailure.storageUnavailable) { try store.append(record) }
    }
    @Test func opaqueDetailRequiresExactBytes() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let client = try f.client(Interceptor { _, _, _ in
            "{\"request_id\":\"\(trace)\",\"item\":\(itemJSON(id: "é", timestamp: "2026-10-22T01:00:00Z"))}"
        })
        await #expect(throws: MemoryFailure.invalidResponse) { try await client.detail(itemID: "e\u{301}", binding: f.binding) }
    }
}
