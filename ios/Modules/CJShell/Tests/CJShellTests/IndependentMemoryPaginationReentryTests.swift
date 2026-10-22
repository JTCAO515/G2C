import Foundation
import Testing
import CJAPI
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJMemoryClient
@testable import CJShell

private let pageTrace="00000000-0000-4000-8000-000000000001"
private actor PageTransport:ClientTransport {
    var replies:[Data];var calls:[String]=[]
    init(_ replies:[Data]){self.replies=replies}
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws ->(HTTPResponse,HTTPBody?) {
        calls.append(operationID)
        guard !replies.isEmpty else {throw MemoryFailure.exchangeUnknown}
        var response=HTTPResponse(status:.ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!]=pageTrace
        response.headerFields[.contentType]="application/json"
        let bytes = operationID == "getMemoryItem" ? replies.removeLast() : replies.removeFirst()
        return(response,HTTPBody(bytes))
    }
}
@MainActor private final class PageBinding {
    let value=MemoryBinding(environment:UUID(),account:UUID(),generation:UUID(),selection:UUID())
    var trigger=2;var armed=false;var calls=0;var callback:(()->Void)?
    func current()->MemoryBinding? {
        if armed {calls+=1;if calls==trigger {armed=false;callback?()}}
        return value
    }
}
@Suite @MainActor struct IndependentMemoryPaginationReentryTests {
    @Test(arguments: [1, 2, 3]) func oldNextPageCannotEraseNewItemSelectionDuringHasMoreCallback(trigger: Int) async throws {
        func data(_ extra:[String:Any])throws->Data {try JSONSerialization.data(withJSONObject:extra.merging(["request_id":pageTrace]){a,_ in a})}
        let item:[String:Any]=["command":["operation_id":"op-a","item_id":"a","subject":"self","slot":"test","text":"synthetic","source_id":"source","source_version":1,"occurred_at":"date unknown","kind":"preference","extent":"long_term","context_id":NSNull()],"version":1,"status":"active","recorded_at":"2026-10-22T01:00:00Z"]
        let transport=PageTransport([try data(["groups":[["subject":"self","status":"active","count":1]]]),try data(["items":[item],"next_after":"a"]),try data(["items":[],"next_after":NSNull()]),try data(["item":item])])
        let binding=PageBinding()
        let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let host=MemoryContainerHost(shell:shell)
        let client=MemoryClient(endpoint:try MemoryEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:100000,maximumResponseBytes:100000),credentials:{_ in "SYNTHETIC"},currentBinding:{binding.current()},pendingStore:nil,interceptedTransport:transport)
        #expect(host.bind(MemoryContainerBinding(client:client,memory:binding.value,shellGeneration:shell.generation,pageSize:2,synthetic:true,currentBinding:{binding.current()})))
        await host.loadGroups(context:host.captureAction())
        guard case .loaded(let groups)=host.groups else {Issue.record("setup groups failed");return}
        #expect(host.selectGroup(try #require(groups.first),context:host.captureAction()))
        await host.loadItems(context:host.captureAction())
        #expect(host.hasMore)
        let old=try #require(host.captureAction());var selected=false
        binding.callback={selected=host.selectItem("a",context:host.captureAction())}
        binding.trigger=trigger;binding.armed=true;binding.calls=0
        await host.loadItems(context:old,more:true)
        #expect(selected)
        #expect(await transport.calls.count==2,"Old page dispatched after a newer item-selection epoch")
        await host.loadDetail(context:host.captureAction())
        #expect(await transport.calls.last=="getMemoryItem","Old page cleared the newly selected detail item")
        guard case .loaded(let detail)=host.detail else { Issue.record("Selected detail was not loaded"); return }
        #expect(detail?.command.item_id == "a")
    }
}
