import Foundation
import Testing
@testable import CJMessageHTTP

/// #1993: `rich.cards` (LIO-answer-rich.1) as the App reads them, with the contract's own examples.
struct LioAnswerCardsWireTests {
    private let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"

    private var root: URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { url.deleteLastPathComponent() }
        return url
    }

    private func page(answer: String, rich: String, extra: String = "") -> Data {
        let answerJSON = String(decoding: (try? JSONEncoder().encode(answer)) ?? Data(), as: UTF8.self)
        return Data("""
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[
            {"message_id":"m1","text":"Q","answer":\(answerJSON),"status":"completed","sources":[]\(extra),"rich":\(rich)}],"next_before":null}
            """.utf8)
    }

    private func read(_ rich: String, answer: String = "可以打车去故宫。", extra: String = "") throws -> LioTimelineWire.Rich? {
        try LioTimelineWire.decodePage(page(answer: answer, rich: rich, extra: extra), for: conversation, version: .v2).messages.first?.rich
    }

    private func cards(_ json: String) -> String { #"{"version":"LIO-answer-rich.1","cards":\#(json)}"# }

    private let taxi = #"{"type":"taxi","label":"打车去这里","open":{"tool":"taxi","parameters":{"destination":"故宫博物院","lat":"39.918058","lng":"116.397026"}}}"#
    private let metro = #"{"type":"metro","label":"看地铁线路","open":{"tool":"metro-guide","parameters":{}},"data":{"city":{"id":"beijing","zh":"北京","en":"Beijing"}}}"#
    private let transport = #"{"type":"transport","label":"查火车和航班","open":{"tool":"transport","parameters":{"from":"beijing","to":"shanghai"}},"data":{"from":{"id":"beijing","zh":"北京","en":"Beijing"},"to":{"id":"shanghai","zh":"上海","en":"Shanghai"}}}"#
    private let currency = #"{"type":"currency","label":"汇率换算","open":{"tool":"currency","parameters":{}},"data":{"quote":"USD","cny_per_unit":"7.1234","as_of":"2026-11-26"}}"#

    // MARK: Reading

    @Test func threeCardsAreReadInTheContractsOrder() throws {
        let rich = try #require(try read(cards("[\(currency),\(transport),\(taxi)]")))
        #expect(rich.cards.map(\.kind) == [.taxi, .transport, .currency], "taxi, metro, transport, currency")
        #expect(rich.cards[0].parameters == ["destination": "故宫博物院", "lat": "39.918058", "lng": "116.397026"])
        #expect(rich.cards[1].detail == .transport(from: .init(id: "beijing", zh: "北京", en: "Beijing"),
                                                    to: .init(id: "shanghai", zh: "上海", en: "Shanghai")))
        #expect(rich.cards[1].parameters == ["from": "beijing", "to": "shanghai"])
        #expect(rich.cards[2].detail == .currency(quote: "USD", cnyPerUnit: "7.1234", asOf: "2026-11-26"))
        #expect(rich.cards[2].parameters.isEmpty)
    }

    @Test func aMetroCardKeepsTheCityAndIgnoresARouteThisAppDoesNotReadYet() throws {
        let withRoute = #"{"type":"metro","label":"Metro map","open":{"tool":"metro-guide","parameters":{}},"data":{"city":{"id":"beijing","zh":"北京","en":"Beijing"},"route":{"from":{"zh":"天安门西"},"to":{"zh":"王府井"},"lines":[{"zh":"1号线"}]}}}"#
        let card = try #require(try read(cards("[\(withRoute)]"))?.cards.first)
        #expect(card.kind == .metro && card.detail == .metro(city: .init(id: "beijing", zh: "北京", en: "Beijing")))
    }

    @Test func aCurrencyCardWithoutDataIsValid() throws {
        let bare = #"{"type":"currency","label":"Convert currency","open":{"tool":"currency","parameters":{}}}"#
        #expect(try read(cards("[\(bare)]"))?.cards == [.init(kind: .currency)])
        let quoteOnly = #"{"type":"currency","label":"汇率换算","open":{"tool":"currency","parameters":{}},"data":{"quote":"EUR"}}"#
        #expect(try read(cards("[\(quoteOnly)]"))?.cards.first?.detail == .currency(quote: "EUR", cnyPerUnit: nil, asOf: nil))
    }

    @Test func englishLabelsFromTheTableAreAccepted() throws {
        let english = #"{"type":"taxi","label":"Taxi there","open":{"tool":"taxi","parameters":{"destination":"故宫博物院","lat":"39.9","lng":"116.4","address":"景山前街4号","destinationEN":"The Palace Museum"}}}"#
        #expect(try read(cards("[\(english)]"))?.cards.first?.parameters.count == 5)
    }

    @Test func aCoordinateOutsideChinaIsNoDestinationOnlyTheTaxiPageOpens() throws {
        let london = #"{"type":"taxi","label":"打车去这里","open":{"tool":"taxi","parameters":{"destination":"Big Ben","lat":"51.5","lng":"-0.12"}}}"#
        #expect(try read(cards("[\(london)]"))?.cards == [.init(kind: .taxi)])
        for (lat, lng) in [("2.9", "116.4"), ("54.1", "116.4"), ("39.9", "72.9"), ("39.9", "136.1")] {
            let edge = london.replacingOccurrences(of: "51.5", with: lat).replacingOccurrences(of: "-0.12", with: lng)
            #expect(try read(cards("[\(edge)]"))?.cards == [.init(kind: .taxi)], "\(lat),\(lng)")
        }
        for (lat, lng) in [("3", "73"), ("54", "136"), ("39.918058", "116.397026")] {
            let edge = london.replacingOccurrences(of: "51.5", with: lat).replacingOccurrences(of: "-0.12", with: lng)
            #expect(try read(cards("[\(edge)]"))?.cards.first?.parameters["lat"] == lat, "\(lat),\(lng)")
        }
    }

    @Test(arguments: [
        #""39.1234567""#, #""39,5""#, #""1e1""#, #"" 39.5""#, #""39.""#, #"".5""#, #""abc""#, #""--1""#,
    ]) func aCoordinateThatIsNotAPlainDecimalDropsTheCard(lat: String) throws {
        let card = #"{"type":"taxi","label":"打车去这里","open":{"tool":"taxi","parameters":{"destination":"X","lat":\#(lat),"lng":"116.4"}}}"#
        #expect(try read(cards("[\(card),\(metro)]"))?.cards.map(\.kind) == [.metro])
    }

    @Test func richIsReadWhenOnlyOnePartIsGood() throws {
        let bad = #"{"type":"hotel","label":"x","open":{"tool":"hotels","parameters":{}}}"#
        let place = #"{"type":"place","start":4,"end":6,"place_id":"pl_bj_gugong"}"#
        let mixed = #"{"version":"LIO-answer-rich.1","entities":[\#(place)],"cards":[\#(bad)]}"#
        let rich = try #require(try read(mixed))
        #expect(rich.entities.count == 1 && rich.cards.isEmpty, "cards that fail leave the entities alone")
        let many = (0..<21).map { #"{"type":"place","start":\#($0 * 2),"end":\#($0 * 2 + 2),"place_id":"pl_bj_p\#($0)"}"# }.joined(separator: ",")
        let both = #"{"version":"LIO-answer-rich.1","entities":[\#(many)],"cards":[\#(taxi)]}"#
        let other = try #require(try read(both, answer: String(repeating: "甲乙", count: 30)))
        #expect(other.entities.isEmpty && other.cards.map(\.kind) == [.taxi], "entities over the limit leave the cards alone")
        #expect(try read(cards("[\(bad)]")) == nil, "nothing good in either part: no rich")
    }

    @Test func aPlanReplyCarriesNoCards() throws {
        let trip = #","trip":{"trip_id":"trip-1","title":"北京三日","days":[]}"#
        let place = #"{"type":"place","start":4,"end":6,"place_id":"pl_bj_gugong"}"#
        let rich = #"{"version":"LIO-answer-rich.1","entities":[\#(place)],"cards":[\#(taxi)]}"#
        let result = try read(rich, extra: trip)
        #expect(result?.cards.isEmpty == true && result?.entities.count == 1)
        #expect(try read(cards("[\(taxi)]"), extra: trip) == nil)
    }

    @Test func cardsNeverAppearOnARowThatIsNotCompletedWithAnAnswer() throws {
        let answering = Data("""
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[
            {"message_id":"m1","text":"Q","answer":"可以打车","status":"answering","sources":[],"rich":\(cards("[\(taxi)]"))}],"next_before":null}
            """.utf8)
        #expect(try LioTimelineWire.decodePage(answering, for: conversation, version: .v2).messages[0].rich == nil)
    }

    @Test func rateAndDayRules() {
        for good in ["7", "7.1", "0.5", "0.000001", "7.123456", "1234", "1234.5", "10"] { #expect(LioTimelineWire.validRate(good), "\(good)") }
        for bad in ["", "0", "0.0", "0.000000", "07.1", "00", "12345", "7.", ".5", "7.1234567", "-1", "1e3", "7,1", "7 ", "٧"] {
            #expect(!LioTimelineWire.validRate(bad), "\(bad)")
        }
        for good in ["2026-11-26", "2024-02-29", "2000-02-29", "2026-12-31"] { #expect(LioTimelineWire.validDay(good), "\(good)") }
        for bad in ["2026-13-01", "2026-00-10", "2026-02-29", "1900-02-29", "2026-04-31", "2026-1-1", "26-11-26", "2026/11/26", "2026-11-26 ", ""] {
            #expect(!LioTimelineWire.validDay(bad), "\(bad)")
        }
    }

    // MARK: The contract's examples

    private func examples() throws -> (answers: [String: String], valid: [[String: Any]], invalid: [[String: Any]]) {
        let data = try Data(contentsOf: root.appendingPathComponent("contracts/message/lio-answer-rich-examples.1.json"))
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        return (try #require(object["answers"] as? [String: String]), try #require(object["valid"] as? [[String: Any]]),
                try #require(object["invalid"] as? [[String: Any]]))
    }

    private func decode(_ example: [String: Any], _ answers: [String: String]) throws -> LioTimelineWire.Rich? {
        let rich = String(decoding: try JSONSerialization.data(withJSONObject: try #require(example["rich"])), as: UTF8.self)
        return try read(rich, answer: try #require(answers[example["answer"] as? String ?? ""]))
    }

    private func onlyCards(_ example: [String: Any]) -> Bool {
        guard let rich = example["rich"] as? [String: Any] else { return false }
        return rich["cards"] != nil && rich["entities"] == nil && rich["trip_receipt"] == nil && rich["memory"] == nil
    }

    @Test func everyValidCardExampleIsReadInFull() throws {
        let all = try examples()
        var checked = 0
        for example in all.valid where onlyCards(example) {
            let sent = (example["rich"] as? [String: Any])?["cards"] as? [[String: Any]] ?? []
            let rich = try #require(try decode(example, all.answers), "\(example["name"] ?? "")")
            #expect(rich.cards.map(\.kind.rawValue) == sent.compactMap { $0["type"] as? String }, "\(example["name"] ?? "")")
            checked += 1
        }
        #expect(checked == 8, "the eight card examples")
    }

    @Test func theInvalidCardExamplesLeaveOnlyWhatIsRight() throws {
        let all = try examples()
        let expected: [String: [String]] = [
            "empty cards": [], "four cards": [], "same card type twice": ["taxi"], "unknown card type": ["metro"],
            "tool that is not in the table": ["metro"], "card type and tool disagree": ["taxi"],
            "label not from the table": ["metro"], "taxi with half a destination": ["metro"],
            "taxi coordinate with 7 decimals": ["metro"], "taxi destination outside China": ["taxi", "metro"],
            "taxi parameter not in the table": ["metro"], "zero-width character in a parameter": ["metro"],
            "bidi character in a parameter": ["metro"], "parameter of 201 characters": ["metro"],
            "metro with parameters": ["taxi"], "metro without data": ["taxi"], "data text of 41 characters": ["taxi"],
            "transport from equals to": [], "transport data names other cities": [], "currency quote BTC": [],
            "currency rate without a date": [], "currency date without a rate": [], "currency rate zero": [],
            "currency rate zero-padded": [], "card carries the user position": ["taxi", "metro"],
        ]
        var seen = Set<String>()
        for example in all.invalid where onlyCards(example) {
            let name = example["name"] as? String ?? ""
            let kinds = try decode(example, all.answers)?.cards.map(\.kind.rawValue) ?? []
            #expect(kinds == expected[name], "\(name)")
            seen.insert(name)
        }
        #expect(seen == Set(expected.keys), "every named example was found: \(Set(expected.keys).subtracting(seen))")
    }

    @Test func theOutsideChinaExampleKeepsTheTaxiCardWithoutADestination() throws {
        let all = try examples()
        let example = try #require(all.invalid.first { ($0["name"] as? String) == "taxi destination outside China" })
        let taxi = try #require(try decode(example, all.answers)?.cards.first)
        #expect(taxi.kind == .taxi && taxi.parameters.isEmpty)
    }

    @Test func everyExampleOfTheContractReadsWithoutFailingThePage() throws {
        let all = try examples()
        for example in all.valid + all.invalid { _ = try decode(example, all.answers) }
    }
}
