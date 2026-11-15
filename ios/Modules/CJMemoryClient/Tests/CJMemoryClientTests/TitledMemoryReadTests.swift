import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJAPI
@testable import CJMemoryClient

@MainActor struct TitledMemoryReadTests {
    @Test func requiredNullPayloadsDecodeWithoutInventingItemOrTitle() throws {
        let bytes = Data("null".utf8)
        let title = try JSONDecoder().decode(Components.Schemas.MemoryItemV3.titlePayload.self,from:bytes)
        #expect(title.value1 == nil && title.value2 != nil)
        #expect(try JSONEncoder().encode(title) == bytes)
        let item = try JSONDecoder().decode(Components.Schemas.MemoryDetailV3Response.itemPayload.self,from:bytes)
        #expect(item.value1 == nil && item.value2 != nil)
        #expect(try JSONEncoder().encode(item) == bytes)
    }
    private func item(_ title: String?, id: String = "item") -> String {
        let titleField = title.map { ",\"title\":\($0)" } ?? ""
        return "{\"command\":{\"operation_id\":\"op\",\"item_id\":\"\(id)\",\"subject\":\"traveller\",\"slot\":\"preference\",\"text\":\"body e\\u0301\",\"occurred_at\":\"date unknown\",\"source_id\":\"source-original\",\"source_version\":3,\"kind\":\"preference\",\"extent\":\"long_term\",\"context\":null},\"version\":4,\"status\":\"active\",\"recorded_at\":\"2026-10-30T11:12:13.123456Z\"\(titleField)}"
    }
    private func envelope(_ item: String, list: Bool, version: String = "MEMORY-result.3") -> String {
        "{\"version\":\"\(version)\",\"request_id\":\"\(trace)\",\"\(list ? "items" : "item")\":\(list ? "[" + item + "]" : item)}"
    }
    private func client(_ f: Fixture, _ wire: any ClientTransport) throws -> TypedMemoryClient {
        try TypedMemoryClient(endpoint:f.endpoint,credentials:{ _ in "synthetic-only" },currentBinding:{ f.current },
                              pendingStore:f.typedStore(),interceptedTransport:wire,readVersion:.v3)
    }

