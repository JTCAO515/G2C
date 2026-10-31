import Foundation
import CJAPI
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

public enum RunDraftStatusVersion: Sendable { case v1, v2, v3, v4 }

public enum RunDraftReadState: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    case unread, loading, unavailable, loaded(Components.Schemas.RunDraftStatusResponse)
    case loadedBudget(Components.Schemas.RunDraftStatusV2Response)
    case loadedTravel(Components.Schemas.RunDraftStatusV3Response)
    case loadedTrip(RunTripDraftStatus)
    public var description: String { "<redacted draft read state>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
    public func label(_ language: RunDisplayLanguage) -> String {
        switch self {
        case .unread: language.text("Draft result not read", "尚未读取草稿结果")
        case .loading: language.text("Reading draft result…", "正在读取草稿结果…")
        case .unavailable: language.text("Draft result unavailable; outcome unknown", "草稿结果不可用，结果未知")
        case .loaded(let value): outcomeLabel(value.draft_outcome.rawValue, language)
        case .loadedBudget(let value): outcomeLabel(value.draft_outcome.rawValue, language)
        case .loadedTravel(let value): outcomeLabel(value.draft_outcome.rawValue, language)
        case .loadedTrip(let value): outcomeLabel(value.draftOutcome.rawValue, language)
        }
    }
    public var runStatus: Components.Schemas.RunDisplaySnapshot.statusPayload? {
        switch self {
        case .loaded(let value): Components.Schemas.RunDisplaySnapshot.statusPayload(rawValue:value.run_status.rawValue)
        case .loadedBudget(let value): Components.Schemas.RunDisplaySnapshot.statusPayload(rawValue:value.run_status.rawValue)
        case .loadedTravel(let value): Components.Schemas.RunDisplaySnapshot.statusPayload(rawValue:value.run_status.rawValue)
        case .loadedTrip(let value): Components.Schemas.RunDisplaySnapshot.statusPayload(rawValue:value.runStatus.rawValue)
        case .unread, .loading, .unavailable: nil
        }
    }
    /// Only the versioned persisted reason is displayed; failed/unknown never implies quota exhaustion.
    public func budgetLabel(_ language: RunDisplayLanguage) -> String? {
        let stage: String
        switch self {
        case .loadedBudget(let value):stage = value.budget_exhausted_stage.rawValue
        case .loadedTravel(let value):stage = value.budget_exhausted_stage.rawValue
        case .loadedTrip(let value):stage = value.budgetStage.rawValue
        case .unread,.loading,.unavailable,.loaded:return nil
        }
        switch stage {
        case "answer":return language.text("Budget exhausted before answer generation", "生成回答前预算已耗尽")
        case "draft":return language.text("Budget exhausted before draft generation", "生成草稿前预算已耗尽")
        default:return nil
        }
    }
    // Wire versions stay in their original payloads. Only bilingual presentation
    // is shared, after the generated closed enums have decoded at the boundary.
    private func outcomeLabel(_ outcome: String,_ language: RunDisplayLanguage) -> String {
        switch outcome {
        case "not_requested":language.text("No draft was requested for this message", "此消息未请求草稿")
        case "not_recorded":language.text("No draft result recorded; outcome unknown", "尚无草稿结果记录，结果未知")
        case "published":language.text("Draft candidate recorded; not a saved trip", "已记录草稿候选，尚非正式行程")
        case "validation_failed":language.text("Draft failed validation; no candidate published", "草稿校验失败，未发布候选")
        case "provider_failed":language.text("Draft generation failed; no candidate published", "草稿生成失败，未发布候选")
        case "provider_unknown":language.text("Draft generation result unknown; do not generate again", "草稿生成结果未知，请勿再次生成")
        case "budget_exhausted":language.text("Draft generation budget exhausted", "草稿生成预算已耗尽")
        default:language.text("Draft result unavailable; outcome unknown", "草稿结果不可用，结果未知")
        }
    }

}

