import Foundation
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes
private enum Failed: Error { case check }
private struct Settings:Decodable { let baseURL:URL;let token:String;let actionID:String;let needsID:String;let originalBase64:String }
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
@main struct NeedsLoopbackClient {
    static func main() async {
        var stage="configuration"
        do {
            guard CommandLine.arguments.count==2 else { throw Failed.check }
            let s=try JSONDecoder().decode(Settings.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
            guard let original=Data(base64Encoded:s.originalBase64),String(data:original,encoding:.utf8) != nil else { throw Failed.check }
            let config=URLSessionConfiguration.ephemeral;config.connectionProxyDictionary=[:];config.httpCookieStorage=nil;config.urlCache=nil
            let session=URLSession(configuration:config,delegate:NoRedirects(),delegateQueue:nil);defer{session.invalidateAndCancel()}
            let client=Client(serverURL:s.baseURL,configuration:.memory,transport:LocalTransport(base:URLSessionTransport(configuration:.init(session:session)),token:s.token))
            stage="act"
            let saved=try await client.actOnNeeds(.init(body:.binary(HTTPBody(original)))).ok.body.json.receipt
            guard saved.action_id==s.actionID,saved.needs_id==s.needsID,saved.version==1,saved.operation == .manual_patch else { throw Failed.check }
            stage="original-query"
            let query=try await client.queryNeedsAction(.init(query:.init(action_id:s.actionID))).ok.body.json
            guard case .NeedsReceipt(let receipt)=query.receipt,receipt==saved else { throw Failed.check }
            stage="exact-revision"
            let read=try await client.getNeedsRevision(.init(query:.init(needs_id:receipt.needs_id,version:receipt.version))).ok.body.json
            guard case .NeedsRevision(let revision)=read.revision,revision.action_id==s.actionID,
                  Data(base64Encoded:revision.original_input_utf8_base64)==original,revision.source_kind == .user_provided else { throw Failed.check }
            let source=try JSONDecoder().decode(Components.Schemas.NeedsCommand.self,from:original)
            guard source.action_id==revision.action_id,source.source.kind == .manual else { throw Failed.check }
            stage="detail"
            let detail=try await client.getNeeds(.init(query:.init(needs_id:s.needsID))).ok.body.json
            guard case .NeedsSnapshot(let value)=detail.needs,value.version==1,value.source_kind == .user_provided,
                  value.content_utf8_base64==revision.content_utf8_base64,value.fields.budget_currency==nil,
                  case .NeedsMoneyObservationKnown(let amount)?=value.fields.budget_total,amount.value=="1000.00",
                  case .NeedsMissingObservation?=value.fields.budget_paid,
                  case .NeedsUnknownObservation?=value.fields.budget_per_person,
                  case .NeedsUncertainObservation(let pace)?=value.fields.pace,pace.note=="Undecided / 未定",
                  let event=value.fields.arrival,
                  case .NeedsLocalDateObservationKnown(let date)=event.date,date.value=="2026-11-01",
                  case .NeedsLocalTimeObservationKnown(let time)=event.time,time.value=="01:30",
                  case .NeedsTimezoneObservationKnown(let zone)=event.timezone,zone.value=="America/New_York",
                  let item=value.fields.fixed_items?.first,
                  case .NeedsLockedObservationKnown(let locked)=item.locked,locked.value,
                  case .NeedsBookingObservationKnown(let booking)=item.booking_status,booking.value == .booked,
                  item.applies_to==["companion:mother"] else { throw Failed.check }
            stage="explicit-null"
            let absent=try await client.queryNeedsAction(.init(query:.init(action_id:"never-observed"))).ok.body.json
            guard case .case2(let none)=absent.receipt,none.value==nil else { throw Failed.check }
            print("PASS generated NEEDS four real operations, original revision bytes, absent/missing/unknown/uncertain, decimal/local walltime and locked user claim")
        } catch {
            if let error=error as? ClientError { print("FAIL NEEDS client stage=\(stage) HTTP=\(error.response?.status.code ?? 0) decoded=\(error.underlyingError is DecodingError)") }
            else { print("FAIL NEEDS client stage=\(stage)") }
            exit(1)
        }
    }
}
