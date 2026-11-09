import Foundation
import Testing

struct LioCopyTests {
    // Scan Swift string literals on the entire app-owned user surface, including
    // both languages, accessibility labels, invite and consent. Do not inspect
    // traveller text or server answer content. Never pass raw statuses to views.
    private let banned = #"原|运行|投递|上下文|回执|候选|版本号|核实|对账|读取|查询|确认结果|(?<![A-Za-z])(?:run|needs|unknown|scope|receipt|delivery|context|candidate|query|reconcile|version number|check result|read result)(?![A-Za-z])"#

    @Test func userCopyHasZeroBackendTerms() throws {
        let shell = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let ios = shell.deletingLastPathComponent().deletingLastPathComponent()
        let userSources = shell.appendingPathComponent("Sources/CJLioUser")
        let enumerator = try #require(FileManager.default.enumerator(at: userSources, includingPropertiesForKeys: nil))
        let userFiles = enumerator.compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" }
        #expect(!userFiles.isEmpty)
        let files = userFiles + [
            shell.appendingPathComponent("Sources/CJShell/DemoV2ConsentView.swift"),
            shell.appendingPathComponent("Sources/CJShell/LioRecordedTripMap.swift"),
            shell.appendingPathComponent("Sources/CJShell/LioSavedMemoryView.swift"),
            shell.appendingPathComponent("Sources/CJShell/LioMemoryDeletionView.swift"),
            ios.appendingPathComponent("App/DemoBetaApp.swift"),
            ios.appendingPathComponent("App/CJProbeApp.swift")
        ]
        let literals = try NSRegularExpression(pattern: #"\"\"\"[\s\S]*?\"\"\"|\"(?:\\.|[^\"\\\n])*\""#)
        let vocabulary = try NSRegularExpression(pattern: banned, options: [.caseInsensitive])
        let matches = try files.flatMap { file -> [String] in
            let text = try String(contentsOf: file, encoding: .utf8)
            return literals.matches(in: text, range: NSRange(text.startIndex..., in: text)).compactMap { match in
                guard let span = Range(match.range, in: text) else { return nil }
                let literal = String(text[span])
                guard vocabulary.firstMatch(in: literal, range: NSRange(literal.startIndex..., in: literal)) != nil else {
                    return nil
                }
                let line = text[..<span.lowerBound].filter { $0 == "\n" }.count + 1
                return "\(file.lastPathComponent):\(line): \(literal)"
            }
        }
        #expect(matches.isEmpty, "Forbidden copy: \(matches.joined(separator: "\n"))")
        print("Lio user copy: \(matches.count) forbidden terms in \(files.count) Swift files")
    }
}
