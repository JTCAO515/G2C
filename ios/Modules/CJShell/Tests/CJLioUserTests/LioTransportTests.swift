import Foundation
import Testing
@testable import CJLioUser

/// #1519: intercity transport search (trains, flights, buses) in the Tools tab.
struct LioTransportCityTests {
    @Test func resolvesChineseEnglishAndCommonSpellings() {
        #expect(LioTransportCity.resolve("上海")?.id == "shanghai")
        #expect(LioTransportCity.resolve("上海市")?.id == "shanghai")
        #expect(LioTransportCity.resolve("  shanghai ")?.id == "shanghai")
        #expect(LioTransportCity.resolve("Shanghai City")?.id == "shanghai")
        #expect(LioTransportCity.resolve("XI'AN")?.id == "xian")
        #expect(LioTransportCity.resolve("Xian")?.id == "xian")
        #expect(LioTransportCity.resolve("西安")?.id == "xian")
        #expect(LioTransportCity.resolve("Peking")?.id == "beijing")
        #expect(LioTransportCity.resolve("Canton")?.id == "guangzhou")
        #expect(LioTransportCity.resolve("中国北京")?.id == "beijing")
    }

    @Test func unknownOrOutOfScopePlacesAreNotGuessed() {
        #expect(LioTransportCity.resolve("") == nil)
        #expect(LioTransportCity.resolve("上") == nil)
        #expect(LioTransportCity.resolve("Atlantis") == nil)
        #expect(LioTransportCity.resolve("Hong Kong") == nil)
        #expect(LioTransportCity.resolve("台北") == nil)
    }

    @Test func everyCityHasBilingualNamesStationsAndAirports() {
        #expect(LioTransportCity.all.count >= 12)
        #expect(Set(LioTransportCity.all.map(\.id)).count == LioTransportCity.all.count)
        for city in LioTransportCity.all {
            #expect(!city.nameZH.isEmpty && !city.nameEN.isEmpty)
            #expect(city.railSlug.allSatisfy { $0.isLowercase || $0 == "-" })
            #expect(city.flightCityCode.count == 3 && city.flightCityCode == city.flightCityCode.uppercased())
            #expect(!city.stations.isEmpty && !city.airports.isEmpty)
            for hub in city.stations {
                #expect(hub.kind == .station && hub.nameZH.hasSuffix("站") && hub.code == nil)
                #expect(hub.nameEN.hasSuffix("Railway Station"))
            }
            for hub in city.airports {
                #expect(hub.kind == .airport && hub.nameZH.hasSuffix("机场"))
                #expect(hub.code?.count == 3)
                #expect(hub.nameEN.hasSuffix("Airport"))
            }
        }
    }

    @Test func hubsShowTheOtherLanguageUnderEnglishNames() {
        let hongqiao = LioTransportCity.resolve("上海")!.stations[0]
        #expect(hongqiao.name(in: .english) == "Shanghai Hongqiao Railway Station")
        #expect(hongqiao.secondaryName(in: .english) == "上海虹桥站")
        #expect(hongqiao.name(in: .chinese) == "上海虹桥站")
        #expect(hongqiao.secondaryName(in: .chinese) == nil)
    }
}

struct LioTransportQueryTests {
    private static let today = LioTransportQuery.date(year: 2026, month: 11, day: 25)

    @Test func buildsAQueryInShanghaiTime() throws {
        let date = LioTransportQuery.date(year: 2026, month: 12, day: 3)
        let query = try LioTransportQuery.make(from: "Shanghai", to: "北京", date: date, today: Self.today).get()
        #expect(query.from.id == "shanghai" && query.to.id == "beijing")
        #expect(query.day == "2026-12-03")
        #expect(query.swapped.from.id == "beijing" && query.swapped.to.id == "shanghai")
    }

    @Test func rejectsUnknownSameCityAndPastDates() {
        let date = LioTransportQuery.date(year: 2026, month: 12, day: 3)
        #expect(LioTransportQuery.make(from: "Nowhere", to: "北京", date: date, today: Self.today) == .failure(.unknownFrom))
        #expect(LioTransportQuery.make(from: "上海", to: "", date: date, today: Self.today) == .failure(.unknownTo))
        #expect(LioTransportQuery.make(from: "上海", to: "shanghai", date: date, today: Self.today) == .failure(.sameCity))
        let yesterday = LioTransportQuery.date(year: 2026, month: 11, day: 24)
        #expect(LioTransportQuery.make(from: "上海", to: "北京", date: yesterday, today: Self.today) == .failure(.pastDate))
        #expect((try? LioTransportQuery.make(from: "上海", to: "北京", date: Self.today, today: Self.today).get()) != nil)
        for problem in [LioTransportQuery.Problem.unknownFrom, .unknownTo, .sameCity, .pastDate] {
            #expect(!problem.message(.english).isEmpty && !problem.message(.chinese).isEmpty)
        }
    }
}

