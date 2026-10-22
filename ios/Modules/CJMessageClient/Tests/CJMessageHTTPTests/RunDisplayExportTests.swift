import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime

private actor RunDisplayIntercept: ClientTransport {
    let bytes:Data
    let trace:String?
    var paths:[String?]=[]
    init(bytes:Data,trace:String?) {self.bytes=bytes;self.trace=trace}
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        #expect(request.method == .get && operationID == "getRunDisplaySnapshot")
        #expect(body == nil)
        paths.append(request.path)
        var response=HTTPResponse(status:.ok)
        if let trace {response.headerFields[HTTPField.Name("X-Request-ID")!]=trace}
        response.headerFields[.contentType]="application/json"
        return (response,HTTPBody(bytes))
    }
}
struct RunDisplayExportTests {
    let trace="7ac6d943-3772-4aa2-aea7-aed4c819a6f5"
    private func snapshot(_ status:String="queued")->[String:Any] {
        ["conversation_id":"fixture-chat","generation":"fixture-generation","message_id":"m/+%e\u{301}","run_id":"fixture-run","message_sequence":1,"status":status,"event_highwater":0,"text":"","text_state":status=="completed" ? "complete":"partial"]
    }
    private func data(_ snapshot:Any) throws -> Data {try JSONSerialization.data(withJSONObject:["request_id":trace,"snapshot":snapshot])}
    @Test func officialGETUsesOriginalQueryAndRequiresHeader() async throws {
        let transport=RunDisplayIntercept(bytes:try data(snapshot()),trace:trace)
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:transport)
        let id="m/+%e\u{301}"
        let result=try await client.getRunDisplaySnapshot(.init(query:.init(message_id:id)))
        let body=try result.ok.body.json
        #expect(body.snapshot.message_id==id && body.snapshot.status == .queued)
        #expect(try result.ok.headers.X_hyphen_Request_hyphen_ID==trace)
        let paths=await transport.paths
        let path=try #require(paths.first ?? nil)
        let items=try #require(URLComponents(string:"https://synthetic.invalid"+path)?.queryItems)
        #expect(items.count==1 && items[0].name=="message_id")
        #expect(Data((items[0].value ?? "").utf8)==Data(id.utf8))
        let missing=RunDisplayIntercept(bytes:try data(snapshot()),trace:nil)
        let rejected=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),transport:missing)
        await #expect(throws:(any Error).self) {try await rejected.getRunDisplaySnapshot(.init(query:.init(message_id:id)))}
    }
    @Test func sevenStatusesAndTextStateUseOfficialTypes() throws {
        let statuses=["queued","running","completed","failed","cancelled","context_invalid","unknown"]
        #expect(Components.Schemas.RunDisplaySnapshot.statusPayload.allCases.count==7)
        for status in statuses {
            let decoded=try JSONDecoder().decode(Components.Schemas.RunDisplayResponse.self,from:data(snapshot(status)))
            #expect(decoded.snapshot.status.rawValue==status)
            #expect(decoded.snapshot.text_state.rawValue==(status=="completed" ? "complete":"partial"))
            #expect(decoded.snapshot.message_sequence==1 && decoded.snapshot.event_highwater==0)
        }
    }
    @Test func requiredSnapshotAndStrictGeneratedFieldsDoNotBecomeEmpty() throws {
        let missing=try JSONSerialization.data(withJSONObject:["request_id":trace])
        #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.RunDisplayResponse.self,from:missing)}
        #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.RunDisplayResponse.self,from:data(NSNull()))}
        var unknown=snapshot();unknown["status"]="invented"
        var wrongText=snapshot();wrongText["text_state"]="finished"
        var noGeneration=snapshot();noGeneration.removeValue(forKey:"generation")
        var extra=snapshot();extra["scope"]="caller-scope"
        for value in [unknown,wrongText,noGeneration,extra] {
            #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.RunDisplayResponse.self,from:data(value))}
        }
    }
}
