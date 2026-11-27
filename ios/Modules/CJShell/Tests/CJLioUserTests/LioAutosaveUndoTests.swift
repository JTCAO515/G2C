import Foundation
import Testing
@testable import CJLioUser
@testable import CJMessageHTTP

/// #1994 (58.1 T-1, App): the Undo button on the receipt of an automatic save, behind `G2CAutosaveUndoEnabled` (and only
/// with `G2CAnswerRichEnabled`). The server decides every outcome; these tests use the contract's shapes and a fake transport.
@MainActor
struct LioAutosaveUndoTests {
    typealias Receipt = LioTimelineWire.TripReceipt
    typealias Phase = LioAutosaveUndo.Phase

    private let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"
    private let until = "2026-11-28T03:04:05.678+00:00"
    private var deadline: Date { LioAutosaveUndo.deadline(of: receipt())! }

    // MARK: The switch

    @Test func flagIsOffUnlessTheBuildSaysYes() {
        #expect(LioAutosaveUndoFeature.infoKey == "G2CAutosaveUndoEnabled")
        #expect(!LioAutosaveUndoFeature.enabled(infoValue: nil))
        #expect(!LioAutosaveUndoFeature.enabled(infoValue: "NO"))
        #expect(!LioAutosaveUndoFeature.enabled(infoValue: "yes"))
        #expect(!LioAutosaveUndoFeature.enabled(infoValue: true))
        #expect(!LioAutosaveUndoFeature.enabled(infoValue: "$(G2C_AUTOSAVE_UNDO_ENABLED)"))
        #expect(LioAutosaveUndoFeature.enabled(infoValue: "YES"))
        #expect(!LioAutosaveUndoFeature.enabledInBuild, "the test bundle sets no flag")
        #expect(!LioAutosaveUndoFeature.activeInBuild)
    }

    @Test func theWholeFeatureNeedsRichAnswersToo() {
        #expect(LioAutosaveUndoFeature.active(undo: true, rich: true))
        #expect(!LioAutosaveUndoFeature.active(undo: true, rich: false))
        #expect(!LioAutosaveUndoFeature.active(undo: false, rich: true))
        #expect(!LioAutosaveUndoFeature.active(undo: false, rich: false))
    }

    @Test func infoPlistReadsTheFlagFromABuildSettingThatNoConfigurationSets() throws {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(plist.contains("<key>G2CAutosaveUndoEnabled</key><string>$(G2C_AUTOSAVE_UNDO_ENABLED)</string>"))
        #expect(!project.contains("G2C_AUTOSAVE_UNDO_ENABLED"), "off unless the release script passes it")
    }

