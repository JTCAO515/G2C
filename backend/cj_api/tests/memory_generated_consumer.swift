import Foundation
import CJAPI
import OpenAPIRuntime
import HTTPTypes

private enum CheckFailed: Error { case invalid }
private struct FixtureTransport: ClientTransport {
    let original: Data
    let receiptJSON: String
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let payload: String
        switch operationID {
        case "saveMemory":
            guard request.method == .post, request.path == "/v1/memories",
                  request.headerFields[.contentType] == "application/octet-stream", let body,
                  try await Data(collecting: body, upTo: 32768) == original else { throw CheckFailed.invalid }
            payload = "{\"request_id\":\"00000000-0000-4000-8000-000000000001\",\"receipt\":\(receiptJSON)}"
        case "queryMemoryReceipt":
            guard request.path == "/v1/memory-receipts?operation_id=original%2Boperation" else { throw CheckFailed.invalid }
            payload = "{\"request_id\":\"00000000-0000-4000-8000-000000000001\",\"receipt\":null}"
        case "listMemories":
            payload = "{\"request_id\":\"00000000-0000-4000-8000-000000000001\",\"items\":[],\"next_after\":null}"
        case "getMemoryItem":
            payload = "{\"request_id\":\"00000000-0000-4000-8000-000000000001\",\"item\":null}"
        case "listMemoryGroups":
            payload = "{\"request_id\":\"00000000-0000-4000-8000-000000000001\",\"groups\":[]}"
        default: throw CheckFailed.invalid
        }
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[.init("X-Request-ID")!] = "00000000-0000-4000-8000-000000000001"
        return (response, HTTPBody(payload))
    }
}

@main struct MemoryGeneratedConsumer {
    static func decode<T: Decodable>(_ type: T.Type, _ text: String) throws -> T {
        try JSONDecoder().decode(type, from: Data(text.utf8))
    }
    static func main() async throws {
        let original = Data("e\u{301} 中文 original immutable fixture\n".utf8)
        let receipt = "{\"operation_id\":\"original+operation\",\"item_id\":\"item\",\"version\":1,\"status\":\"candidate\"}"
        guard let url = URL(string: "https://fixture.invalid") else { throw CheckFailed.invalid }
        let client = Client(serverURL: url, transport: FixtureTransport(original: original, receiptJSON: receipt))
        let saved = try await client.saveMemory(.init(body: .binary(HTTPBody(original)))).ok.body.json
        guard saved.receipt.status == .candidate, saved.receipt.operation_id == "original+operation" else { throw CheckFailed.invalid }
        let query = try await client.queryMemoryReceipt(.init(query: .init(operation_id: "original+operation"))).ok.body.json
        guard case .case2(let missing) = query.receipt, missing.value == nil else { throw CheckFailed.invalid }
        let page = try await client.listMemories(.init(query: .init(limit: 1))).ok.body.json
        guard case .case2(let end) = page.next_after, end.value == nil else { throw CheckFailed.invalid }
        let detail = try await client.getMemoryItem(.init(query: .init(item_id: "item"))).ok.body.json
        guard case .case2(let absent) = detail.item, absent.value == nil else { throw CheckFailed.invalid }
        _ = try await client.listMemoryGroups().ok.body.json
        print("PASS actual generated MEMORY Client five operations; exact body, query encoding, candidate and required null")
        let rid = "\"request_id\":\"00000000-0000-4000-8000-000000000001\""
        for body in ["{\(rid)}", "{\(rid),\"receipt\":\"invalid fallback\"}", "{\(rid),\"receipt\":\(receipt.replacingOccurrences(of: "candidate", with: "invented"))}"] {
            do {
                let result = try decode(Components.Schemas.MemoryReceiptQueryResponse.self, body)
                if case .case2(let fallback) = result.receipt, fallback.value != nil { continue }
                throw CheckFailed.invalid
            } catch is DecodingError { }
        }
        print("PASS generated missing receipt / invalid enum; nonnull null-fallback must be rejected explicitly")
    }
}
