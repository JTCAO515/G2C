import Foundation
import Testing

/// CJProbeApp crash 2026-11-27: on iOS 27 SwiftUI's `LazyView` can call the `WindowGroup` content factory on the
/// `com.apple.SwiftUI.AsyncRenderer` thread. A closure written in the `@MainActor` `App.body` is
/// inferred `@MainActor`, and Swift 6 traps at its entry off the main thread. The app target is not part
/// of this package, so these checks read the entry file; the compiler enforces the rest (a `@Sendable`
/// function type cannot be formed from a main-actor-isolated initializer).
struct AppRootIsolationTests {
    private func source() throws -> String {
        let file = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("CJProbeApp.swift")
        return try String(contentsOf: file, encoding: .utf8)
    }

    @Test func windowGroupReceivesAFunctionNotAClosure() throws {
        let text = try source()
        #expect(text.contains("WindowGroup(content: Self.makeEntry)"))
        // No trailing-closure WindowGroup in any form: it would be inferred @MainActor again.
        let trailingClosure = try NSRegularExpression(pattern: #"WindowGroup\s*(\([^)]*\))?\s*\{"#)
        #expect(trailingClosure.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) == nil)
    }

    @Test func entryFactoryHasNoIsolationAndOwnsNoState() throws {
        let text = try source()
        #expect(text.contains("private static let makeEntry: @Sendable () -> CJProbeRootEntry = CJProbeRootEntry.init"))
        let start = try #require(text.range(of: "struct CJProbeRootEntry: View {"))
        let end = try #require(text.range(of: "struct CJProbeRoot: View {"))
        let block = String(text[start.upperBound..<end.lowerBound])
        #expect(block.contains("nonisolated init() {}"))
        #expect(!block.contains("@State") && !block.contains("@AppStorage") && !block.contains("shell"))
        #expect(block.contains("var body: some View { CJProbeRoot() }"))
    }

    @Test func appStateLivesInTheRootViewNotTheApp() throws {
        let text = try source()
        let app = try #require(text.range(of: "struct CJProbeApp: App {"))
        let entry = try #require(text.range(of: "struct CJProbeRootEntry: View {"))
        let appBody = text[app.upperBound..<entry.lowerBound]
        for forbidden in ["@State", "@AppStorage", "@Environment", "ShellState", "shell"] {
            #expect(!appBody.contains(forbidden), "CJProbeApp must not hold \(forbidden)")
        }
        #expect(text.contains("struct CJProbeRoot: View {\n    @State private var shell: ShellState"))
    }
}
