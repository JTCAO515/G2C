import Foundation
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes

private enum Failed: Error { case check }
private struct Configuration: Decodable {
    let baseURL: URL
    let token: String
    let operationID: String
    let itemID: String
    let originalBase64: String
    let expectedItems: Int
    let expectedInputHash: String
}
private struct LocalTransport: ClientTransport {
    let base: URLSessionTransport
    let token: String
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        guard baseURL.scheme == "http",baseURL.host == "127.0.0.1",baseURL.port != nil else { throw Failed.check }
        var request = request
        request.headerFields[.authorization] = "Bearer " + token
        return try await base.send(request,body:body,baseURL:baseURL,operationID:operationID)
    }
}
@main struct MemoryLoopbackClient {
    static func main() async {
        var stage = "configuration"
        do {
            guard CommandLine.arguments.count == 2 else { throw Failed.check }
            let c = try JSONDecoder().decode(Configuration.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
            guard let raw = Data(base64Encoded:c.originalBase64),String(data:raw,encoding:.utf8) != nil else { throw Failed.check }
            let settings = URLSessionConfiguration.ephemeral
            settings.connectionProxyDictionary = [:]
            let session = URLSession(configuration:settings)
            defer { session.invalidateAndCancel() }
            let client = Client(serverURL:c.baseURL,configuration:.memory,transport:LocalTransport(base:URLSessionTransport(configuration:.init(session:session)),token:c.token))
            stage = "save"
            let saved = try await client.saveMemory(.init(body:.binary(HTTPBody(raw)))).ok.body.json
            guard Data(saved.receipt.operation_id.utf8) == Data(c.operationID.utf8),saved.receipt.status == .candidate,saved.receipt.input_sha256 == c.expectedInputHash else { throw Failed.check }
            stage = "query"
            let found = try await client.queryMemoryReceipt(.init(query:.init(operation_id:c.operationID))).ok.body.json
            guard case .MemoryReceipt(let receipt) = found.receipt,receipt == saved.receipt else { throw Failed.check }
            stage = "detail"
            let detail = try await client.getMemoryItem(.init(query:.init(item_id:c.itemID))).ok.body.json
            guard case .MemoryItem(let item) = detail.item,
                  Data(item.command.operation_id.utf8) == Data(c.operationID.utf8),item.status == .candidate,
                  case .case2(let noContext) = item.command.context_id,noContext.value == nil else { throw Failed.check }
            stage = "list"
            var after: String? = nil
            var identifiers = Set<Data>()
            for _ in 0..<20 {
                let page = try await client.listMemories(.init(query:.init(limit:2,after:after))).ok.body.json
                for value in page.items {
                    guard identifiers.insert(Data(value.command.item_id.utf8)).inserted else { throw Failed.check }
                }
                switch page.next_after {
                case .case1(let anchor):
                    guard let last = page.items.last,Data(anchor.utf8) == Data(last.command.item_id.utf8) else { throw Failed.check }
                    after = anchor
                case .case2(let end):
                    guard end.value == nil,page.items.isEmpty,identifiers.count == c.expectedItems else { throw Failed.check }
                    stage = "groups"
                    let groups = try await client.listMemoryGroups().ok.body.json
                    guard groups.groups.reduce(0,{$0+$1.count}) == c.expectedItems else { throw Failed.check }
                    let absent = try await client.queryMemoryReceipt(.init(query:.init(operation_id:"never-observed"))).ok.body.json
                    guard case .case2(let missing) = absent.receipt,missing.value == nil else { throw Failed.check }
                    print("PASS live generated MEMORY five operations, original bytes/IDs, committed receipt, paged detail/groups and explicit null")
                    return
                }
            }
            throw Failed.check
        } catch {
            // No token/URL/body/ID/error content in diagnostics.
            if let clientError = error as? ClientError {
                let status = clientError.response?.status.code ?? 0
                print("FAIL generated MEMORY live consumer stage=\(stage) HTTP=\(status) decoded=\(clientError.underlyingError is DecodingError)")
            } else { print("FAIL generated MEMORY live consumer stage=\(stage)") }
            exit(1)
        }
    }
}
