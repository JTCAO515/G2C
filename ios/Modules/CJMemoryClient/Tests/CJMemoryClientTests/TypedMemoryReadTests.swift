import Foundation
import Testing
import CJAPI
@testable import CJMemoryClient

@MainActor struct TypedMemoryReadTests {
    private func item(_ id: String = "item",context: String = "null",extent: String = "long_term") -> String {
        "{\"command\":{\"operation_id\":\"op\",\"item_id\":\"\(id)\",\"subject\":\"traveller\",\"slot\":\"preference\",\"text\":\"原文e\\u0301\",\"occurred_at\":\"去年\",\"source_id\":\"source-original\",\"source_version\":3,\"kind\":\"preference\",\"extent\":\"\(extent)\",\"context\":\(context)},\"version\":4,\"status\":\"active\",\"recorded_at\":\"2026-10-30T11:12:13.123456Z\"}"
    }
    private func detail(_ item: String) -> String { "{\"version\":\"MEMORY-result.2\",\"request_id\":\"\(trace)\",\"item\":\(item)}" }
    private func list(_ items: String) -> String { "{\"version\":\"MEMORY-result.2\",\"request_id\":\"\(trace)\",\"items\":[\(items)]}" }
    @Test func typedReadsNeverReinterpretTravelAsConversationOrDiscardSource() async throws {
        let contexts = ["null","{\"kind\":\"legacy\",\"id\":\"same-id\",\"expected_version\":null}","{\"kind\":\"travel\",\"id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"expected_version\":7}"]
        for (index,context) in contexts.enumerated() {
            let f = try Fixture();defer { f.cleanup() }
            let raw = detail(item(context:context,extent:index == 0 ? "long_term" : "current"))
            let wire = Interceptor { _,_,operation in #expect(operation == "getTypedMemoryItem");return raw }
            let client = try f.typedClient(wire)
            let observed = try await client.detail(itemID:"item",binding:f.binding)
            let read = try #require(observed)
            #expect(read.item.value.command.source_id == "source-original" && read.item.value.command.source_version == 3)
            #expect(Data(read.item.value.command.text.utf8) == Data("原文e\u{301}".utf8))
            switch index {
            case 0:#expect(read.item.scope == .longTerm)
            case 1:#expect(read.item.scope == .legacyConversation("same-id"))
            default:#expect(read.item.scope == .travel(try MemoryTravelSelection(id:String(repeating:"a",count:32),expectedVersion:7)))
            }
            try client.validateRead(read,binding:f.binding)
        }
    }
    @Test(arguments:["true","7.0","7e0","0","-1","9223372036854775808"])
    func storedTravelVersionCannotBeNormalizedOrDefaulted(token: String) async throws {
        let f = try Fixture();defer { f.cleanup() }
        let raw = detail(item(context:"{\"kind\":\"travel\",\"id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"expected_version\":\(token)}",extent:"current"))
        let client = try f.typedClient(Interceptor { _,_,_ in raw })
        await #expect(throws:(any Error).self) { try await client.detail(itemID:"item",binding:f.binding) }
    }
    @Test func invalidConditionalContextCannotBecomeEmptyOrAnotherKind() async throws {
        let bad = ["null","{\"kind\":\"unknown\",\"id\":\"chat\",\"expected_version\":null}",
            "{\"kind\":\"legacy\",\"id\":\"chat\",\"expected_version\":1}",
            "{\"kind\":\"travel\",\"id\":\"chat\",\"expected_version\":7}",
            "{\"kind\":\"legacy\",\"id\":\"chat\",\"expected_version\":null,\"extra\":true}"]
        for context in bad {
            let f = try Fixture();defer { f.cleanup() }
            let raw = detail(item(context:context,extent:"current"))
            let client = try f.typedClient(Interceptor { _,_,_ in raw })
            await #expect(throws:(any Error).self) { try await client.detail(itemID:"item",binding:f.binding) }
        }
    }
    @Test func cursorAndReadAreBoundToClientAndGenerationAndEmptyPageIsExplicit() async throws {
        let f = try Fixture();defer { f.cleanup() }
        let first = list(item())
        let empty = list("")
        let wire = Interceptor { request,_,operation in
            #expect(operation == "listTypedMemories")
            return request.path?.contains("after=item") == true ? empty : first
        }
        let client = try f.typedClient(wire)
        let page = try await client.list(limit:20,binding:f.binding)
        let next = try #require(page.next),read = try #require(page.items.first)
        let last = try await client.list(limit:20,after:next,binding:f.binding)
        #expect(last.items.isEmpty && last.next == nil)
        let other = try f.typedClient(wire)
        #expect(throws:MemoryFailure.staleBinding) { try other.validateRead(read,binding:f.binding) }
        await #expect(throws:MemoryFailure.staleBinding) { try await other.list(limit:20,after:next,binding:f.binding) }
        client.invalidate()
        #expect(throws:MemoryFailure.staleBinding) { try client.validateRead(read,binding:f.binding) }
        await #expect(throws:MemoryFailure.staleBinding) { try await client.list(limit:20,after:next,binding:f.binding) }
        #expect(await wire.calls.count == 2)
    }
    @Test func duplicateAndOutOfOrderRowsAreNotAValidPage() async throws {
        for values in [item() + "," + item(),item("z") + "," + item("a")] {
            let f = try Fixture();defer { f.cleanup() }
            let raw = list(values),client = try f.typedClient(Interceptor { _,_,_ in raw })
            await #expect(throws:MemoryFailure.invalidResponse) { try await client.list(limit:20,binding:f.binding) }
        }
    }
}
