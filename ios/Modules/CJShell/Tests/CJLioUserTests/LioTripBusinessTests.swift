import Foundation
import Testing
@testable import CJLioUser

/// #1765 (W8-2): business items on the trip home, behind `G2CTripBusinessEnabled`. Facts come only from the bundled
/// copies of the business entries and the scene pack's flows, which must match their sources in the repository.
struct LioTripBusinessTests {
    private static let shanghai = TimeZone(identifier: "Asia/Shanghai")!
    private static let losAngeles = TimeZone(identifier: "America/Los_Angeles")!

    /// The repository root, from this file's place in it.
    private static let root: URL = {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { url.deleteLastPathComponent() }
        return url
    }()

    private static let resources = root.appendingPathComponent("ios/Modules/CJShell/Sources/CJLioUser/Resources")

    private static func at(_ text: String, _ timeZone: TimeZone = shanghai) -> Date {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = timeZone
        formatter.dateFormat = "yyyy-MM-dd HH:mm"
        return formatter.date(from: text)!
    }

    private static func profile(purpose: LioTripPurpose?, city: String? = "guangzhou") -> LioTripProfile {
        LioTripProfile(arrival: LioTripDay("2026-12-08"), stayDays: 5, cityID: city, purpose: purpose,
                       startedAt: at("2026-11-27 09:00"))
    }

    private static func guide() throws -> LioTripBusinessGuide {
        try #require(LioTripBusinessGuide.bundled(), "the bundled business files must read")
    }

    private static let allTools: Set<LioTool> = [.taxi, .translation, .showCards, .payment, .returnHotel]

    private static func input(_ profile: LioTripProfile?, business: LioTripBusinessGuide?, now: Date = at("2026-11-28 10:00"),
                              timeZone: TimeZone = shanghai, routable: Set<LioTool> = allTools) -> LioTripChecklistInput {
        var input = LioTripChecklistInput(now: now, timeZone: timeZone, profile: profile,
                                          entry: .visaFree(maxDays: 30, checkedOn: "2026-11-25"),
                                          arrivalChecklist: .init(done: [], total: 6), hotelSaved: false, showCards: true,
                                          attractionBooking: true)
        input.business = business
        input.routableTools = routable
        return input
    }

    private static func business(_ list: LioTripChecklist) -> [LioTripBusinessTask] {
        list.tasks.compactMap { task in
            if case .business(let business) = task.kind { return business }
            return nil
        }
    }

    private static func task(_ item: LioTripBusinessTask.Item, _ list: LioTripChecklist) throws -> LioTripBusinessTask {
        try #require(business(list).first { $0.item == item })
    }

    // MARK: - Switch

    @Test func theSwitchIsOffUnlessTheBuildSaysYes() throws {
        #expect(LioTripBusinessFeature.infoKey == "G2CTripBusinessEnabled")
        #expect(!LioTripBusinessFeature.enabled(infoValue: nil))
        #expect(!LioTripBusinessFeature.enabled(infoValue: "NO"))
        #expect(!LioTripBusinessFeature.enabled(infoValue: true))
        #expect(LioTripBusinessFeature.enabled(infoValue: "YES"))
        #expect(!LioTripBusinessFeature.enabledInBuild, "the test bundle sets no flag")
        let plist = try String(contentsOf: Self.root.appendingPathComponent("ios/App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: Self.root.appendingPathComponent("ios/CJProbeApp.xcodeproj/project.pbxproj"),
                                 encoding: .utf8)
        #expect(plist.contains("<key>G2CTripBusinessEnabled</key><string>$(G2C_TRIP_BUSINESS_ENABLED)</string>"))
        #expect(!project.contains("G2C_TRIP_BUSINESS_ENABLED"), "off unless the release script passes it")
        let flags = try String(contentsOf: Self.root.appendingPathComponent("tooling/release/app_flags.json"), encoding: .utf8)
        let release = try #require(flags.components(separatedBy: "\"release\"").last)
        #expect(flags.contains("\"G2C_TRIP_BUSINESS_ENABLED\""))
        #expect(!release.contains("G2C_TRIP_BUSINESS_ENABLED"), "not in release.on: JT decides")
    }

    // MARK: - Copies match their sources

    @Test func theBundledEntriesAreAByteForByteCopyOfTheKnowledgeFile() throws {
        let sourceURL = Self.root.appendingPathComponent("knowledge/business/guangzhou.v1.json")
        try #require(FileManager.default.fileExists(atPath: sourceURL.path),
                     "knowledge/business/guangzhou.v1.json is missing; this test reads the repository checkout")
        let source = try Data(contentsOf: sourceURL)
        let copy = try Data(contentsOf: Self.resources.appendingPathComponent("LioBusinessGuangzhou.v1.json"))
        #expect(copy == source, "copy knowledge/business/guangzhou.v1.json over Resources/LioBusinessGuangzhou.v1.json")
        let bundled = try #require(Bundle.module.url(forResource: "LioBusinessGuangzhou.v1", withExtension: "json"))
        #expect(try Data(contentsOf: bundled) == source, "the App bundles the file as it is")
    }

