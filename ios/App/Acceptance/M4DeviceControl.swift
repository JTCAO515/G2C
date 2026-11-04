#if DEBUG && G2C_M4_DEVICE_ACCEPTANCE
import Foundation
import Security

private final class M4ControlBundle: NSObject {}

/// Compiled only into the generated device XCTest bundle, never the product.
@MainActor enum M4DeviceControl {
    private struct Bootstrap: Decodable { let endpoint, token: String }
    private struct Connection {
        let endpoint: URL
        let token: String
        let session: URLSession
    }
    private static let connection: Result<Connection, any Error> = Result {
        let bundle = Bundle(for: M4ControlBundle.self)
        guard let bootstrap = bundle.url(forResource:"M4ControlBootstrap",withExtension:"plist"),
              let certificate = bundle.url(forResource:"G2CM4LocalServer",withExtension:"cer") else {
            throw M4LocalTLSFailure.invalidCertificate
        }
        let value = try PropertyListDecoder().decode(Bootstrap.self,from:Data(contentsOf:bootstrap))
        guard let url = URL(string:value.endpoint), url.scheme == "https",
              let host = url.host, let port = url.port,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              !value.token.isEmpty else { throw M4LocalTLSFailure.invalidCertificate }
        let pin = try M4LocalServerTrust(host:host,port:port,certificateDER:Data(contentsOf:certificate))
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = nil
        configuration.urlCredentialStorage = nil
        configuration.urlCache = nil
        return Connection(endpoint:url,token:value.token,
            session:URLSession(configuration:configuration,delegate:M4ControlDelegate(pin:pin),delegateQueue:nil))
    }
    static func data(from url: URL) async throws -> (Data, URLResponse) {
        let connection = try connection.get()
        guard url.scheme == "https", url.host == connection.endpoint.host,
              url.port == connection.endpoint.port, url.user == nil, url.password == nil else {
            throw M4LocalTLSFailure.invalidCertificate
        }
        var request = URLRequest(url:url)
        request.setValue(connection.token,forHTTPHeaderField:"X-G2C-M4-Control")
        return try await connection.session.data(for:request)
    }
}

private final class M4ControlDelegate: NSObject, URLSessionTaskDelegate, Sendable {
    let pin: M4LocalServerTrust
    init(pin: M4LocalServerTrust) { self.pin = pin }
    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge) async
        -> (URLSession.AuthChallengeDisposition, URLCredential?) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust,
              pin.accepts(trust,host:challenge.protectionSpace.host,port:challenge.protectionSpace.port) else {
            return (.cancelAuthenticationChallenge,nil)
        }
        return (.useCredential,URLCredential(trust:trust))
    }
    func urlSession(_ session: URLSession, task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest) async -> URLRequest? { nil }
}
#endif
