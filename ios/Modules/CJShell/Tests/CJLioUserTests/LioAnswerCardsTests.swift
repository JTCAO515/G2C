import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

/// #1993 (58.1 D-5): tool cards under an answer, from the server's `rich.cards`.
struct LioAnswerCardsTests {
    private typealias Card = LioTimelineWire.Card
    private let beijing = LioTimelineWire.CardCity(id: "beijing", zh: "北京", en: "Beijing")
    private let shanghai = LioTimelineWire.CardCity(id: "shanghai", zh: "上海", en: "Shanghai")

    private func taxi(_ extra: [String: String] = [:]) -> Card {
        .init(kind: .taxi, parameters: ["destination": "故宫博物院", "lat": "39.918058", "lng": "116.397026"].merging(extra) { $1 })
    }

    private func present(_ card: Card, _ language: LioLanguage = .chinese) -> LioAnswerCardPresentation {
        .init(card: card, language: language)
    }

    // MARK: Words

    @Test func eachCardHasTheContractsLabelInTheAppsLanguage() {
        let titles: [(Card.Kind, String, String)] = [
            (.taxi, "打车去这里", "Taxi there"), (.metro, "看地铁线路", "Metro map"),
            (.transport, "查火车和航班", "Trains & flights"), (.currency, "汇率换算", "Convert currency")]
        for (kind, zh, en) in titles {
            #expect(present(.init(kind: kind), .chinese).title == zh && present(.init(kind: kind), .english).title == en)
        }
    }

    @Test func theLineUnderTheTitleComesFromTheCardsData() {
        #expect(present(taxi()).detail == "故宫博物院")
        #expect(present(taxi(["destinationEN": "The Palace Museum"]), .english).detail == "The Palace Museum")
        #expect(present(taxi(), .english).detail == "故宫博物院", "no English name: the Chinese one is shown, as on a driver's card")
        #expect(present(.init(kind: .taxi)).detail == nil)
        #expect(present(.init(kind: .metro, detail: .metro(city: beijing))).detail == "北京")
        #expect(present(.init(kind: .metro, detail: .metro(city: beijing)), .english).detail == "Beijing")
        let transport = Card(kind: .transport, parameters: ["from": "beijing", "to": "shanghai"], detail: .transport(from: beijing, to: shanghai))
        #expect(present(transport).detail == "北京 → 上海" && present(transport, .english).detail == "Beijing → Shanghai")
    }

