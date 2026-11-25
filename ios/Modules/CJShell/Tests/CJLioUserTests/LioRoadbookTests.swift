import Foundation
import PDFKit
import Testing
@testable import CJLioUser

/// #1514: the travel roadbook reads the same `LioRichItinerary` as the day-by-day plan (#1453),
/// splits each day into morning / afternoon / evening, keeps an on-device copy and exports a PDF on the device.
@MainActor struct LioRoadbookTests {
    static func place(_ zh: String, _ en: String, matched: Bool = true, address: String? = "北京市东城区景山前街4号",
                      point: LioItinerary.Point? = .init(latitude: 39.9163, longitude: 116.3972)) -> LioRichItinerary.Place {
        .init(nameZH: zh, nameEN: en, address: address, matched: matched, point: point)
    }

    static func stop(_ id: String, _ time: String?, kind: LioRichItinerary.Kind = .sight,
                     place: LioRichItinerary.Place = place("故宫博物院", "Palace Museum"),
                     tip: String? = nil) -> LioRichItinerary.Stop {
        .init(id: id, kind: kind, text: "看 \(id)", time: time, place: place, note: "约 1 小时", tip: tip)
    }

    static func itinerary(dates: [String?] = [nil, nil, nil], stopsPerDay: Int = 2) -> LioRichItinerary {
        let days = dates.enumerated().map { index, date in
            let stops = (0..<stopsPerDay).map { stop("d\(index + 1)s\($0)", String(format: "%02d:00", 9 + $0 * 4),
                                                       tip: $0 == 0 ? "提前 7 天预约，周一闭馆。" : nil) }
            let legs = zip(stops, stops.dropFirst()).map {
                LioRichItinerary.Leg(fromID: $0.id, toID: $1.id, estimate: .init(mode: .walking, seconds: 900, metres: 1100))
            }
            return LioRichItinerary.Day(number: index + 1, date: date, theme: "皇城中轴", area: "东城区", stops: stops, legs: legs)
        }
        return .init(title: "北京三天自由行", undated: dates.allSatisfy { $0 == nil }, days: days,
                     lodgingArea: "住王府井或东四一带，地铁方便。",
                     hotels: [.init(id: "h1", place: place("王府井一带", "Wangfujing area"), note: "步行可到故宫")])
    }

    static func roadbook(_ itinerary: LioRichItinerary = itinerary(), id: String = "planned.beijing",
                         created: TimeInterval = 1_800_000_000) -> LioRoadbook {
        .init(id: id, source: .planned, city: .init(nameZH: "北京", nameEN: "Beijing"),
              createdAt: Date(timeIntervalSince1970: created), itinerary: itinerary)
    }

    // MARK: periods

    @Test func stopsAreGroupedIntoMorningAfternoonAndEveningInOrder() {
        let stops = [Self.stop("a", "08:30"), Self.stop("b", "13:15–14:15"), Self.stop("c", "15:00"),
                     Self.stop("d", "19:30"), Self.stop("e", nil)]
        let legs = [LioRichItinerary.Leg(fromID: "a", toID: "b", estimate: nil)]
        let day = LioRichItinerary.Day(number: 1, date: nil, theme: "", area: "", stops: stops, legs: legs)
        let segments = LioRoadbook.segments(day)
        #expect(segments.map(\.period) == [.morning, .afternoon, .evening])
        #expect(segments.map { $0.entries.map(\.stop.id) } == [["a"], ["b", "c"], ["d", "e"]])
        #expect(segments.flatMap(\.entries).map(\.number) == [1, 2, 3, 4, 5], "numbers match the map and the plan")
        #expect(segments[0].entries[0].legAfter?.toID == "b", "the leg after the last morning stop is kept")
        #expect(segments[1].entries[0].legAfter == nil)
    }

    @Test func untimedOrOutOfOrderStopsStayWithThePreviousPeriod() {
        let day = LioRichItinerary.Day(number: 1, date: nil, theme: "", area: "",
                                       stops: [Self.stop("a", nil), Self.stop("b", "14:00"), Self.stop("c", "09:00"),
                                               Self.stop("d", "至 第 2 天 10:00"), Self.stop("e", "Until Day 2 10:00")],
                                       legs: [])
        let segments = LioRoadbook.segments(day)
        #expect(segments.map(\.period) == [.morning, .afternoon])
        #expect(segments.map { $0.entries.map(\.stop.id) } == [["a"], ["b", "c", "d", "e"]])
        #expect(LioRoadbook.segments(.init(number: 2, date: nil, theme: "", area: "", stops: [], legs: [])).isEmpty)
    }

