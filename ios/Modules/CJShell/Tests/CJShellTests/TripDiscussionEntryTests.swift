import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJTripClient
import CJMessageHTTP
@testable import CJShell

private let discussionTripTrace = "00000000-0000-4000-8000-000000000021"
private actor DiscussionTripRead: ClientTransport {
    let raw: Data
    var calls = 0
    init(_ raw: Data) { self.raw=raw }
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        #expect(request.method == .get && body == nil && operationID == "readStructuredTripV1")
        calls += 1
        var headers=HTTPFields();headers[.contentType]="application/json";headers[.cacheControl]="no-store";headers[.init("x-request-id")!]=discussionTripTrace
        return (HTTPResponse(status:.ok,headerFields:headers),HTTPBody(raw))
    }
}
@MainActor private final class DiscussionTripLifetime {
    let binding=TripBinding(environment:UUID(),account:UUID(),generation:UUID(),selection:UUID())
    var current=true
}
@MainActor struct TripDiscussionEntryTests {
    private func source(_ name:String) throws -> Data {
        struct Golden: Decodable { let name:String;let canonical_utf8_base64:String;let sha256:String }
        var root=URL(fileURLWithPath:#filePath)
        for _ in 0..<4 { root.deleteLastPathComponent() }
        let values=try JSONDecoder().decode([Golden].self,from:Data(contentsOf:root.appendingPathComponent("CJTripClient/Tests/CJTripClientTests/Fixtures/STRUCTURED-V1.json")))
        let fixture=try #require(values.first { $0.name==name }),raw=try #require(Data(base64Encoded:fixture.canonical_utf8_base64))
        return Data(("{\"version\":\"TRIP-structured-read.1\",\"request_id\":\""+discussionTripTrace+"\",\"trip\":{\"trip_id\":\"trip-a\",\"version\":7,\"content_sha256\":\""+fixture.sha256+"\",\"content\":"+String(decoding:raw,as:UTF8.self)+"}}").utf8)
    }
    private func setup(_ name:String) throws -> (TripTimelineHost,TripClient,DiscussionTripLifetime,ShellGeneration,DiscussionTripRead) {
        let lifetime=DiscussionTripLifetime(),shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let wire=DiscussionTripRead(try source(name))
        let client=TripClient(endpoint:try TripEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:16384,maximumResponseBytes:100000),credentials:{ _ in "synthetic" },currentBinding:{ lifetime.current ? lifetime.binding : nil },interceptedTransport:wire)
        let host=TripTimelineHost(client:client,binding:lifetime.binding,generation:shell.generation,current:{ lifetime.current })
        return (host,client,lifetime,shell.generation,wire)
    }
    @Test func onlyAcceptedExplicitSourceMintsDayItemAndWholeTrip() async throws {
        let (host,_,lifetime,generation,wire)=try setup("explicit")
        #expect(throws:(any Error).self) { try host.discussion(day:nil,itemID:nil) }
        await host.perform(try host.select("trip-a"))
        let day=try MessageTripSelection.Day(date:"2026-11-01",timezone:"Asia/Shanghai")
        let choice=try host.discussion(day:day,itemID:"item-1")
        try choice.validate(scopeEnvironment:lifetime.binding.environment.uuidString,scopeAccount:lifetime.binding.account.uuidString,generation:generation)
        #expect(choice.selection.id=="trip-a" && choice.selection.expectedVersion==7 && choice.selection.day==day && choice.selection.itemID=="item-1")
        let whole=try host.discussion(day:nil,itemID:nil)
        #expect(whole.selection.day==nil && whole.selection.itemID==nil)
        #expect(Mirror(reflecting:choice).children.isEmpty)
        #expect(await wire.calls==1)
        #expect(throws:(any Error).self) { try host.discussion(day:nil,itemID:"other-item") }
        #expect(throws:(any Error).self) { try host.discussion(day:MessageTripSelection.Day(date:"2026-11-01",timezone:"America/New_York"),itemID:"item-1") }
    }
    @Test func unknownScheduleNeverBecomesDeviceDayButItemIsStillExplicit() async throws {
        let (host,_,_,_,_)=try setup("unknown")
        await host.perform(try host.select("trip-a"))
        let item=try host.discussion(day:nil,itemID:"item-1")
        #expect(item.selection.day==nil && item.selection.itemID=="item-1")
        #expect(throws:(any Error).self) { try host.discussion(day:MessageTripSelection.Day(date:"2026-11-01",timezone:"Asia/Shanghai"),itemID:"item-1") }
    }
    @Test func closingViewKeepsCapturedSourceButABAOrOwnerChangeRetiresIt() async throws {
        let (host,client,lifetime,generation,_)=try setup("explicit")
        await host.perform(try host.select("trip-a"))
        let choice=try host.discussion(day:nil,itemID:"item-1")
        host.invalidate()
        try choice.validate(scopeEnvironment:lifetime.binding.environment.uuidString,scopeAccount:lifetime.binding.account.uuidString,generation:generation)
        #expect(throws:TripFailure.staleBinding) { try choice.validate(scopeEnvironment:lifetime.binding.environment.uuidString,scopeAccount:UUID().uuidString,generation:generation) }
        _=try client.prepareStructuredDetail(id:"trip-b",binding:lifetime.binding)
        _=try client.prepareStructuredDetail(id:"trip-a",binding:lifetime.binding)
        #expect(throws:TripFailure.staleBinding) { try choice.validate(scopeEnvironment:lifetime.binding.environment.uuidString,scopeAccount:lifetime.binding.account.uuidString,generation:generation) }
    }
    @Test func identityRetirementHidesSourceAndCannotMintAnotherEntry() async throws {
        let (host,_,lifetime,generation,_)=try setup("explicit")
        await host.perform(try host.select("trip-a"))
        let choice=try host.discussion(day:nil,itemID:nil)
        lifetime.current=false
        #expect(host.display()==nil)
        #expect(throws:TripFailure.staleBinding) { try host.discussion(day:nil,itemID:nil) }
        #expect(throws:TripFailure.staleBinding) { try choice.validate(scopeEnvironment:lifetime.binding.environment.uuidString,scopeAccount:lifetime.binding.account.uuidString,generation:generation) }
    }
}
