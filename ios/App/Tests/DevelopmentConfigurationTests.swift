import Foundation
import Testing
@testable import G2CDevelopmentConfiguration

private func token(subject: String = "fixture", signature: String = "synthetic") throws -> String {
    let body = try JSONSerialization.data(withJSONObject: ["iss": "https://local.g2c.invalid", "aud": "g2c-local", "sub": subject])
    let payload = body.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    return "synthetic.\(payload).\(signature)"
}

struct DevelopmentConfigurationTests {
    @Test func missingEnvironmentNeverAssembles() throws {
        #expect(DevelopmentSessionConfiguration.read([:]) == nil)
        #expect(DevelopmentSessionConfiguration.read(["G2C_DEV_API_BASE_URL": "http://127.0.0.1:8765"]) == nil)
        #expect(DevelopmentSessionConfiguration.read(["G2C_DEV_TOKEN": try token()]) == nil)
    }
    @Test func onlyExplicitLoopbackAndValidLocalInputs() throws {
        for url in ["https://127.0.0.1:8765", "http://localhost:8765", "http://example.com:8765",
                    "http://127.0.0.1", "http://user@127.0.0.1:8765", "http://127.0.0.1:8765/path", "http://127.0.0.1:8765?x=1"] {
            #expect(DevelopmentSessionConfiguration.read(["G2C_DEV_API_BASE_URL": url, "G2C_DEV_TOKEN": try token()]) == nil)
        }
        for invalid in ["", "synthetic", "token with spaces", "one.two.three"] {
            #expect(DevelopmentSessionConfiguration.read(["G2C_DEV_API_BASE_URL": "http://127.0.0.1:8765", "G2C_DEV_TOKEN": invalid]) == nil)
        }
    }
    @Test func debugOptInAndReleaseDenial() throws {
        let environment = ["G2C_DEV_API_BASE_URL": "http://127.0.0.1:8765", "G2C_DEV_TOKEN": try token(), "G2C_DEV_PROPOSAL_ID": "p-fixture"]
        #if DEBUG
        let config = try #require(DevelopmentSessionConfiguration.read(environment))
        #expect(config.proposalID == "p-fixture")
        #expect(!String(reflecting: config).contains(try token()))
        #else
        #expect(DevelopmentSessionConfiguration.read(environment) == nil)
        #endif
    }
    @Test func renewedTokenKeepsStoragePartitionAndOtherUserDoesNot() throws {
        #if DEBUG
        func config(_ subject: String, signature: String) throws -> DevelopmentSessionConfiguration {
            let value = try token(subject: subject, signature: signature)
            return try #require(DevelopmentSessionConfiguration.read(["G2C_DEV_API_BASE_URL": "http://127.0.0.1:8765", "G2C_DEV_TOKEN": value]))
        }
        let a = try config("alice", signature: "first"), renewed = try config("alice", signature: "second"), b = try config("bob", signature: "first")
        #expect(a.accountID == renewed.accountID && a.environmentID == renewed.environmentID)
        #expect(a.accountID != b.accountID)
        #endif
    }
}
