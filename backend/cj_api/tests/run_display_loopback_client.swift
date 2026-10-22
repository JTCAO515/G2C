import Foundation
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes
private enum Failed:Error { case check }
private struct Settings:Decodable { let baseURL:URL;let token:String;let messageID:String;let expectedStatus:String;let expectedTextBase64:String;let expectedHighwater:Int }
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
@main struct RunDisplayLoopbackClient {
    static func main() async {
        do {
            guard CommandLine.arguments.count==2 else { throw Failed.check }
            let s=try JSONDecoder().decode(Settings.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
            let config=URLSessionConfiguration.ephemeral;config.connectionProxyDictionary=[:];config.httpCookieStorage=nil;config.urlCache=nil
            let session=URLSession(configuration:config,delegate:NoRedirects(),delegateQueue:nil);defer{session.invalidateAndCancel()}
            let client=Client(serverURL:s.baseURL,configuration:.memory,transport:LocalTransport(base:URLSessionTransport(configuration:.init(session:session)),token:s.token))
            let response=try await client.getRunDisplaySnapshot(.init(query:.init(message_id:s.messageID))).ok
            let body=try response.body.json
            guard body.request_id==response.headers.X_hyphen_Request_hyphen_ID,
                  Data(body.snapshot.message_id.utf8)==Data(s.messageID.utf8),body.snapshot.status.rawValue==s.expectedStatus,
                  body.snapshot.event_highwater==s.expectedHighwater,body.snapshot.message_sequence>0,
                  Data(body.snapshot.text.utf8)==Data(base64Encoded:s.expectedTextBase64),
                  body.snapshot.text_state.rawValue==(s.expectedStatus=="completed" ? "complete":"partial") else { throw Failed.check }
            print("PASS generated protected RUN display, exact text/opaque message ID, read-time state/highwater and BASE header trace")
        } catch {
            if let error=error as? ClientError { print("FAIL RUN display generated client HTTP=\(error.response?.status.code ?? 0) decoded=\(error.underlyingError is DecodingError)") }
            else { print("FAIL RUN display generated client") }
            exit(1)
        }
    }
}
