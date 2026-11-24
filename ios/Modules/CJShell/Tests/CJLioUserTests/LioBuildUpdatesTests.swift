import Foundation
import Testing
@testable import CJLioUser

struct LioBuildUpdatesTests {
    @Test func bundledBookKeepsOnlyCurrentAndPreviousAndBothLanguages() throws {
        let book = try LioBuildUpdates.bundled.get()
        #expect(book.currentBuild == 54)
        #expect(book.releases.map(\.build) == [54, 53])
        let current = try book.release(for: 54)
        let previous = try book.release(for: 53)
        #expect(current.previousBuild == 53)
        #expect(current.sections.map(\.id) == [.changes, .comparison, .testing, .known, .service])
        #expect(current.whatToTest(.chinese).contains("用默认字号测中英界面"))
        #expect(current.whatToTest(.english).contains("Taxi place search and Nearby require internet access and an enabled tester account."))
        #expect(current.whatToTest(.chinese).contains("「插件」改名为「工具」"))
        #expect(current.whatToTest(.english).contains("Translation is one page"))
        #expect(previous.whatToTest(.chinese).contains("常用语卡片可放大、朗读"))
        #expect(previous.whatToTest(.english).contains("Phrase cards show and read common phrases."))
        #expect(previous.whatToTest(.chinese).contains("用默认字号测中英界面"))
        #expect(throws: LioBuildUpdates.Failure.unlistedBuild) { try book.release(for: 51) }
    }

    @Test func malformedOrIncompleteReleaseContentIsNotAccepted() throws {
        var root = fixture()
        root["schema"] = 2
        #expect(throws: LioBuildUpdates.Failure.invalidBook) { try LioBuildUpdates.decode(data(root)) }
        root = fixture()
        root["currentBuild"] = 45
        #expect(throws: LioBuildUpdates.Failure.invalidBook) { try LioBuildUpdates.decode(data(root)) }
        root = fixture()
        var releases = root["releases"] as! [[String: Any]]
        releases.append(releases[1]); root["releases"] = releases
        #expect(throws: LioBuildUpdates.Failure.invalidBook) { try LioBuildUpdates.decode(data(root)) }
        #expect(throws: LioBuildUpdates.Failure.invalidBook) { try LioBuildUpdates.decode(Data("{}".utf8)) }
    }

    @Test func duplicateFieldsAreRejectedAtBothLevels() throws {
        let valid = String(decoding: try data(fixture()), as: UTF8.self)
        let duplicateRoot = valid.replacingOccurrences(of: "\"schema\":1", with: "\"schema\":1,\"schema\":1")
        #expect(duplicateRoot != valid)
        #expect(throws: LioBuildUpdates.Failure.invalidBook) { try LioBuildUpdates.decode(Data(duplicateRoot.utf8)) }
        let duplicateNested = valid.replacingOccurrences(of: "\"en\":\"Heading\"", with: "\"en\":\"Heading\",\"en\":\"Heading\"")
        #expect(duplicateNested != valid)
        #expect(throws: LioBuildUpdates.Failure.invalidBook) { try LioBuildUpdates.decode(Data(duplicateNested.utf8)) }
    }

    @Test func missingTranslationOrTooManySuggestedChecksIsRejected() throws {
        var root = fixture()
        var releases = root["releases"] as! [[String: Any]]
        var sections = releases[0]["sections"] as! [[String: Any]]
        sections[0]["items"] = ["en": ["Readable"]]
        releases[0]["sections"] = sections; root["releases"] = releases
        #expect(throws: LioBuildUpdates.Failure.invalidBook) { try LioBuildUpdates.decode(data(root)) }
        root = fixture(); releases = root["releases"] as! [[String: Any]]; sections = releases[0]["sections"] as! [[String: Any]]
        sections[2]["items"] = ["en": Array(repeating: "Check", count: 5), "zh": Array(repeating: "检查", count: 5)]
        releases[0]["sections"] = sections; root["releases"] = releases
        #expect(throws: LioBuildUpdates.Failure.invalidBook) { try LioBuildUpdates.decode(data(root)) }
    }

    private func fixture() -> [String: Any] {
        let sections: [[String: Any]] = LioBuildUpdates.SectionID.allCases.map { id in
            ["id": id.rawValue, "title": ["en": "Heading", "zh": "标题"],
             "items": ["en": id == .testing ? ["One", "Two"] : ["One"], "zh": id == .testing ? ["一", "二"] : ["一"]]]
        }
        return ["schema": 1, "currentBuild": 44, "releases": [
            ["build": 44, "previousBuild": 43, "sections": sections],
            ["build": 43, "previousBuild": 42, "sections": sections]]]
    }
    private func data(_ object: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: object) }
}
