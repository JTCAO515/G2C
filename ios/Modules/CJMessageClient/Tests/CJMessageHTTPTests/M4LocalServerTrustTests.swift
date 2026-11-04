#if DEBUG && G2C_M4_DEVICE_ACCEPTANCE && canImport(Security)
import Foundation
import Security
import Testing
@testable import CJMessageHTTP

struct M4LocalServerTrustTests {
    private func certificate() throws -> Data {
        let path = try #require(ProcessInfo.processInfo.environment["G2C_M4_TLS_TEST_CERT"])
        return try Data(contentsOf: URL(fileURLWithPath: path))
    }
    private func trust(_ data: Data) throws -> SecTrust {
        let certificate = try #require(SecCertificateCreateWithData(nil, data as CFData))
        var trust: SecTrust?
        #expect(SecTrustCreateWithCertificates([certificate] as CFArray, SecPolicyCreateSSL(true, nil), &trust) == errSecSuccess)
        return try #require(trust)
    }

    @Test func onlyTheApprovedLeafHostAndPortAreTrusted() throws {
        let data = try certificate(), host = "192.168.1.6", port = 18443
        let pin = try M4LocalServerTrust(host:host,port:port,certificateDER:data)
        #expect(pin.accepts(try trust(data),host:host,port:port))
        #expect(!pin.accepts(try trust(data),host:"192.168.1.7",port:port))
        #expect(!pin.accepts(try trust(data),host:host,port:18444))
        var changed = data
        changed[changed.count - 1] ^= 1
        let differentPin = try M4LocalServerTrust(host:host,port:port,certificateDER:changed)
        #expect(!differentPin.accepts(try trust(data),host:host,port:port))
        #expect(throws:M4LocalTLSFailure.self) {
            try M4LocalServerTrust(host:host,port:port,certificateDER:Data("not a certificate".utf8))
        }
    }

    @Test func thePinnedCertificateStillNeedsServerNameAndTimeValidity() throws {
        let data = try certificate(), host = "192.168.1.6", port = 18443
        let wrongName = try M4LocalServerTrust(host:"192.168.1.7",port:port,certificateDER:data)
        #expect(!wrongName.accepts(try trust(data),host:"192.168.1.7",port:port))
        let pin = try M4LocalServerTrust(host:host,port:port,certificateDER:data)
        let expired = try trust(data)
        #expect(SecTrustSetVerifyDate(expired, Date().addingTimeInterval(48 * 3600) as CFDate) == errSecSuccess)
        #expect(!pin.accepts(expired,host:host,port:port))
    }
}
#endif
