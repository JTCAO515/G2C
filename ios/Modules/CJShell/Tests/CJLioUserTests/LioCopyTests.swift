import Foundation
import Testing

struct LioCopyTests {
    // Scan Swift literals and decoded resource strings on the app-owned user surface, including
    // both languages, accessibility labels, invite and consent. Do not inspect
    // traveller text or server answer content. Never pass raw statuses to views.
    private let banned = #"原|运行|投递|上下文|回执|候选|版本号|核实|对账|读取|查询|确认结果|待\s*#\d+|(?<![A-Za-z])(?:run|needs|unknown|scope|receipt|delivery|context|candidate|query|reconcil(?:e|iation)|backend|payload|idempotenc(?:y|e)|(?:version|request)\s+(?:number|id)|original\s+(?:request|action|operation)|(?:check|read|verify)\s+(?:the\s+)?result|pending\s+#\d+)(?![A-Za-z])"#

    @Test func vocabularyCatchesTechnicalCopyInBothLanguages() throws {
        let vocabulary = try NSRegularExpression(pattern: banned, options: [.caseInsensitive])
        for copy in ["查看原操作", "读取结果", "待 #225 定案后替换", "Placeholder pending #225.", "RUN", "REQUEST ID", "original  action",
                     "Verify the result", "Reconciliation", "Backend", "Payload"] {
            #expect(vocabulary.firstMatch(in: copy, range: NSRange(copy.startIndex..., in: copy)) != nil, "\(copy)")
        }
        for copy in ["Go for a runaround", "Open your saved trip", "Ask again", "Meet at gate #4", "查看已保存的行程", "这次没答完"] {
            #expect(vocabulary.firstMatch(in: copy, range: NSRange(copy.startIndex..., in: copy)) == nil, "\(copy)")
        }
    }

    /// A Swift literal that is nothing but one web address (no spaces, escapes or interpolation) is a link
    /// target, not copy, so its query parameter names are not scanned. Text around an address still is.
    private static let bareURLLiteral = try! NSRegularExpression(pattern: #"^"https://[^\s"\\]+"$"#)

    private func isBareURL(_ literal: String) -> Bool {
        Self.bareURLLiteral.firstMatch(in: literal, range: NSRange(literal.startIndex..., in: literal)) != nil
    }

    @Test func onlyBareWebAddressesAreExempt() throws {
        let vocabulary = try NSRegularExpression(pattern: banned, options: [.caseInsensitive])
        func flagged(_ literal: String) -> Bool {
            !isBareURL(literal) && vocabulary.firstMatch(in: literal, range: NSRange(literal.startIndex..., in: literal)) != nil
        }
        // An address whose parameter is named query is a link, not copy.
        #expect(!flagged(#""https://www.klook.com/search/result/?query=Mutianyu""#))
        // Copy that says query is still caught, and so is an address with text after it.
        #expect(flagged(#""Search query""#))
        #expect(flagged(#""https://www.klook.com/search/result/?query=x 查询""#))
        #expect(flagged(#""Open https://www.klook.com/search/result/?query=x""#))
        #expect(flagged(#""https://example.com/?query=\(name)""#))
        #expect(flagged(#""http://example.com/?query=x""#))
    }

    private func resourceStrings(_ value: Any) -> [String] {
        if let text = value as? String { return [text] }
        if let array = value as? [Any] { return array.flatMap(resourceStrings) }
        if let object = value as? [String: Any] { return object.values.flatMap(resourceStrings) }
        return []
    }

    /// Strings a metro map file shows, leaving out only place names: station names, the operator, and the
    /// city and its province (Xi'an's 龙首原 and the city 太原 are places, not the banned "原操作"). Line
    /// names, river names and the rest of the source note are still checked.
    private func metroMapStrings(_ object: Any) -> [String] {
        guard let file = object as? [String: Any] else { return resourceStrings(object) }
        let stations = (file["stations"] as? [[String: Any]] ?? []).map { station in
            station.filter { $0.key != "nameZH" && $0.key != "nameEN" }
        }
        let source = (file["source"] as? [String: Any] ?? [:]).filter { $0.key != "operatorZH" && $0.key != "operatorEN" }
        let city = (file["cityInfo"] as? [String: Any] ?? [:]).filter { !["nameZH", "nameEN", "provinceZH"].contains($0.key) }
        return file.filter { !["stations", "source", "cityInfo"].contains($0.key) }.values.flatMap(resourceStrings)
            + stations.flatMap(resourceStrings) + resourceStrings(source) + resourceStrings(city)
    }

    @Test func metroMapsSkipOnlyStationNames() throws {
        let vocabulary = try NSRegularExpression(pattern: banned, options: [.caseInsensitive])
        func flagged(_ object: [String: Any]) -> [String] {
            metroMapStrings(object).filter { vocabulary.firstMatch(in: $0, range: NSRange($0.startIndex..., in: $0)) != nil }
        }
        let station: [String: Any] = ["id": "s1", "nameZH": "龙首原", "nameEN": "Longshouyuan"]
        #expect(flagged(["stations": [station]]).isEmpty)
        // The same character anywhere else in a map file is still caught.
        #expect(flagged(["stations": [station], "lines": [["nameZH": "原线", "nameEN": "Line 1"]]]) == ["原线"])
        #expect(flagged(["stations": [station], "water": [["nameZH": "原江", "nameEN": "River"]]]) == ["原江"])
        #expect(flagged(["stations": [station], "source": ["operatorZH": "太原地铁"]]).isEmpty)
        #expect(flagged(["stations": [station], "cityInfo": ["nameZH": "太原", "provinceZH": "山西省", "featured": 1]]).isEmpty)
        #expect(flagged(["stations": [station], "source": ["operatorZH": "太原地铁", "englishZH": "原来的拼音"]]) == ["原来的拼音"])
    }

    @Test func userCopyHasZeroBackendTerms() throws {
        let shell = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let ios = shell.deletingLastPathComponent().deletingLastPathComponent()
        let userSources = shell.appendingPathComponent("Sources/CJLioUser")
        let enumerator = try #require(FileManager.default.enumerator(at: userSources, includingPropertiesForKeys: nil))
        let userFiles = enumerator.compactMap { $0 as? URL }.filter { ["swift", "json"].contains($0.pathExtension) }
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
            if file.pathExtension == "json" {
                let object = try JSONSerialization.jsonObject(with: Data(text.utf8))
                let strings = file.lastPathComponent.hasPrefix("LioMetroMap.") ? metroMapStrings(object) : resourceStrings(object)
                return strings.filter { value in
                    vocabulary.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)) != nil
                }.map { "\(file.lastPathComponent): \($0)" }
            }
            return literals.matches(in: text, range: NSRange(text.startIndex..., in: text)).compactMap { match in
                guard let span = Range(match.range, in: text) else { return nil }
                let literal = String(text[span])
                guard !isBareURL(literal), vocabulary.firstMatch(in: literal, range: NSRange(literal.startIndex..., in: literal)) != nil else {
                    return nil
                }
                let line = text[..<span.lowerBound].filter { $0 == "\n" }.count + 1
                return "\(file.lastPathComponent):\(line): \(literal)"
            }
        }
        #expect(matches.isEmpty, "Forbidden copy: \(matches.joined(separator: "\n"))")
        print("Lio user copy: \(matches.count) forbidden terms in \(files.count) source/resource files")
    }
}
