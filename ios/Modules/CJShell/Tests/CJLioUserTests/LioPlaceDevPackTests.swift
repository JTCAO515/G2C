#if DEBUG
import Foundation
import Testing
@testable import CJLioUser

/// #1992 follow-up: the place page reads the unreviewed development pack (`LioDevPlacesPack`, #2033) in Debug
/// builds when one is asked for at launch, marks those places as development data, and still hides the buttons
/// that need a coordinate the pack does not have. Release and Beta builds compile all of this out.
@MainActor struct LioPlaceDevPackTests {
    private static let all: Set<LioTool> = [.taxi, .attractionBooking]

    /// A small pack in a temporary directory: a sight with no coordinate, an airport with none, a restaurant
    /// that has one (a later pack will), and a sight that is also in the library below.
    private static let packJSON = """
    {"version": "g2c-places-dev.1", "warning": "x", "generated_on": "2026-11-27", "places": [
      {"id": "pl_sh_waitan", "city": "shanghai", "category": "attraction", "tier": "main", "subcategory": "street",
       "name_zh": "外滩", "name_en": "The Bund", "aliases_zh": [], "aliases_en": [], "address_zh": null,
       "intro_short_zh": "沿江看老建筑", "intro_short_en": "Old buildings along the river.",
       "ticket": {"booking": null, "passport_required": null, "price_cny": null, "closed_weekdays": null,
                  "booking_channel_zh": null, "booking_url": null},
       "location": null, "rank": null, "review": {"status": "unreviewed", "reviewer": null, "reviewed_on": null, "note": null}},
      {"id": "pl_sh_pvg", "city": "shanghai", "category": "hub", "tier": "main", "hub_type": "airport", "code": "PVG",
       "name_zh": "上海浦东国际机场", "name_en": "Shanghai Pudong International Airport", "aliases_zh": [], "aliases_en": [],
       "location": null, "rank": null, "review": {"status": "unreviewed", "reviewer": null, "reviewed_on": null, "note": null}},
      {"id": "pl_sh_xiaoyang", "city": "shanghai", "category": "food", "tier": "main", "name_zh": "小杨生煎",
       "name_en": "Yang's Dumplings", "aliases_zh": [], "aliases_en": [], "intro_short_en": "Pan-fried buns.",
       "location": {"gcj02": {"lat": 31.2398, "lng": 121.4912}, "amap_id": "B0001", "amap_name": "小杨生煎",
                    "method": "amap-poi-search", "geocoded_on": "2026-11-30"},
       "rank": null, "review": {"status": "unreviewed", "reviewer": null, "reviewed_on": null, "note": null}},
      {"id": "pl_bj_gugong", "city": "beijing", "category": "attraction", "tier": "main", "name_zh": "故宫(开发包)",
       "name_en": "Palace (dev pack)", "aliases_zh": [], "aliases_en": [], "location": null, "rank": null,
       "review": {"status": "unreviewed", "reviewer": null, "reviewed_on": null, "note": null}}
    ]}
    """

    private static let libraryJSON = """
    {"version": "g2c-places-app.1", "places": [
      {"id": "pl_bj_gugong", "city": "beijing", "category": "attraction", "kind": "museum", "name_zh": "故宫博物院",
       "name_en": "The Palace Museum", "lat": 39.9165, "lng": 116.3971}]}
    """

    private static let samplesJSON = """
    {"places": [{"id": "pl_bj_sample", "city": "beijing", "category": "attraction", "name_zh": "样例", "name_en": "Sample"},
                {"id": "pl_sh_waitan", "city": "shanghai", "category": "attraction", "name_zh": "外滩样例", "name_en": "Bund sample",
                 "lat": 31.24, "lng": 121.49}]}
    """

