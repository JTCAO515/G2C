import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

/// #2010 (M-5): the "Based on your preferences" label on the trip canvas. The server's `rich.memory.used` rides on the
/// chat row of a plan; saving that plan keeps it (an optional field of the saved plan, so older files open as before);
/// the canvas shows one label for the whole plan when both switches are on; a tap on a memory opens "My memory" at that
/// item, or at the list when the item is gone.
@MainActor struct LioTripMemoryLabelTests {
    private static let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"

    private func folder() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("memory-label-\(UUID().uuidString)", isDirectory: true)
    }

    private static func used(_ ids: [String], total: Int? = nil) -> LioTimelineWire.MemoryUsed {
        let items = ids.map { LioTimelineWire.MemoryUsed.Item(itemID: $0, title: "标题 \($0)") }
        return LioTimelineWire.MemoryUsed.validated(items, total: total ?? ids.count)!
    }

    private static func plan(_ id: String = "trip-1", version: Int64 = 1, memory: LioTimelineWire.MemoryUsed? = nil) -> LioPlanSummary {
        var plan = LioPlanSummary(tripID: id, tripVersion: version, title: "北京三日", startDate: "2026-12-01", undated: false,
                                  days: [.init(number: 1, date: "2026-12-01", items: [
                                    .init(id: "a", label: "故宫", startTime: "09:00", endTime: nil, fixed: nil)])])
        plan.memoryUsed = memory
        return plan
    }

    private func rawRecords(_ directory: URL) throws -> [[String: Any]] {
        let data = try Data(contentsOf: directory.appendingPathComponent(LioSavedPlans.fileName))
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        return try #require(object["records"] as? [[String: Any]])
    }

    // MARK: Saved plans

    @Test func aPlanWithoutMemoriesIsWrittenExactlyAsBeforeAndReadsBackWithNone() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioSavedPlans(directory: directory, isCurrent: { true })
        try store.save(Self.plan())
        let record = try #require(try rawRecords(directory).first)
        #expect(record["memoryUsed"] == nil, "no key at all, so the file is what older builds wrote")
        #expect(Set(record.keys) == ["savedAt", "tripID", "tripVersion", "source", "startDate", "trip"])
        #expect(try store.load().first?.memoryUsed == nil)
    }

    @Test func anOlderFileWithoutTheKeyOpensAndKeepsEveryOtherFieldWhenSavedAgain() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioSavedPlans(directory: directory, isCurrent: { true })
        let rich = LioPlanSummary(tripID: "trip-rich", tripVersion: 7, source: .chat, startDate: "2026-12-01",
                                  itinerary: LioRoadbookTests.itinerary(dates: ["2026-12-01", "2026-12-02"]))
        let template = LioPlanSummary(template: LioRoadbookTemplates.beijing(.english))
        try store.save(rich, at: Date(timeIntervalSince1970: 1))
        try store.save(template, at: Date(timeIntervalSince1970: 2))
        // This is the file an older build wrote: version 2, no memory key anywhere.
        #expect(try rawRecords(directory).allSatisfy { $0["memoryUsed"] == nil })
        let older = try store.load()
        #expect(older.count == 2 && older.allSatisfy { $0.memoryUsed == nil })

        // A newer save of one trip, with memories, leaves the other trip's every field as it was.
        var withMemory = rich
        withMemory.memoryUsed = Self.used(["mem-1", "mem-2"], total: 4)
        try store.save(withMemory, at: Date(timeIntervalSince1970: 3))
        let after = try store.load()
        #expect(after.map(\.tripID) == ["trip-rich", template.tripID])
        let others = try #require(after.last)
        #expect(others == template && others.itinerary == template.itinerary && others.memoryUsed == nil)
        #expect(others.itinerary.hotels == template.itinerary.hotels && others.source == .template && others.startDate == template.startDate)
        let kept = try #require(after.first)
        #expect(kept.itinerary == rich.itinerary && kept.itinerary.days[0].legs == rich.itinerary.days[0].legs)
        #expect(kept.memoryUsed == withMemory.memoryUsed)
    }

    @Test func memoriesSurviveReopeningAndAnotherTripBeingSaved() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let memory = Self.used(["mem-1", "mem_2.x:3"], total: 7)
        try LioSavedPlans(directory: directory, isCurrent: { true }).save(Self.plan(memory: memory), at: Date(timeIntervalSince1970: 1))
        try LioSavedPlans(directory: directory, isCurrent: { true }).save(Self.plan("trip-2"), at: Date(timeIntervalSince1970: 2))
        let plans = try LioSavedPlans(directory: directory, isCurrent: { true }).load()
        #expect(plans.map(\.tripID) == ["trip-2", "trip-1"])
        #expect(plans[1].memoryUsed == memory && plans[1].memoryUsed?.total == 7 && plans[0].memoryUsed == nil)
        let raw = try #require(try rawRecords(directory).first { $0["tripID"] as? String == "trip-1" })
        #expect(raw["memoryUsed"] != nil)
    }

    @Test func aDamagedOrOutOfRuleValueCostsTheLabelAndNeverTheTrip() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioSavedPlans(directory: directory, isCurrent: { true })
        try store.save(Self.plan(memory: Self.used(["mem-1"], total: 2)))
        let url = directory.appendingPathComponent(LioSavedPlans.fileName)
        let original = try Data(contentsOf: url)
        let expected = try #require(try store.load().first)
        #expect(expected.memoryUsed?.total == 2)
        let item = #"{"itemID":"mem-1","title":"标题 mem-1"}"#
        let tooMany = (1...4).map { #"{"itemID":"m\#($0)","title":"t"}"# }.joined(separator: ",")
        let damaged = [
            #""x""#, "7", "[]", "null", #"{"items":"x","total":1}"#, #"{"items":[\#(item)]}"#,
            #"{"items":[\#(item)],"total":0}"#, #"{"items":[\#(item)],"total":100}"#,
            #"{"items":[\#(tooMany)],"total":9}"#, #"{"items":[{"itemID":"-bad","title":"t"}],"total":1}"#,
            #"{"items":[{"itemID":"ok","title":"一\n二"}],"total":1}"#, #"{"items":[],"total":1}"#,
        ]
        for value in damaged {
            var object = try #require(JSONSerialization.jsonObject(with: original) as? [String: Any])
            var records = try #require(object["records"] as? [[String: Any]])
            records[0]["memoryUsed"] = try JSONSerialization.jsonObject(with: Data(value.utf8), options: .fragmentsAllowed)
            object["records"] = records
            try JSONSerialization.data(withJSONObject: object).write(to: url)
            let plans = try store.load()
            #expect(plans.count == 1, "the trip is still there: \(value)")
            #expect(plans.first == expected && plans.first?.itinerary == expected.itinerary, "\(value)")
            #expect(plans.first?.memoryUsed == nil, "\(value)")
        }
    }

    @Test func memoriesAreNotPartOfWhatMakesTwoPlansTheSameTrip() throws {
        let with = Self.plan(memory: Self.used(["mem-1"]))
        #expect(with == Self.plan(), "display only: saved or not is decided by the trip's content")
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let model = LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true }))
        model.save(with)
        #expect(model.isSaved(Self.plan()) && model.hasSavedCopy(of: Self.plan()))
        #expect(model.plans.first?.memoryUsed == with.memoryUsed)
    }

    // MARK: Saving from the chat

    private func chatPlans(read: @escaping LioChatTripPlaces.Read) -> LioChatTripPlaces {
        LioChatTripPlaces(enabled: true, read: read, maximumRetries: 0, timeout: .seconds(5))
    }

    @Test(arguments: [true, false]) func theSaveButtonKeepsTheMemoriesWhetherOrNotThePlacesWereRead(places enabled: Bool) async throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let model = LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true }))
        let plan = Self.plan(memory: Self.used(["mem-1"], total: 3))
        let reference = LioChatTripReference(tripID: "trip-1", tripVersion: 1, contentSHA256: "0")
        let places = enabled ? chatPlans { _ in throw CancellationError() }
                             : LioChatTripPlaces(enabled: false, read: { _ in throw CancellationError() })
        let outcome = await model.save(plan, reference: reference, places: places)
        #expect(outcome != nil)
        let saved = try #require(model.plans.first)
        #expect(saved == plan && saved.memoryUsed == plan.memoryUsed)
        #expect(try LioSavedPlans(directory: directory, isCurrent: { true }).load().first?.memoryUsed == plan.memoryUsed)
    }

    // MARK: From the chat row

    private func row(memory: String?, trip: Bool = true, id: String = "m1") -> String {
        let rich = memory.map { #","rich":{"version":"LIO-answer-rich.1","memory":\#($0)}"# } ?? ""
        let tripJSON = trip ? #","trip":{"trip_id":"trip-1","title":"北京三日","days":[]}"# : ""
        return #"{"message_id":"\#(id)","text":"Q","answer":"为你排了北京三日。","status":"completed","sources":[]\#(tripJSON)\#(rich)}"#
    }

    private func conversation(_ rows: [String], richEnabled: Bool = true) async throws -> LioConversation {
        let data = Data(#"{"version":"LIO-timeline.2","conversation_id":"\#(Self.conversation)","messages":[\#(rows.joined(separator: ","))],"next_before":null}"#.utf8)
        let wire = try LioTimelineWire.decodePage(data, for: Self.conversation, version: .v2)
        let page = LioTimelinePage(turns: wire.messages.map { LioTimelineTurn($0, richEnabled: richEnabled) },
                                   nextBefore: nil, conversationID: wire.conversationID)
        let model = LioConversation(service: LioService(updates: { _ in AsyncStream { $0.yield(.snapshot(page)); $0.finish() } },
                                                         events: { _ in AsyncStream { $0.finish() } }))
        await model.refreshTimeline()
        return model
    }

    private let twoUsed = #"{"used":[{"item_id":"mem-1","title":"不吃辣"},{"item_id":"mem-2","title":"慢节奏"}],"used_total":3}"#

    @Test func theRowsMemoriesReachTheTurnOnlyWhenRichIsOn() async throws {
        let on = try await conversation([row(memory: twoUsed)])
        #expect(on.turns.first?.memoryUsed?.items.map(\.title) == ["不吃辣", "慢节奏"] && on.turns.first?.memoryUsed?.total == 3)
        let off = try await conversation([row(memory: twoUsed)], richEnabled: false)
        #expect(off.turns.first?.memoryUsed == nil)
        let none = try await conversation([row(memory: nil)])
        #expect(none.turns.first?.memoryUsed == nil)
    }

    @Test func aPlanSavedFromThisChatCarriesTheMemoriesOfItsOwnRow() async throws {
        let chat = try await conversation([row(memory: twoUsed)])
        let carried = chat.carryingMemoryUsed(Self.plan(), enabled: true)
        #expect(carried.memoryUsed?.items.map(\.itemID) == ["mem-1", "mem-2"] && carried.memoryUsed?.total == 3)
        #expect(carried == Self.plan(), "nothing else about the plan changes")
    }

    @Test func switchedOffOrWithoutAMatchingRowThePlanIsReturnedAsItIs() async throws {
        let chat = try await conversation([row(memory: twoUsed)])
        #expect(chat.carryingMemoryUsed(Self.plan(), enabled: false).memoryUsed == nil, "switch off: nothing is stored")
        #expect(chat.carryingMemoryUsed(Self.plan("other-trip"), enabled: true).memoryUsed == nil, "another trip's row is not this plan's")
        let withoutMemory = try await conversation([row(memory: nil)])
        #expect(withoutMemory.carryingMemoryUsed(Self.plan(), enabled: true).memoryUsed == nil)
        let own = Self.plan(memory: Self.used(["old-1"]))
        #expect(withoutMemory.carryingMemoryUsed(own, enabled: true).memoryUsed == own.memoryUsed,
                "a plan opened from Trips keeps what it was saved with")
        let newer = chat.carryingMemoryUsed(own, enabled: true)
        #expect(newer.memoryUsed?.items.map(\.itemID) == ["mem-1", "mem-2"], "this chat's row says more recently")
    }

    // MARK: The label

    @Test func theLabelNeedsBothSwitchesAndSomeMemories() {
        let plan = Self.plan(memory: Self.used(["mem-1", "mem-2"]))
        #expect(LioTripMemoryLabel.make(for: plan, labelEnabled: true, canvasEnabled: true) != nil)
        #expect(LioTripMemoryLabel.make(for: plan, labelEnabled: false, canvasEnabled: true) == nil)
        #expect(LioTripMemoryLabel.make(for: plan, labelEnabled: true, canvasEnabled: false) == nil)
        #expect(LioTripMemoryLabel.make(for: plan, labelEnabled: false, canvasEnabled: false) == nil)
        #expect(LioTripMemoryLabel.make(for: Self.plan(), labelEnabled: true, canvasEnabled: true) == nil, "no memories, no label")
        #expect(LioTripMemoryLabel.make(for: nil, labelEnabled: true, canvasEnabled: true) == nil, "a canvas with no plan has none")
    }

    @Test func theLabelListsAtMostThreeAndSaysHowManyMoreWereUsed() throws {
        let three = try #require(LioTripMemoryLabel.make(for: Self.plan(memory: Self.used(["a", "b", "c"], total: 3)),
                                                         labelEnabled: true, canvasEnabled: true))
        #expect(three.entries.map(\.itemID) == ["a", "b", "c"] && three.more == 0)
        #expect(three.moreText(.english) == nil && three.moreText(.chinese) == nil)
        let more = try #require(LioTripMemoryLabel.make(for: Self.plan(memory: Self.used(["a", "b"], total: 5)),
                                                        labelEnabled: true, canvasEnabled: true))
        #expect(more.entries.count == 2 && more.more == 3)
        #expect(more.moreText(.english) == "and 3 more" && more.moreText(.chinese) == "等 5 条")
        #expect(more.title(.english) == "Based on your preferences" && more.title(.chinese) == "按你的偏好")
        #expect(more.intro(.english) == "Based on what you asked me to remember:")
        #expect(more.accessibilityValue(expanded: true, .english) == "Expanded" && more.accessibilityValue(expanded: false, .chinese) == "已收起")
    }

    // MARK: Opening a memory

    @Test func aTapOpensTheItemWhenItIsStillThereAndTheListWhenItIsNot() {
        #expect(LioMemoryOpening.target(itemID: "mem-1", loaded: ["mem-0", "mem-1"]) == .item("mem-1"))
        #expect(LioMemoryOpening.target(itemID: "mem-1", loaded: ["mem-0"]) == .list, "stopped or deleted since the plan was saved")
        #expect(LioMemoryOpening.target(itemID: "mem-1", loaded: []) == .list)
        #expect(LioMemoryOpening.target(itemID: "mem-1", loaded: nil) == .list, "not read yet")
        #expect(LioMemoryOpening.target(itemID: nil, loaded: ["mem-1"]) == .list)
        #expect(LioMemoryOpening.target(itemID: "-bad", loaded: ["-bad"]) == .list, "not an item id of the contract's form")
    }

    @Test func theRouterOpensMeAtTheNamedItemOrTheList() {
        let router = LioRouter(tab: .trips, toolsShown: true)
        #expect(router.memoryRequest == nil)
        router.openMemory(itemID: "mem-1")
        #expect(router.tab == .me && router.memoryRequest?.itemID == "mem-1")
        let first = router.memoryRequest
        router.tab = .trips
        router.openMemory(itemID: "mem-1")
        #expect(router.memoryRequest != first, "asking again is a new request, so the page opens again")
        router.openMemory(itemID: "not an id!")
        #expect(router.tab == .me && router.memoryRequest?.itemID == nil, "the list")
        router.openMemory()
        #expect(router.memoryRequest?.itemID == nil)
        #expect(router.toolsPath.isEmpty, "the Tools tab is untouched")
    }

    // MARK: The switch

    @Test func theSwitchIsOffByDefaultAndListedButNotOnInTheRelease() throws {
        #expect(LioTripMemoryLabelFeature.infoKey == "G2CTripMemoryLabelEnabled")
        #expect(LioTripMemoryLabelFeature.enabled(infoValue: "YES"))
        for value: Any? in [nil, "", "NO", "yes", "1", true, 1, "$(G2C_TRIP_MEMORY_LABEL_ENABLED)"] {
            #expect(!LioTripMemoryLabelFeature.enabled(infoValue: value), "\(String(describing: value))")
        }
        #expect(!LioTripMemoryLabelFeature.enabledInBuild, "the test bundle sets no flag")
        var ios = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { ios.deleteLastPathComponent() }
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        #expect(plist.contains("<key>G2CTripMemoryLabelEnabled</key><string>$(G2C_TRIP_MEMORY_LABEL_ENABLED)</string>"))
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(!project.contains("G2C_TRIP_MEMORY_LABEL_ENABLED"), "the setting stays unset in the project")
        let manifestURL = ios.deletingLastPathComponent().appendingPathComponent("tooling/release/app_flags.json")
        let manifest = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any])
        let flags = try #require(manifest["flags"] as? [[String: String]])
        #expect(flags.contains(["setting": "G2C_TRIP_MEMORY_LABEL_ENABLED", "plist": "G2CTripMemoryLabelEnabled"]))
        let release = try #require(manifest["release"] as? [String: Any])
        #expect(!(try #require(release["on"] as? [String])).contains("G2C_TRIP_MEMORY_LABEL_ENABLED"))
    }
}