    @Test func periodBoundaries() {
        #expect(LioRoadbookPeriod(time: "00:00") == .morning)
        #expect(LioRoadbookPeriod(time: "11:59") == .morning)
        #expect(LioRoadbookPeriod(time: "12:00") == .afternoon)
        #expect(LioRoadbookPeriod(time: "17:59") == .afternoon)
        #expect(LioRoadbookPeriod(time: "18:00") == .evening)
        #expect(LioRoadbookPeriod(time: "9:30") == .morning)
        #expect(LioRoadbookPeriod(time: "25:00") == nil)
        #expect(LioRoadbookPeriod(time: "约 1 小时") == nil)
        #expect(LioRoadbookPeriod(time: nil) == nil)
        for period in LioRoadbookPeriod.allCases {
            #expect(!period.title(.english).isEmpty && !period.title(.chinese).isEmpty && !period.symbol.isEmpty)
        }
        #expect(LioRoadbookPeriod.morning.title(.chinese) == "上午")
        #expect(LioRoadbookPeriod.evening.title(.english) == "Evening")
    }

    // MARK: cover

    @Test func coverShowsCityDaysAndDatesInBothLanguages() {
        let undated = Self.roadbook()
        #expect(undated.coverTitle(.chinese) == "北京")
        #expect(undated.coverTitle(.english) == "Beijing")
        #expect(undated.coverLine(.chinese) == "3 天 · 日期待定")
        #expect(undated.coverLine(.english) == "3 days · Dates not set")

        let dated = Self.roadbook(Self.itinerary(dates: ["2026-12-01", "2026-12-02", "2026-12-03"]))
        #expect(dated.coverLine(.chinese) == "3 天 · 12月1日–12月3日")
        #expect(dated.coverLine(.english) == "3 days · Dec 1 – Dec 3")

        let one = Self.roadbook(Self.itinerary(dates: ["2026-12-01"]))
        #expect(one.coverLine(.english) == "1 day · Dec 1")

        let noCity = LioRoadbook(id: "x", source: .template, city: nil, createdAt: .now, itinerary: Self.itinerary())
        #expect(noCity.coverTitle(.chinese) == "北京三天自由行", "without a city the plan title is used")
        #expect(LioRoadbook.officialNotice(.chinese).contains("以官方为准"))
        #expect(LioRoadbook.officialNotice(.english).localizedCaseInsensitiveContains("official"))
        for source in LioRoadbook.Source.allCases {
            #expect(!source.title(.english).isEmpty && !source.title(.chinese).isEmpty)
        }
    }

    // MARK: actions reuse taxi and driver card

    @Test func taxiAndDriverCardOnlyForCheckedPlaces() {
        let checked = Self.place("故宫博物院", "Palace Museum")
        #expect(LioRoadbook.taxiDestination(checked)?.nameZH == "故宫博物院")
        #expect(LioRoadbook.taxiDestination(checked)?.coordinate.referenceSystem == .gcj02)
        #expect(LioRoadbook.driverAddress(checked) == "北京市东城区景山前街4号")

        let suggested = Self.place("某餐厅", "Some restaurant", matched: false)
        #expect(LioRoadbook.taxiDestination(suggested) == nil)
        #expect(LioRoadbook.driverAddress(suggested) == nil)

        let noPoint = Self.place("故宫博物院", "Palace Museum", point: nil)
        #expect(LioRoadbook.taxiDestination(noPoint) == nil, "no checked coordinate, no ride")
        #expect(LioRoadbook.driverAddress(noPoint) != nil, "the driver can still read a checked address")
    }

    // MARK: static essentials

