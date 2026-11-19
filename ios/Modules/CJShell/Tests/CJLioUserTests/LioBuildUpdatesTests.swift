import Foundation
import Testing
@testable import CJLioUser

struct LioBuildUpdatesTests {
    @Test func bundledBookKeepsOnlyCurrentAndPreviousAndBothLanguages() throws {
        let book = try LioBuildUpdates.bundled.get()
        #expect(book.currentBuild == 49)
        #expect(book.releases.map(\.build) == [49, 48])
        let current = try book.release(for: 49)
        #expect(current.previousBuild == 48)
        #expect(current.sections.map(\.id) == [.changes, .comparison, .testing, .known, .service])
        #expect(current.whatToTest(.chinese).contains("行程正式保存、修改与撤销，以及全国规划仍在验证。"))
        #expect(current.whatToTest(.english).contains("Formal itinerary saving, edits and undo, and planning across China are still being validated."))
        #expect(current.whatToTest(.chinese).contains("构建 48"))
        #expect(throws: LioBuildUpdates.Failure.unlistedBuild) { try book.release(for: 50) }
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
