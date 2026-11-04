import Foundation
import Testing
@testable import G2CDevelopmentConfiguration

struct DevelopmentDeviceIdentityTests {
    @Test func signedIdentityIsExactAndNeverWildcardOrAnotherBundle() throws {
        #expect(try DevelopmentKeychainIdentity.validated(bundleIdentifier:"space.go2china.app",signedIdentifier:"ABCDEFGHIJ.space.go2china.app") == "ABCDEFGHIJ.space.go2china.app")
        for value in [nil,"space.go2china.app","ABCDEFGHIJ.*","ABCDEFGHIJ.other.app","SHORT.space.go2china.app","ABCDEFGHIJ.space.go2china.app.extra","bad prefix.space.go2china.app"] {
            #expect(throws:DevelopmentKeychainIdentity.Failure.self) {
                try DevelopmentKeychainIdentity.validated(bundleIdentifier:"space.go2china.app",signedIdentifier:value)
            }
        }
    }
    @Test func accountInputKeepsTheExistingCountTypeAndChoiceBoundary() throws {
        #expect(try DevelopmentAccountInput.decode(Data("{\"A\":\"SYNTHETIC\"}".utf8)) == ["A":"SYNTHETIC"])
        for raw in ["[]","{\"A\":7}","{\" \":\"SYNTHETIC\"}"] {
            #expect(throws:(any Error).self) { try DevelopmentAccountInput.decode(Data(raw.utf8)) }
        }
        let tooMany=Dictionary(uniqueKeysWithValues:(0..<9).map{(String($0),"SYNTHETIC")})
        #expect(throws:(any Error).self) {
            try DevelopmentAccountInput.decode(JSONSerialization.data(withJSONObject:tooMany))
        }
    }
}
