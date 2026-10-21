import Foundation
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes

// Harness control over stdin, not an alternative API wire model. Never print token/body.
private struct Control: Decodable {
    var baseURL: URL
    var token: String
    var rawBase64: String
    var messageID: String
    var expectedSHA256: String
}
private enum CheckFailure: Error { case invalid }
private final class NoRedirects: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest) async -> URLRequest? { nil }
}
private struct LocalTransport: ClientTransport {
    let transport: URLSessionTransport
    let token: String
    var omitReceiptFixture = false
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String)
        async throws -> (HTTPResponse, HTTPBody?) {
        guard baseURL.scheme == "http", baseURL.host == "127.0.0.1", baseURL.port != nil else {
            throw CheckFailure.invalid
        }
        var request = request
        request.headerFields[.authorization] = "Bearer " + token
        if omitReceiptFixture {
            guard let name = HTTPField.Name("X-CJ005-Test-Omit-Receipt") else { throw CheckFailure.invalid }
            request.headerFields[name] = "1"
        }
        return try await transport.send(request, body: body, baseURL: baseURL, operationID: operationID)
    }
}

@main
struct LoopbackGeneratedClient {
    static func main() async {
        do {
            let control = try JSONDecoder().decode(Control.self,from:FileHandle.standardInput.readDataToEndOfFile())
            guard let raw = Data(base64Encoded:control.rawBase64) else { throw CheckFailure.invalid }
            let configuration = URLSessionConfiguration.ephemeral
            configuration.connectionProxyDictionary = [:]
            configuration.httpCookieStorage = nil
            configuration.urlCache = nil
            configuration.timeoutIntervalForRequest = 10
            configuration.timeoutIntervalForResource = 20
            let session = URLSession(configuration:configuration,delegate:NoRedirects(),delegateQueue:nil)
            defer { session.invalidateAndCancel() }
            let transport = URLSessionTransport(configuration:.init(session:session))
            let client = Client(serverURL:control.baseURL,transport:LocalTransport(transport:transport,token:control.token))
            let first = try await client.receiveMessage(.init(body:.binary(HTTPBody(raw)))).ok.body.json
            let second = try await client.receiveMessage(.init(body:.binary(HTTPBody(raw)))).ok.body.json
            guard first.receipt == second.receipt,
                  first.receipt.message_id == control.messageID,
                  first.receipt.input_sha256 == control.expectedSHA256 else { throw CheckFailure.invalid }
            print("PASS generated Swift real HTTP receive/repeat preserves original receipt")
            let found = try await client.queryMessageReceipt(.init(query:.init(message_id:control.messageID))).ok.body.json
            guard case .MessageReceipt(let receipt) = found.receipt, receipt == first.receipt else { throw CheckFailure.invalid }
            print("PASS generated Swift real HTTP object receipt and opaque query ID")
            let absent = try await client.queryMessageReceipt(.init(query:.init(message_id:"never-observed-swift"))).ok.body.json
            guard case .case2(let value) = absent.receipt, value.value == nil else { throw CheckFailure.invalid }
            print("PASS generated Swift real HTTP explicit null; no resend authority")
            let malformed = Client(serverURL:control.baseURL,
                transport:LocalTransport(transport:transport,token:control.token,omitReceiptFixture:true))
            do {
                _ = try await malformed.queryMessageReceipt(.init(query:.init(message_id:control.messageID)))
                throw CheckFailure.invalid
            } catch let error as ClientError {
                guard error.response?.status.code == 200,
                      case DecodingError.keyNotFound(let key, _) = error.underlyingError,
                      key.stringValue == "receipt" else { throw CheckFailure.invalid }
                print("PASS generated Swift real HTTP test-malformed missing receipt is keyNotFound, never null")
            }
        } catch {
            // Runtime ClientError may retain input/token/body, so no error interpolation.
            print("FAIL generated Swift local integration")
            exit(1)
        }
    }
}
