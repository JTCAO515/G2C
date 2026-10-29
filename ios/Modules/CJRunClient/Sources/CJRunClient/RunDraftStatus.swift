import Foundation
import CJAPI
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

public enum RunDraftReadState: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    case unread, loading, unavailable, loaded(Components.Schemas.RunDraftStatusResponse)
    public var description: String { "<redacted draft read state>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
    public func label(_ language: RunDisplayLanguage) -> String {
        switch self {
        case .unread: language.text("Draft result not read", "尚未读取草稿结果")
        case .loading: language.text("Reading draft result…", "正在读取草稿结果…")
        case .unavailable: language.text("Draft result unavailable; outcome unknown", "草稿结果不可用，结果未知")
        case .loaded(let value):
            switch value.draft_outcome {
            case .not_requested: language.text("No draft was requested for this message", "此消息未请求草稿")
            case .not_recorded: language.text("No draft result recorded; outcome unknown", "尚无草稿结果记录，结果未知")
            case .published: language.text("Draft candidate recorded; not a saved trip", "已记录草稿候选，尚非正式行程")
            case .validation_failed: language.text("Draft failed validation; no candidate published", "草稿校验失败，未发布候选")
            case .provider_failed: language.text("Draft generation failed; no candidate published", "草稿生成失败，未发布候选")
            case .provider_unknown: language.text("Draft generation result unknown; do not generate again", "草稿生成结果未知，请勿再次生成")
            }
        }
    }
}

@MainActor func readOriginalDraftStatus(endpoint: MessageEndpoint, transport: any ClientTransport,
    bearer: String, receipt: Components.Schemas.MessageReceipt, snapshot: Components.Schemas.RunDisplaySnapshot,
    validate: @MainActor @Sendable () throws -> Void) async throws -> Components.Schemas.RunDraftStatusResponse {
    var url = URLComponents()
    url.path = "/v1/run-draft-status"
    url.queryItems = [URLQueryItem(name: "message_id", value: receipt.message_id)]
    url.percentEncodedQuery = url.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
    guard let path = url.string else { throw RunDisplayFailure.invalidReference }
    var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: path)
    request.headerFields[.authorization] = "Bearer " + bearer
    request.headerFields[.accept] = "application/json"
    try validate()
    let (response, body) = try await transport.send(request, body: nil, baseURL: endpoint.url, operationID: "getRunDraftStatus")
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
    let value = try JSONDecoder().decode(Components.Schemas.RunDraftStatusResponse.self, from: bytes)
    guard exact(value.request_id, traces[0].value), exact(value.message_id, receipt.message_id),
          exact(value.conversation_id, receipt.conversation_id), exact(value.generation, receipt.generation),
          exact(value.run_id, receipt.run_id), value.message_sequence == receipt.sequence,
          value.event_highwater >= snapshot.event_highwater else { throw RunDisplayFailure.invalidResponse }
    if value.event_highwater == snapshot.event_highwater || (snapshot.status != .queued && snapshot.status != .running) {
        guard value.run_status.rawValue == snapshot.status.rawValue,
              value.event_highwater == snapshot.event_highwater else { throw RunDisplayFailure.inconsistentSnapshot }
    }
    try validate()
    return value
}
