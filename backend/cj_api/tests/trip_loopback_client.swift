import Foundation
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes

private enum Failed: Error { case check }
private struct Settings: Decodable {
    let baseURL: URL
    let token: String
    let proposalID: String
    let actionID: String
    let confirmationRef: String
    let tripID: String
    let contentBase64: String
    let expectedTotalTrips: Int
}
private final class NoRedirects: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest) async -> URLRequest? { nil }
}
private struct LocalTransport: ClientTransport {
    let base: URLSessionTransport
    let token: String
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        guard baseURL.scheme == "http",baseURL.host == "127.0.0.1",baseURL.port != nil else { throw Failed.check }
        var request=request;request.headerFields[.authorization]="Bearer "+token
        return try await base.send(request,body:body,baseURL:baseURL,operationID:operationID)
    }
}
@main struct TripLoopbackClient {
    static func main() async {
        var stage="configuration"
        do {
            guard CommandLine.arguments.count==2 else { throw Failed.check }
            let s=try JSONDecoder().decode(Settings.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
            let config=URLSessionConfiguration.ephemeral
            config.connectionProxyDictionary=[:];config.httpCookieStorage=nil;config.urlCache=nil
            let session=URLSession(configuration:config,delegate:NoRedirects(),delegateQueue:nil)
            defer { session.invalidateAndCancel() }
            let client=Client(serverURL:s.baseURL,configuration:.memory,
                transport:LocalTransport(base:URLSessionTransport(configuration:.init(session:session)),token:s.token))
            stage="proposal"
            let shown=try await client.getTripProposal(.init(query:.init(proposal_id:s.proposalID))).ok.body.json.proposal
            guard shown.proposal_id==s.proposalID,shown.trip_id==s.tripID,shown.status == .pending,
                  shown.expected_version==0,shown.content_utf8_base64==s.contentBase64 else { throw Failed.check }
            let original=try JSONSerialization.data(withJSONObject:[s.actionID,"accept",shown.proposal_id,shown.candidate_hash,s.confirmationRef],options:[.withoutEscapingSlashes])
            stage="accept"
            let saved=try await client.actOnTripProposal(.init(body:.binary(HTTPBody(original)))).ok.body.json.receipt
            guard saved.action_id==s.actionID,saved.kind == .accept,saved.candidate_hash==shown.candidate_hash,
                  case .case1(let version)=saved.committed_version,version==1 else { throw Failed.check }
            stage="original-query"
            let queried=try await client.queryTripAction(.init(query:.init(action_id:s.actionID))).ok.body.json
            guard case .TripActionReceipt(let originalReceipt)=queried.receipt,originalReceipt==saved else { throw Failed.check }
            let missing=try await client.queryTripAction(.init(query:.init(action_id:"never-observed"))).ok.body.json
            guard case .case2(let absent)=missing.receipt,absent.value==nil else { throw Failed.check }
            stage="formal-detail"
            let detail=try await client.getTrip(.init(query:.init(trip_id:s.tripID))).ok.body.json
            guard case .TripRecord(let trip)=detail.trip,trip.version==1,trip.content_utf8_base64==s.contentBase64,
                  trip.document.items.allSatisfy({$0.verification == .pending}) else { throw Failed.check }
            stage="list"
            var after:String?=nil;var ids=Set<Data>()
            for _ in 0..<20 {
                let page=try await client.listTrips(.init(query:.init(limit:2,after:after))).ok.body.json
                for trip in page.trips { guard ids.insert(Data(trip.trip_id.utf8)).inserted else { throw Failed.check } }
                switch page.next_after {
                case .case1(let id):guard page.trips.last?.trip_id==id else { throw Failed.check };after=id
                case .case2(let end):
                    guard end.value==nil,page.trips.isEmpty,ids.count==s.expectedTotalTrips else { throw Failed.check }
                    let terminal=try await client.getTripProposal(.init(query:.init(proposal_id:s.proposalID))).ok.body.json.proposal
                    guard terminal.status == .accepted,terminal.candidate_hash==shown.candidate_hash else { throw Failed.check }
                    print("PASS official generated TRIP five operations, canonical acceptance, historical receipt, exact pending content and live pages")
                    return
                }
            }
            throw Failed.check
        } catch {
            if let error=error as? ClientError {
                print("FAIL TRIP generated client stage=\(stage) HTTP=\(error.response?.status.code ?? 0) decoded=\(error.underlyingError is DecodingError)")
            } else { print("FAIL TRIP generated client stage=\(stage)") }
            exit(1)
        }
    }
}