    @Test func essentialsAreBilingualAndReuseTheAppsDirectories() {
        for language in [LioLanguage.english, .chinese] {
            let sections = LioRoadbookEssentials.sections(language)
            #expect(sections.map(\.id) == ["emergency", "phrases", "payment", "internet"])
            for section in sections {
                #expect(!section.title.isEmpty && !section.symbol.isEmpty && !section.items.isEmpty)
                for item in section.items { #expect(!item.title.isEmpty) }
            }
            let phones = sections[0].items.compactMap(\.phone)
            #expect(phones.starts(with: ["110", "120", "119", "122"]))
            #expect(phones.contains("12345") && phones.contains("12367"))
            let phrases = sections[1].items
            #expect(phrases.contains { $0.chinese == "麻烦送我到这个地址。" })
            #expect(phrases.allSatisfy { $0.chinese != nil }, "phrases always carry Chinese to show people")
        }
        let english = LioRoadbookEssentials.sections(.english)
        #expect(english[1].items.contains { $0.title == "Please take me to this address." })
        let text = LioRoadbookEssentials.sections(.chinese).flatMap(\.items).map { $0.title + ($0.detail ?? "") }.joined()
        #expect(!text.contains("¥") && !text.contains("元"), "no prices in static text")
    }

    // MARK: offline archive

    @Test func archiveRoundTripsEveryField() throws {
        let original = Self.roadbook(Self.itinerary(dates: ["2026-12-01", "2026-12-02", "2026-12-03"]))
        let archive = LioRoadbookArchive(original)
        let data = try JSONEncoder().encode(archive)
        let decoded = try JSONDecoder().decode(LioRoadbookArchive.self, from: data)
        #expect(decoded == archive)
        let restored = try decoded.roadbook()
        #expect(LioRoadbookArchive(restored) == archive)
        #expect(restored.id == original.id && restored.source == .planned && restored.city?.nameEN == "Beijing")
        #expect(restored.itinerary.days[0].stops[0].tip == "提前 7 天预约，周一闭馆。")
        #expect(restored.itinerary.days[0].legs[0].estimate?.mode == .walking)
        #expect(restored.itinerary.days[0].stops[0].place.mapPoint?.latitude == 39.9163)
        #expect(restored.itinerary.hotels.first?.place.nameEN == "Wangfujing area")
    }

    @Test func archiveRefusesUnknownVersionsAndValues() throws {
        var json = try #require(String(data: JSONEncoder().encode(LioRoadbookArchive(Self.roadbook())), encoding: .utf8))
        #expect(throws: LioRoadbookArchive.Failure.self) {
            try JSONDecoder().decode(LioRoadbookArchive.self, from: Data(json.replacingOccurrences(of: "\"version\":1", with: "\"version\":2").utf8)).roadbook()
        }
        json = json.replacingOccurrences(of: "\"kind\":\"sight\"", with: "\"kind\":\"rocket\"")
        #expect(throws: LioRoadbookArchive.Failure.self) {
            try JSONDecoder().decode(LioRoadbookArchive.self, from: Data(json.utf8)).roadbook()
        }
    }

    @Test func storeKeepsCopiesOnThisDeviceOnly() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("roadbook-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioRoadbookStore(directory: directory)
        #expect(store.load().isEmpty, "a missing folder is an empty library")

        try store.save(Self.roadbook(id: "older/../trip:1", created: 1_000))
        try store.save(Self.roadbook(id: "newer", created: 2_000))
        try store.save(Self.roadbook(id: "newer", created: 3_000))
        #expect(store.load().map(\.id) == ["newer", "older/../trip:1"], "newest first, one copy per id")
        #expect(store.contains("newer") && !store.contains("missing"))

        let files = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        #expect(files.count == 2)
        #expect(files.allSatisfy { $0.deletingLastPathComponent().standardizedFileURL == directory.standardizedFileURL },
                "ids never become paths")
        #expect(try directory.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup == true)

        try Data("not json".utf8).write(to: directory.appendingPathComponent("broken.json"))
        #expect(store.load().map(\.id) == ["newer", "older/../trip:1"], "an unreadable copy is skipped, not fatal")

        try store.remove("newer")
        #expect(store.load().map(\.id) == ["older/../trip:1"])
        try store.remove("missing")
    }

    // MARK: PDF on the device

    @Test func pdfHasACoverEveryDayAndTheEssentials() throws {
        let book = Self.roadbook()
        let data = LioRoadbookPDF.data(for: book, language: .chinese)
        let pdf = try #require(PDFDocument(data: data))
        #expect(pdf.pageCount >= 1 + 3 + 1, "cover, one page per day, essentials")
        let cover = try #require(pdf.page(at: 0)?.string)
        #expect(cover.contains("北京") && cover.contains("3 天"))
        let text = try #require(pdf.string)
        for expected in ["第 1 天", "第 3 天", "上午", "下午", "故宫博物院", "北京市东城区景山前街4号", "提前 7 天预约",
                         "以官方为准", "步行", "住宿", "110", "120", "麻烦送我到这个地址"] {
            #expect(text.contains(expected), "\(expected)")
        }
        #expect(!text.contains("Dates not set"))
    }

    @Test func englishPdfKeepsChineseNamesForDrivers() throws {
        let text = try #require(PDFDocument(data: LioRoadbookPDF.data(for: Self.roadbook(), language: .english))?.string)
        for expected in ["Beijing", "Day 1", "Morning", "Palace Museum", "故宫博物院", "北京市东城区景山前街4号",
                         "official", "Police", "110", "Please take me to this address.", "麻烦送我到这个地址"] {
            #expect(text.contains(expected), "\(expected)")
        }
    }

    @Test func longDaysContinueOnTheNextPage() throws {
        let short = try #require(PDFDocument(data: LioRoadbookPDF.data(for: Self.roadbook(Self.itinerary(dates: [nil], stopsPerDay: 2)), language: .chinese)))
        let long = try #require(PDFDocument(data: LioRoadbookPDF.data(for: Self.roadbook(Self.itinerary(dates: [nil], stopsPerDay: 60)), language: .chinese)))
        #expect(long.pageCount > short.pageCount)
        #expect(long.string?.contains("看 d1s59") == true, "nothing is cut off")
    }

    @Test func pdfFileIsWrittenLocallyWithASafeName() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("roadbook-pdf-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let url = try LioRoadbookPDF.write(Self.roadbook(), language: .english, to: directory)
        #expect(url.lastPathComponent == "Beijing-roadbook.pdf")
        #expect(url.deletingLastPathComponent().standardizedFileURL == directory.standardizedFileURL)
        #expect(PDFDocument(url: url) != nil)
        let odd = LioRoadbook(id: "x", source: .template, city: .init(nameZH: "西安", nameEN: "Xi'an / Shaanxi"),
                              createdAt: .now, itinerary: Self.itinerary())
        #expect(LioRoadbookPDF.fileName(for: odd, language: .english) == "Xi-an-Shaanxi-roadbook.pdf")
        #expect(LioRoadbookPDF.fileName(for: odd, language: .chinese) == "西安-路书.pdf")
    }
}

