#if DEBUG && G2C_DEMO_BETA && targetEnvironment(simulator)
import SwiftUI
import Foundation
import CJMessageHTTP

private nonisolated final class B691RedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

/// The real Root keeps its Beta origin. Only the explicit simulator fixture's
/// HTTP boundary forwards these allowlisted synthetic requests to loopback.
private nonisolated final class B691RootHTTP: URLProtocol, @unchecked Sendable {
    private var session: URLSession?
    private var forwardedTask: URLSessionDataTask?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let original = request.url, original.scheme == "https", original.host == "api-beta.go2china.space",
              original.port == nil, original.user == nil, original.password == nil,
              let raw = ProcessInfo.processInfo.environment["B691_LOCAL_ENDPOINT"],
              let endpoint = URL(string: raw), endpoint.scheme == "http", endpoint.host == "127.0.0.1", endpoint.port != nil,
              request.value(forHTTPHeaderField: "Authorization")?.hasPrefix("Bearer b691fixture.") == true
                || request.value(forHTTPHeaderField: "Authorization")?.hasPrefix("Cleanup PROGRESS.SYNTHETIC.B691.") == true,
              (request.httpMethod == "GET" && ["/v1/message-receipts", "/v4/cleanup-device-registrations", "/v1/account-cleanup-preparations"].contains(original.path))
                || original.path.hasPrefix("/v1/account-cleanup-operations/")
                || (request.httpMethod == "POST" && ["/v4/cleanup-devices", "/v1/account-cleanup-operations"].contains(original.path)) else {
            client?.urlProtocol(self, didFailWithError: URLError(.unsupportedURL)); return
        }
        guard var components = URLComponents(url: original, resolvingAgainstBaseURL: false) else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL)); return
        }
        components.scheme = "http"; components.host = "127.0.0.1"; components.port = endpoint.port
        var forwarded = request; forwarded.url = components.url
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = []; configuration.urlCache = nil; configuration.httpCookieStorage = nil
        configuration.urlCredentialStorage = nil; configuration.timeoutIntervalForRequest = 5
        let session = URLSession(configuration: configuration, delegate: B691RedirectBlocker(), delegateQueue: nil)
        self.session = session
        forwardedTask = session.dataTask(with: forwarded) { [weak self] bytes, response, error in
            guard let self else { return }
            defer { session.finishTasksAndInvalidate() }
            if let error { self.client?.urlProtocol(self, didFailWithError: error); return }
            guard let http = response as? HTTPURLResponse, let bytes,
                  let response = HTTPURLResponse(url: original, statusCode: http.statusCode,
                    httpVersion: "HTTP/1.1", headerFields: http.allHeaderFields as? [String: String]) else {
                self.client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse)); return
            }
            self.client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            self.client?.urlProtocol(self, didLoad: bytes); self.client?.urlProtocolDidFinishLoading(self)
        }
        forwardedTask?.resume()
    }
    override func stopLoading() { forwardedTask?.cancel(); session?.invalidateAndCancel() }
}

@main
struct DemoCleanupRenewalFixture: App {
    @State private var status = "UNRUN"
    var body: some Scene {
        WindowGroup {
            Text(status).accessibilityIdentifier("b691.status")
                .task {
                    do {
                        guard let raw = ProcessInfo.processInfo.environment["B691_LOCAL_ENDPOINT"],
                              let endpoint = URL(string: raw), endpoint.host == "127.0.0.1" else {
                            throw URLError(.badURL)
                        }
                        if let refusal = ProcessInfo.processInfo.environment["B691_REFUSAL_MODE"], !refusal.isEmpty {
                            do {
                                try NoRedirectTransport.installB691LocalFixture(B691RootHTTP.self)
                                throw URLError(.unknown)
                            } catch MessageHTTPFailure.invalidConfiguration { }
                            if refusal == "wrong-bundle" {
                                do {
                                    _ = try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1)
                                    throw URLError(.unknown)
                                } catch MessageHTTPFailure.invalidConfiguration { }
                            }
                            var request = URLRequest(url: endpoint.appendingPathComponent("fixture-admission-result"))
                            request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                            request.httpBody = try JSONEncoder().encode(["mode": refusal, "result": "DENIED"])
                            let (_, response) = try await URLSession.shared.data(for: request)
                            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
                            status = "PASS"; return
                        }
                        if ProcessInfo.processInfo.environment["B691_ROOT_LIFECYCLE"] != "1" {
                        for scenario in DemoCleanupRenewalProbe.scenarios {
                            let result = try await DemoCleanupRenewalProbe.run(endpoint: endpoint, scenario: scenario)
                            var request = URLRequest(url: endpoint.appendingPathComponent("probe-result"))
                            request.httpMethod = "POST"
                            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                            request.httpBody = try JSONEncoder().encode(result)
                            let (_, response) = try await URLSession.shared.data(for: request)
                            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
                        }
                        } else {
                        // A marker without installation must never fall through
                        // to the real Beta network.
                        do {
                            _ = try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1)
                            throw URLError(.unknown)
                        } catch MessageHTTPFailure.invalidConfiguration { }
                        try NoRedirectTransport.installB691LocalFixture(B691RootHTTP.self)
                        for scenario in ["registrationUnknown", "preparedUnregister", "preparationUnknown", "foreignOwner", "confirmationDispatched", "verifiedRefusal"] {
                            let result = try await DemoCleanupRenewalProbe.runRoot(scenario: scenario)
                            var request = URLRequest(url: endpoint.appendingPathComponent("root-probe-result"))
                            request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                            request.httpBody = try JSONEncoder().encode(result)
                            let (_, response) = try await URLSession.shared.data(for: request)
                            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
                        }
                        }
                        status = "PASS"
                    } catch {
                        status = "FAIL: " + String(describing: error)
                    }
                }
        }
    }
}
#endif
