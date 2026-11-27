import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

/// #1994 (58.1 T-1, App): the receipt line under an answer and the one-time notice at the account's first automatic
/// save, behind `G2CAutosaveNoticeEnabled` (and only with `G2CAnswerRichEnabled`).
@MainActor
struct LioAutosaveNoticeTests {
    typealias Receipt = LioTimelineWire.TripReceipt

    // MARK: The switch

    @Test func flagIsOffUnlessTheBuildSaysYes() {
        #expect(LioAutosaveNoticeFeature.infoKey == "G2CAutosaveNoticeEnabled")
        #expect(!LioAutosaveNoticeFeature.enabled(infoValue: nil))
        #expect(!LioAutosaveNoticeFeature.enabled(infoValue: "NO"))
        #expect(!LioAutosaveNoticeFeature.enabled(infoValue: "yes"))
        #expect(!LioAutosaveNoticeFeature.enabled(infoValue: true))
        #expect(!LioAutosaveNoticeFeature.enabled(infoValue: "$(G2C_AUTOSAVE_NOTICE_ENABLED)"))
        #expect(LioAutosaveNoticeFeature.enabled(infoValue: "YES"))
        #expect(!LioAutosaveNoticeFeature.enabledInBuild, "the test bundle sets no flag")
        #expect(!LioAutosaveNoticeFeature.activeInBuild)
    }

    @Test func theWholeFeatureNeedsRichAnswersToo() {
        #expect(LioAutosaveNoticeFeature.active(notice: true, rich: true))
        #expect(!LioAutosaveNoticeFeature.active(notice: true, rich: false))
        #expect(!LioAutosaveNoticeFeature.active(notice: false, rich: true))
        #expect(!LioAutosaveNoticeFeature.active(notice: false, rich: false))
    }

    @Test func infoPlistReadsTheFlagFromABuildSettingThatNoConfigurationSets() throws {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(plist.contains("<key>G2CAutosaveNoticeEnabled</key><string>$(G2C_AUTOSAVE_NOTICE_ENABLED)</string>"))
        #expect(!project.contains("G2C_AUTOSAVE_NOTICE_ENABLED"), "off unless the release script passes it")
    }