    @Test(arguments:["null", "\"\"", "\"  \"", "\"豪华出行\"", "\"Luxury travel\"", "\"cafe\\u0301\""])
    func titlesAreAdvisoryAndOriginalBytesStayAuthoritative(title: String) async throws {
        for listing in [false, true] {
            let f = try Fixture(); defer { f.cleanup() }
            let raw = envelope(item(title),list:listing)
            let wire = Interceptor { request,bytes,operation in
                #expect(operation == (listing ? "listTitledMemories" : "getTitledMemoryItem"))
                #expect(request.method == .get && bytes.isEmpty)
                #expect(request.path?.hasPrefix(listing ? "/v3/memories?" : "/v3/memory-items?") == true)
                return raw
            }
            let reader = try client(f,wire)
            let read: TypedMemoryRead
            if listing { read = try #require(try await reader.list(limit:20,binding:f.binding).items.first) }
            else { read = try #require(try await reader.detail(itemID:"item",binding:f.binding)) }
            let expected: String?
            if title == "null" { expected = nil }
            else {
                let decoded = try JSONDecoder().decode(String.self,from:Data(title.utf8))
                expected = decoded.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty ? nil : decoded
            }
            #expect(read.item.title.map { Data($0.utf8) } == expected.map { Data($0.utf8) })
            #expect(Data(read.item.value.command.text.utf8) == Data("body e\u{301}".utf8))
            #expect(read.item.value.command.source_id == "source-original" && read.item.value.command.source_version == 3)
            #expect(read.item.value.version == 4 && read.item.scope == .longTerm)
            try reader.validateRead(read,binding:f.binding)
        }
    }

    @Test func malformedTitlesAreFailuresRatherThanBodyFallback() async throws {
        let bad: [String?] = [nil, "true", "7", "[]", "{}", "\"line\\nnext\"", "\"line\\r\\nnext\"", "\"a\\tb\"",
                              "\"" + String(repeating:"a",count:4097) + "\""]
        for title in bad {
            for listing in [false, true] {
                let f = try Fixture(); defer { f.cleanup() }
                let raw = envelope(item(title),list:listing)
                let wire = Interceptor { _,_,_ in raw }, reader = try client(f,wire)
                if listing { await #expect(throws:(any Error).self) { try await reader.list(limit:20,binding:f.binding) } }
                else { await #expect(throws:(any Error).self) { try await reader.detail(itemID:"item",binding:f.binding) } }
                #expect(await wire.calls.count == 1)
            }
        }
    }

    @Test func nullItemIsAbsentButMalformedItemCannotBecomeNull() async throws {
        for malformed in [false, true] {
            let f = try Fixture(); defer { f.cleanup() }
            let value = malformed ? item("null").replacingOccurrences(of:"\"text\":\"body e\\u0301\",",with:"") : "null"
            let raw = envelope(value,list:false)
            let reader = try client(f,Interceptor { _,_,_ in raw })
            if malformed { await #expect(throws:(any Error).self) { try await reader.detail(itemID:"item",binding:f.binding) } }
            else { #expect(try await reader.detail(itemID:"item",binding:f.binding) == nil) }
        }
    }

    @Test func wrongVersionAndHTTPFailureNeverSelectV2() async throws {
        for status in [HTTPResponse.Status.ok,.notFound] {
            let f = try Fixture(); defer { f.cleanup() }
            let raw = status == .ok ? envelope(item("null"),list:false,version:"MEMORY-result.2")
                : "{\"request_id\":\"\(trace)\",\"error\":{\"code\":\"MEMORY_NOT_FOUND\",\"category\":\"access\",\"message_en\":\"Unavailable\",\"message_zh\":\"不可用\",\"outcome\":\"failed\",\"recovery\":\"do_not_retry\"}}"
            let wire = Interceptor(status:status) { _,_,_ in raw }, reader = try client(f,wire)
            await #expect(throws:(any Error).self) { try await reader.detail(itemID:"item",binding:f.binding) }
            let calls = await wire.calls
            #expect(calls.count == 1 && calls.first?.0 == "getTitledMemoryItem")
        }
    }

    @Test func titledCursorsAndReadsRetainOwnerAndGenerationFences() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let raw = envelope(item("\"Luxury travel\""),list:true), empty = envelope("",list:true)
        let wire = Interceptor { request,_,_ in request.path?.contains("after=item") == true ? empty : raw }
        let reader = try client(f,wire), page = try await reader.list(limit:20,binding:f.binding)
        let read = try #require(page.items.first), cursor = try #require(page.next)
        let last = try await reader.list(limit:20,after:cursor,binding:f.binding)
        #expect(last.items.isEmpty && last.next == nil)
        let foreign = try client(f,wire)
        #expect(throws:MemoryFailure.staleBinding) { try foreign.validateRead(read,binding:f.binding) }
        await #expect(throws:MemoryFailure.staleBinding) { try await foreign.list(limit:20,after:cursor,binding:f.binding) }
        reader.retirePresentation()
        #expect(throws:MemoryFailure.staleBinding) { try reader.validateRead(read,binding:f.binding) }
        await #expect(throws:MemoryFailure.staleBinding) { try await reader.list(limit:20,after:cursor,binding:f.binding) }
        #expect(await wire.calls.count == 2)
    }

    @Test func duplicateAndOutOfOrderTitledRowsAreNotAValidPage() async throws {
        for rows in [item("null") + "," + item("null"), item("null",id:"z") + "," + item("null",id:"a")] {
            let f = try Fixture(); defer { f.cleanup() }
            let raw = envelope(rows,list:true), reader = try client(f,Interceptor { _,_,_ in raw })
            await #expect(throws:MemoryFailure.invalidResponse) { try await reader.list(limit:20,binding:f.binding) }
        }
    }

    @Test func v2IsStillTheDefaultAndDoesNotInventTitles() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let raw = envelope(item(nil),list:false,version:"MEMORY-result.2")
        let wire = Interceptor { request,_,operation in
            #expect(operation == "getTypedMemoryItem" && request.path?.hasPrefix("/v2/memory-items?") == true)
            return raw
        }
        let reader = try f.typedClient(wire)
        let read = try #require(try await reader.detail(itemID:"item",binding:f.binding))
        #expect(read.item.title == nil)
        #expect(Data(read.item.value.command.text.utf8) == Data("body e\u{301}".utf8))
    }

    @Test func titledReadSelectionNeverChangesTheSaveWireOrOriginalBytes() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let command = try TypedMemoryCommand(operationID:"save",itemID:"saved-item",subject:"traveller",slot:"preference",
                                             text:"body e\u{301}",occurredAt:"date unknown",kind:.preference,travelContext:nil)
        let wire = Interceptor { request,bytes,operation in
            #expect(operation == "saveTypedMemory" && request.method == .post && request.path == "/v2/memories")
            #expect(bytes == command.originalUTF8)
            return "{\"version\":\"MEMORY-result.2\",\"request_id\":\"\(trace)\",\"receipt\":{\"operation_id\":\"save\",\"item_id\":\"saved-item\",\"version\":1,\"status\":\"active\",\"input_sha256\":\"\(digest(bytes))\"}}"
        }
        let reader = try client(f,wire)
        guard case .saved = try await reader.save(command,binding:f.binding) else { Issue.record("V2 save did not complete"); return }
        #expect(await wire.calls.count == 1)
    }
}
