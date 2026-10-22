import Foundation
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes
private enum Failed:Error { case check }
private struct Settings:Decodable { let baseURL:URL;let token:String;let messageID:String;let attemptID:String;let operationID:String;let runID:String }
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
@main struct OriginalUsageLoopbackClient {
    static func main() async {
        do {
            guard CommandLine.arguments.count==2 else { throw Failed.check }
            let s=try JSONDecoder().decode(Settings.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
            let config=URLSessionConfiguration.ephemeral;config.connectionProxyDictionary=[:];config.httpCookieStorage=nil;config.urlCache=nil
            let session=URLSession(configuration:config,delegate:NoRedirects(),delegateQueue:nil);defer{session.invalidateAndCancel()}
            let client=Client(serverURL:s.baseURL,configuration:.memory,transport:LocalTransport(base:URLSessionTransport(configuration:.init(session:session)),token:s.token))
            let r=try await client.getOriginalUsageAssociation(.init(query:.init(message_id:s.messageID))).ok;let body=try r.body.json;let a=body.association
            guard body.request_id==r.headers.X_hyphen_Request_hyphen_ID,Data(a.message_id.utf8)==Data(s.messageID.utf8),
                  Data(a.attempt_id.utf8)==Data(s.attemptID.utf8),Data(a.operation_id.utf8)==Data(s.operationID.utf8),
                  Data(a.run_id.utf8)==Data(s.runID.utf8),a.message_sequence>0 else { throw Failed.check }
            print("PASS generated protected original message usage association, exact stored refs and BASE trace only")
        } catch {
            if let e=error as? ClientError { print("FAIL original usage generated client HTTP=\(e.response?.status.code ?? 0) decoded=\(e.underlyingError is DecodingError)") }
            else { print("FAIL original usage generated client") };exit(1)
        }
    }
}
