import Foundation
import CryptoKit
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes
private enum Failed:Error {case check}
private struct Settings:Decodable {
    let baseURL:URL;let tokenA:String;let tokenB:String
    let pauseBase64:String;let resumeBase64:String;let unknownBase64:String
    let pauseID:String;let resumeID:String;let unknownID:String;let outputPath:String
}
private actor Recorder {
    struct Entry:Codable,Sendable {let requestID:String;let operationID:String;let status:Int;let sha256:String}
    var entries:[Entry]=[]
    func add(_ entry:Entry){entries.append(entry)}
    func snapshot()->[Entry]{entries}
}
private final class NoRedirects:NSObject,URLSessionTaskDelegate {
    func urlSession(_ session:URLSession,task:URLSessionTask,willPerformHTTPRedirection response:HTTPURLResponse,newRequest request:URLRequest) async -> URLRequest?{nil}
}
private struct LocalTransport:ClientTransport {
    let base:URLSessionTransport;let token:String;let recorder:Recorder
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws ->(HTTPResponse,HTTPBody?){
        guard baseURL.scheme=="http",baseURL.host=="127.0.0.1",baseURL.port != nil else{throw Failed.check}
        var request=request;request.headerFields[.authorization]="Bearer "+token
        let(response,body)=try await base.send(request,body:body,baseURL:baseURL,operationID:operationID)
        guard let body,let rid=response.headerFields[.init("X-Request-ID")!] else{throw Failed.check}
        let raw=try await Data(collecting:body,upTo:65536)
        guard let json=try JSONSerialization.jsonObject(with:raw) as? [String:Any],json["request_id"] as? String==rid else{throw Failed.check}
        await recorder.add(.init(requestID:rid,operationID:operationID,status:response.status.code,sha256:SHA256.hash(data:raw).map{String(format:"%02x",$0)}.joined()))
        return(response,HTTPBody(raw))
    }
}
private func hash(_ raw:Data)->String{SHA256.hash(data:raw).map{String(format:"%02x",$0)}.joined()}
private func original(_ response:Components.Schemas.MemoryManagementReceiptResponse)throws->Components.Schemas.MemoryManagementReceipt{
    guard case .MemoryManagementReceipt(let receipt)=response.receipt else{throw Failed.check};return receipt
}
@main struct ManagementLoopbackClient {
    static func main() async {
        do {
            guard CommandLine.arguments.count==2 else{throw Failed.check}
            let s=try JSONDecoder().decode(Settings.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
            guard let pause=Data(base64Encoded:s.pauseBase64),let resume=Data(base64Encoded:s.resumeBase64),let unknown=Data(base64Encoded:s.unknownBase64) else{throw Failed.check}
            let config=URLSessionConfiguration.ephemeral;config.connectionProxyDictionary=[:];config.httpCookieStorage=nil;config.urlCache=nil
            let session=URLSession(configuration:config,delegate:NoRedirects(),delegateQueue:nil);defer{session.invalidateAndCancel()}
            let base=URLSessionTransport(configuration:.init(session:session));let recorder=Recorder()
            let a=Client(serverURL:s.baseURL,configuration:.memory,transport:LocalTransport(base:base,token:s.tokenA,recorder:recorder))
            let b=Client(serverURL:s.baseURL,configuration:.memory,transport:LocalTransport(base:base,token:s.tokenB,recorder:recorder))
            let paused=try await a.applyMemoryManagementAction(.init(body:.binary(HTTPBody(pause)))).ok.body.json.receipt
            guard Data(paused.action_id.utf8)==Data(s.pauseID.utf8),paused.status == .disabled,paused.version==2,paused.input_sha256==hash(pause) else{throw Failed.check}
            let queried=try original(try await a.queryMemoryManagementReceipt(.init(query:.init(action_id:s.pauseID))).ok.body.json)
            guard queried==paused else{throw Failed.check}
            let resumed=try await a.applyMemoryManagementAction(.init(body:.binary(HTTPBody(resume)))).ok.body.json.receipt
            guard Data(resumed.action_id.utf8)==Data(s.resumeID.utf8),resumed.status == .active,resumed.version==3,resumed.input_sha256==hash(resume) else{throw Failed.check}
            let current=try original(try await a.queryMemoryManagementReceipt(.init(query:.init(action_id:s.resumeID))).ok.body.json)
            let historical=try original(try await a.queryMemoryManagementReceipt(.init(query:.init(action_id:s.pauseID))).ok.body.json)
            guard current==resumed,historical==paused else{throw Failed.check}
            let uncertain=try await a.applyMemoryManagementAction(.init(body:.binary(HTTPBody(unknown))))
            guard case .default(let code,let failure)=uncertain,code==503,try failure.body.json.error.recovery == .reconcile_original else{throw Failed.check}
            // Never resend: exactly one apply attempt, then original-ID query only.
            let reconciled=try original(try await a.queryMemoryManagementReceipt(.init(query:.init(action_id:s.unknownID))).ok.body.json)
            guard Data(reconciled.action_id.utf8)==Data(s.unknownID.utf8),reconciled.status == .disabled,reconciled.version==4,reconciled.input_sha256==hash(unknown) else{throw Failed.check}
            let foreign=try await b.queryMemoryManagementReceipt(.init(query:.init(action_id:s.pauseID))).ok.body.json
            guard case .case2(let absent)=foreign.receipt,absent.value==nil else{throw Failed.check}
            try JSONEncoder().encode(await recorder.snapshot()).write(to:URL(fileURLWithPath:s.outputPath))
            print("PASS official Swift URLSession -> numeric HTTP -> canonical MEMORY/a7 -> real PG: pause/query/resume/historical receipt, unknown original query without resend, exact UTF8/hash and account isolation")
        }catch{
            if let error=error as? ClientError{print("FAIL management network client HTTP=\(error.response?.status.code ?? 0) decoded=\(error.underlyingError is DecodingError)")}
            else{print("FAIL management network client")}
            exit(1)
        }
    }
}