struct LioTransportLinkTests {
    private static func query() throws -> LioTransportQuery {
        try LioTransportQuery.make(from: "上海", to: "Beijing",
                                   date: LioTransportQuery.date(year: 2026, month: 12, day: 3),
                                   today: LioTransportQuery.date(year: 2026, month: 11, day: 25)).get()
    }

    @Test func trainsOpen12306AndTheTripComRoutePage() throws {
        let english = LioTransportLinks.booking(.rail, query: try Self.query(), language: .english)
        #expect(english.map(\.provider) == [.railway12306, .tripCom])
        #expect(english[0].url.absoluteString == "https://www.12306.cn/en/index.html")
        #expect(english[1].url.absoluteString == "https://www.trip.com/trains/china/route/shanghai-to-beijing/")
        let chinese = LioTransportLinks.booking(.rail, query: try Self.query(), language: .chinese)
        #expect(chinese[0].url.absoluteString == "https://www.12306.cn/index/")
    }

    @Test func flightsOpenTripComWithTheDate() throws {
        let links = LioTransportLinks.booking(.flight, query: try Self.query(), language: .english)
        #expect(links.map(\.provider) == [.tripCom])
        #expect(links[0].url.absoluteString ==
                "https://www.trip.com/flights/showfarefirst?dcity=sha&acity=bjs&ddate=2026-12-03&triptype=ow&class=y&quantity=1")
    }

    @Test func busesHaveNoBookingLinkOnlyAGuide() throws {
        #expect(LioTransportLinks.booking(.bus, query: try Self.query(), language: .english).isEmpty)
    }

    @Test func everyLinkIsHTTPSAndLabelledInBothLanguages() throws {
        for mode in LioTransportMode.allCases {
            for language in [LioLanguage.english, .chinese] {
                for link in LioTransportLinks.booking(mode, query: try Self.query(), language: language) {
                    #expect(link.url.scheme == "https")
                    #expect(!link.provider.label(language).isEmpty)
                }
            }
        }
    }
}

struct LioTransportResultTests {
    private static let hongqiao = LioTransportCity.resolve("上海")!.stations[0]
    private static let beijingSouth = LioTransportCity.resolve("北京")!.stations[0]

    private static func train(_ number: String, minutes: Int, fares: [Int]) -> LioTransportOption {
        LioTransportOption(mode: .rail, number: number, carrierZH: nil, carrierEN: nil,
                           departure: hongqiao, arrival: beijingSouth, departTime: "08:00", arriveTime: "12:28",
                           durationMinutes: minutes,
                           fares: fares.map { LioTransportFare(classZH: "二等座", classEN: "Second class", priceMinor: $0) })
    }

    @Test func summarisesFastestAndCheapest() {
        let result = LioTransportModeResult.options([
            Self.train("G2", minutes: 268, fares: [62_600, 100_600]),
            Self.train("G10", minutes: 300, fares: [55_300]),
            Self.train("D1", minutes: 600, fares: []),
        ])
        #expect(result.fastestMinutes == 268)
        #expect(result.lowestPriceMinor == 55_300)
        #expect(LioTransportModeResult.guideOnly.fastestMinutes == nil)
        #expect(LioTransportModeResult.unavailable.lowestPriceMinor == nil)
        #expect(!Self.train("G2", minutes: 268, fares: []).arrivesNextDay)
        let overnight = LioTransportOption(mode: .rail, number: "D312", carrierZH: nil, carrierEN: nil,
                                           departure: Self.hongqiao, arrival: Self.beijingSouth, departTime: "19:45",
                                           arriveTime: "07:36", durationMinutes: 711, fares: [])
        #expect(overnight.arrivesNextDay)
    }

    @Test func formatsDurationsAndPricesInBothLanguages() {
        #expect(LioTransportFormat.duration(268, .english) == "4h 28m")
        #expect(LioTransportFormat.duration(268, .chinese) == "4小时28分")
        #expect(LioTransportFormat.duration(45, .english) == "45m")
        #expect(LioTransportFormat.duration(120, .chinese) == "2小时")
        #expect(LioTransportFormat.price(62_600) == "¥626")
        #expect(LioTransportFormat.price(62_650) == "¥626.5")
        #expect(LioTransportFormat.price(5) == "¥0.05")
        #expect(LioTransportFormat.from(55_300, .english) == "from ¥553")
        #expect(LioTransportFormat.from(55_300, .chinese) == "¥553 起")
    }

    @Test func trainSeatsAreNeverClaimedOnlyPointedTo12306() {
        for language in [LioLanguage.english, .chinese] {
            let note = LioTransportMode.rail.availabilityNote(language)
            #expect(note.contains("12306"))
        }
        #expect(LioTransportMode.flight.availabilityNote(.english).localizedStandardContains("change"))
        #expect(!LioTransportMode.bus.availabilityNote(.chinese).isEmpty)
    }