/// Review follow-ups on #1524: per-account folder, signed-out guard, tighter files, one export at a time.
@MainActor struct LioRoadbookStorageHardeningTests {
    @Test func copiesLiveInTheAccountsMessageFolder() {
        let account = URL(fileURLWithPath: "/tmp/account-a", isDirectory: true)
        #expect(LioRoadbookStore.storageDirectory(inMessageDirectory: account).lastPathComponent == "roadbooks")
        #expect(LioRoadbookStore.storageDirectory(inMessageDirectory: account).deletingLastPathComponent().path == account.path)
    }

    @Test func aRetiredAccountCanNeitherReadNorWrite() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("roadbook-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        try LioRoadbookStore(directory: directory).save(LioRoadbookTests.roadbook())
        let retired = LioRoadbookStore(directory: directory, isCurrent: { false })
        #expect(retired.load().isEmpty)
        #expect(!retired.contains("planned.beijing"))
        #expect(throws: LioRoadbookStore.Failure.notCurrent) { try retired.save(LioRoadbookTests.roadbook(id: "other")) }
        #expect(throws: LioRoadbookStore.Failure.notCurrent) { try retired.remove("planned.beijing") }
        #expect(LioRoadbookStore(directory: directory).load().map(\.id) == ["planned.beijing"])
    }

    @Test func theFolderIsPrivateToTheApp() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("roadbook-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        try LioRoadbookStore(directory: directory).save(LioRoadbookTests.roadbook())
        let permissions = try FileManager.default.attributesOfItem(atPath: directory.path)[.posixPermissions] as? Int
        #expect(permissions == 0o700)
    }

    @Test func onlyTheLatestExportIsKept() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("roadbook-pdf-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let first = try LioRoadbookPDF.write(LioRoadbookTests.roadbook(), language: .english, to: directory)
        let second = try LioRoadbookPDF.write(LioRoadbookTests.roadbook(), language: .chinese, to: directory)
        let files = try FileManager.default.contentsOfDirectory(atPath: directory.path)
        #expect(files == [second.lastPathComponent])
        #expect(!FileManager.default.fileExists(atPath: first.path))
    }

    @Test func emptyNotesAreLeftOut() throws {
        let base = LioRoadbookTests.itinerary()
        let itinerary = LioRichItinerary(title: base.title, undated: true, days: base.days, lodgingArea: "",
                                         hotels: [.init(id: "h", place: LioRoadbookTests.place("王府井一带", "Wangfujing area"), note: "  ")])
        let book = LioRoadbookTests.roadbook(itinerary)
        #expect(LioRoadbook.visibleNote(book.itinerary.hotels[0].note) == nil)
        #expect(LioRoadbook.visibleNote(" 步行可到故宫 ") == "步行可到故宫")
    }
}
