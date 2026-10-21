import Foundation
import OpenAPIURLSession

public enum ProbeResult: Sendable {
    case connected(Components.Schemas.ProbeResponse)
    case rejected(status: Int, Components.Schemas.ErrorResponse)
}

public enum ProbeFailure: Error {
    case missingLocalConfiguration
    case invalidResponseTrace
}

public struct ProbeConnection: Sendable {
    private let baseURL: URL

    public init(environment: [String: String]) throws {
        guard environment["CJ_ENV"] == "local",
              let raw = environment["CJ_API_BASE_URL"], let url = URL(string: raw),
              url.scheme == "http", url.host == "127.0.0.1", url.port != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else {
            throw ProbeFailure.missingLocalConfiguration
        }
        self.baseURL = url
    }

    public func fetch() async throws -> ProbeResult {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 10
        config.timeoutIntervalForResource = 15
        config.httpCookieStorage = nil
        config.urlCache = nil
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        let client = Client(serverURL: baseURL, transport: URLSessionTransport(configuration: .init(session: session)))
        let output = try await client.getProbe()
        try Task.checkCancellation()
        switch output {
        case .ok(let response):
            let body = try response.body.json
            guard UUID(uuidString: body.request_id) != nil,
                  response.headers.X_hyphen_Request_hyphen_ID == body.request_id else {
                throw ProbeFailure.invalidResponseTrace
            }
            return .connected(body)
        case .default(let status, let response):
            let body = try response.body.json
            guard UUID(uuidString: body.request_id) != nil,
                  response.headers.X_hyphen_Request_hyphen_ID == body.request_id else {
                throw ProbeFailure.invalidResponseTrace
            }
            return .rejected(status: status, body)
        }
    }
}