    /// Writes `text` to a fresh temporary directory, returns the file's path and removes the directory afterwards.
    private func withFile<T>(_ text: String, _ body: (String) throws -> T) throws -> T {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("places-devpack-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let url = directory.appendingPathComponent("pack.json")
        try text.write(to: url, atomically: true, encoding: .utf8)
        return try body(url.path)
    }

    private func repository(pack path: String?, viaEnvironment: Bool = false, library: Bool = false) -> LioPlaceRepository {
        let arguments = path.map { viaEnvironment ? ["app"] : ["app", LioDevPlacesPack.argument, $0] } ?? ["app"]
        let environment = path.map { viaEnvironment ? [LioDevPlacesPack.environmentKey: $0] : [:] } ?? [:]
        return LioPlaceRepository.debugRepository(
            library: library ? Data(Self.libraryJSON.utf8) : nil, samples: Data(Self.samplesJSON.utf8),
            arguments: arguments, environment: environment)
    }

    // MARK: Where the places come from

    @Test func withoutAPackTheSamplesAreShownAndNothingIsDevelopmentData() {
        let repository = repository(pack: nil)
        #expect(repository.places.map(\.id) == ["pl_bj_sample", "pl_sh_waitan"])
        #expect(repository.places.allSatisfy { !repository.isDevelopmentData($0) })
    }

    @Test func aPackGivenByArgumentOrEnvironmentReplacesTheSamples() throws {
        try withFile(Self.packJSON) { path in
            for viaEnvironment in [false, true] {
                let repository = repository(pack: path, viaEnvironment: viaEnvironment)
                #expect(repository.places.map(\.id) == ["pl_sh_waitan", "pl_sh_pvg", "pl_sh_xiaoyang", "pl_bj_gugong"])
                #expect(repository.place(id: "pl_bj_sample") == nil)
                // The pack's entry, not the sample with the same id.
                #expect(repository.place(id: "pl_sh_waitan")?.nameEN == "The Bund")
                #expect(repository.places.allSatisfy { repository.isDevelopmentData($0) })
            }
        }
    }

    @Test func theReviewedLibraryComesFirstAndIsNeverMarkedAsDevelopmentData() throws {
        try withFile(Self.packJSON) { path in
            let repository = repository(pack: path, library: true)
            let palace = try #require(repository.place(id: "pl_bj_gugong"))
            #expect(palace.nameZH == "故宫博物院" && palace.point != nil)
            #expect(!repository.isDevelopmentData(palace))
            #expect(repository.isDevelopmentData(try #require(repository.place(id: "pl_sh_waitan"))))
            #expect(repository.places.count == 4)
        }
    }

    @Test func aPackThatCannotBeUsedFallsBackToTheSamples() throws {
        let reviewed = Self.packJSON.replacingOccurrences(of: "\"unreviewed\"", with: "\"approved\"")
        try withFile(reviewed) { path in
            #expect(repository(pack: path).places.map(\.id) == ["pl_bj_sample", "pl_sh_waitan"])
        }
        try withFile("{oops") { path in
            #expect(repository(pack: path).places.map(\.id) == ["pl_bj_sample", "pl_sh_waitan"])
        }
        #expect(repository(pack: "/nowhere/pack.json").places.map(\.id) == ["pl_bj_sample", "pl_sh_waitan"])
    }

    /// The committed pack reads through the place model too: no entry is lost, none has a coordinate yet.
    @Test func theCommittedPackReadsThroughThePlaceModel() throws {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let path = root.appendingPathComponent("knowledge/places/dev/places-dev-pack.v1.json").path
        guard FileManager.default.fileExists(atPath: path) else { return }
        let pack = try #require(LioDevPlacesPack.load(arguments: ["a", LioDevPlacesPack.argument, path], environment: [:]))
        let repository = repository(pack: path)
        #expect(repository.places.count == pack.places.count && repository.places.count > 100)
        #expect(repository.places.allSatisfy { repository.isDevelopmentData($0) })
        for place in repository.places where pack.place(id: place.id)?.location == nil { #expect(place.point == nil) }
    }

    // MARK: What the page says

    @Test func aPlaceFromThePackIsLabelledInBothLanguages() throws {
        try withFile(Self.packJSON) { path in
            let repository = repository(pack: path)
            let place = try #require(repository.place(id: "pl_sh_waitan"))
            let english = LioPlacePresentation(place, language: .english, developmentData: repository.isDevelopmentData(place))
            let chinese = LioPlacePresentation(place, language: .chinese, developmentData: repository.isDevelopmentData(place))
            #expect(english.developmentLabel == "Dev data" && chinese.developmentLabel == "开发数据")
            #expect(english.developmentNote?.hasPrefix("Dev data") == true && chinese.developmentNote?.hasPrefix("开发数据") == true)
        }
        // Any other place has no label.
        let sample = try #require(repository(pack: nil).place(id: "pl_bj_sample"))
        #expect(LioPlacePresentation(sample, language: .english).developmentLabel == nil)
        #expect(LioPlacePresentation(sample, language: .english).developmentNote == nil)
    }

    @Test func theLabelWordsAreOnTheCopyList() {
        #expect(LioPlaceCopy.devData.isPlaceholder && LioPlaceCopy.devDataNote.isPlaceholder)
        #expect(LioPlaceCopy.devData.text(.english) == "Dev data" && LioPlaceCopy.devData.text(.chinese) == "开发数据")
    }

    // MARK: No coordinate

    @Test func aPlaceWithoutACoordinateHasNoTaxiAndNoNearbyListAndNothingCrashes() throws {
        try withFile(Self.packJSON) { path in
            let repository = repository(pack: path)
            let bund = try #require(repository.place(id: "pl_sh_waitan"))
            #expect(bund.point == nil)
            let page = LioPlacePresentation(bund, language: .english, developmentData: true)
            let actions = page.actions { Self.all.contains($0) }
            // The existing rules: no checked coordinate, no taxi; directions fall back to a search by name; a sight
            // with no booking requirement has no booking button.
            #expect(actions.taxi == nil && actions.booking == nil)
            #expect(actions.actions == [.driver, .navigate])
            #expect(actions.navigation?.point == nil && actions.navigation?.query == "外滩")
            #expect(actions.navigation?.urls.isEmpty == false)
            #expect(actions.driver?.noteEN == "Address not confirmed")
            #expect(page.nearbyFood(in: repository).isEmpty)

            // A hub with no coordinate has neither taxi nor directions, only the driver card.
            let airport = try #require(repository.place(id: "pl_sh_pvg"))
            let hub = LioPlacePresentation(airport, language: .english, developmentData: true)
            #expect(hub.actions { Self.all.contains($0) }.actions == [.driver])
            #expect(hub.kindLabel == "Airport")
        }
    }

    @Test func aPlaceWithACoordinateInThePackGetsTheTaxiAndAppearsNearby() throws {
        try withFile(Self.packJSON) { path in
            let repository = repository(pack: path)
            let restaurant = try #require(repository.place(id: "pl_sh_xiaoyang"))
            #expect(restaurant.point == .init(latitude: 31.2398, longitude: 121.4912))
            let actions = LioPlacePresentation(restaurant, language: .english, developmentData: true)
                .actions { Self.all.contains($0) }
            #expect(actions.taxi != nil && actions.navigation?.point != nil)
        }
    }

    // MARK: Release and Beta

    /// Release and Beta builds must not contain the pack's reader at all: every mention of it in the place page's
    /// own files is inside `#if DEBUG` (the type itself is a `#if DEBUG` file, which its own tests cover).
    @Test func everyUseOfThePackIsInsideADebugBlock() throws {
        var directory = URL(fileURLWithPath: #filePath)
        for _ in 0..<2 { directory.deleteLastPathComponent() }          // Tests/CJLioUserTests -> Tests... -> CJShell
        directory.deleteLastPathComponent()
        let sources = directory.appendingPathComponent("Sources/CJLioUser")
        for name in ["LioPlaceRepository.swift", "LioPlacePage.swift", "LioPlacePresentation.swift", "LioPlaceActions.swift",
                     "LioPlaceCopy.swift", "LioPlace.swift"] {
            let text = try String(contentsOf: sources.appendingPathComponent(name), encoding: .utf8)
            var stack: [Bool] = []                                       // true while inside the DEBUG branch of an #if
            for line in text.split(separator: "\n", omittingEmptySubsequences: false) {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("#if") { stack.append(trimmed == "#if DEBUG") }
                else if trimmed == "#else" || trimmed.hasPrefix("#elseif") { if !stack.isEmpty { stack[stack.count - 1] = false } }
                else if trimmed == "#endif" { _ = stack.popLast() }
                else if !trimmed.hasPrefix("//"), trimmed.contains("LioDevPlacesPack") {
                    #expect(stack.contains(true), "\(name): \(trimmed)")
                }
            }
            #expect(stack.isEmpty, "\(name): unbalanced #if")
        }
        let manifest = try String(contentsOf: directory.appendingPathComponent("Package.swift"), encoding: .utf8)
        #expect(!manifest.contains("places-dev") && !manifest.contains("DevPack"))
    }
}
#endif