    @Test func guideOnlyServiceNeverInventsTimetables() async throws {
        let query = try LioTransportQuery.make(from: "上海", to: "北京",
                                               date: LioTransportQuery.date(year: 2026, month: 12, day: 3),
                                               today: LioTransportQuery.date(year: 2026, month: 11, day: 25)).get()
        let result = try await LioTransportService.guideOnly.search(query)
        #expect(result.rail == .guideOnly && result.flight == .guideOnly && result.bus == .guideOnly)
        #expect(!result.isSample)
    }

    #if DEBUG
    @Test func previewDataIsMarkedAsSampleAndUsesTheQueryCities() async throws {
        let query = try LioTransportQuery.make(from: "上海", to: "北京",
                                               date: LioTransportQuery.date(year: 2026, month: 12, day: 3),
                                               today: LioTransportQuery.date(year: 2026, month: 11, day: 25)).get()
        let result = try await LioTransportService.preview.search(query)
        #expect(result.isSample)
        guard case .options(let trains) = result.rail, case .options(let flights) = result.flight else {
            Issue.record("preview should have trains and flights"); return
        }
        #expect(!trains.isEmpty && !flights.isEmpty)
        let names = { (hubs: [LioTransportHub]) in hubs.map(\.nameZH) }
        #expect(trains.allSatisfy { names(query.from.stations).contains($0.departure.nameZH)
                && names(query.to.stations).contains($0.arrival.nameZH) })
        #expect(flights.allSatisfy { names(query.from.airports).contains($0.departure.nameZH)
                && names(query.to.airports).contains($0.arrival.nameZH) })
        #expect(flights.allSatisfy { $0.carrierEN != nil && $0.carrierZH != nil })
        #expect(result.bus == .guideOnly)
    }
    #endif
}

struct LioTransportEntryTests {
    @Test func hiddenUnlessTheBuildEnablesIt() async throws {
        #expect(LioTransportService.fromBuild(arguments: [], info: nil) == nil)
        #expect(LioTransportService.fromBuild(arguments: [], info: [:]) == nil)
        #expect(LioTransportService.fromBuild(arguments: [], info: ["G2CTransportEnabled": "NO"]) == nil)
        #expect(LioTransportService.fromBuild(arguments: [], info: ["G2CTransportEnabled": "$(G2C_TRANSPORT_ENABLED)"]) == nil)
        let enabled = try #require(LioTransportService.fromBuild(arguments: [], info: ["G2CTransportEnabled": "YES"]))
        let query = try LioTransportQuery.make(from: "上海", to: "北京",
                                               date: LioTransportQuery.date(year: 2026, month: 12, day: 3),
                                               today: LioTransportQuery.date(year: 2026, month: 11, day: 25)).get()
        let result = try await enabled.search(query)
        #expect(!result.isSample && result.rail == .guideOnly)
    }

    #if DEBUG
    @Test func debugPreviewArgumentShowsSampleData() async throws {
        let preview = try #require(LioTransportService.fromBuild(arguments: ["--lio-transport-preview"], info: nil))
        let query = try LioTransportQuery.make(from: "上海", to: "北京",
                                               date: LioTransportQuery.date(year: 2026, month: 12, day: 3),
                                               today: LioTransportQuery.date(year: 2026, month: 11, day: 25)).get()
        #expect(try await preview.search(query).isSample)
    }
    #endif
}

struct LioTransportGuideTests {
    @Test func everyModeHasBilingualTipsWithSourcesAndACheckDate() {
        #expect(LioTransportGuide.checkedOn == "2026-11-25")
        for mode in LioTransportMode.allCases {
            let tips = LioTransportGuide.tips(for: mode)
            #expect(tips.count >= 3, "\(mode)")
            #expect(Set(tips.map(\.id)).count == tips.count)
            for tip in tips {
                #expect(!tip.title(.english).isEmpty && !tip.title(.chinese).isEmpty)
                #expect(!tip.body(.english).isEmpty && !tip.body(.chinese).isEmpty)
                #expect(!tip.body(.english).contains { ("\u{4E00}"..."\u{9FFF}").contains($0) }, "\(tip.id)")
            }
            let sources = LioTransportGuide.sources(for: mode)
            #expect(!sources.isEmpty)
            #expect(sources.allSatisfy { $0.url.scheme == "https" && !$0.name.isEmpty })
        }
        let rail = LioTransportGuide.tips(for: .rail).map(\.id)
        #expect(rail.contains("rail.passport") && rail.contains("rail.arrive-early") && rail.contains("rail.gates"))
    }

    @Test func modesHaveBilingualNamesAndStableIdentifiers() {
        #expect(LioTransportMode.allCases == [.rail, .flight, .bus])
        #expect(LioTransportMode.allCases.map(\.identifier) ==
                ["lio.transport.mode.rail", "lio.transport.mode.flight", "lio.transport.mode.bus"])
        for mode in LioTransportMode.allCases {
            #expect(!mode.symbol.isEmpty)
            #expect(!mode.name(.english).isEmpty && !mode.name(.chinese).isEmpty)
        }
    }
}