@MainActor func readOriginalDraftStatus(endpoint: MessageEndpoint, transport: any ClientTransport,
    bearer: String, receipt: Components.Schemas.MessageReceipt, snapshot: Components.Schemas.RunDisplaySnapshot,
    version: RunDraftStatusVersion = .v1, reference: RunTravelReference? = nil, tripReference: MessageTripReference? = nil, validate: @MainActor @Sendable () throws -> Void) async throws -> RunDraftReadState {
    guard (version == .v3) == (reference != nil), (version == .v4) == (tripReference != nil) else { throw RunDisplayFailure.invalidReference }
    var url = URLComponents()
    url.path = version == .v1 ? "/v1/run-draft-status" : version == .v2 ? "/v2/run-draft-status" : version == .v3 ? "/v3/run-draft-status" : "/v4/run-draft-status"
    url.queryItems = [URLQueryItem(name: "message_id", value: receipt.message_id)]
    url.percentEncodedQuery = url.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
    guard let path = url.string else { throw RunDisplayFailure.invalidReference }
    var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: path)
    request.headerFields[.authorization] = "Bearer " + bearer
    request.headerFields[.accept] = "application/json"
    try validate()
    let (response, body) = try await transport.send(request, body: nil, baseURL: endpoint.url, operationID: version == .v1 ? "getRunDraftStatus" : version == .v2 ? "getRunDraftStatusV2" : version == .v3 ? "getTravelRunDraftStatus" : "getTripRunDraftStatusV4")
    try validate()
    guard response.status.code == 200 else { throw RunDisplayFailure.rejected(status: response.status.code) }
    let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
    let controls = response.headerFields.filter { $0.name == .cacheControl }
    let media = response.headerFields.filter { $0.name == .contentType }
    guard traces.count == 1, UUID(uuidString: traces[0].value) != nil,
          controls.count == 1, controls[0].value.lowercased() == "no-store",
          media.count == 1, media[0].value.split(separator: ";").first?.lowercased() == "application/json",
          let body else { throw RunDisplayFailure.invalidResponse }
    let bytes = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
    try validate()
    var parser = StrictRunJSON(bytes: Array(bytes)); try parser.check()
    let references: (requestID: String, conversation: String, generation: String, message: String,
                     run: String, sequence: Int, highwater: Int, status: String)
    let result: RunDraftReadState
    switch version {
    case .v1:
        let value = try JSONDecoder().decode(Components.Schemas.RunDraftStatusResponse.self, from: bytes)
        references = (value.request_id, value.conversation_id, value.generation, value.message_id,
                      value.run_id, value.message_sequence, value.event_highwater, value.run_status.rawValue)
        result = .loaded(value)
    case .v2:
        let value = try JSONDecoder().decode(Components.Schemas.RunDraftStatusV2Response.self, from: bytes)
        references = (value.request_id, value.conversation_id, value.generation, value.message_id,
                      value.run_id, value.message_sequence, value.event_highwater, value.run_status.rawValue)
        result = .loadedBudget(value)
    case .v3:
        let value = try JSONDecoder().decode(Components.Schemas.RunDraftStatusV3Response.self,from:bytes)
        try reference?.requireOriginal(value.reference)
        references = (value.request_id,value.conversation_id,value.generation,value.message_id,
                      value.run_id,value.message_sequence,value.event_highwater,value.run_status.rawValue)
        result = .loadedTravel(value)
    case .v4:
        guard let tripReference else { throw RunDisplayFailure.invalidReference }
        let (value,fields)=try decodeTripDraftStatus(bytes,reference:tripReference)
        references=fields;result = .loadedTrip(value)
    }
    guard exact(references.requestID, traces[0].value), exact(references.message, receipt.message_id),
          exact(references.conversation, receipt.conversation_id), exact(references.generation, receipt.generation),
          exact(references.run, receipt.run_id), references.sequence == receipt.sequence,
          references.highwater >= snapshot.event_highwater else { throw RunDisplayFailure.invalidResponse }
    if references.highwater == snapshot.event_highwater || (snapshot.status != .queued && snapshot.status != .running) {
        guard references.status == snapshot.status.rawValue,
              references.highwater == snapshot.event_highwater else { throw RunDisplayFailure.inconsistentSnapshot }
    }
    try validate()
    return result
}
