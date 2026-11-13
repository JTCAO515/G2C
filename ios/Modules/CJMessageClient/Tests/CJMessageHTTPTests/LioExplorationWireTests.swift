import Foundation
import Testing
@testable import CJMessageHTTP

struct LioExplorationWireTests {
    private func examples() throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        return try #require(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("contracts/message/lio-exploration-examples.4.json"))) as? [String: Any])
    }
    private func example(_ name: String) throws -> [String: Any] { try #require(try examples()[name] as? [String: Any]) }
    private func data(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes]) }
    private func change(_ value: Any, path: [Any], to changed: Any) throws -> Any {
        guard !path.isEmpty else { return changed }
        var rest = path; let first = rest.removeFirst()
        if let index = first as? Int {
            var rows = try #require(value as? [Any]);rows[index] = try change(rows[index], path: rest, to: changed);return rows
        }
        var fields = try #require(value as? [String: Any]);let key = try #require(first as? String)
        fields[key] = try change(fields[key] ?? NSNull(), path: rest, to: changed);return fields
    }
    private let row: [Any] = ["messages", 0]

    @Test(arguments: ["zh", "en", "waiting", "planning_started", "structured4_undated", "structured4_dated", "legacy_card2"])
    func allFrozenExamplesRetainTheirNewFieldsAndOldReadersRejectThem(_ name: String) throws {
        let input = try data(example(name)), page = try LioExplorationWire.decodePage(input)
        #expect(page.inputUTF8 == input)
        #expect(page.messages.count == 1)
        #expect(page.conversationID == "lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        #expect(throws: Error.self) { try LioTimelineWire.decodePage(input) }
        #expect(throws: Error.self) { try LioTimelineWire.decodePage(input, version: .v2) }
        if name == "zh" || name == "en" {
            let message = try #require(page.messages.first)
            #expect(message.segments.first?.purpose == .direction)
            #expect(message.questions[0].multiple)
            #expect(message.questions[0].options.map(\.id) == ["interests.history", "interests.food", "interests.nature"])
            #expect(message.exits.count == 2)
        }
    }

    @Test func cardThreeKeepsItsRealIdentityCalendarAndRestDays() throws {
        for name in ["structured4_undated", "structured4_dated"] {
            let page = try LioExplorationWire.decodePage(data(example(name)))
            guard case .rich(let card) = page.messages[0].trip else { Issue.record("rich Card3 required"); return }
            #expect(card.days.map(\.index) == [1, 2, 3])
            #expect(card.days.map { $0.items.count } == [1, 0, 0])
            if name == "structured4_undated" { #expect(card.calendar == .undated) }
            else { #expect(card.days.map(\.date) == ["2026-12-01", "2026-12-02", "2026-12-03"]) }
        }
        let old = try LioExplorationWire.decodePage(data(example("legacy_card2")))
        guard case .calendar(let card) = old.messages[0].trip else { Issue.record("legacy Card2 required"); return }
        #expect(card.calendar == nil && card.dateChecks == nil)
    }

    @Test func controlsCannotAddJointReplyLinesOrMalformedPresentationIDs() throws {
        let base = try example("en")
        let controls = Array(0...31) + Array(127...159) + [0x2028, 0x2029]
        for path: [Any] in [row + ["question_groups", 0, "options", 0, "send_text"], row + ["exits", 0, "send_text"]] {
            for code in controls {
                let text = "History" + String(try #require(UnicodeScalar(code)))
                #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: path, to: text))) }
            }
            for text in ["   ", "\t", "\n"] {
                #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: path, to: text))) }
            }
        }
        for path: [Any] in [row + ["question_groups", 0, "options", 0, "id"], row + ["exits", 0, "id"]] {
            #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: path, to: "interests.history\n"))) }
        }
    }

    @Test func exactProjectionAndUniqueFactorOptionNoticeExitIdentitiesAreRequired() throws {
        let base = try example("en")
        let mutations: [([Any], Any)] = [
            (row + ["answer"], "A different answer"),
            (row + ["question_groups", 0, "options", 0, "id"], "pace.history"),
            (row + ["question_groups", 0, "options", 1, "id"], "interests.history"),
            (row + ["exits", 1, "id"], "continue_refining"),
            (row + ["profile"], [["factor_key": "pace", "display_text": "Easy pace", "state": "unknown"]]),
            (row + ["question_groups", 0, "multiple"], 1),
            (row + ["extra_private_field"], true)
        ]
        for (path, value) in mutations {
            #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: path, to: value))) }
        }
        let rows = try #require(base["messages"] as? [[String: Any]])
        let groups = try #require(rows[0]["question_groups"] as? [[String: Any]])
        #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: row + ["question_groups"], to: groups + groups))) }
    }

    @Test func terminalRowsCannotRetainProgressAndPlanningDaysMustBeBoundedIntegers() throws {
        let base = try example("planning_started")
        for value: Any in [0, 367, true, 1.5] {
            #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: row + ["progress", "duration_days"], to: value))) }
        }
        #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: row + ["status"], to: "completed"))) }
        #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: row + ["progress", "extra"], to: true))) }
    }

    @Test func cardMutationsCannotRelabelFourAsOldOrInventCalendarChecks() throws {
        let base = try example("structured4_undated")
        for (field, value): (String, Any) in [("version", "LIO-trip-card.2"), ("content_version", "structured.3"),
                                            ("calendar", NSNull()), ("date_checks", NSNull()), ("price", 100), ("content_sha256", "bad")] {
            #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: row + ["trip", field], to: value))) }
        }
        #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: row + ["trip", "days", 1, "day_index"], to: 3))) }
        #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: row + ["trip", "date_checks", 0, "state"], to: "clear"))) }
    }

    @Test func profilesAndNoticesKeepTheirTypedValuesAndSourceData() throws {
        var value = try example("waiting")
        var rows = try #require(value["messages"] as? [[String: Any]])
        rows[0]["progress"] = NSNull()
        rows[0]["status"] = "completed"
        rows[0]["profile"] = [
            ["factor_key": "city", "display_text": "Beijing", "state": "known"],
            ["factor_key": "duration_days", "display_text": "Flexible", "state": "not_needed"],
            ["factor_key": "pace", "display_text": "Easy pace", "state": "inferred"],
            ["factor_key": "interests", "display_text": "A mix", "state": "default"],
            ["factor_key": "lodging_tier", "display_text": "Comfortable stay", "state": "memory"]
        ]
        let citation: [String: Any] = ["title": "Official guidance", "url": "https://example.org/guide", "observed_at": "2026-11-14T00:00:00Z"]
        let note: [String: Any] = ["id": "weather.1", "type": "weather", "severity": "warning", "item_ids": ["stop.1"], "text": "Bring a raincoat.", "source": citation]
        rows[0]["notices"] = [note]
        rows[0]["answer"] = "Bring a raincoat."
        value["messages"] = rows
        let message = try LioExplorationWire.decodePage(data(value)).messages[0]
        #expect(message.profile.map(\.state) == [.known, .notNeeded, .inferred, .defaultValue, .memory])
        #expect(message.notices[0].kind == .weather && message.notices[0].severity == .warning)
        #expect(message.notices[0].source.link?.absoluteString == "https://example.org/guide")
        #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(value, path: row + ["notices"], to: [note, note, note]))) }
        #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(value, path: row + ["notices", 0, "source", "observed_at"], to: "not a date"))) }
        #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(value, path: row + ["notices", 0, "item_ids"], to: ["stop.1", "stop.1"]))) }
    }

    @Test func citationDatesMustBeWholeRealRFC3339Values() throws {
        let base = try example("waiting")
        for date in ["2026-11-14T00:00:00Z", "2024-02-29t23:59:59.123456789z", "2026-11-14T00:00:00+23:59"] {
            let source: [String: Any] = ["title": "Guidance", "url": NSNull(), "observed_at": date]
            _ = try LioExplorationWire.decodePage(data(change(base, path: row + ["sources"], to: [source])))
        }
        for date in ["2026-02-30T00:00:00Z", "2026-11-14T00:00:00Zgarbage", "2025-02-29T00:00:00Z", "2026-11-14T24:00:00Z", "2026-11-14T00:00:60Z", "2026-11-14T00:00:00+24:00", "2026-11-14 00:00:00Z", "2026-11-14T00:00:00Z\n"] {
            let source: [String: Any] = ["title": "Guidance", "url": NSNull(), "observed_at": date]
            #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(base, path: row + ["sources"], to: [source]))) }
            let notice: [String: Any] = ["id": "weather.1", "type": "weather", "severity": "info", "item_ids": [], "text": "A weather note.", "source": source]
            let withNotice = try change(base, path: row + ["notices"], to: [notice])
            #expect(throws: Error.self) { try LioExplorationWire.decodePage(data(change(withNotice, path: row + ["answer"], to: "A weather note."))) }
        }
    }

    @Test func traceBindingAndRawOriginalsRemainSeparateFromDisplayData() throws {
        let input = try data(example("en"))
        #expect(throws: Error.self) { try LioExplorationWire.decodePage(input, for: "lio-dialogue-00000000000000000000000000000000") }
        let malformed = Data(String(decoding: input, as: UTF8.self).replacingOccurrences(of: "\"version\":\"LIO-timeline.4\"", with: "\"version\":\"LIO-timeline.4\",\"version\":\"LIO-timeline.4\"").utf8)
        #expect(throws: Error.self) { try LioExplorationWire.decodePage(malformed) }
    }
}