    @Test func aRateIsCalledAReferenceRateWithItsDate() {
        let rate = Card(kind: .currency, detail: .currency(quote: "USD", cnyPerUnit: "7.1234", asOf: "2026-11-26"))
        #expect(present(rate).detail == "1 USD ≈ ¥7.1234 · 参考汇率，截至2026-11-26")
        #expect(present(rate, .english).detail == "1 USD ≈ ¥7.1234 · Reference rate, as of 2026-11-26")
        #expect(present(.init(kind: .currency, detail: .currency(quote: "USD", cnyPerUnit: nil, asOf: nil))).detail == nil,
                "no rate (older than the server allows): nothing is claimed")
        #expect(present(.init(kind: .currency)).detail == nil)
    }

    // MARK: Where a card goes

    @Test func everyCardTypeNamesAToolThisAppRegistersAndThatToolReadsTheCardsParameters() throws {
        for kind in Card.Kind.allCases {
            let entry = try #require(LioToolRegistry.entry(for: LioTool(kind.tool)), "\(kind.rawValue)")
            #expect(entry.tool.rawValue == kind.tool)
        }
        let taxiEntry = try #require(LioToolRegistry.entry(for: .taxi))
        #expect(Set(taxi(["address": "景山前街4号", "destinationEN": "The Palace Museum"]).parameters.keys).isSubset(of: taxiEntry.parameters))
        let transportEntry = try #require(LioToolRegistry.entry(for: .transport))
        #expect(["from", "to"].allSatisfy(transportEntry.parameters.contains))
        #expect(Card.Kind.allCases.map(\.tool) == ["taxi", "metro-guide", "transport", "currency"])
    }

    @Test func aTapOpensTheTypesToolWithTheCardsParameters() throws {
        let route = try #require(present(taxi(["address": "景山前街4号"])).route())
        #expect(route.tool == .taxi)
        #expect(route.parameters == ["destination": "故宫博物院", "lat": "39.918058", "lng": "116.397026", "address": "景山前街4号"])
        #expect(LioTaxiPlace(route: route)?.nameZH == "故宫博物院", "the taxi page reads it as a destination")
        let transport = Card(kind: .transport, parameters: ["from": "beijing", "to": "shanghai"], detail: .transport(from: beijing, to: shanghai))
        #expect(present(transport).route()?.tool == .transport && present(transport).route()?.parameters == ["from": "beijing", "to": "shanghai"])
        #expect(present(.init(kind: .metro, detail: .metro(city: beijing))).route()?.tool == .metro)
        #expect(present(.init(kind: .metro, detail: .metro(city: beijing))).route()?.parameters.isEmpty == true)
        #expect(present(.init(kind: .currency)).route()?.tool == .currency)
    }

    @Test func onlyTheParametersTheRegistryDeclaresReachTheTool() throws {
        // A card can never carry another key (the wire drops the card), but the route is the second lock.
        let sneaky = Card(kind: .taxi, parameters: ["destination": "X", "lat": "39.9", "lng": "116.4", "phone": "123", "evil": "y"])
        let route = try #require(present(sneaky).route())
        #expect(route.parameters.keys.sorted() == ["destination", "lat", "lng"])
        let metro = Card(kind: .metro, parameters: ["city": "beijing"], detail: .metro(city: beijing))
        #expect(present(metro).route()?.parameters.isEmpty == true, "the metro entry declares no parameters of its own here")
    }

    @Test func aCardOpensOnlyWhenThisBuildShowsItsTool() {
        let card = present(taxi())
        #expect(card.openable(in: [.taxi, .currency])?.tool == .taxi)
        #expect(card.openable(in: [.currency]) == nil, "the tool is gated off in this build")
        #expect(card.openable(in: []) == nil, "no Tools tab: nothing opens")
    }

    @Test func aToolThisAppDoesNotRegisterNeverOpens() {
        let registry = LioToolRegistry.entries.filter { $0.tool != .transport }
        let transport = Card(kind: .transport, parameters: ["from": "beijing", "to": "shanghai"], detail: .transport(from: beijing, to: shanghai))
        #expect(present(transport).route(entries: registry) == nil)
        #expect(present(transport).openable(in: [.transport], entries: registry) == nil, "even when the build claims it is shown")
        #expect(present(transport).openable(in: [.transport]) != nil)
    }

    @Test func aCardThatCannotOpenSaysItIsNotInThisVersion() {
        let card = present(taxi())
        #expect(card.spoken(opens: false) == "打车去这里。故宫博物院。这个版本还没有这个工具。")
        #expect(card.spoken(opens: true) == "打车去这里。故宫博物院")
        let english = present(taxi(["destinationEN": "The Palace Museum"]), .english)
        #expect(english.spoken(opens: false) == "Taxi there. The Palace Museum. This tool isn't in this version yet.")
    }

    @Test func wordsAreInBothLanguagesAndAllArePlaceholders() {
        for word in LioAnswerCardCopy.allCases {
            #expect(!word.text(.english).isEmpty && !word.text(.chinese).isEmpty && word.text(.english) != word.text(.chinese), "\(word.rawValue)")
            #expect(word.isPlaceholder)
        }
    }

    // MARK: The turn

    @Test func aTurnReadsCardsOnlyWhenTheSwitchIsOn() {
        let message = LioTimelineWire.Message(
            id: "m1", question: "Q", answer: "可以打车去故宫。", state: .completed, activity: nil, sources: [], trip: nil, memoryTags: [],
            rich: .init(cards: [taxi()]))
        #expect(LioTimelineTurn(message, richEnabled: false, places: .samples).cards.isEmpty)
        #expect(LioTimelineTurn(message, richEnabled: true, places: .samples).cards == [taxi()])
        let plain = LioTimelineWire.Message(id: "m2", question: "Q", answer: "好", state: .completed, activity: nil, sources: [], trip: nil, memoryTags: [])
        #expect(LioTimelineTurn(plain, richEnabled: true, places: .samples).cards.isEmpty)
    }
}
