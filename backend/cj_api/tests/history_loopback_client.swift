import Foundation
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes

private struct Control: Decodable {
    var baseURL: URL; var token: String
    var conversationID: String; var generation: String
    var emptyConversationID: String; var emptyGeneration: String
    var expectedDraftRevision: Int64; var expectedDraftBase64: String
    var newDraftBase64: String; var firstMessageBase64: String
}
private enum Failed: Error { case check }
private final class NoRedirects: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest) async -> URLRequest? { nil }
}
private struct LocalTransport: ClientTransport {
    let base: URLSessionTransport; let token: String; var omitField: String? = nil
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String)
        async throws -> (HTTPResponse,HTTPBody?) {
        guard baseURL.scheme=="http",baseURL.host=="127.0.0.1",baseURL.port != nil else { throw Failed.check }
        var request=request;request.headerFields[.authorization]="Bearer "+token
        if let field=omitField {
            guard let name=HTTPField.Name("X-CJ005-Test-Omit-Field") else { throw Failed.check }
            request.headerFields[name]=field
        }
        return try await base.send(request,body:body,baseURL:baseURL,operationID:operationID)
    }
}

@main
struct HistoryLoopbackClient {
    static func bytes(_ value:String) throws -> Data {
        guard let raw=Data(base64Encoded:value),raw.base64EncodedString()==value,
              String(data:raw,encoding:.utf8) != nil else { throw Failed.check }
        return raw
    }
    static func main() async {
        do {
            let c=try JSONDecoder().decode(Control.self,from:FileHandle.standardInput.readDataToEndOfFile())
            let config=URLSessionConfiguration.ephemeral
            config.connectionProxyDictionary=[:];config.httpCookieStorage=nil;config.urlCache=nil
            config.timeoutIntervalForRequest=10;config.timeoutIntervalForResource=20
            let session=URLSession(configuration:config,delegate:NoRedirects(),delegateQueue:nil)
            defer { session.invalidateAndCancel() }
            let transport=URLSessionTransport(configuration:.init(session:session))
            let client=Client(serverURL:c.baseURL,transport:LocalTransport(base:transport,token:c.token))
            let first=try await client.listConversations(.init(query:.init(limit:1))).ok.body.json
            guard case .case1(let cursor)=first.next_cursor else { throw Failed.check }
            let last=try await client.listConversations(.init(query:.init(limit:1,cursor:cursor))).ok.body.json
            guard case .case2(let value)=last.next_cursor,value.value==nil,
                  first.conversations.count==1,last.conversations.count==1 else { throw Failed.check }
            print("PASS generated live list AEAD pages and required explicit next_cursor null")
            let history=try await client.readMessageHistory(.init(query:.init(conversation_id:c.conversationID,limit:1))).ok.body.json
            guard history.messages.count==1,
                  try bytes(history.messages[0].original_utf8_base64)==bytes(c.firstMessageBase64),
                  case .case1(let historyCursor)=history.next_cursor else { throw Failed.check }
            let next=try await client.readMessageHistory(.init(query:.init(conversation_id:c.conversationID,limit:1,cursor:historyCursor))).ok.body.json
            guard case .case2(let end)=next.next_cursor,end.value==nil else { throw Failed.check }
            print("PASS generated live private message history original bytes and authenticated cursor")
            let absent=try await client.readMessageDraft(.init(query:.init(conversation_id:c.emptyConversationID,generation:c.emptyGeneration))).ok.body.json
            guard case .case2(let noDraft)=absent.draft,noDraft.value==nil else { throw Failed.check }
            let current=try await client.readMessageDraft(.init(query:.init(conversation_id:c.conversationID,generation:c.generation))).ok.body.json
            guard case .MessageDraftSnapshot(let draft)=current.draft,
                  draft.revision==c.expectedDraftRevision,
                  try bytes(draft.original_utf8_base64)==bytes(c.expectedDraftBase64) else { throw Failed.check }
            let saved=try await client.saveMessageDraft(.init(query:.init(conversation_id:c.conversationID,generation:c.generation,expected_revision:c.expectedDraftRevision),body:.binary(HTTPBody(try bytes(c.newDraftBase64))))).ok.body.json
            guard saved.draft.revision==c.expectedDraftRevision+1,
                  try bytes(saved.draft.original_utf8_base64)==bytes(c.newDraftBase64) else { throw Failed.check }
            print("PASS generated live draft null/object/CAS and exact UTF8 bytes")
            for field in ["next_cursor","draft"] {
                let malformed=Client(serverURL:c.baseURL,transport:LocalTransport(base:transport,token:c.token,omitField:field))
                do {
                    if field=="next_cursor" { _=try await malformed.listConversations(.init(query:.init(limit:1))) }
                    else { _=try await malformed.readMessageDraft(.init(query:.init(conversation_id:c.conversationID,generation:c.generation))) }
                    throw Failed.check
                } catch let error as ClientError {
                    guard error.response?.status.code==200,
                          case DecodingError.keyNotFound(let key,_)=error.underlyingError,
                          key.stringValue==field else { throw Failed.check }
                }
            }
            print("PASS generated live missing nullable keys throw keyNotFound; test mutation only after real query")
        } catch {
            // Never interpolate runtime ClientError/input/token/private body.
            print("FAIL generated history loopback consumer")
            exit(1)
        }
    }
}
