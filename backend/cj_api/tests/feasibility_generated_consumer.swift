import Foundation
import CryptoKit
import CJAPI
import OpenAPIRuntime
import HTTPTypes
private enum Failed:Error{case check,unexpected}
private func sha(_ raw:Data)->String{SHA256.hash(data:raw).map{String(format:"%02x",$0)}.joined()}
private func original(_ id:String)->String{"\n { \"action_id\":\"source-1\",\"needs_id\":\"\(id)\",\"source\":{\"kind\":\"manual\",\"text\":\"e\u{301} 原始 / synthetic\"},\"expected_version\":0,\"changes\":{\"budget_total\":{\"state\":\"known\",\"value\":\"100.000001\"}} }\n"}
private struct Transport:ClientTransport{
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String)async throws->(HTTPResponse,HTTPBody?){
        let conflict=request.path=="/v1/needs-feasibility?needs_id=needs-conflict"
        guard operationID=="evaluateCurrentNeedsFeasibility",conflict || request.path=="/v1/needs-feasibility?needs_id=needs-unknown" else{throw Failed.check}
        let id=conflict ? "needs-conflict":"needs-unknown",raw=original(conflict ? "needs-conflict":"needs-unknown")
        let evidence:[String:Any]=["path":"budget_total","declaration":["state":"known","value":"100.000001"],"revision":1,"action_id":"source-1","original_input_sha256":sha(Data(raw.utf8))]
        let check:[String:Any]=["code":"BUDGET_SCOPE_UNPROVEN","status":"UNKNOWN","missing":["typed_cost_coverage"],"zh":"仅原声明，整体未知","en":"Declarations only; overall unknown","details":[["relation","equal"]],"evidence":[evidence]]
        let report:[String:Any]=["version":"CJ-FEASIBILITY-CURRENT-READ@0.1.0-candidate.1","evaluator_version":"CJ-FEASIBILITY-NEEDS@0.1.0-candidate.1","status":conflict ? "CONFLICT":"UNKNOWN","needs_id":id,"revision":1,"content_sha256":String(repeating:"b",count:64),"overall":"UNKNOWN","checks":[check],"sources":[["revision":1,"action_id":"source-1","original_input_utf8":raw,"original_input_sha256":sha(Data(raw.utf8))]]]
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json";response.headerFields[.init("X-Request-ID")!]="00000000-0000-4000-8000-000000000001"
        return(response,HTTPBody(try JSONSerialization.data(withJSONObject:["request_id":"00000000-0000-4000-8000-000000000001","evaluation":report])))
    }
}
@main struct FeasibilityConsumer{
    static func main()async throws{
        guard let url=URL(string:"https://fixture.invalid") else{throw Failed.check}
        let client=Client(serverURL:url,configuration:.memory,transport:Transport())
        for id in ["needs-conflict","needs-unknown"]{
            let response=try await client.evaluateCurrentNeedsFeasibility(.init(query:.init(needs_id:id))).ok
            let body=try response.body.json,report=body.evaluation
            guard body.request_id==response.headers.X_hyphen_Request_hyphen_ID,report.needs_id==id,report.overall == .UNKNOWN,
                  report.status.rawValue==(id=="needs-conflict" ? "CONFLICT":"UNKNOWN"),
                  Data(report.sources[0].original_input_utf8.utf8)==Data(original(id).utf8),
                  report.sources[0].original_input_sha256==sha(Data(original(id).utf8)),report.checks[0].status == .UNKNOWN,
                  report.checks[0].details==[["relation","equal"]] else{throw Failed.check}
            let declaration=try JSONSerialization.jsonObject(with:JSONEncoder().encode(report.checks[0].evidence[0].declaration)) as? [String:Any]
            guard declaration?["value"] as? String=="100.000001" else{throw Failed.check}
            var malformed=try JSONSerialization.jsonObject(with:JSONEncoder().encode(body)) as! [String:Any]
            var invalid=malformed["evaluation"] as! [String:Any];invalid["overall"]="FEASIBLE";malformed["evaluation"]=invalid
            do{_=try JSONDecoder().decode(Components.Schemas.FeasibilityCurrentResponse.self,from:JSONSerialization.data(withJSONObject:malformed));throw Failed.unexpected}
            catch is DecodingError{}
        }
        for raw in [#"{"request_id":"00000000-0000-4000-8000-000000000001"}"#,#"{"request_id":"00000000-0000-4000-8000-000000000001","evaluation":null}"#]{
            do{_=try JSONDecoder().decode(Components.Schemas.FeasibilityCurrentResponse.self,from:Data(raw.utf8));throw Failed.unexpected}
            catch is DecodingError{}
        }
        print("PASS official FEASIBILITY read operation, CONFLICT/UNKNOWN and always overall UNKNOWN, exact source UTF8/hash/decimal declaration; missing/null/FEASIBLE consumer rejection")
    }
}