    @Test func flagIsListedAndNotOnInTheRelease() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let manifestURL = root.appendingPathComponent("tooling/release/app_flags.json")
        let manifest = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any])
        let flags = try #require(manifest["flags"] as? [[String: String]])
        #expect(flags.contains(["setting": "G2C_AUTOSAVE_NOTICE_ENABLED", "plist": "G2CAutosaveNoticeEnabled"]))
        let release = try #require(manifest["release"] as? [String: Any])
        #expect(!(try #require(release["on"] as? [String])).contains("G2C_AUTOSAVE_NOTICE_ENABLED"))
    }

    // MARK: What reaches a turn

    private func receipt(first: Bool = true, status: Receipt.Status = .saved) -> Receipt {
        switch status {
        case .saved:
            Receipt(status: .saved, actionID: "lio-plan-run-1", tripID: "trip-1", committedVersion: 1, firstAutosave: first,
                    summary: .init(days: [.init(day: 1, added: 3)]), undo: .init(state: .expired, until: "2026-11-28T03:04:05.678+00:00"))
        case .notSaved: Receipt(status: .notSaved, actionID: "lio-plan-run-1", reason: .conflict)
        case .unknown: Receipt(status: .unknown, actionID: "lio-plan-run-1")
        }
    }

    private func message(_ receipt: Receipt?, state: LioTimelineWire.Message.State = .completed) -> LioTimelineWire.Message {
        LioTimelineWire.Message(id: "m1", question: "Q", answer: state == .completed ? "A" : "", state: state, activity: nil, sources: [],
                                trip: nil, memoryTags: [], rich: receipt.map { .init(tripReceipt: $0) })
    }

    @Test func theReceiptNeedsRichAndTheSwitchAndTheServersField() {
        let value = receipt()
        #expect(LioTimelineTurn(message(value), richEnabled: true, autosaveNoticeEnabled: true).tripReceipt == value)
        #expect(LioTimelineTurn(message(value), richEnabled: true, autosaveNoticeEnabled: false).tripReceipt == nil, "switch off")
        #expect(LioTimelineTurn(message(value), richEnabled: false, autosaveNoticeEnabled: true).tripReceipt == nil, "rich off")
        #expect(LioTimelineTurn(message(nil), richEnabled: true, autosaveNoticeEnabled: true).tripReceipt == nil, "nothing sent")
    }

    @Test func aFailedRowKeepsTheReceiptSoTheNoticeIsNotMissed() {
        let turn = LioTimelineTurn(message(receipt(), state: .unavailable), richEnabled: true, autosaveNoticeEnabled: true)
        #expect(turn.tripReceipt?.isFirstSave == true)
        if case .failed = turn.status {} else { Issue.record("the row failed") }
    }

    // MARK: The one-time state

    private func temporaryDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("autosave-notice-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    private func store(_ directory: URL, current: @escaping @MainActor () -> Bool = { true }) -> LioAutosaveNoticeStore {
        LioAutosaveNoticeStore(directory: directory, isCurrent: current)
    }

    @Test func itShowsForTheFirstSavedReceiptUntilTheTravellerTapsGotIt() throws {
        let directory = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let notice = LioAutosaveNotice(store: store(directory))
        #expect(notice.shows(for: receipt()))
        #expect(notice.shows(for: receipt()), "reading the same receipt again does not use it up")
        notice.acknowledge()
        #expect(!notice.shows(for: receipt()))
        #expect(notice.acknowledged && !notice.saveFailed)
    }

    @Test func itNeverShowsForAnythingButASavedFirstReceipt() throws {
        let notice = LioAutosaveNotice(store: nil)
        #expect(!notice.shows(for: nil))
        #expect(!notice.shows(for: receipt(first: false)), "a save that is not the first")
        #expect(!notice.shows(for: receipt(status: .notSaved)))
        #expect(!notice.shows(for: receipt(status: .unknown)), "not saved yet, nothing to tell")
        #expect(notice.shows(for: receipt()))
    }

    @Test func onceTappedItStaysGoneAfterARestartAndAfterSigningOutAndBackIn() throws {
        let directory = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        LioAutosaveNotice(store: store(directory)).acknowledge()
        // A new model on the same account folder is a new launch, or the same account signing in again.
        let again = LioAutosaveNotice(store: store(directory))
        #expect(again.acknowledged && !again.shows(for: receipt()))
        #expect(FileManager.default.fileExists(atPath: directory.appendingPathComponent(LioAutosaveNoticeStore.fileName).path))
    }

    @Test func anotherAccountHasItsOwnNotice() throws {
        let first = try temporaryDirectory(), second = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: first); try? FileManager.default.removeItem(at: second) }
        LioAutosaveNotice(store: store(first)).acknowledge()
        let other = LioAutosaveNotice(store: store(second))
        #expect(other.shows(for: receipt()), "the second account has not been told")
        #expect(!LioAutosaveNotice(store: store(first)).shows(for: receipt()))
        other.acknowledge()
        #expect(!LioAutosaveNotice(store: store(second)).shows(for: receipt()))
    }

    @Test(arguments: [
        Data(), Data("not json".utf8), Data("{}".utf8), Data(#"{"version":1}"#.utf8),
        Data(#"{"version":2,"acknowledgedAt":0}"#.utf8), Data(#"{"version":0,"acknowledgedAt":0}"#.utf8),
        Data(#"{"version":"1","acknowledgedAt":0}"#.utf8), Data([0xFF, 0xFE, 0x00]),
    ]) func aDamagedOrNewerFileReadsAsNotShownYet(bytes: Data) throws {
        let directory = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        try bytes.write(to: directory.appendingPathComponent(LioAutosaveNoticeStore.fileName))
        let notice = LioAutosaveNotice(store: store(directory))
        #expect(!notice.acknowledged && notice.shows(for: receipt()), "one notice too many, never one too few")
        notice.acknowledge()
        #expect(LioAutosaveNotice(store: store(directory)).acknowledged, "tapping repairs the file")
    }

    @Test func aFileThatIsAFolderOrUnreadableReadsAsNotShownYet() throws {
        let directory = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory.appendingPathComponent(LioAutosaveNoticeStore.fileName),
                                                withIntermediateDirectories: true)
        #expect(LioAutosaveNotice(store: store(directory)).shows(for: receipt()))
    }

    @Test func aWriteThatFailsStillQuietsTheNoticeForTheSessionAndShowsAgainAfterARestart() throws {
        let directory = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        // The record's path is taken by a folder, so it can not be written.
        let blocked = directory.appendingPathComponent(LioAutosaveNoticeStore.fileName)
        try FileManager.default.createDirectory(at: blocked.appendingPathComponent("x"), withIntermediateDirectories: true)
        let notice = LioAutosaveNotice(store: store(directory))
        notice.acknowledge()
        #expect(notice.saveFailed && notice.acknowledged && !notice.shows(for: receipt()), "no nagging this session")
        #expect(LioAutosaveNotice(store: store(directory)).shows(for: receipt()), "but not remembered")
    }

    @Test func aSessionThatIsNoLongerCurrentShowsNothingAndWritesNothing() throws {
        let directory = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        var current = true
        let notice = LioAutosaveNotice(store: store(directory, current: { current }))
        #expect(notice.shows(for: receipt()))
        current = false
        #expect(!notice.shows(for: receipt()))
        notice.acknowledge()
        #expect(!notice.acknowledged)
        #expect(!FileManager.default.fileExists(atPath: directory.appendingPathComponent(LioAutosaveNoticeStore.fileName).path))
        current = true
        #expect(notice.shows(for: receipt()), "nothing was recorded for it")
    }

    @Test func theRecordSitsBesideTheTripHomesFileAndHoldsNoPersonalData() throws {
        let directory = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let tripHome = LioTripHomeStore(directory: LioTripHomeStore.storageDirectory(inMessageDirectory: directory), isCurrent: { true })
        let beside = try #require(LioAutosaveNoticeStore(tripHome: tripHome))
        #expect(LioAutosaveNoticeStore(tripHome: nil) == nil, "no account folder, nothing is kept")
        LioAutosaveNotice(store: beside).acknowledge()
        let file = LioTripHomeStore.storageDirectory(inMessageDirectory: directory).appendingPathComponent(LioAutosaveNoticeStore.fileName)
        let object = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any])
        #expect(Set(object.keys) == ["version", "acknowledgedAt"])
    }

    // MARK: Words

    @Test func theNoticeIsTheCoordinatorsSentenceAndHasAButton() {
        #expect(LioAutosaveCopy.notice(.chinese) == "对话里的行程会自动存进你的行程，可随时撤销或修改")
        #expect(LioAutosaveCopy.notice(.english).hasPrefix("Trips from your chats are saved to your trip automatically"))
        #expect(LioAutosaveCopy.gotIt(.chinese) == "知道了")
    }

    @Test func theHeadlineFollowsWhatWasSaved() {
        func headline(_ receipt: Receipt) -> String { LioAutosaveCopy.headline(receipt, .chinese) }
        func saved(version: Int, summary: Receipt.Summary?) -> Receipt {
            Receipt(status: .saved, actionID: "a", tripID: "t", committedVersion: version, summary: summary, undo: .init(state: .unavailable))
        }
        #expect(headline(saved(version: 1, summary: nil)) == "行程已新建")
        #expect(headline(saved(version: 3, summary: nil)) == "已加入行程")
        #expect(headline(saved(version: 3, summary: .init(days: [.init(day: 1, added: 2)]))) == "已加入行程")
        #expect(headline(saved(version: 3, summary: .init(days: [.init(day: 1, added: 0, updated: 1)]))) == "行程已更新")
        #expect(headline(saved(version: 3, summary: .init(days: [], wishlistAdded: 2))) == "已加入「想去」")
        #expect(headline(saved(version: 3, summary: .init(days: [], legsUpdated: 1))) == "行程已更新")
        #expect(headline(receipt(status: .notSaved)) == "这次未保存到行程。")
        #expect(headline(receipt(status: .unknown)) == "还没确认是否保存。")
    }

    @Test func theLinesUnderItAreCountsAndTheStateOfTheUndoAndNeverAPlaceName() {
        let summary = Receipt.Summary(days: [.init(day: 1, city: .init(id: "beijing", zh: "北京", en: "Beijing"), added: 3, updated: 1, removed: 2)],
                                      wishlistAdded: 2, legsUpdated: 1)
        #expect(LioAutosaveCopy.counts(summary, .chinese) == "新增 3 个地点，更新 1 个，移除 2 个，「想去」加入 2 个，更新 1 段路线")
        #expect(LioAutosaveCopy.counts(summary, .english) == "3 added, 1 updated, 2 removed, 2 added to Want to go, 1 routes updated")
        #expect(LioAutosaveCopy.counts(.init(days: []), .chinese) == nil)
        func saved(_ state: Receipt.Undo.State) -> Receipt {
            Receipt(status: .saved, actionID: "a", tripID: "t", committedVersion: 2, summary: .init(days: [.init(day: 1, added: 1)]),
                    undo: .init(state: state))
        }
        #expect(LioAutosaveCopy.details(saved(.available), .chinese) == ["新增 1 个地点"], "no Undo button and no promise of one")
        #expect(LioAutosaveCopy.details(saved(.expired), .chinese) == ["新增 1 个地点", "这次改动已超过撤销时间。"])
        #expect(LioAutosaveCopy.details(saved(.superseded), .chinese).last == "行程有新改动，无法撤销这次。")
        #expect(LioAutosaveCopy.details(saved(.undone), .chinese).last == "已撤销")
        #expect(LioAutosaveCopy.details(saved(.unavailable), .chinese) == ["新增 1 个地点"])
        #expect(LioAutosaveCopy.details(receipt(status: .notSaved), .chinese) == ["行程刚有新改动。"])
        #expect(LioAutosaveCopy.details(Receipt(status: .notSaved, actionID: "a"), .chinese).isEmpty)
        #expect(LioAutosaveCopy.details(receipt(status: .unknown), .chinese).isEmpty)
        #expect(!(LioAutosaveCopy.counts(summary, .chinese) ?? "").contains("北京"))
    }
}
