import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

/// #1991 (58.1 D-3): the switch, the entities as the App checks them, the words drawn as places and the bubble card's data.
struct LioAnswerRichTests {
    // MARK: Helpers

    private static func place(_ id: String, zh: String, en: String, extra: String = "") -> String {
        #"{"id":"\#(id)","name_zh":"\#(zh)","name_en":"\#(en)","category":"attraction"\#(extra)}"#
    }

    private static let library = LioPlaceRepository(data: Data("""
        {"places":[
        \(place("pl_bj_gugong", zh: "故宫博物院", en: "The Palace Museum", extra: #","intro_short_zh":"明清两代的皇宫。","intro_short_en":"The imperial palace.","ticket":{"booking":"required","closed_weekdays":[1]},"lat":39.918058,"lng":116.397026"#)),
        \(place("pl_bj_jingshan", zh: "景山公园", en: "Jingshan Park")),
        \(place("pl_bj_wangfujing", zh: "王府井", en: "Wangfujing")),
        \(place("pl_bj_tiantan", zh: "天坛公园", en: "Temple of Heaven")),
        \(place("pl_bj_tiananmen", zh: "天安门", en: "Tiananmen")),
        \(place("pl_bj_yiheyuan", zh: "颐和园", en: "Summer Palace"))]}
        """.utf8))

    private func entity(_ start: Int, _ end: Int, _ id: String = "pl_bj_gugong") -> LioTimelineWire.Entity {
        .init(start: start, end: end, placeID: id)
    }

    private func resolve(_ answer: String, _ entities: [LioTimelineWire.Entity]) -> [LioPlaceSpan] {
        LioPlaceMentions.resolve(answer: answer, entities: entities, in: Self.library)
    }

    /// The text each span covers, counted in scalars.
    private func pieces(_ answer: String, _ spans: [LioPlaceSpan]) -> [String] {
        let scalars = Array(answer.unicodeScalars)
        return spans.map { span in
            var text = String.UnicodeScalarView()
            text.append(contentsOf: scalars[span.start..<span.end])
            return String(text)
        }
    }

