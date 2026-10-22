import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime

private struct ManualExportNoRequest: ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        Issue.record("export checks must never issue manual preview POST")
        throw URLError(.unsupportedURL)
    }
}
struct ManualPreviewExportTests {
    let trace="e3538f39-72f9-4351-b2b3-cb6a991ce97f"
    var original:Data {Data(#"{"items":[{"evidence":[],"id":"a","text":"原文","verification":"pending"}],"title":"Original"}"#.utf8)}
    private func request() -> [String:Any] {
        ["trip_id":"t1","expected_version":1,"original_content_utf8_base64":original.base64EncodedString(),"selected_ids":[],"title_selected":false,"title":NSNull(),"text_updates":[],"order":NSNull()]
    }
    private func response(canSave:Bool=false,protection:String="UNKNOWN") throws -> Data {
        let document:[String:Any]=["title":"Original","items":[["id":"a","text":"原文","verification":"pending","evidence":[]]]]
        let afterDocument=document.merging(["title":"新标题"]) {_,new in new}
        let after=Data(#"{"items":[{"evidence":[],"id":"a","text":"原文","verification":"pending"}],"title":"新标题"}"#.utf8)
        let preview:[String:Any]=["preview_status":"LOCAL","original":["trip_id":"t1","version":1,"content_utf8_base64":original.base64EncodedString(),"document":document],"content_utf8_base64":after.base64EncodedString(),"document":afterDocument,"selected_ids":[],"title_selected":true,"protection_status":protection,"can_save":canSave,"diff":[["path":["title"],"before_utf8_base64":Data("\"Original\"".utf8).base64EncodedString(),"after_utf8_base64":Data("\"新标题\"".utf8).base64EncodedString()]]]
        return try JSONSerialization.data(withJSONObject:["request_id":trace,"preview":preview])
    }
    // Test-only consumer assertion; generated Bool alone does NOT enforce const:false.
    private func localNonSavable(_ preview:Components.Schemas.ManualPreview)->Bool {
        preview.preview_status == .LOCAL && preview.protection_status == .UNKNOWN && !preview.can_save
    }
    @Test func methodAndRequiredNullableRequestPreserveOriginalBytes() throws {
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:ManualExportNoRequest())
        _ = client.previewManualTripEdit
        #expect(Operations.previewManualTripEdit.id=="previewManualTripEdit")
        let decoded=try JSONDecoder().decode(Components.Schemas.ManualPreviewRequest.self,from:JSONSerialization.data(withJSONObject:request()))
        #expect(Data(base64Encoded:decoded.original_content_utf8_base64)==original)
        if case .case2(let title)=decoded.title {#expect(title.value==nil)} else {Issue.record("title null expected")}
        if case .case2(let order)=decoded.order {#expect(order.value==nil)} else {Issue.record("order null expected")}
        let roundtrip=try JSONSerialization.jsonObject(with:JSONEncoder().encode(decoded)) as! [String:Any]
        #expect(roundtrip["original_content_utf8_base64"] as? String == original.base64EncodedString())
        for key in ["title","order"] {
            var missing=request();missing.removeValue(forKey:key)
            #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.ManualPreviewRequest.self,from:JSONSerialization.data(withJSONObject:missing))}
        }
    }
    @Test func originalDiffBytesUnknownProtectionAndNoSaveAreExplicit() throws {
        let value=try JSONDecoder().decode(Components.Schemas.ManualPreviewResponse.self,from:response())
        #expect(localNonSavable(value.preview))
        #expect(Data(base64Encoded:value.preview.original.content_utf8_base64)==original)
        #expect(Data(base64Encoded:value.preview.diff[0].before_utf8_base64)==Data("\"Original\"".utf8))
        #expect(Data(base64Encoded:value.preview.diff[0].after_utf8_base64)==Data("\"新标题\"".utf8))
        let unsafe=try JSONDecoder().decode(Components.Schemas.ManualPreviewResponse.self,from:response(canSave:true))
        #expect(!localNonSavable(unsafe.preview)) // Explicit downstream guard required.
        #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.ManualPreviewResponse.self,from:response(protection:"UNLOCKED"))}
    }
    @Test func requiredPreviewAndBASEErrorsCannotBePreviewSuccess() throws {
        #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.ManualPreviewResponse.self,from:JSONSerialization.data(withJSONObject:["request_id":trace]))}
        for (code,category,outcome,recovery) in [("MANUAL_PREVIEW_CONFLICT","conflict","failed","do_not_retry"),("MANUAL_PREVIEW_UNAVAILABLE","dependency","unknown","retry_safe_read")] {
            let bytes=try JSONSerialization.data(withJSONObject:["request_id":trace,"error":["code":code,"category":category,"outcome":outcome,"recovery":recovery,"message_en":"Synthetic error","message_zh":"合成错误"]])
            let error=try JSONDecoder().decode(Components.Schemas.ErrorResponse.self,from:bytes)
            #expect(error.error.code==code && error.error.outcome.rawValue==outcome && error.error.recovery.rawValue==recovery)
            #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.ManualPreviewResponse.self,from:bytes)}
        }
    }
}
