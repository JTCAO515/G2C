#if DEBUG && G2C_M4_DEVICE_ACCEPTANCE && canImport(Security)
import Foundation
import Security

enum M4LocalTLSFailure: Error { case invalidCertificate }

/// A single operator-approved local test server. The public leaf is bundled only
/// in the ignored Debug build; its private key never leaves the development Mac.
struct M4LocalServerTrust: Sendable {
    let host: String
    let port: Int
    private let certificateDER: Data

    init(host: String, port: Int, certificateDER: Data) throws {
        guard SecCertificateCreateWithData(nil, certificateDER as CFData) != nil else {
            throw M4LocalTLSFailure.invalidCertificate
        }
        self.host = host
        self.port = port
        self.certificateDER = certificateDER
    }

    func accepts(_ trust: SecTrust, host: String, port: Int) -> Bool {
        guard host == self.host, port == self.port,
              let chain = SecTrustCopyCertificateChain(trust) as? [SecCertificate],
              let leaf = chain.first,
              SecCertificateCopyData(leaf) as Data == certificateDER else { return false }
        // The immutable DER was parsed at construction. Trust this exact leaf,
        // then still require normal TLS server-name, validity and signature checks.
        let certificate = SecCertificateCreateWithData(nil, certificateDER as CFData)!
        guard SecTrustSetPolicies(trust, SecPolicyCreateSSL(true, host as CFString)) == errSecSuccess,
              SecTrustSetAnchorCertificates(trust, [certificate] as CFArray) == errSecSuccess,
              SecTrustSetAnchorCertificatesOnly(trust, true) == errSecSuccess,
              SecTrustSetNetworkFetchAllowed(trust, false) == errSecSuccess else { return false }
        return SecTrustEvaluateWithError(trust, nil)
    }
}
#endif