    @Test func theBundledFlowsAreTheScenePacksFlows() throws {
        let sourceURL = Self.root.appendingPathComponent("backend/cj_api/scene_packs/business.json")
        try #require(FileManager.default.fileExists(atPath: sourceURL.path),
                     "backend/cj_api/scene_packs/business.json is missing; this test reads the repository checkout")
        let source = try #require(try JSONSerialization.jsonObject(with: Data(contentsOf: sourceURL)) as? [String: Any])
        let copyData = try Data(contentsOf: Self.resources.appendingPathComponent("LioBusinessFlows.v1.json"))
        let copy = try #require(try JSONSerialization.jsonObject(with: copyData) as? [String: Any])
        #expect(Set(copy.keys) == ["scene_pack", "flows"])
        #expect(copy["scene_pack"] as? String == source["scene_pack"] as? String)
        let sourceFlows = try #require(source["flows"] as? NSArray)
        let copyFlows = try #require(copy["flows"] as? NSArray)
        #expect(copyFlows == sourceFlows, "copy the scene pack's flows into Resources/LioBusinessFlows.v1.json")
        // The items read steps 3 and 5 by position; a reordered pack must be looked at, not silently reused.
        let guide = try Self.guide()
        #expect(guide.step(3)?.en.contains("phrase") == true && guide.step(3)?.en.contains("translation") == true)
        #expect(guide.step(5)?.en.contains("taxi") == true)
    }

    @Test func aCatalogueWithoutOfficialHTTPSPagesIsRejected() throws {
        let raw = try String(contentsOf: Self.resources.appendingPathComponent("LioBusinessGuangzhou.v1.json"), encoding: .utf8)
        #expect(throws: (any Error).self) {
            try LioBusinessCatalogue.decode(Data(raw.replacingOccurrences(of: "https://gaj.gz.gov.cn", with: "http://gaj.gz.gov.cn").utf8))
        }
        #expect(throws: (any Error).self) {
            try LioBusinessCatalogue.decode(Data(raw.replacingOccurrences(of: "\"city\"", with: "\"city\": \"x\", \"city\"").utf8))
        }
        #expect(try LioBusinessCatalogue.decode(Data(raw.utf8)).entries.count == 3)
    }

    // MARK: - When business items appear

    @Test func businessItemsAppearOnlyForABusinessTripWithTheSwitchOn() throws {
        let guide = try Self.guide()
        let leisureOff = LioTripChecklist(Self.input(Self.profile(purpose: nil), business: nil))
        let leisureOn = LioTripChecklist(Self.input(Self.profile(purpose: nil), business: guide))
        let chosenLeisure = LioTripChecklist(Self.input(Self.profile(purpose: .leisure), business: guide))
        let businessOff = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: nil))
        let businessOn = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: guide))
        // A leisure trip's list is exactly the list without the switch.
        #expect(leisureOn == leisureOff)
        #expect(chosenLeisure == leisureOff)
        #expect(businessOff == leisureOff, "with the switch off a business choice changes nothing")
        #expect(Self.business(leisureOff).isEmpty)
        #expect(Self.business(businessOn).map(\.item) == [.registration, .visa, .phrases, .cards, .venue, .meeting])
        // The leisure tasks are all still there, in the same order.
        #expect(businessOn.tasks.filter { if case .business = $0.kind { false } else { true } } == leisureOff.tasks)
        #expect(businessOn.tasks.first { $0.key == "business.meeting" }?.stage == .inChina)
        #expect(businessOn.tasks.first { $0.key == "business.registration" }?.stage == .beforeTrip)
    }

    @Test func guangzhouEntriesAreLeftOutForAnotherFirstCity() throws {
        let list = LioTripChecklist(Self.input(Self.profile(purpose: .business, city: "beijing"), business: try Self.guide()))
        #expect(Self.business(list).map(\.item) == [.phrases, .cards, .meeting])
        let undecided = LioTripChecklist(Self.input(Self.profile(purpose: .business, city: nil), business: try Self.guide()))
        #expect(Self.business(undecided).count == 6)
    }

    // MARK: - Sources, review days and what "Go" does

    @Test func everySourcedItemCarriesItsCheckDayAndOfficialPages() throws {
        let guide = try Self.guide()
        let list = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: guide))
        let topics: [LioTripBusinessTask.Item: String] = [.registration: "trade_fair_registration", .visa: "visa_channel",
                                                          .venue: "venue_transport"]
        for (item, topic) in topics {
            let entry = try #require(guide.catalogue.entry(topic: topic))
            let task = try Self.task(item, list)
            let source = try #require(task.source)
            #expect(source.urls == entry.sourceURLs && !source.urls.isEmpty)
            #expect(source.urls.allSatisfy { $0.scheme == "https" })
            #expect(source.checkedOn == entry.checkedOn && !source.officialOnly)
            #expect(task.text == entry.text, "the entry's own words, not new ones")
            #expect(LioTripHomeCopy.businessSource(source, .chinese).contains("核对于 11月26日"))
            #expect(LioTripHomeCopy.detail(LioTripTask(key: item.key, stage: .beforeTrip, kind: .business(task),
                                                       done: .open, tick: .manual), .english) == entry.textEN)
        }
        // Items without an entry say what the tool does and state no facts.
        for item in [LioTripBusinessTask.Item.phrases, .cards, .meeting] {
            #expect(try Self.task(item, list).source == nil && Self.task(item, list).text == nil)
        }
    }

    @Test func fromItsReviewDayAnEntryOnlySaysGoByTheOfficialNotice() throws {
        let guide = try Self.guide()
        // 9 Dec 23:59 in Beijing: still within review. 10 Dec 00:00 Beijing: registration and venue are due.
        let before = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: guide, now: Self.at("2026-12-09 23:59")))
        #expect(try Self.task(.registration, before).source?.officialOnly == false)
        let due = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: guide, now: Self.at("2026-12-10 00:00")))
        for item in [LioTripBusinessTask.Item.registration, .venue] {
            let task = try Self.task(item, due)
            #expect(task.source?.officialOnly == true)
            #expect(task.text == nil, "no facts once it is due for review")
            #expect(task.source?.urls.isEmpty == false, "the official pages stay")
            let words = LioTripHomeCopy.businessDetail(task, .chinese)
            #expect(words.contains("以官方最新通知为准"))
        }
        #expect(try Self.task(.visa, due).source?.officialOnly == false, "the visa entry is reviewed by 26 Dec")
        // The day is Beijing's, from the checklist's own clock: 9 Dec 08:00 in Los Angeles is already 10 Dec in Beijing.
        let losAngeles = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: guide,
                                                     now: Self.at("2026-12-09 08:00", Self.losAngeles), timeZone: Self.losAngeles))
        #expect(try Self.task(.registration, losAngeles).source?.officialOnly == true)
        let visaDue = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: guide, now: Self.at("2026-12-26 09:00")))
        #expect(try Self.task(.visa, visaDue).text == nil)
    }

    @Test func registrationOpensTheOrganizersOwnPage() throws {
        let guide = try Self.guide()
        let list = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: guide))
        let entry = try #require(guide.catalogue.entry(topic: "trade_fair_registration"))
        guard case .officialPage(let url) = try Self.task(.registration, list).action else {
            Issue.record("pre-registration opens the official page")
            return
        }
        #expect(url == entry.sourceURLs.first && url.scheme == "https" && url.host == "www.cantonfair.org.cn")
    }

    @Test @MainActor func meetingOpensShowCardsAtTheBusinessSection() throws {
        let list = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: try Self.guide()))
        guard case .route(let route) = try Self.task(.meeting, list).action else {
            Issue.record("the meeting item opens a tool through the router")
            return
        }
        #expect(route.tool == .showCards && route["section"] == "business")
        #expect(LioShowCardSection(route: route) == .business)
        // Declared in the registry: the parameter survives a link, and an unknown section lands at the top.
        #expect(LioToolRegistry.entry(for: .showCards)?.parameters == ["section"])
        let link = try #require(route.url)
        #expect(link.absoluteString == "go2china://tool/show-cards?section=business")
        #expect(LioRoute(url: link) == route)
        #expect(LioShowCardSection(route: try #require(LioRoute(tool: .showCards, parameters: ["section": "other"]))) == nil)
        #expect(LioShowCardSection(route: try #require(LioRoute(tool: .showCards))) == nil)
        let router = LioRouter(tab: .trips, toolsShown: true)
        #expect(router.open(route))
        #expect(router.toolsPath == [route] && router.tab == .tools)
    }

    @Test func otherItemsOpenExistingToolsThroughTheRouterOnly() throws {
        let guide = try Self.guide()
        let list = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: guide))
        #expect(try Self.task(.phrases, list).action == .route(try #require(LioRoute(tool: .translation))))
        #expect(try Self.task(.venue, list).action == .route(try #require(LioRoute(tool: .taxi))))
        #expect(try Self.task(.phrases, list).title == guide.step(3))
        #expect(try Self.task(.venue, list).title == guide.step(5))
        // A tool the router cannot open here leaves the item without "Go"; the words and links stay.
        let noTools = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: guide, routable: []))
        #expect(Self.business(noTools).allSatisfy { task in
            if case .route = task.action { return false }
            return true
        })
        #expect(try Self.task(.venue, noTools).source != nil)
    }

    @Test func businessCardsAreWordsOnlyWithNoButton() throws {
        let list = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: try Self.guide()))
        let cards = try Self.task(.cards, list)
        #expect(cards.action == nil && cards.source == nil)
        #expect(LioTripHomeCopy.businessTitle(cards, .chinese) == "带上名片")
        let task = try #require(list.tasks.first { $0.key == "business.cards" })
        #expect(task.tick == .manual, "ticked by hand")
    }

    @Test func theVisaItemOnlyGivesTheOfficialChannels() throws {
        let guide = try Self.guide()
        let entry = try #require(guide.catalogue.entry(topic: "visa_channel"))
        let list = LioTripChecklist(Self.input(Self.profile(purpose: .business), business: guide))
        let visa = try Self.task(.visa, list)
        #expect(visa.title == nil)
        #expect(LioTripHomeCopy.businessTitle(visa, .chinese) == "查看官方签证渠道")
        #expect(LioTripHomeCopy.businessTitle(visa, .english) == "Check the official visa channels")
        #expect(visa.action == nil, "no tool decides anything; the official pages are the way")
        #expect(visa.text == entry.text)
        #expect(visa.source?.urls.contains { $0.host == "www.nia.gov.cn" } == true)
        // Entry decisions stay Arrival Mode's: a business trip adds no entry task and changes no entry status.
        let leisure = LioTripChecklist(Self.input(Self.profile(purpose: nil), business: guide))
        #expect(list.tasks.first { $0.key == "entry" } == leisure.tasks.first { $0.key == "entry" })
        // The fixed wording around the items names no visa type, visa-free or transit rule.
        for item in LioTripBusinessTask.Item.allCases {
            let bare = LioTripBusinessTask(item: item, title: nil, text: nil, source: nil, action: nil)
            for language in [LioLanguage.english, .chinese] {
                let words = LioTripHomeCopy.businessTitle(bare, language) + LioTripHomeCopy.businessDetail(bare, language)
                for banned in ["免签", "过境", "visa-free", "Visa-free", "transit", "Transit", "L visa", "M visa", "商务签"] {
                    #expect(!words.contains(banned), "\(item) says \(banned)")
                }
            }
        }
    }

    // MARK: - Trip settings on this phone

    @Test @MainActor func aSettingsFileWithoutThePurposeReadsAsALeisureTrip() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("trip-business-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent(LioTripHomeStore.fileName)
        let old = #"{"version":1,"snapshot":{"profile":{"arrival":"2026-12-08","stayDays":7,"cityID":"guangzhou","startedAt":0},"ticks":{"done":{"payment":0}}}}"#
        try Data(old.utf8).write(to: file)
        let model = LioTripHomeModel(store: LioTripHomeStore(directory: directory, isCurrent: { true }))
        #expect(model.profile?.purpose == nil && model.profile?.isBusiness == false)
        #expect(model.profile?.cityID == "guangzhou" && model.ticks.isDone("payment"))

        // A purpose this version does not know reads as leisure, and the rest of the trip is kept.
        let newer = old.replacingOccurrences(of: #""stayDays":7"#, with: #""stayDays":7,"purpose":"conference""#)
        try Data(newer.utf8).write(to: file)
        model.reload()
        #expect(model.profile?.purpose == nil && model.profile?.stayDays == 7)

        // Choosing business is kept on this phone and read back.
        model.update { $0.purpose = .business }
        let again = LioTripHomeModel(store: LioTripHomeStore(directory: directory, isCurrent: { true }))
        #expect(again.profile?.purpose == .business)
    }

    @Test func aLeisureProfileWritesTheSameFileAsBefore() throws {
        let profile = Self.profile(purpose: nil)
        let json = try #require(String(data: JSONEncoder().encode(profile), encoding: .utf8))
        #expect(!json.contains("purpose"), "nothing new is written while the purpose is not set")
        let business = try #require(String(data: JSONEncoder().encode(Self.profile(purpose: .business)), encoding: .utf8))
        #expect(business.contains(#""purpose":"business""#))
    }
}
