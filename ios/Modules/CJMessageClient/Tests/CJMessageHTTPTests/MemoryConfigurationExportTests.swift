import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime

private struct ExportOnlyTransport: ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        Issue.record("configuration export smoke test must not issue requests")
        throw URLError(.unsupportedURL)
    }
}
struct MemoryConfigurationExportTests {
    @Test func fixedOfficialMemoryConfigurationCompilesInSharedCJAPI() throws {
        let configuration: Configuration = .memory
        _ = Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:configuration,transport:ExportOnlyTransport())
    }
}
