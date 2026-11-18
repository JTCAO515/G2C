#if DEBUG && G2C_DEMO_BETA && targetEnvironment(simulator)
import SwiftUI
import Foundation
import CJMessageHTTP
import CJSession

private nonisolated final class WarmRootRedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

/// The real Root keeps its Beta origin. Only the explicit simulator fixture's
/// HTTP boundary forwards these allowlisted synthetic requests to loopback.
private nonisolated final class WarmRootHTTP: URLProtocol, @unchecked Sendable {
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
              (request.httpMethod == "GET" && ["/v1/message-receipts", "/v1/lio/timeline", "/v2/lio/timeline", "/v2/lio/messages", "/v4/cleanup-device-registrations", "/v1/account-cleanup-preparations"].contains(original.path))
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
        let session = URLSession(configuration: configuration, delegate: WarmRootRedirectBlocker(), delegateQueue: nil)
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


@main struct LioWarmRootFixture: App {
    @State private var shell = ShellState()
    @State private var root: DevelopmentAccountRoot?
    @State private var originalDisplay: UUID?
    @State private var originalTrip: UUID?
    @State private var fixtureFailure = false
    @State private var bootstrap = "starting"
    @State private var acknowledgedMode = "unknown"
    @State private var materialState = "unknown"
    @State private var inspectedProblem = "not inspected"
    var body: some Scene {
        WindowGroup {
            VStack(spacing: 0) {
                if let root {
                    DemoBetaRootView(shell: shell, root: root)
                    HStack {
                        Button("Hold") { setMode("hold") }.accessibilityIdentifier("fixture.root.hold")
                        Button("Offline") { setMode("offline") }.accessibilityIdentifier("fixture.root.offline")
                        Button("Allow") { setMode("ready") }.accessibilityIdentifier("fixture.root.allow")
                        Button("Other owner") { signIn(root, owner: "b") }.accessibilityIdentifier("fixture.root.other")
                        Button("Deny") { setMode("denied") }.accessibilityIdentifier("fixture.root.deny")
                    }
                    .font(.caption).tint(LioTheme.vermilion).padding(4).background(LioTheme.surface)
                    if ProcessInfo.processInfo.environment["B691_TIMELINE_TIMEOUT"] == "1" {
                        HStack {
                            Button("Time out timeline") { setMode("timeline-timeout") }
                                .accessibilityIdentifier("fixture.root.timeline-timeout")
                            Button("Inspect problem") { inspectProblem() }
                                .accessibilityIdentifier("fixture.root.inspect-problem")
                            Text(inspectedProblem).accessibilityIdentifier("fixture.root.inspected-problem")
                        }
                        .font(.caption2)
                    }
                    if ProcessInfo.processInfo.environment["B691_COLD_DENIAL_NOTES"] == "1" {
                        HStack {
                            Button("Inspect problem") { inspectProblem() }
                                .accessibilityIdentifier("fixture.root.inspect-problem")
                            Text(inspectedProblem).accessibilityIdentifier("fixture.root.inspected-problem")
                        }
                        .font(.caption2)
                    }
                    HStack {
                        Text(bootstrap).accessibilityIdentifier("fixture.root.bootstrap")
                        Text(acknowledgedMode).accessibilityIdentifier("fixture.root.mode")
                        Text(materialState).accessibilityIdentifier("fixture.root.sdk-presence")
                        Text(root.fixtureHasRetained ? "retained" : "empty").accessibilityIdentifier("fixture.root.retained")
                        Text(root.trip == nil ? "retired" : "active").accessibilityIdentifier("fixture.root.business")
                        Text(root.fixtureDisplayID == originalDisplay ? "same" : "changed").accessibilityIdentifier("fixture.root.display")
                        Text(root.trip?.id != originalTrip ? "new" : "original").accessibilityIdentifier("fixture.root.trip")
                        Text(String(describing: root.accounts.state)).accessibilityIdentifier("fixture.root.state")
                    }
                    .font(.caption2).foregroundStyle(LioTheme.ink).background(LioTheme.paper)
                    .overlay(alignment: .bottomLeading) {
                        if let problem = root.lioSessionProblem {
                            Text(String(problem.diagnosis.httpStatus ?? 0) + "|" + problem.origin.rawValue + "|" + (problem.diagnosis.serverReference ?? "-"))
                                .font(.caption2).foregroundStyle(LioTheme.ink)
                                .accessibilityIdentifier("fixture.root.problem")
                            Text(problem.diagnosis.category.rawValue)
                                .accessibilityIdentifier("fixture.root.category")
                        }
                    }
                    .onChange(of: root.accounts.state, initial: true) { _, state in
                        do { materialState = try root.fixtureHasNoSavedMaterial() ? "empty" : "present" }
                        catch { materialState = "unknown" }
                        if case .signedIn = state, originalDisplay == nil {
                            originalDisplay = root.fixtureDisplayID; originalTrip = root.trip?.id
                        }
                    }
                } else {
                    Text(fixtureFailure ? "Fixture setup failed" : "Fixture starting").accessibilityIdentifier("fixture.root.setup")
                }
            }
            .task {
                guard root == nil && !fixtureFailure else { return }
                do {
                    // Without the existing marker/install boundary this transport fails closed.
                    try NoRedirectTransport.installB691LocalFixture(WarmRootHTTP.self)
                    let ready = try DevelopmentAccountRoot(demo: shell)
                    let hasNoMaterial = try ready.fixtureHasNoSavedMaterial()
                    root = ready
                    if hasNoMaterial {
                        bootstrap = "sign-in"
                        signIn(ready, owner: "a")
                    } else {
                        bootstrap = "restore"
                        ready.accounts.restore()
                    }
                } catch { fixtureFailure = true }
            }
        }
    }
    private func signIn(_ root: DevelopmentAccountRoot, owner: String) {
        do {
            let expiry = Date().addingTimeInterval(604000)
            let subject = "m4-synthetic-demo-" + String(repeating: owner, count: 12)
            let claims: [String: Any] = ["sub": subject, "iss": "https://local.g2c.invalid", "aud": "g2c-local", "exp": expiry.timeIntervalSince1970]
            let payload = try JSONSerialization.data(withJSONObject: claims).base64EncodedString()
                .replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
            let grant = DemoInviteGrant(version: DemoBetaConfiguration.inviteVersion,
                access_token: "b691fixture." + payload + ".synthetic", subject: subject,
                expires_at: ISO8601DateFormatter().string(from: expiry))
            let invite: DemoInviteSession
            if ProcessInfo.processInfo.environment["B691_TIMELINE_TIMEOUT"] == "1"
                || ProcessInfo.processInfo.environment["B691_LOCK_SCREEN"] == "1" {
                invite = .lio(grant: grant)
            } else {
                let selection = try DemoCompositionProfile(language: shell.language == .chinese ? .zh : .en,
                    travelID: String(repeating: "a", count: 32), travelVersion: 1)
                invite = DemoInviteSession(grant: grant, composition: selection)
            }
            let material = try SessionMaterial(trustedSDKBytes: JSONEncoder().encode(invite))
            root.accounts.signIn(exchanging: { material })
        } catch { fixtureFailure = true }
    }
    private func inspectProblem() {
        guard let entry = LioDiagnosticLog.shared.entries.first else {
            inspectedProblem = "no problem"
            return
        }
        inspectedProblem = [entry.category.rawValue, entry.origin?.rawValue ?? "-", entry.cause?.rawValue ?? "-",
                            String(entry.errorCode ?? 0), String(entry.httpStatus ?? 0), entry.reference ?? "-"].joined(separator: "|")
    }
    private func setMode(_ mode: String) {
        Task {
            do {
                guard let raw = ProcessInfo.processInfo.environment["B691_LOCAL_ENDPOINT"], let endpoint = URL(string: raw),
                      endpoint.host == "127.0.0.1" else { throw URLError(.badURL) }
                var request = URLRequest(url: endpoint.appendingPathComponent("fixture-mode"))
                request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONEncoder().encode(["mode": mode])
                let (_, response) = try await URLSession.shared.data(for: request)
                guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
                acknowledgedMode = mode
            } catch { fixtureFailure = true }
        }
    }
}
#endif
