#if DEBUG && G2C_M4_DEVICE_ACCEPTANCE && canImport(Security)
import Foundation
import Security
import Testing
@testable import CJMessageHTTP

struct M4LocalServerTrustTests {
    @Test func onlyExplicitCanonicalPortsCanBeApproved() throws {
        #expect(try M4LocalServerTrust.approvedPorts(primary: "18443", additional: nil) == [18443])
        #expect(try M4LocalServerTrust.approvedPorts(primary: "18443", additional: "[]") == [18443])
        #expect(try M4LocalServerTrust.approvedPorts(primary: "18443", additional: "[18444,18445]") == [18443,18444,18445])
        for primary in ["0", "65536", "-1", "018443", "18443 ", "host:18443"] {
            #expect(throws: M4LocalTLSFailure.self) {
                try M4LocalServerTrust.approvedPorts(primary: primary, additional: nil)
            }
        }
        for value in ["{}", "null", "[true]", "[\"18444\"]", "[0]", "[65536]",
                      "[18443]", "[18444,18444]", "[1,2,3,4,5,6,7,8]", String(repeating: " ", count: 4097)] {
            #expect(throws: M4LocalTLSFailure.self) {
                try M4LocalServerTrust.approvedPorts(primary: "18443", additional: value)
            }
        }
    }
    private func certificate() throws -> Data {
        let path = try #require(ProcessInfo.processInfo.environment["G2C_M4_TLS_TEST_CERT"])
        return try Data(contentsOf: URL(fileURLWithPath: path))
    }
    private var host: String {
        get throws { try #require(ProcessInfo.processInfo.environment["G2C_M4_TLS_TEST_HOST"]) }
    }
    private var validTime: Date {
        get throws {
            let raw = try #require(ProcessInfo.processInfo.environment["G2C_M4_TLS_TEST_TIME"])
            return Date(timeIntervalSince1970:try #require(Double(raw)))
        }
    }
    private func trust(_ data: Data) throws -> SecTrust {
        let certificate = try #require(SecCertificateCreateWithData(nil, data as CFData))
        var trust: SecTrust?
        #expect(SecTrustCreateWithCertificates([certificate] as CFArray, SecPolicyCreateSSL(true, nil), &trust) == errSecSuccess)
        let value = try #require(trust)
        #expect(SecTrustSetVerifyDate(value, try validTime as CFDate) == errSecSuccess)
        return value
    }

    @Test func onlyTheApprovedLeafHostAndPortAreTrusted() throws {
        let data = try certificate(), host = try self.host, port = 18443
        let pin = try M4LocalServerTrust(host:host,port:port,certificateDER:data)
        #expect(pin.accepts(try trust(data),host:host,port:port))
        #expect(!pin.accepts(try trust(data),host:"other.m4.invalid",port:port))
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
        let data = try certificate(), host = try self.host, port = 18443
        let wrongName = try M4LocalServerTrust(host:"other.m4.invalid",port:port,certificateDER:data)
        #expect(!wrongName.accepts(try trust(data),host:"other.m4.invalid",port:port))
        let pin = try M4LocalServerTrust(host:host,port:port,certificateDER:data)
        let expired = try trust(data)
        #expect(SecTrustSetVerifyDate(expired, try validTime.addingTimeInterval(48 * 3600) as CFDate) == errSecSuccess)
        #expect(!pin.accepts(expired,host:host,port:port))
    }
}
#endif