    @Test func flagIsListedAndNotOnInTheRelease() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let manifestURL = root.appendingPathComponent("tooling/release/app_flags.json")
        let manifest = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any])
        let flags = try #require(manifest["flags"] as? [[String: String]])
        #expect(flags.contains(["setting": "G2C_AUTOSAVE_UNDO_ENABLED", "plist": "G2CAutosaveUndoEnabled"]))
        let release = try #require(manifest["release"] as? [String: Any])
        #expect(!(try #require(release["on"] as? [String])).contains("G2C_AUTOSAVE_UNDO_ENABLED"))
    }

    // MARK: What reaches a turn

    private func message(_ receipt: Receipt?) -> LioTimelineWire.Message {
        LioTimelineWire.Message(id: "m1", question: "Q", answer: "A", state: .completed, activity: nil, sources: [],
                                trip: nil, memoryTags: [], rich: receipt.map { .init(tripReceipt: $0) })
    }

    @Test func theReceiptIsReadWithTheNoticeOrTheUndoAndAlwaysNeedsRich() {
        let value = receipt()
        func read(rich: Bool, notice: Bool, undo: Bool) -> Receipt? {
            LioTimelineTurn(message(value), richEnabled: rich, autosaveNoticeEnabled: notice, autosaveUndoEnabled: undo).tripReceipt
        }
        #expect(read(rich: true, notice: false, undo: true) == value, "the undo alone reads it")
        #expect(read(rich: true, notice: true, undo: false) == value, "the notice alone reads it, as before")
        #expect(read(rich: true, notice: true, undo: true) == value)
        #expect(read(rich: true, notice: false, undo: false) == nil)
        #expect(read(rich: false, notice: true, undo: true) == nil, "no rich, no receipt")
        #expect(read(rich: false, notice: false, undo: false) == nil)
    }

    // MARK: The button

    private func receipt(state: Receipt.Undo.State = .available, withdraw: Bool = false, saveID: String = "lio-plan-run-5c1f",
                         until: String? = nil) -> Receipt {
        let hashA = String(repeating: "a", count: 64), hashB = String(repeating: "b", count: 64)
        let version = withdraw ? 1 : 7
        let undo: Receipt.Undo = state == .available
            ? .init(state: .available, kind: withdraw ? .withdrawCreated : .restore,
                    actionID: LioTimelineWire.undoActionID(forSave: saveID), until: until ?? self.until,
                    target: .init(tripID: "trip-9a1b", expectedVersion: version, originalHash: hashA, contentVersion: "structured.4",
                                  restore: withdraw ? nil : .init(version: 6, hash: hashB, contentVersion: "structured.4")))
            : .init(state: state, until: state == .unavailable ? nil : until ?? self.until)
        return Receipt(status: .saved, actionID: saveID, tripID: "trip-9a1b", committedVersion: version,
                       summary: .init(days: [.init(day: 1, added: 3)]), undo: undo)
    }

    private func model(send: [LioTripUndoWire.Reply?] = [], read: [LioTripUndoWire.Reply?] = []) -> (LioAutosaveUndo, Script) {
        let script = Script(send: send, read: read)
        let client = LioTripUndoClient(send: { try script.sent($0) }, read: { try script.asked($0) })
        return (LioAutosaveUndo(client: client, pause: { _ in }), script)
    }

    @Test func theButtonShowsOnlyForAnAvailableUndoWhoseTimeIsNotOver() {
        let (undo, _) = model()
        let before = deadline.addingTimeInterval(-3600), after = deadline.addingTimeInterval(1)
        #expect(undo.offers(receipt(), at: before))
        #expect(undo.offers(receipt(withdraw: true), at: before))
        #expect(!undo.offers(receipt(), at: after), "available when read, but the time is over on this device")
        #expect(!undo.offers(receipt(), at: deadline), "at the deadline it is over")
        for state in [Receipt.Undo.State.expired, .superseded, .undone, .unavailable] {
            #expect(!undo.offers(receipt(state: state), at: before), "\(state)")
        }
        #expect(!undo.offers(Receipt(status: .notSaved, actionID: "a", reason: .conflict), at: before))
        #expect(!undo.offers(Receipt(status: .unknown, actionID: "a"), at: before))
        // A receipt that says available without a target never offers anything.
        let id = LioTimelineWire.undoActionID(forSave: "lio-plan-run-5c1f")
        let bare = Receipt(status: .saved, actionID: "lio-plan-run-5c1f", tripID: "t", committedVersion: 7,
                           undo: .init(state: .available, kind: .restore, actionID: id, until: until))
        #expect(!undo.offers(bare, at: before))
    }

    // MARK: The undo

    @Test func aTapSendsOneRequestAndOnSuccessRefreshesWhatTheServerSays() async throws {
        let (undo, script) = model(send: [.committed])
        let value = receipt()
        var refreshed = 0
        await undo.undo(value, conversationID: conversation, at: deadline.addingTimeInterval(-60)) { refreshed += 1 }
        #expect(script.posts.count == 1 && script.gets.isEmpty)
        let post = try #require(script.posts.first)
        #expect(post.version == "LIO-trip-undo.4" && post.conversationID == conversation && post.actionID == value.undo?.actionID)
        #expect(undo.phase(of: value) == .undone)
        #expect(refreshed == 1)
        #expect(!undo.offers(value, at: deadline.addingTimeInterval(-60)), "the button is gone once it is undone")
        #expect(LioAutosaveCopy.details(value, .chinese, phase: .undone).last == "已撤销")
    }

    @Test func aFirstSaveIsWithdrawnAndTheLineSaysSo() async throws {
        let (undo, script) = model(send: [.committed])
        let value = receipt(withdraw: true)
        await undo.undo(value, conversationID: conversation, at: deadline.addingTimeInterval(-60)) {}
        #expect(script.posts.map(\.version) == ["LIO-trip-undo.5"])
        #expect(undo.phase(of: value) == .undone)
        #expect(LioAutosaveCopy.details(value, .chinese, phase: .undone).last == "已撤回")
        #expect(LioAutosaveCopy.details(value, .english, phase: .undone).last == "Withdrawn")
    }

    @Test(arguments: [(LioTripUndoWire.Reply.changed, Phase.superseded), (.refused, .expired)])
    func aRefusalIsShownAndTheServersReadingIsFetched(reply: LioTripUndoWire.Reply, phase: Phase) async {
        let (undo, script) = model(send: [reply])
        let value = receipt()
        var refreshed = 0
        await undo.undo(value, conversationID: conversation, at: deadline.addingTimeInterval(-60)) { refreshed += 1 }
        #expect(undo.phase(of: value) == phase)
        #expect(script.posts.count == 1 && script.gets.isEmpty)
        #expect(refreshed == 1, "the timeline says what the server computed")
        #expect(!undo.offers(value, at: deadline.addingTimeInterval(-60)), "no button for what cannot be undone")
    }

    @Test func nothingWrittenIsAFailureThatCanBeTriedAgainWithTheSameAction() async throws {
        let (undo, script) = model(send: [.notCommitted, .committed])
        let value = receipt()
        let now = deadline.addingTimeInterval(-60)
        var refreshed = 0
        await undo.undo(value, conversationID: conversation, at: now) { refreshed += 1 }
        #expect(undo.phase(of: value) == .failed && refreshed == 0)
        #expect(undo.offers(value, at: now), "the button stays, as Try again")
        #expect(LioAutosaveCopy.details(value, .chinese, phase: .failed).last == "这次没能撤销。")
        await undo.undo(value, conversationID: conversation, at: now) { refreshed += 1 }
        #expect(undo.phase(of: value) == .undone && refreshed == 1)
        #expect(script.posts.map(\.actionID) == [value.undo!.actionID, value.undo!.actionID], "never a new id")
        #expect(script.posts.map(\.body)[0] == script.posts.map(\.body)[1])
    }

    @Test func anAnswerThatIsNotKnownIsConfirmedWithoutASecondWrite() async {
        let (undo, script) = model(send: [nil], read: [nil, .committed])
        let value = receipt()
        var refreshed = 0
        await undo.undo(value, conversationID: conversation, at: deadline.addingTimeInterval(-60)) { refreshed += 1 }
        #expect(script.posts.count == 1 && script.gets.count == 2, "one POST, then the receipt query until it answers")
        #expect(undo.phase(of: value) == .undone && refreshed == 1)
        #expect(script.gets.allSatisfy { $0.actionID == value.undo?.actionID })
    }

    @Test func ifNothingCanBeLearnedItEndsAsAFailureTheTravellerCanRetry() async {
        let (undo, script) = model(send: [nil], read: [])
        let value = receipt()
        var refreshed = 0
        await undo.undo(value, conversationID: conversation, at: deadline.addingTimeInterval(-60)) { refreshed += 1 }
        #expect(script.posts.count == 1 && script.gets.count == LioAutosaveUndo.confirmDelays.count + 1)
        #expect(undo.phase(of: value) == .failed && refreshed == 0)
        #expect(undo.offers(value, at: deadline.addingTimeInterval(-60)))
    }

    @Test func whileItIsBeingConfirmedTheLineSaysSoAndThereIsNoButton() async {
        let gate = Gate()
        let script = Script(send: [nil], read: [nil, .committed])
        let client = LioTripUndoClient(send: { try script.sent($0) }, read: { try script.asked($0) })
        let undo = LioAutosaveUndo(client: client, pause: { _ in await gate.wait() })
        let value = receipt()
        let now = deadline.addingTimeInterval(-60)
        let task = Task { await undo.undo(value, conversationID: conversation, at: now) {} }
        for _ in 0..<100 where undo.phase(of: value) != .confirming { await Task.yield() }
        #expect(undo.phase(of: value) == .confirming)
        #expect(!undo.offers(value, at: now))
        #expect(LioAutosaveCopy.details(value, .chinese, phase: .confirming).last == "正在确认是否已撤销…")
        #expect(LioAutosaveCopy.details(value, .chinese, phase: .undoing).last == "正在撤销…")
        await gate.open()
        await task.value
        #expect(undo.phase(of: value) == .undone)
    }

    @Test func aSecondTapWhileTheFirstIsRunningSendsNothing() async {
        let gate = Gate()
        let script = Script(send: [.committed], read: [])
        let client = LioTripUndoClient(send: { request in await gate.wait(); return try script.sent(request) },
                                       read: { try script.asked($0) })
        let undo = LioAutosaveUndo(client: client, pause: { _ in })
        let value = receipt()
        let now = deadline.addingTimeInterval(-60)
        let first = Task { await undo.undo(value, conversationID: conversation, at: now) {} }
        for _ in 0..<100 where undo.phase(of: value) != .undoing { await Task.yield() }
        #expect(undo.phase(of: value) == .undoing && !undo.offers(value, at: now))
        await undo.undo(value, conversationID: conversation, at: now) { Issue.record("the second tap must not refresh") }
        await undo.undo(value, conversationID: conversation, at: now) { Issue.record("nor the third") }
        await gate.open()
        await first.value
        #expect(script.posts.count == 1, "one request for any number of taps")
        #expect(undo.phase(of: value) == .undone)
    }

    @Test func nothingIsSentWhenTheButtonWouldNotShow() async {
        let now = deadline.addingTimeInterval(-60)
        for (value, at, id) in [(receipt(), deadline.addingTimeInterval(60), conversation as String?), (receipt(state: .expired), now, conversation),
                                (receipt(state: .superseded), now, conversation), (receipt(state: .undone), now, conversation),
                                (receipt(state: .unavailable), now, conversation), (receipt(), now, nil), (receipt(), now, "x")] {
            let (undo, script) = model(send: [.committed])
            await undo.undo(value, conversationID: id, at: at) { Issue.record("refresh") }
            #expect(script.posts.isEmpty && script.gets.isEmpty && undo.phase(of: value) == nil)
        }
    }

    // MARK: Words

    @Test func theServersReadingWinsOverWhatThisDeviceKnows() {
        func note(_ receipt: Receipt, _ phase: Phase?) -> String? { LioAutosaveCopy.undoNote(receipt, phase: phase, .chinese) }
        #expect(note(receipt(), nil) == nil, "available and nothing happened: only the button")
        #expect(note(receipt(), .undone) == "已撤销", "committed, the reading not here yet")
        #expect(note(receipt(), .superseded) == "行程有新改动，无法撤销这次。")
        #expect(note(receipt(), .expired) == "这次改动已超过撤销时间。")
        #expect(note(receipt(state: .expired), .failed) == "这次改动已超过撤销时间。")
        #expect(note(receipt(state: .superseded), .undoing) == "行程有新改动，无法撤销这次。")
        #expect(note(receipt(state: .undone), nil) == "已撤销")
        #expect(note(receipt(state: .unavailable), .undone) == nil)
        #expect(LioAutosaveCopy.undoButton(.chinese) == "撤销" && LioAutosaveCopy.undoButton(.english) == "Undo")
        #expect(LioAutosaveCopy.retryButton(.chinese) == "重试")
    }

    @Test func theTimeLeftIsToTheHourAndHoldsNoPlaceName() {
        let end = deadline
        #expect(LioAutosaveCopy.timeLeft(until: end, now: end.addingTimeInterval(-23.5 * 3600), .chinese) == "还可撤销约 24 小时")
        #expect(LioAutosaveCopy.timeLeft(until: end, now: end.addingTimeInterval(-3 * 3600), .chinese) == "还可撤销约 3 小时")
        #expect(LioAutosaveCopy.timeLeft(until: end, now: end.addingTimeInterval(-600), .chinese) == "还可撤销不到 1 小时")
        #expect(LioAutosaveCopy.timeLeft(until: end, now: end.addingTimeInterval(-3 * 3600), .english) == "Undo for 3 more hours")
    }

    @Test func theDeadlineIsParsedFromTheServersTimestamp() {
        #expect(LioAutosaveUndo.deadline(of: receipt())?.timeIntervalSince1970 == 1_795_835_045.678)
        #expect(LioAutosaveUndo.deadline(of: receipt(state: .unavailable)) == nil)
        #expect(LioAutosaveUndo.deadline(of: Receipt(status: .unknown, actionID: "a")) == nil)
    }

    // MARK: Fakes

    @MainActor private final class Script {
        var send: [LioTripUndoWire.Reply?]
        var read: [LioTripUndoWire.Reply?]
        private(set) var posts: [LioTripUndoWire.Request] = []
        private(set) var gets: [LioTripUndoWire.Request] = []
        init(send: [LioTripUndoWire.Reply?], read: [LioTripUndoWire.Reply?]) { self.send = send; self.read = read }
        func sent(_ request: LioTripUndoWire.Request) throws -> LioTripUndoWire.Reply {
            posts.append(request)
            guard !send.isEmpty, let reply = send.removeFirst() else { throw URLError(.networkConnectionLost) }
            return reply
        }
        func asked(_ request: LioTripUndoWire.Request) throws -> LioTripUndoWire.Reply {
            gets.append(request)
            guard !read.isEmpty, let reply = read.removeFirst() else { throw URLError(.notConnectedToInternet) }
            return reply
        }
    }

    private actor Gate {
        private var opened = false
        private var waiting: [CheckedContinuation<Void, Never>] = []
        func wait() async { if opened { return }; await withCheckedContinuation { waiting.append($0) } }
        func open() { opened = true; waiting.forEach { $0.resume() }; waiting = [] }
    }
}
