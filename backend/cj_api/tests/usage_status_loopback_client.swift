import Foundation
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes
private enum Failed:Error { case check }
private struct Settings:Decodable { let baseURL:URL;let token:String;let unknownID:String;let zeroID:String;let bigID:String;let reservedUnits:String;let bigUnits:String;let unit:String }
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
@main struct UsageStatusLoopbackClient {
    static func main() async {
        do {
            guard CommandLine.arguments.count==2 else { throw Failed.check }
            let s=try JSONDecoder().decode(Settings.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
            let config=URLSessionConfiguration.ephemeral;config.connectionProxyDictionary=[:];config.httpCookieStorage=nil;config.urlCache=nil
            let session=URLSession(configuration:config,delegate:NoRedirects(),delegateQueue:nil);defer{session.invalidateAndCancel()}
            let client=Client(serverURL:s.baseURL,configuration:.memory,transport:LocalTransport(base:URLSessionTransport(configuration:.init(session:session)),token:s.token))
            for id in [s.unknownID,s.zeroID,s.bigID] {
                let response=try await client.getUsageAttemptStatus(.init(query:.init(attempt_id:id))).ok
                let body=try response.body.json;let a=body.attempt
                guard body.request_id==response.headers.X_hyphen_Request_hyphen_ID,Data(a.attempt_id.utf8)==Data(id.utf8),a.unit==s.unit,a.reserved_units==s.reservedUnits else { throw Failed.check }
                if id==s.unknownID {
                    guard a.status == .unknown,case .case2(let x)=a.confirmed_units,x.value==nil,
                          case .case2(let y)=a.confirmed_output,y.value==nil,case .case2(let r)=a.receipt_id,r.value==nil else { throw Failed.check }
                } else {
                    guard a.status == .settled,case .case1(let amount)=a.confirmed_units,amount==(id==s.zeroID ? "0":s.bigUnits),
                          case .case1(let output)=a.confirmed_output,output=="0",case .case1(let receipt)=a.receipt_id,!receipt.isEmpty else { throw Failed.check }
                }
            }
            print("PASS generated original USAGE status, opaque unit, >Int64 exact strings, confirmed zero versus unknown null and trace")
        } catch {
            if let error=error as? ClientError { print("FAIL USAGE generated client HTTP=\(error.response?.status.code ?? 0) decoded=\(error.underlyingError is DecodingError)") }
            else { print("FAIL USAGE generated client") }
            exit(1)
        }
    }
}
