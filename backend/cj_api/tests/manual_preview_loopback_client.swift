import Foundation
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes
private enum Failed:Error { case check }
private struct Settings:Decodable { let baseURL:URL;let token:String;let requestBase64:String }
private final class NoRedirects:NSObject,URLSessionTaskDelegate {
    func urlSession(_ session:URLSession,task:URLSessionTask,willPerformHTTPRedirection response:HTTPURLResponse,newRequest request:URLRequest) async -> URLRequest? { nil }
}
private struct LocalTransport:ClientTransport {
    let base:URLSessionTransport;let token:String
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        guard baseURL.scheme=="http",baseURL.host=="127.0.0.1",baseURL.port != nil else { throw Failed.check }
        var r=request;r.headerFields[.authorization]="Bearer "+token
        return try await base.send(r,body:body,baseURL:baseURL,operationID:operationID)
    }
}
@main struct ManualPreviewLoopbackClient {
    static func main() async {
        do {
            guard CommandLine.arguments.count==2 else { throw Failed.check }
            let s=try JSONDecoder().decode(Settings.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
            guard let raw=Data(base64Encoded:s.requestBase64) else { throw Failed.check }
            let request=try JSONDecoder().decode(Components.Schemas.ManualPreviewRequest.self,from:raw)
            let retained=request
            let config=URLSessionConfiguration.ephemeral;config.connectionProxyDictionary=[:];config.httpCookieStorage=nil;config.urlCache=nil
            let session=URLSession(configuration:config,delegate:NoRedirects(),delegateQueue:nil);defer{session.invalidateAndCancel()}
            let client=Client(serverURL:s.baseURL,configuration:.memory,transport:LocalTransport(base:URLSessionTransport(configuration:.init(session:session)),token:s.token))
            let response=try await client.previewManualTripEdit(.init(body:.json(request))).ok
            let body=try response.body.json;let p=body.preview
            guard body.request_id==response.headers.X_hyphen_Request_hyphen_ID,p.preview_status == .LOCAL,p.protection_status == .UNKNOWN,!p.can_save,
                  p.original.trip_id==request.trip_id,p.original.version==request.expected_version,
                  p.original.content_utf8_base64==request.original_content_utf8_base64,
                  p.document.items.map(\.id)==["c","b","a"],p.document.items[1]==p.original.document.items[1],
                  p.document.items[0]==p.original.document.items[2],p.document.items[2].verification == .pending,
                  p.document.items[2].evidence.isEmpty,Data(p.document.items[2].text.utf8)==Data("Changed e\u{301} 中文".utf8),
                  p.diff.map(\.path)==[["title"],["items","order"],["items","id","a"]] else { throw Failed.check }
            for change in p.diff {
                guard let before=Data(base64Encoded:change.before_utf8_base64),let after=Data(base64Encoded:change.after_utf8_base64),
                      String(data:before,encoding:.utf8) != nil,String(data:after,encoding:.utf8) != nil else { throw Failed.check }
            }
            var stale=request;stale.expected_version+=1
            let conflict=try await client.previewManualTripEdit(.init(body:.json(stale)))
            guard case .default(let status,let error)=conflict,status==409,
                  try error.body.json.error.code=="MANUAL_PREVIEW_CONFLICT",request==retained else { throw Failed.check }
            print("PASS generated readonly manual preview exact before/after/diff, selected-only scope, unavailable save and retained draft on409")
        } catch {
            if let error=error as? ClientError { print("FAIL manual preview client HTTP=\(error.response?.status.code ?? 0) decoded=\(error.underlyingError is DecodingError)") }
            else { print("FAIL manual preview client") }
            exit(1)
        }
    }
}
