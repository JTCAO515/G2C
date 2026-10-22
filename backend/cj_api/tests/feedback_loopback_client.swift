import Foundation
import CryptoKit
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes
private enum Failed:Error { case check }
private struct Settings:Decodable { let baseURL:URL;let token:String;let generalBase64:String;let linkedBase64:String;let messageID:String;let runID:String;let messageInputHash:String;let highwater:Int }
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
@main struct FeedbackLoopbackClient {
    static func main() async {
        var stage="configuration"
        do {
            guard CommandLine.arguments.count==2 else { throw Failed.check }
            let s=try JSONDecoder().decode(Settings.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
            let config=URLSessionConfiguration.ephemeral;config.connectionProxyDictionary=[:];config.httpCookieStorage=nil;config.urlCache=nil
            let session=URLSession(configuration:config,delegate:NoRedirects(),delegateQueue:nil);defer{session.invalidateAndCancel()}
            let client=Client(serverURL:s.baseURL,configuration:.memory,transport:LocalTransport(base:URLSessionTransport(configuration:.init(session:session)),token:s.token))
            for (linked,encoded) in [(false,s.generalBase64),(true,s.linkedBase64)] {
                guard let original=Data(base64Encoded:encoded) else { throw Failed.check }
                let action=try JSONDecoder().decode(Components.Schemas.FeedbackAction.self,from:original)
                stage=linked ? "linked-submit" : "general-submit"
                let receipt=try await client.submitFeedback(.init(body:.binary(HTTPBody(original)))).ok.body.json.receipt
                let expected=SHA256.hash(data:original).map{String(format:"%02x",$0)}.joined()
                guard receipt.action_id==action.action_id,receipt.input_sha256==expected,receipt.status == .submitted,
                      receipt.message_en.rawValue=="Feedback submitted.",receipt.message_zh.rawValue=="反馈已提交。" else { throw Failed.check }
                if linked {
                    guard case .FeedbackSourceObservation(let source)=receipt.source,
                          Data(source.message_id.utf8)==Data(s.messageID.utf8),Data(source.run_id.utf8)==Data(s.runID.utf8),
                          source.message_input_sha256==s.messageInputHash,source.run_status_at_read == .completed,
                          source.event_highwater_at_read==s.highwater else { throw Failed.check }
                } else { guard case .case2(let none)=receipt.source,none.value==nil else { throw Failed.check } }
                stage="original-query"
                let q=try await client.queryFeedbackAction(.init(query:.init(action_id:action.action_id))).ok.body.json
                guard case .FeedbackReceipt(let old)=q.receipt,old==receipt else { throw Failed.check }
            }
            let q=try await client.queryFeedbackAction(.init(query:.init(action_id:"never-observed"))).ok.body.json
            guard case .case2(let none)=q.receipt,none.value==nil else { throw Failed.check }
            print("PASS generated FEEDBACK submit/query general and linked, exact original digest/UTC receipt, minimal historical source and explicit null")
        } catch {
            if let error=error as? ClientError { print("FAIL FEEDBACK client stage=\(stage) HTTP=\(error.response?.status.code ?? 0) decoded=\(error.underlyingError is DecodingError)") }
            else { print("FAIL FEEDBACK client stage=\(stage)") }
            exit(1)
        }
    }
}
