import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import C0API

private struct C0Transport: ClientTransport {
    let name: String
    var missingHeader = false
    var mutation: String? = nil
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        #expect(request.path == "/v1/probe")
        let url = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures")!
        var bytes = try Data(contentsOf: url)
        let object = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        var headers: HTTPFields = [.contentType: "application/json"]
        if !missingHeader { headers[.init("X-Request-ID")!] = object["request_id"] as? String }
        if mutation == "missing" { bytes = Data("{}".utf8) }
        if mutation == "malformed" { bytes = Data("{broken".utf8) }
        if mutation == "future" {
            var modified = object
            modified["status"] = "future-status"
            bytes = try JSONSerialization.data(withJSONObject: modified)
        }
        return (HTTPResponse(status: .init(code: name == "normal" ? 200 : 409), headerFields: headers), HTTPBody(bytes))
    }
}
private func client(_ name: String, missingHeader: Bool = false) -> Client {
    Client(serverURL: URL(string: "https://cj004.invalid")!, transport: C0Transport(name: name, missingHeader: missingHeader))
}
@Test func c0NormalGeneratedClient() async throws {
    let response = try await client("normal").getProbe()
    #expect(try response.ok.body.json.status == .ok)
    #expect(try response.ok.body.json.contract_version == ._1_period_0_period_0)
}
@Test func c0UnknownIsNotSuccess() async throws {
    switch try await client("unknown").getProbe() {
    case .default(let status, let response):
        #expect(status == 409)
        #expect(try response.body.json.error.outcome == .unknown)
        #expect(try response.body.json.error.recovery == .reconcile_original)
    case .ok: Issue.record("Unknown result became success")
    }
}
@Test func c0ConflictIsStructured() async throws {
    switch try await client("conflict").getProbe() {
    case .default(_, let response): #expect(try response.body.json.error.outcome == .failed)
    case .ok: Issue.record("Conflict became success")
    }
}
@Test func c0MissingRequiredHeaderFails() async {
    await #expect(throws: (any Error).self) { _ = try await client("normal", missingHeader: true).getProbe() }
}

@Test(arguments: ["missing", "malformed", "future"])
func c0InvalidBodyFails(mutation: String) async {
    let probe = Client(serverURL: URL(string: "https://cj004.invalid")!, transport: C0Transport(name: "normal", mutation: mutation))
    await #expect(throws: (any Error).self) { _ = try await probe.getProbe() }
}
