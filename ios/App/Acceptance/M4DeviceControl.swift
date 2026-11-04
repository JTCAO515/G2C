#if DEBUG && G2C_M4_DEVICE_ACCEPTANCE
import Foundation
import Security
import Darwin

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
        configuration.waitsForConnectivity = true
        configuration.timeoutIntervalForResource = 60
        return Connection(endpoint:url,token:value.token,
            session:URLSession(configuration:configuration,delegate:M4ControlDelegate(pin:pin),delegateQueue:nil))
    }
    static func triggerLocalNetworkAlert() throws {
        let value = try connection.get()
        let descriptor = socket(AF_INET,SOCK_DGRAM,0)
        guard descriptor >= 0 else { throw M4LocalTLSFailure.invalidCertificate }
        defer { close(descriptor) }
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = in_port_t(9).bigEndian
        guard inet_pton(AF_INET,value.endpoint.host!,&address.sin_addr) == 1 else {
            throw M4LocalTLSFailure.invalidCertificate
        }
        // Apple TN3179: connecting a local UDP socket requests permission
        // without sending traffic. The real TLS request still proves access.
        _ = withUnsafePointer(to:&address) { pointer in
            pointer.withMemoryRebound(to:sockaddr.self,capacity:1) {
                Darwin.connect(descriptor,$0,socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
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
    static func unauthenticatedData(from url: URL) async throws -> (Data, URLResponse) {
        let connection = try connection.get()
        guard url.scheme == "https", url.host == connection.endpoint.host,
              url.port == connection.endpoint.port, url.user == nil, url.password == nil else {
            throw M4LocalTLSFailure.invalidCertificate
        }
        return try await connection.session.data(from:url)
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
