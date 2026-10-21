import Foundation
import OpenAPIURLSession

public enum ProbeResult: Sendable {
    case connected(Components.Schemas.ProbeResponse)
    case rejected(status: Int, Components.Schemas.ErrorResponse)
}

public enum ProbeFailure: Error {
    case missingLocalConfiguration
    case invalidResponseTrace
    case redirectRejected(status: Int)
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
        let redirectDelegate = RejectRedirects()
        let session = URLSession(configuration: config, delegate: redirectDelegate, delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        let client = Client(serverURL: baseURL, transport: URLSessionTransport(configuration: .init(session: session)))
        let output: Operations.getProbe.Output
        do {
            output = try await client.getProbe()
        } catch {
            if let status = await redirectDelegate.rejection.status {
                throw ProbeFailure.redirectRejected(status: status)
            }
            throw error
        }
        if let status = await redirectDelegate.rejection.status {
            throw ProbeFailure.redirectRejected(status: status)
        }
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

// Refuse the redirect before URLSession can dispatch to its destination, even on loopback.
private final class RejectRedirects: NSObject, URLSessionTaskDelegate {
    let rejection = RedirectRejection()

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest) async -> URLRequest? {
        await rejection.record(response.statusCode)
        return nil
    }
}

private actor RedirectRejection {
    private(set) var status: Int?
    func record(_ status: Int) { self.status = status }
}