    private var root: URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { url.deleteLastPathComponent() }
        return url
    }

    // MARK: The switch

    @Test func theSwitchIsOffByDefaultAndListedAndOnInTheRelease() throws {
        #expect(LioAnswerRichFeature.infoKey == "G2CAnswerRichEnabled")
        #expect(LioAnswerRichFeature.enabled(infoValue: "YES"))
        for value: Any? in [nil, "", "NO", "yes", "1", true, 1, "$(G2C_ANSWER_RICH_ENABLED)"] {
            #expect(!LioAnswerRichFeature.enabled(infoValue: value), "\(String(describing: value))")
        }
        #expect(!LioAnswerRichFeature.enabledInBuild, "the test bundle sets no flag")
        let ios = root.appendingPathComponent("ios")
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        #expect(plist.contains("<key>G2CAnswerRichEnabled</key><string>$(G2C_ANSWER_RICH_ENABLED)</string>"))
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(!project.contains("G2C_ANSWER_RICH_ENABLED"), "the setting stays unset in the project")
        let manifestURL = root.appendingPathComponent("tooling/release/app_flags.json")
        let manifest = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any])
        let flags = try #require(manifest["flags"] as? [[String: String]])
        #expect(flags.contains(["setting": "G2C_ANSWER_RICH_ENABLED", "plist": "G2CAnswerRichEnabled"]))
        let release = try #require(manifest["release"] as? [String: Any])
        // On for the 58.1 TestFlight build (coordinator, under JT's pre-authorisation, 2026-11-28, stop point 6); the setting itself stays unset in the project.
        #expect((try #require(release["on"] as? [String])).contains("G2C_ANSWER_RICH_ENABLED"))
    }

    @Test func aTurnReadsPlacesOnlyWhenTheSwitchIsOn() {
        let answer = "上午去故宫博物院。"
        let message = LioTimelineWire.Message(
            id: "m1", question: "Q", answer: answer, state: .completed, activity: nil, sources: [], trip: nil, memoryTags: [],
            rich: .init(entities: [entity(3, 8)]))
        let off = LioTimelineTurn(message, richEnabled: false, places: Self.library)
        #expect(off.places.isEmpty)
        let on = LioTimelineTurn(message, richEnabled: true, places: Self.library)
        #expect(on.places == [LioPlaceSpan(start: 3, end: 8, placeID: "pl_bj_gugong")])
        let plain = LioTimelineTurn(.init(id: "m2", question: "Q", answer: answer, state: .completed, activity: nil,
                                          sources: [], trip: nil, memoryTags: []), richEnabled: true, places: Self.library)
        #expect(plain.places.isEmpty && plain.answer == answer)
    }

    // MARK: Entities against the text

    @Test func chineseRangesAreScalarsOfTheWholeAnswer() {
        let answer = "上午去故宫博物院，下午去景山公园。"
        let spans = resolve(answer, [entity(3, 8), entity(12, 16, "pl_bj_jingshan")])
        #expect(pieces(answer, spans) == ["故宫博物院", "景山公园"])
        #expect(spans.map(\.placeID) == ["pl_bj_gugong", "pl_bj_jingshan"])
    }

    /// The contract's own example: after the emoji the UTF-16 offset is one more than the scalar offset.
    @Test func anEmojiBeforeAPlaceMovesUTF16ButNotScalars() {
        let answer = "上午去**故宫**，下午去景山公园看全景😀。\n\n晚上可以去王府井走走。"
        #expect(Array(answer.unicodeScalars).count == 35 && answer.utf16.count == 36)
        let spans = resolve(answer, [entity(5, 7), entity(13, 17, "pl_bj_jingshan"), entity(29, 32, "pl_bj_wangfujing")])
        #expect(pieces(answer, spans) == ["故宫", "景山公园", "王府井"])
        // A reader that counted UTF-16 would be one late: the same numbers give a different piece.
        #expect(String(decoding: Array(answer.utf16)[30..<33], as: UTF16.self) == "王府井", "王府井 is [30,33) in UTF-16")
        #expect(pieces(answer, resolve(answer, [entity(30, 33, "pl_bj_wangfujing")])) != ["王府井"], "and those numbers are not it in scalars")
    }

    @Test(arguments: [
        ("👨‍👩‍👧‍👦 去故宫", 9, 11), ("🇨🇳 欢迎来到北京，先去天坛看看。", 12, 14),
        ("e\u{301}故宫", 2, 4), ("👍🏽故宫", 2, 4), ("故宫\r\n景山公园", 0, 2),
    ]) func rangesAfterCombinedCharactersStillLineUp(answer: String, start: Int, end: Int) {
        let spans = resolve(answer, [entity(start, end)])
        #expect(spans.count == 1)
        #expect(pieces(answer, spans).first.map { ["故宫", "天坛"].contains($0) } == true, "\(pieces(answer, spans))")
    }

    @Test(arguments: [
        ("🇨🇳 欢迎来到北京，先去天坛看看。", 1, 4),     // starts inside a flag
        ("🇨🇳 欢迎", 0, 1),                            // ends inside a flag
        ("👨‍👩‍👧‍👦故宫", 1, 5),                       // starts after a joiner
        ("👨‍👩‍👧‍👦故宫", 0, 3),                       // ends inside the family
        ("e\u{301}故宫", 1, 4),                       // starts between a letter and its accent
        ("👍🏽故宫", 1, 4),                            // starts between an emoji and its skin tone
        ("故宫\r\n景山公园", 0, 3),                    // ends between CR and LF
    ]) func aRangeThatCutsACharacterIsDropped(answer: String, start: Int, end: Int) {
        #expect(resolve(answer, [entity(start, end)]).isEmpty)
    }

    @Test func lineBreaksBlanksAndMarkdownCharactersAreNotPlaces() {
        let answer = "天安门。\n\n第二天去颐和园。 景山公园 *故宫* 王府井"
        #expect(resolve(answer, [entity(1, 8, "pl_bj_tiananmen")]).isEmpty, "crosses the blank line")
        #expect(resolve(answer, [entity(3, 5, "pl_bj_tiananmen")]).isEmpty, "the full stop and a newline")
        #expect(resolve(answer, [entity(10, 15, "pl_bj_yiheyuan")]).isEmpty, "ends in a space")
        #expect(resolve(answer, [entity(14, 18, "pl_bj_jingshan")]).isEmpty, "begins with a space")
        #expect(resolve(answer, [entity(20, 24)]).isEmpty, "a Markdown asterisk inside")
        #expect(pieces(answer, resolve(answer, [entity(15, 19, "pl_bj_jingshan")])) == ["景山公园"], "the same word without the blanks")
        let marks = ["[故宫", "故宫]", "故(宫", "故宫_", "故宫`", "故宫#", "故宫|", "故宫\\", "故宫~", "故宫!", "故宫<", "故宫>"]
        for text in marks {
            #expect(resolve(text, [entity(0, text.unicodeScalars.count)]).isEmpty, "\(text)")
        }
        for text in ["故宫\n", "故\u{2028}宫", "故宫\u{85}", "故\u{0}宫", "故\t宫"] {
            #expect(resolve(text, [entity(0, text.unicodeScalars.count)]).isEmpty, "\(text.unicodeScalars.map(\.value))")
        }
    }

    @Test func rangesOutsideTheTextAreDropped() {
        let answer = "上午去故宫。"
        #expect(resolve(answer, [entity(3, 5)]).count == 1)
        #expect(resolve(answer, [entity(3, 7)]).isEmpty, "past the end")
        #expect(resolve(answer, [entity(6, 8)]).isEmpty)
        #expect(resolve(answer, [entity(100, 102)]).isEmpty)
        #expect(resolve(answer, [entity(-1, 2)]).isEmpty)
        #expect(resolve(answer, [entity(3, 3)]).isEmpty && resolve(answer, [entity(3, 4)]).isEmpty)
        #expect(resolve(answer, [entity(3, 2)]).isEmpty && resolve(answer, [entity(Int.max - 1, Int.max)]).isEmpty)
        #expect(resolve(answer, [entity(Int.min, Int.max)]).isEmpty)
        #expect(resolve(answer, [entity(0, 33)]).isEmpty, "longer than 32 scalars")
        #expect(resolve(String(repeating: "甲", count: 40), [entity(0, 33)]).isEmpty)
    }

    @Test func emptyInputsGiveNothing() {
        #expect(resolve("", [entity(0, 2)]).isEmpty)
        #expect(resolve("上午去故宫。", []).isEmpty)
        #expect(resolve("", []).isEmpty)
    }

    @Test func overlappingOrUnorderedRangesDropTheWholeList() {
        let answer = "上午去故宫博物院，下午去景山公园。"
        #expect(resolve(answer, [entity(3, 8), entity(6, 16, "pl_bj_jingshan")]).isEmpty, "overlap")
        #expect(resolve(answer, [entity(12, 16, "pl_bj_jingshan"), entity(3, 8)]).isEmpty, "out of order")
        #expect(resolve(answer, [entity(3, 8), entity(3, 8, "pl_bj_jingshan")]).isEmpty, "same range twice")
        #expect(pieces(answer, resolve(answer, [entity(3, 8), entity(8, 9, "pl_bj_jingshan")])) == ["故宫博物院"], "touching is not overlapping")
        #expect(resolve(answer, [entity(3, 8), entity(12, 16, "pl_bj_jingshan")]).count == 2)
    }

    @Test func onlyTheFirstMentionOfAPlaceIsKept() {
        let answer = "故宫很大，故宫很美，景山公园也不错。"
        let spans = resolve(answer, [entity(0, 2), entity(5, 7), entity(10, 14, "pl_bj_jingshan")])
        #expect(pieces(answer, spans) == ["故宫", "景山公园"])
    }

    @Test func aPlaceTheLibraryDoesNotHaveStaysPlainText() {
        let answer = "上午去故宫，下午去某个新地方。"
        #expect(resolve(answer, [entity(3, 5, "pl_bj_not_in_library")]).isEmpty)
        #expect(resolve(answer, [entity(3, 5, "PL_BJ_GUGONG")]).isEmpty, "a malformed id")
        #expect(resolve(answer, [entity(3, 5, "pl_bj_gugong")]).count == 1)
        let spans = LioPlaceMentions.resolve(answer: answer, entities: [entity(3, 5)]) { _ in false }
        #expect(spans.isEmpty)
    }

    /// Nothing the server (or a damaged copy of what it sent) can say makes this crash, and what comes out always fits.
    @Test func randomEntitiesNeverCrashAndEverySpanIsSound() {
        var generator = SystemRandomNumberGenerator()
        let alphabet: [String] = ["故", "宫", "a", "b", " ", "\n", "😀", "🇨🇳", "👨‍👩‍👧‍👦", "e\u{301}", "*", "，", "\r\n", "👍🏽"]
        for _ in 0..<400 {
            let answer = (0..<Int.random(in: 0...40, using: &generator)).map { _ in alphabet.randomElement(using: &generator)! }.joined()
            let count = answer.unicodeScalars.count
            let entities = (0..<Int.random(in: 0...6, using: &generator)).map { _ in
                let start = Int.random(in: -3...(count + 3), using: &generator)
                return entity(start, start + Int.random(in: -2...34, using: &generator),
                              ["pl_bj_gugong", "pl_bj_jingshan", "pl_bj_nope", "x"].randomElement(using: &generator)!)
            }
            let spans = resolve(answer, entities)
            var cursor = 0
            var boundaries = Set<Int>([0]); var at = 0
            for character in answer { at += character.unicodeScalars.count; boundaries.insert(at) }
            for (span, piece) in zip(spans, pieces(answer, spans)) {
                #expect(span.start >= cursor && span.end <= count && (2...32).contains(span.end - span.start))
                #expect(boundaries.contains(span.start) && boundaries.contains(span.end))
                #expect(!piece.contains("\n") && !piece.contains("*") && piece == piece.trimmingCharacters(in: .whitespaces))
                cursor = span.end
            }
            #expect(Set(spans.map(\.placeID)).count == spans.count)
        }
    }

    // MARK: The contract's examples

    private struct Examples: Decodable {
        struct Example: Decodable {
            let name: String
            let answer: String
            let rich: AnyJSON
            let pieces: [String]?
        }
        let answers: [String: String]
        let valid: [Example]
        let invalid: [Example]
    }

    /// Any JSON value, kept as bytes so a row can carry it exactly as the example has it.
    private struct AnyJSON: Decodable {
        let data: Data
        init(from decoder: Decoder) throws {
            let value = try decoder.singleValueContainer().decode(JSONValue.self)
            data = try JSONEncoder().encode(value)
        }
    }

    private indirect enum JSONValue: Codable {
        case null, bool(Bool), number(Double), string(String), array([JSONValue]), object([String: JSONValue])
        init(from decoder: Decoder) throws {
            let c = try decoder.singleValueContainer()
            if c.decodeNil() { self = .null }
            else if let v = try? c.decode(Bool.self) { self = .bool(v) }
            else if let v = try? c.decode(Int.self) { self = .number(Double(v)) }
            else if let v = try? c.decode(Double.self) { self = .number(v) }
            else if let v = try? c.decode(String.self) { self = .string(v) }
            else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
            else { self = .object(try c.decode([String: JSONValue].self)) }
        }
        func encode(to encoder: Encoder) throws {
            var c = encoder.singleValueContainer()
            switch self {
            case .null: try c.encodeNil()
            case .bool(let v): try c.encode(v)
            case .number(let v): v == v.rounded() && abs(v) < 1e15 ? try c.encode(Int(v)) : try c.encode(v)
            case .string(let v): try c.encode(v)
            case .array(let v): try c.encode(v)
            case .object(let v): try c.encode(v)
            }
        }
    }

    private func examples() throws -> Examples {
        try JSONDecoder().decode(Examples.self,
            from: Data(contentsOf: root.appendingPathComponent("contracts/message/lio-answer-rich-examples.1.json")))
    }

    /// The example as a timeline row, read the way the App reads the server's page.
    private func spans(for example: Examples.Example, in answers: [String: String]) throws -> [LioPlaceSpan] {
        let answer = try #require(answers[example.answer])
        let answerJSON = String(decoding: try JSONEncoder().encode(answer), as: UTF8.self)
        let rich = String(decoding: example.rich.data, as: UTF8.self)
        let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"
        let page = Data("""
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[
            {"message_id":"m1","text":"Q","answer":\(answerJSON),"status":"completed","sources":[],"rich":\(rich)}],"next_before":null}
            """.utf8)
        let message = try #require(LioTimelineWire.decodePage(page, for: conversation, version: .v2).messages.first)
        let all = LioPlaceRepository(places: [
            "pl_bj_gugong", "pl_bj_jingshan", "pl_bj_wangfujing", "pl_bj_tiantan", "pl_bj_tiananmen", "pl_bj_yiheyuan",
            "pl_bj_x", "pl_bj_p0",
        ].compactMap { id in LioPlaceRepository.places(in: Data("[\(Self.place(id, zh: "名", en: "N"))]".utf8)).first })
        return LioPlaceMentions.resolve(answer: answer, entities: message.rich?.entities ?? [], in: all)
    }

    @Test func everyValidEntityExampleResolvesToItsPieces() throws {
        let all = try examples()
        var checked = 0
        for example in all.valid {
            guard let expected = example.pieces else { continue }
            let found = try spans(for: example, in: all.answers)
            // The example's ids are the library's (`pl_bj_*`); the test library above has them all.
            #expect(pieces(try #require(all.answers[example.answer]), found) == expected, "\(example.name)")
            checked += 1
        }
        #expect(checked >= 4, "the four entity examples")
    }

    @Test func theInvalidEntityExamplesNeverBecomeWrongWords() throws {
        let all = try examples()
        let expected: [String: [String]] = [
            "wrong version": [], "empty entities": [], "21 entities": [],
            "start equals end": ["景山公园", "王府井"], "span of 1 scalar": ["景山公园", "王府井"],
            "span of 33 scalars": ["景山公园", "王府井"], "negative offset": ["景山公园", "王府井"],
            "float offset": ["景山公园", "王府井"],
            "overlapping entities": [], "entities out of order": [],
            "same place linked twice": ["故宫", "王府井"],
            "place id in capitals": ["景山公园", "王府井"], "place id without a short name": ["景山公园", "王府井"],
            "entity type poi": ["景山公园", "王府井"],
            "span past the end of the answer": ["故宫", "景山公园"],
            "span with edge blank": [], "span crossing the blank line": [], "span cutting a flag emoji": [],
        ]
        var seen = Set<String>()
        for example in all.invalid {
            guard let want = expected[example.name] else { continue }
            let found = try spans(for: example, in: all.answers)
            #expect(pieces(try #require(all.answers[example.answer]), found) == want, "\(example.name)")
            seen.insert(example.name)
        }
        #expect(seen == Set(expected.keys), "every named example was found: \(Set(expected.keys).subtracting(seen))")
    }

    @Test func everyExampleOfTheContractReadsWithoutFailingThePage() throws {
        let all = try examples()
        for example in all.valid + all.invalid {
            _ = try spans(for: example, in: all.answers)
        }
    }

    // MARK: Words in the answer

    @Test func placeWordsBecomeLinksOnlyThisRenderCanMake() throws {
        let source = "上午去**故宫**，下午去景山公园。"
        let spans = [LioPlaceSpan(start: 5, end: 7, placeID: "pl_bj_gugong"), LioPlaceSpan(start: 13, end: 17, placeID: "pl_bj_jingshan")]
        let plain = try #require(LioReplyMarkdown.render(source))
        let value = try #require(LioReplyMarkdown.render(source, places: spans))
        #expect(String(value.characters) == String(plain.characters), "the words are the same; only links are added")
        let bold = value.runs.first { String(value[$0.range].characters) == "故宫" }
        #expect(bold?.inlinePresentationIntent?.contains(.stronglyEmphasized) == true, "a bold place stays bold")
        let links = value.runs.compactMap { run in run.link.map { (String(value[run.range].characters), $0) } }
        #expect(links.map(\.0) == ["故宫", "景山公园"])
        #expect(links.compactMap { LioPlaceLinkMarker.placeID(in: $0.1) } == ["pl_bj_gugong", "pl_bj_jingshan"])
        #expect(Set(links.map { $0.1.scheme }).count == 1, "one nonce for the whole render")
        let again = try #require(LioReplyMarkdown.render(source, places: spans))
        let schemes = Set(value.runs.compactMap { $0.link?.scheme } + again.runs.compactMap { $0.link?.scheme })
        #expect(schemes.count == 2, "a fresh nonce for each render")
        #expect(links.allSatisfy { $0.1.scheme?.hasPrefix(LioPlaceLinkMarker.schemePrefix) == true })
    }

    @Test func withoutPlacesTheRenderIsWhatItWas() throws {
        let source = "Try **a museum** and [a walk](https://example.com/walk)."
        #expect(LioReplyMarkdown.render(source) == LioReplyMarkdown.render(source, places: []))
    }

    @Test func aPlaceLinkTheModelWroteIsRemovedWhateverItSays() throws {
        let forged = "去[故宫](g2c-place-0000000000000000:pl_bj_gugong)看看，或者[这里](g2c-place:pl_bj_gugong)、[那里](G2C-PLACE-1:pl_bj_gugong)。"
        let without = try #require(LioReplyMarkdown.render(forged))
        #expect(without.runs.allSatisfy { $0.link == nil }, "no places asked for: every such link goes")
        // With real places on, the same forged links still go and only the real one stays.
        let withReal = try #require(LioReplyMarkdown.render(forged, places: [LioPlaceSpan(start: 0, end: 1, placeID: "pl_bj_gugong")]))
        let links = withReal.runs.compactMap { $0.link }
        #expect(links.count == 1)
        #expect(String(withReal[withReal.runs.first { $0.link != nil }!.range].characters) == "去")
        #expect(!String(withReal.characters).contains("g2c-place"), "no raw link text is left in the answer")
    }

    @Test func otherLinksKeepTheirRules() throws {
        let source = "看[官网](https://example.com/a)和[怪链接](javascript:alert(1))，去故宫。"
        let at = source.unicodeScalars.distance(from: source.startIndex, to: try #require(source.range(of: "故宫")).lowerBound)
        let value = try #require(LioReplyMarkdown.render(source, places: [LioPlaceSpan(start: at, end: at + 2, placeID: "pl_bj_gugong")]))
        let links = value.runs.compactMap { $0.link }
        #expect(links.contains { $0.scheme == "https" })
        #expect(!links.contains { $0.scheme == "javascript" })
        #expect(links.compactMap { LioPlaceLinkMarker.placeID(in: $0) } == ["pl_bj_gugong"])
    }

    @Test func spansThatDoNotFitTheSourceStayPlainText() throws {
        let marker = LioPlaceLinkMarker()
        let source = "去故宫"
        let marked = marker.mark(source, spans: [.init(start: 1, end: 3, placeID: "pl_bj_gugong"), .init(start: 2, end: 9, placeID: "pl_bj_x")])
        #expect(marked.words.map(\.placeID) == ["pl_bj_gugong"])
        #expect(marked.text.unicodeScalars.filter { $0.value < 0xF0000 }.map(String.init).joined() == source, "only marks were added")
        #expect(marked.text.unicodeScalars.count == source.unicodeScalars.count + 2)
        #expect(marker.mark(source, spans: []).text == source)
        #expect(marker.mark(source, spans: [.init(start: 5, end: 7, placeID: "pl_bj_gugong")]).text == source)
        #expect(marker.mark("", spans: [.init(start: 0, end: 2, placeID: "pl_bj_gugong")]).text == "")
    }

    @Test func marksAreRandomPerRenderAndAnythingLikeThemInTheModelsTextIsReplaced() {
        let one = LioPlaceLinkMarker(), two = LioPlaceLinkMarker()
        #expect(one.scheme != two.scheme && one.open != one.close)
        #expect((0xF0000...0xFFFFD).contains(one.open.value) && (0xF0000...0xFFFFD).contains(one.close.value))
        let hostile = "去" + String(one.open) + "故宫" + String(one.close) + "，再去景山公园"
        let marked = one.mark(hostile, spans: [.init(start: 2, end: 4, placeID: "pl_bj_gugong")])
        #expect(marked.text.unicodeScalars.filter { $0 == one.open }.count == 1, "only the real open mark")
        #expect(marked.text.unicodeScalars.filter { $0 == one.close }.count == 1)
        #expect(marked.text.contains("\u{FFFD}"), "the model's copies were replaced, one for one")
        #expect(marked.text.unicodeScalars.count == hostile.unicodeScalars.count + 2)
    }

    @Test func marksThatDoNotComeBackInOrderGiveNoLinksAndNoLeftovers() {
        let marker = LioPlaceLinkMarker()
        let words = [LioPlaceSpan(start: 0, end: 2, placeID: "pl_bj_gugong")]
        func text(_ pieces: [String]) -> AttributedString { AttributedString(pieces.joined()) }
        let o = String(marker.open), c = String(marker.close)
        let good = marker.link(text(["去", o, "故宫", c, "。"]), words: words)
        #expect(String(good.characters) == "去故宫。" && good.runs.compactMap(\.link).count == 1)
        for broken in [["去", o, "故宫", "。"], ["去", c, "故宫", o, "。"], ["去", o, "故", o, "宫", c, "。"], [o, c, "故宫"]] {
            let result = marker.link(text(broken), words: words)
            #expect(result.runs.allSatisfy { $0.link == nil }, "\(broken.count)")
            #expect(!result.unicodeScalars.contains { $0 == marker.open || $0 == marker.close }, "no mark is left")
        }
        let more = marker.link(text(["去", o, "故宫", c, "和", o, "景山", c]), words: words)
        #expect(more.runs.allSatisfy { $0.link == nil }, "more marks than words")
        #expect(String(more.characters) == "去故宫和景山")
    }

    @Test func aLinkIsReadBackToItsPlaceIdOrNothing() throws {
        let marker = LioPlaceLinkMarker()
        let url = try #require(URL(string: "\(marker.scheme):pl_bj_gugong"))
        #expect(LioPlaceLinkMarker.placeID(in: url) == "pl_bj_gugong" && marker.owns(url))
        for text in ["https://example.com/pl_bj_gugong", "g2c-place-1:PL_BJ_X", "g2c-place-1:", "g2c-place-1:pl_bj_", "go2china://tool/taxi"] {
            #expect(LioPlaceLinkMarker.placeID(in: URL(string: text)!) == nil, "\(text)")
        }
        #expect(LioPlaceLinkMarker.isPlaceLink(URL(string: "g2c-place-1:x")!) && !LioPlaceLinkMarker.isPlaceLink(URL(string: "https://a.b")!))
    }

    // MARK: Two bubbles

    @Test func placeRangesFollowTheirWordsIntoTheirBubble() {
        let answer = "第一天看天安门。\n\n第二天去颐和园。"
        let parts = LioAnswerParts(answer)
        let spans = resolve(answer, [entity(4, 7, "pl_bj_tiananmen"), entity(14, 17, "pl_bj_yiheyuan")])
        #expect(spans.count == 2)
        let split = parts.places(spans)
        #expect(pieces(parts.head, split.head) == ["天安门"])
        #expect(pieces(try! #require(parts.tail), split.tail) == ["颐和园"])
        #expect(split.tail.first?.start == 4, "counted from the start of the second bubble")
    }

    @Test func oneBubbleKeepsEveryRangeAsItWas() {
        let answer = "第一天看天安门。\n\n第二天去颐和园。"
        let whole = LioAnswerParts(whole: answer)
        let spans = resolve(answer, [entity(4, 7, "pl_bj_tiananmen"), entity(14, 17, "pl_bj_yiheyuan")])
        #expect(whole.places(spans).head == spans && whole.places(spans).tail.isEmpty)
    }

    @Test func rangesAfterEmojiAndExtraNewlinesStillLandOnTheirWords() {
        let answer = "先去故宫😀。\n\n\n\n再去景山公园。"
        let parts = LioAnswerParts(answer)
        #expect(parts.tail == "再去景山公园。")
        let spans = resolve(answer, [entity(2, 4), entity(12, 16, "pl_bj_jingshan")])
        #expect(pieces(answer, spans) == ["故宫", "景山公园"])
        let split = parts.places(spans)
        #expect(pieces(parts.head, split.head) == ["故宫"])
        #expect(pieces(parts.tail!, split.tail) == ["景山公园"])
    }

    @Test func aSpanThatWouldCrossTheCutBelongsToNeitherBubble() {
        let parts = LioAnswerParts("甲乙丙。\n\n丁戊己。")
        let crossing = LioPlaceSpan(start: 3, end: 7, placeID: "pl_bj_x")
        #expect(parts.places([crossing]).head.isEmpty && parts.places([crossing]).tail.isEmpty)
    }

    @Test func aStreamingAnswerStillSplitsWithoutRanges() {
        for step in ["", "故", "故宫。\n", "故宫。\n\n", "故宫。\n\n景"] {
            let parts = LioAnswerParts(step)
            #expect(parts.places([]).head.isEmpty && parts.places([]).tail.isEmpty)
        }
    }

    // MARK: The card's words and data

    @Test func theCardKnowsThePlaceItIsFor() throws {
        let place = try #require(Self.library.place(id: "pl_bj_gugong"))
        let zh = LioPlacePresentation(place, language: .chinese)
        #expect(zh.title == "故宫博物院" && zh.subtitle == "The Palace Museum")
        #expect(zh.oneLiner == "明清两代的皇宫。")
        #expect(zh.bubbleHint == "需要预约 · 周一闭馆")
        let en = LioPlacePresentation(place, language: .english)
        #expect(en.title == "The Palace Museum" && en.subtitle == "故宫博物院" && en.oneLiner == "The imperial palace.")
        #expect(en.bubbleHint == "Booking required · Closed Mondays")
        let bare = try #require(Self.library.place(id: "pl_bj_jingshan"))
        #expect(LioPlacePresentation(bare, language: .chinese).bubbleHint == nil, "no hint when the library has none")
    }

    @Test func aPlaceFromTheDevelopmentPackIsMarkedOnTheCard() throws {
        let place = try #require(Self.library.place(id: "pl_bj_gugong"))
        #expect(LioPlacePresentation(place, language: .chinese).developmentLabel == nil)
        let marked = LioPlacePresentation(place, language: .chinese, developmentData: true)
        #expect(marked.developmentLabel == "开发数据" && marked.developmentNote?.isEmpty == false)
        #expect(Self.library.isDevelopmentData(place) == false, "the test library is not the pack")
    }

    @Test func aPlaceWithAnAddressAndAPointOffersAllButtonsThatCanWork() throws {
        let place = try #require(Self.library.place(id: "pl_bj_gugong"))
        let all = LioPlacePresentation(place, language: .chinese).actions { _ in true }
        #expect(all.actions == [.taxi, .driver, .navigate, .book])
        #expect(all.taxi?.parameters["destination"] == "故宫博物院" && all.taxi?.parameters["lat"] == "39.918058")
        let none = LioPlacePresentation(place, language: .chinese).actions { _ in false }
        #expect(none.actions == [.driver, .navigate], "no tool, no taxi or booking button; the rest never need one")
    }

    @Test func wordsAreInBothLanguagesAndPlaceholdersAreListed() {
        for word in LioPlaceBubbleCopy.allCases {
            #expect(!word.text(.english).isEmpty && !word.text(.chinese).isEmpty && word.text(.english) != word.text(.chinese), "\(word.rawValue)")
        }
        #expect(LioPlaceBubbleCopy.more.text(.chinese) == "更多" && LioPlaceBubbleCopy.more.text(.english) == "See more")
        #expect(LioPlaceBubbleCopy.allCases.filter(\.isPlaceholder).map(\.rawValue).sorted()
                == ["place.bubble.added", "place.bubble.already_added", "place.bubble.close", "place.mention.hint", "place.mention.kind"])
    }

    @Test func theCopyKeysThatAreInTheCopyFileAreExactlyAsItSaysThem() throws {
        let url = root.deletingLastPathComponent().appendingPathComponent("codex-inbox/G4/ui-copy.json")
        guard let data = try? Data(contentsOf: url) else { return }   // the copy file lives outside the repository
        let copy = try #require(JSONSerialization.jsonObject(with: data) as? [String: [String: String]])
        for word in LioPlaceBubbleCopy.allCases where !word.isPlaceholder {
            #expect(copy[word.rawValue]?["zh"] == word.text(.chinese), "\(word.rawValue)")
            #expect(copy[word.rawValue]?["en"] == word.text(.english), "\(word.rawValue)")
        }
    }

    @Test func voiceOverReadsTheNameAndThenPlace() {
        #expect(LioPlaceBubbleCopy.spoken("故宫博物院", .chinese) == "故宫博物院，地点")
        #expect(LioPlaceBubbleCopy.spoken("The Palace Museum", .english) == "The Palace Museum, place")
    }

    // MARK: Add to trip

    @MainActor private func store() -> (LioTripCanvasStore, URL) {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("LioPlaceTripAdd-\(UUID().uuidString)", isDirectory: true)
        return (LioTripCanvasStore(directory: directory, isCurrent: { true }), directory)
    }

    @MainActor @Test func addingAPlaceKeepsItOnTheWantToGoList() throws {
        let (store, directory) = store()
        defer { try? FileManager.default.removeItem(at: directory) }
        let place = try #require(Self.library.place(id: "pl_bj_gugong"))
        #expect(store.addWish(place, plan: nil) == .added)
        let canvas = try #require(try store.canvas(for: LioTripCanvas.standaloneID))
        let wish = try #require(canvas.wishlist.first)
        #expect(wish.placeID == "pl_bj_gugong" && wish.nameZH == "故宫博物院" && wish.nameEN == "The Palace Museum")
        #expect(wish.coordinate == .init(latitude: 39.918058, longitude: 116.397026))
        #expect(store.addWish(place, plan: nil) == .alreadyThere, "twice changes nothing")
        #expect(try store.canvas(for: LioTripCanvas.standaloneID)?.wishlist.count == 1)
        let other = try #require(Self.library.place(id: "pl_bj_jingshan"))
        #expect(store.addWish(other, plan: nil) == .added)
        #expect(try store.canvas(for: LioTripCanvas.standaloneID)?.wishlist.count == 2)
    }

    @MainActor @Test func aCanvasFileFromANewerAppIsNeverWrittenOver() throws {
        let (store, directory) = store()
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent(LioTripCanvasStore.fileName)
        let newer = Data(#"{"version":99,"canvases":[]}"#.utf8)
        try newer.write(to: file)
        let place = try #require(Self.library.place(id: "pl_bj_gugong"))
        #expect(store.addWish(place, plan: nil) == .failed)
        #expect(try Data(contentsOf: file) == newer)
    }

    @MainActor @Test func aStoreThatIsNoLongerTheSessionsFails() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("LioPlaceTripAdd-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripCanvasStore(directory: directory, isCurrent: { false })
        #expect(store.addWish(try #require(Self.library.place(id: "pl_bj_gugong")), plan: nil) == .failed)
        #expect(!FileManager.default.fileExists(atPath: directory.path))
    }
}
