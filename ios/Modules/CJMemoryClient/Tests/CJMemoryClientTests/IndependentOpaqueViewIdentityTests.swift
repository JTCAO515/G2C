import Foundation
import Testing
import CJAPI
@testable import CJMemoryClient

@Suite @MainActor struct IndependentOpaqueViewIdentityTests {
    @Test func acceptedOpaqueRowsHaveUniqueCurrentViewIDs() async throws {
        let f=try Fixture();defer{f.cleanup()}
        let first="e\u{301}",second="é"
        let json="{\"request_id\":\"\(trace)\",\"items\":[\(itemJSON(id:first,timestamp:"2026-10-22T01:00:00Z")),\(itemJSON(id:second,timestamp:"2026-10-22T01:00:00Z"))],\"next_after\":\"\(second)\"}"
        let client=try f.client(Interceptor {_,_,_ in json})
        let page=try await client.list(limit:2,binding:f.binding)
        #expect(page.items.count==2)
        #expect(Set(page.items.map {Data($0.command.item_id.utf8)}).count==2)
        // Exact current MemoryItemsView ForEach identity key path. This is an
        // identity/Hashable check; it does not claim a rendered-device observation.
        #expect(page.items.map { Data($0.command.item_id.utf8) } == [Data(first.utf8), Data(second.utf8)])
        let currentViewIDs=page.items.map(\.memoryRowIdentity)
        #expect(page.items.reversed().map(\.memoryRowIdentity) == currentViewIDs.reversed())
        #expect(Set(currentViewIDs).count==page.items.count,
            "Byte-distinct legal server IDs must have distinct ForEach identity")
    }
}
