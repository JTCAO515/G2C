import Foundation
import Testing
@testable import CJShell

struct LioDeviceDefaultsCleanupTests {
    private func isolated() throws -> (UserDefaults, String) {
        let suite = "lio.defaults-cleanup." + UUID().uuidString
        return (try #require(UserDefaults(suiteName: suite)), suite)
    }

    @Test func deletingTheAccountLeavesNationalityAndArrivalProgressEmpty() throws {
        let (defaults, suite) = try isolated()
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set("GB", forKey: "lio.local-support.nationality")
        defaults.set("entry,payment", forKey: "lio.arrival.progress.v1")
        defaults.set("en", forKey: "cj.ui.language.v1")
        #expect(throws: LioDeviceDefaultsCleanup.Failure.stillPresent) { try LioDeviceDefaultsCleanup.requireAbsent(in: defaults) }

        LioDeviceDefaultsCleanup.erase(in: defaults)

        try LioDeviceDefaultsCleanup.requireAbsent(in: defaults)
        #expect(defaults.string(forKey: "lio.local-support.nationality") == nil)
        #expect(defaults.string(forKey: "lio.arrival.progress.v1") == nil)
        // Only the two approved values: other preferences such as the language stay.
        #expect(defaults.string(forKey: "cj.ui.language.v1") == "en")
        // Running it again (a resumed cleanup) is harmless.
        LioDeviceDefaultsCleanup.erase(in: defaults)
        try LioDeviceDefaultsCleanup.requireAbsent(in: defaults)
    }

    @Test func eachKeyAloneKeepsTheCheckIncomplete() throws {
        for key in LioDeviceDefaultsCleanup.keys {
            let (defaults, suite) = try isolated()
            defer { defaults.removePersistentDomain(forName: suite) }
            defaults.set("x", forKey: key)
            #expect(throws: LioDeviceDefaultsCleanup.Failure.stillPresent) { try LioDeviceDefaultsCleanup.requireAbsent(in: defaults) }
        }
    }

    /// The cleanup names the keys the app actually stores (as `@AppStorage` literals or named constants);
    /// a renamed key would otherwise survive deletion.
    @Test func keysMatchTheStoredValuesInTheApp() throws {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<3 { root.deleteLastPathComponent() }
        let sources = root.appendingPathComponent("Sources/CJLioUser")
        let files = try FileManager.default.contentsOfDirectory(atPath: sources.path).filter { $0.hasSuffix(".swift") }
        let text = try files.map { try String(contentsOf: sources.appendingPathComponent($0), encoding: .utf8) }.joined()
        for key in LioDeviceDefaultsCleanup.keys {
            #expect(text.contains("\"" + key + "\""), "\(key) is no longer stored by the app")
        }
        // No other version of these values is stored that the cleanup would miss.
        #expect(!text.contains("lio.arrival.progress.v2"))
        #expect(!text.contains("lio.local-support.nationality.v"))
    }
}
