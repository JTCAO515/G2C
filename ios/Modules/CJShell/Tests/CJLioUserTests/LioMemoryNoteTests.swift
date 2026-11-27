import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

/// #2001 (M-3, App): the line "based on what you asked me to remember" under an answer, behind `G2CMemoryNoteEnabled`.
struct LioMemoryNoteTests {
    // MARK: the flag

    @Test func flagIsOffUnlessTheBuildSaysYes() {
        #expect(LioMemoryNoteFeature.infoKey == "G2CMemoryNoteEnabled")
        #expect(!LioMemoryNoteFeature.enabled(infoValue: nil))
        #expect(!LioMemoryNoteFeature.enabled(infoValue: "NO"))
        #expect(!LioMemoryNoteFeature.enabled(infoValue: true))
        #expect(LioMemoryNoteFeature.enabled(infoValue: "YES"))
        #expect(!LioMemoryNoteFeature.enabledInBuild, "the test bundle sets no flag")
    }

    @Test func infoPlistReadsTheFlagFromABuildSettingThatNoConfigurationSets() throws {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(plist.contains("<key>G2CMemoryNoteEnabled</key><string>$(G2C_MEMORY_NOTE_ENABLED)</string>"))
        #expect(!project.contains("G2C_MEMORY_NOTE_ENABLED"), "off unless the release script passes it")
    }

    @Test func flagIsListedAndNotOnInTheRelease() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let manifestURL = root.appendingPathComponent("tooling/release/app_flags.json")
        let manifest = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any])
        let flags = try #require(manifest["flags"] as? [[String: String]])
        #expect(flags.contains(["setting": "G2C_MEMORY_NOTE_ENABLED", "plist": "G2CMemoryNoteEnabled"]))
        let release = try #require(manifest["release"] as? [String: Any])
        #expect(!(try #require(release["on"] as? [String])).contains("G2C_MEMORY_NOTE_ENABLED"))
    }

    // MARK: what reaches a turn

    private func message(used: LioTimelineWire.MemoryUsed?) -> LioTimelineWire.Message {
        LioTimelineWire.Message(id: "m1", question: "Q", answer: "A", state: .completed, activity: nil, sources: [], trip: nil,
                                memoryTags: [], rich: used.map { .init(entities: [], memoryUsed: $0) })
    }

    private let sample = LioTimelineWire.MemoryUsed(items: [.init(itemID: "mem-1", title: "节奏慢"), .init(itemID: "mem-2", title: "不吃辣")], total: 3)

    @Test func theLineNeedsRichAndTheNoteFlagAndTheServersField() {
        let on = LioTimelineTurn(message(used: sample), richEnabled: true, memoryNoteEnabled: true)
        #expect(on.memoryNote == LioMemoryUsedNote(sample))
        #expect(LioTimelineTurn(message(used: sample), richEnabled: true, memoryNoteEnabled: false).memoryNote == nil, "note flag off")
        #expect(LioTimelineTurn(message(used: sample), richEnabled: false, memoryNoteEnabled: true).memoryNote == nil, "rich off")
        #expect(LioTimelineTurn(message(used: nil), richEnabled: true, memoryNoteEnabled: true).memoryNote == nil, "nothing sent")
        let plain = LioTimelineWire.Message(id: "m2", question: "Q", answer: "A", state: .completed, activity: nil,
                                            sources: [], trip: nil, memoryTags: [])
        #expect(LioTimelineTurn(plain, richEnabled: true, memoryNoteEnabled: true).memoryNote == nil)
    }

    @Test func aTitleTheDisplayRulesRefuseIsLeftOutAndWithNoneLeftThereIsNoLine() {
        let mixed = LioTimelineWire.MemoryUsed(items: [.init(itemID: "a", title: "节奏慢"), .init(itemID: "b", title: "https://api.go2china.space/x")], total: 2)
        let note = LioMemoryUsedNote(mixed)
        #expect(note?.titles == ["节奏慢"] && note?.total == 2)
        let none = LioTimelineWire.MemoryUsed(items: [.init(itemID: "b", title: "https://api.go2china.space/x")], total: 1)
        #expect(LioMemoryUsedNote(none) == nil)
        #expect(LioMemoryUsedNote(nil) == nil)
    }

    // MARK: wording

    @Test func oneRememberedPreferenceUsesTheApprovedLine() throws {
        let note = try #require(LioMemoryUsedNote(.init(items: [.init(itemID: "a", title: "不吃辣")], total: 1)))
        #expect(LioMemoryNoteCopy.line(note, .chinese) == "按你记住的「不吃辣」")
        #expect(LioMemoryNoteCopy.line(note, .english) == "Based on your saved preference: 不吃辣")
    }

    @Test func severalSayHowManyAndNameTheFirstOnes() throws {
        let note = try #require(LioMemoryUsedNote(sample))
        #expect(LioMemoryNoteCopy.line(note, .chinese) == "按你记住的 3 条偏好：节奏慢、不吃辣等")
        #expect(LioMemoryNoteCopy.line(note, .english) == "Based on your 3 saved preferences: 节奏慢, 不吃辣 and more")
        let all = try #require(LioMemoryUsedNote(.init(items: [.init(itemID: "a", title: "x1"), .init(itemID: "b", title: "x2")], total: 2)))
        #expect(LioMemoryNoteCopy.line(all, .chinese) == "按你记住的 2 条偏好：x1、x2", "no \"etc.\" when every one is named")
    }

    @Test func theLineNeverCarriesAnythingButTitlesAndACount() throws {
        // The wire has no field for the remembered text, so the line cannot show it; the strings are title-only.
        let note = try #require(LioMemoryUsedNote(sample))
        for language in [LioLanguage.english, .chinese] {
            let line = LioMemoryNoteCopy.line(note, language)
            #expect(line.contains("节奏慢") && line.contains("3"))
            #expect(!LioMemoryNoteCopy.hint(language).isEmpty)
        }
    }
}
