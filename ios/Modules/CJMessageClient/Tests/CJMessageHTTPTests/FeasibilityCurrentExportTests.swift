import Foundation
import CryptoKit
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

private actor FeasibilityIntercept: ClientTransport {
    let bytes:Data;let status:Int;let trace:String
    var paths:[String?]=[]
    init(bytes:Data,status:Int=200,trace:String) {self.bytes=bytes;self.status=status;self.trace=trace}
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        #expect(request.method == .get && body == nil && operationID==Operations.evaluateCurrentNeedsFeasibility.id)
        paths.append(request.path)
        var response=HTTPResponse(status:.init(code:status));response.headerFields[.contentType]="application/json";response.headerFields[HTTPField.Name("X-Request-ID")!]=trace
        return(response,HTTPBody(bytes))
    }
}
struct FeasibilityCurrentExportTests {
    let trace="b7d55cfd-8af6-454e-b252-3c38c38f4f34"
    var original:String {" {\"budget\":\"123.4500\",\"note\":\"e\u{301}\"} \n"}
    var inputHash:String {SHA256.hash(data:Data(original.utf8)).map{String(format:"%02x",$0)}.joined()}
    private func report(status:String="CONFLICT",overall:String="UNKNOWN")->[String:Any] {
        let evidence:[String:Any]=["path":"budget","declaration":"123.4500","revision":1,"action_id":"synthetic-action","original_input_sha256":inputHash]
        let nullEvidence:[String:Any]=["path":"optional","declaration":NSNull(),"revision":NSNull(),"action_id":NSNull(),"original_input_sha256":NSNull()]
        let check:[String:Any]=["code":"synthetic_codec_check","status":status=="UNKNOWN" ? "PASS":"CONFLICT","missing":[],"zh":"合成检查","en":"Synthetic check","details":[["amount","123.4500"]],"evidence":[evidence,nullEvidence]]
        return ["version":"CJ-FEASIBILITY-CURRENT-READ@0.1.0-candidate.1","evaluator_version":"CJ-FEASIBILITY-NEEDS@0.1.0-candidate.1","status":status,"needs_id":"synthetic-needs","revision":1,"content_sha256":String(repeating:"0",count:64),"overall":overall,"checks":[check],"sources":[["revision":1,"action_id":"synthetic-action","original_input_utf8":original,"original_input_sha256":inputHash]]]
    }
    private func bytes(_ value:[String:Any]) throws -> Data {try JSONSerialization.data(withJSONObject:["request_id":trace,"evaluation":value])}
    @Test func officialGETPreservesOriginalUTF8HashAndDecimalText() async throws {
        let wire=FeasibilityIntercept(bytes:try bytes(report()),trace:trace)
        let transport=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:nil,validatePreview:nil)
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:transport)
        let output=try await client.evaluateCurrentNeedsFeasibility(.init(query:.init(needs_id:"synthetic-needs")))
        let value=try output.ok.body.json
        #expect(value.request_id==trace && value.evaluation.status == .CONFLICT && value.evaluation.overall == .UNKNOWN)
        #expect(Data(value.evaluation.sources[0].original_input_utf8.utf8)==Data(original.utf8))
        #expect(value.evaluation.sources[0].original_input_sha256==inputHash)
        #expect(value.evaluation.checks[0].evidence[0].declaration.value as? String == "123.4500")
        #expect(value.evaluation.checks[0].details[0][1]=="123.4500")
        #expect(value.evaluation.checks[0].evidence[1].declaration.value==nil)
        let paths=await wire.paths;#expect(paths==["/v1/needs-feasibility?needs_id=synthetic-needs"])
    }
    @Test func unknownLocalPassAndInvalidSuccessShapesCannotBecomeFeasible() throws {
        let decoder=JSONDecoder()
        let value=try decoder.decode(Components.Schemas.FeasibilityCurrentResponse.self,from:bytes(report(status:"UNKNOWN")))
        #expect(value.evaluation.status == .UNKNOWN && value.evaluation.overall == .UNKNOWN)
        #expect(value.evaluation.checks[0].status == .PASS)
        for invalid in [report(status:"FEASIBLE"),report(overall:"FEASIBLE"),report(status:"INVALID")] {
            #expect(throws:DecodingError.self) {try decoder.decode(Components.Schemas.FeasibilityCurrentResponse.self,from:bytes(invalid))}
        }
        for missing:[String:Any] in [["request_id":trace],["request_id":trace,"evaluation":NSNull()]] {
            #expect(throws:DecodingError.self) {try decoder.decode(Components.Schemas.FeasibilityCurrentResponse.self,from:JSONSerialization.data(withJSONObject:missing))}
        }
    }
    @Test func sourceInvalidAndUnavailableAreSafeBASEErrorsNotReports() async throws {
        for code in ["FEASIBILITY_INPUT_INVALID","FEASIBILITY_UNAVAILABLE"] {
            let error=try JSONSerialization.data(withJSONObject:["request_id":trace,"error":["code":code,"category":"dependency","outcome":"unknown","recovery":"retry_safe_read","message_en":"Synthetic unavailable","message_zh":"合成不可用"]])
            let wire=FeasibilityIntercept(bytes:error,status:503,trace:trace)
            let transport=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:nil,validatePreview:nil)
            let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),transport:transport)
            let output=try await client.evaluateCurrentNeedsFeasibility(.init(query:.init(needs_id:"synthetic-needs")))
            if case .default(let status,let response)=output {
                let value=try response.body.json
                #expect(status==503 && value.error.code==code && value.error.outcome == .unknown && value.error.recovery == .retry_safe_read)
            } else {Issue.record("invalid/unavailable must not become successful report")}
            #expect(await wire.paths.count==1)
            #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.FeasibilityCurrentResponse.self,from:error)}
        }
    }
}
