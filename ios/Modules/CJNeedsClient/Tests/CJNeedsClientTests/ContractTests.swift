import Testing
import Foundation
import CJAPI
@testable import CJNeedsClient

@Suite struct ContractTests {
    @Test func absentAndFourStatesUseOfficialGeneratedTypes() throws {
        let data = Data(#"{"party_size":{"state":"missing"},"budget_total":{"state":"unknown"},"pace":{"state":"uncertain","note":"不确定 / unsure"},"budget_paid":{"state":"known","value":"12.3400"}}"#.utf8)
        let f = try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: data)
        #expect(f.arrival == nil && f.companions == nil && f.budget_per_person == nil)
        #expect(NeedsObservationInput(f.party_size).state == .missing)
        #expect(NeedsObservationInput(f.budget_total).state == .unknown)
        #expect(NeedsObservationInput(f.pace).note == "不确定 / unsure")
        #expect(NeedsObservationInput(f.budget_paid).value == "12.3400")
        let output = String(decoding: try encoded(f), as: UTF8.self)
        #expect(!output.contains("arrival") && !output.contains("null") && !output.contains("budget_per_person"))
    }
    @Test func patchOnlyIncludesExplicitlyChangedField() throws {
        let f = NeedsSchema.NeedsFields(party_size: .NeedsPartySizeObservationKnown(.init(state: .known, value: 8)), budget_paid: .NeedsMoneyObservationKnown(.init(state: .known, value: "000")))
        var draft = NeedsDraft(needsID: "needs-1", expectedVersion: 4, fields: f)
        draft.sourceText = "只改节奏 / pace only"
        draft.set(.pace, .init(state: .known, value: "slow / 慢一点"))
        let frozen = try draft.freeze(actionID: "correction:1")
        #expect(frozen.command.expected_version == 4)
        #expect(frozen.command.changes.party_size == nil && frozen.command.changes.budget_paid == nil)
        #expect(String(decoding: try encoded(frozen.command.changes), as: UTF8.self) == #"{"pace":{"state":"known","value":"slow / 慢一点"}}"#)
    }
    @Test func emptyPatchAndInvalidIDsRejectWithoutUUIDAssumption() throws {
        var draft = NeedsDraft(needsID: "visit:1", expectedVersion: 0); draft.sourceText = "explicit"
        #expect(throws: NeedsFailure.invalidInput) { try draft.freeze(actionID: "action:1") }
        draft.set(.partySize, .init(state: .known, value: "2"))
        #expect(try draft.freeze(actionID: String(repeating: "a", count: 96)).command.expected_version == 0)
        for id in ["", "é", "_x", "a/b", String(repeating: "a", count: 97)] {
            #expect(throws: NeedsFailure.invalidInput) { try draft.freeze(actionID: id) }
        }
    }
    @Test func decimalAndBudgetMeaningAreNeverCalculated() throws {
        var draft = NeedsDraft(needsID: "n", expectedVersion: 0); draft.sourceText = "预算 / budget"
        draft.set(.total, .init(state: .known, value: "1234.560000"))
        draft.set(.perPerson, .init(state: .unknown))
        draft.set(.paid, .init(state: .missing))
        draft.set(.currency, .init(state: .known, value: "CNY"))
        draft.set(.basis, .init(state: .uncertain, note: "总计还是每人尚未定"))
        draft.set(.includes, .init(state: .known, value: "includes hotels\nexcludes international travel"))
        let a = try draft.freeze(actionID: "budget")
        #expect(NeedsObservationInput(a.command.changes.budget_total).value == "1234.560000")
        #expect(NeedsObservationInput(a.command.changes.budget_per_person).state == .unknown)
        #expect(NeedsObservationInput(a.command.changes.budget_paid).state == .missing)
        #expect(a.command.changes.party_size == nil)
        for value in ["-1", "1e2", "1.0000000", "01", "1,000", "nan"] {
            draft.set(.total, .init(state: .known, value: value))
            #expect(throws: NeedsFailure.invalidInput) { try draft.freeze(actionID: "bad") }
        }
    }
    @Test func fixedItemsCompanionsConditionsRemainExplicit() throws {
        var draft = NeedsDraft(needsID: "n", expectedVersion: 0); draft.sourceText = "用户声称已订 / user claims booked"
        draft.companions = [.init(id: "mother", label: "母亲")]
        var item = NeedsFixedInput(id: "hotel:1"); item.kind = .hotel; item.description = "User says booked"
        item.appliesTo = ["companion:mother"]; item.locked = .init(state: .known, value: "true"); item.booking = .init(state: .known, value: "booked")
        item.start.markUnrecordedMissing(); item.end.markUnrecordedMissing(); draft.fixedItems = [item]
        var condition = NeedsConditionInput(id: "knee"); condition.appliesTo = ["companion:mother"]; condition.description = "temporary injury"
        draft.conditions = [condition]
        let a = try draft.freeze(actionID: "fixed")
        #expect(a.command.changes.party_size == nil)
        let f = try fields(a); try validateFields(f, complete: true)
        #expect(f.fixed_items?.first?.applies_to == ["companion:mother"])
        #expect(NeedsObservationInput(f.fixed_items?.first?.locked).value == "true")
        #expect(NeedsObservationInput(f.fixed_items?.first?.booking_status).value == "booked")
        let text = String(decoding: a.originalUTF8, as: UTF8.self)
        #expect(!text.contains("verified") && !text.contains("memory") && !text.contains("trip_id"))
        var invalid = f; invalid.companions = .init()
        #expect(throws: NeedsFailure.invalidInput) { try validateFields(invalid, complete: true) }
    }
    @Test func explicitEmptyCollectionIsDifferentFromAbsent() throws {
        var draft = NeedsDraft(needsID: "n", expectedVersion: 2); draft.sourceText = "clear fixed items"
        draft.fixedItems = []
        let a = try draft.freeze(actionID: "clear")
        #expect(a.command.changes.fixed_items == [])
        #expect(a.command.changes.temporary_conditions == nil && a.command.changes.companions == nil)
    }
    @Test func malformedGeneratedObservationsReject() {
        for raw in [#"{"party_size":{"state":"known","value":"3"}}"#, #"{"party_size":{"state":"guessed"}}"#, #"{"party_size":{"state":"unknown","value":0}}"#] {
            #expect(throws: (any Error).self) { try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: Data(raw.utf8)) }
        }
    }
    @Test func sourceBytesAreNotUnicodeNormalized() throws {
        let a = try original(text: "e\u{301}")
        let b = try original(text: "é")
        #expect(a.command.source.text == b.command.source.text) // Swift canonical string equality.
        #expect(a.originalUTF8 != b.originalUTF8)
        #expect(Data(a.command.source.text.utf8) == Data("e\u{301}".utf8))
    }
    @Test func invalidLocalValuesRejectWithoutDateConversion() {
        #expect(localDate("2024-02-29")); #expect(!localDate("2025-02-29"))
        #expect(localTime("01:30")); #expect(!localTime("24:00")); #expect(!localTime("12:00Z"))
    }
}
@Suite(.serialized) struct LocalTimeTests {
    @Test func deviceTimezoneDoesNotChangeLocalDSTOrDecimalBytes() throws {
        let old = NSTimeZone.default; defer { NSTimeZone.default = old }
        var draft = NeedsDraft(needsID: "n", expectedVersion: 0); draft.sourceText = "当地时间 / local time"
        var input = NeedsEventInput(); input.date = .init(state: .known, value: "2026-11-01")
        input.time = .init(state: .known, value: "01:30:00"); input.timezone = .init(state: .known, value: "America/New_York")
        input.place = .init(state: .unknown); draft.set(.arrival, input)
        NSTimeZone.default = try #require(TimeZone(identifier: "Asia/Shanghai")); let first = try draft.freeze(actionID: "local")
        NSTimeZone.default = try #require(TimeZone(identifier: "Pacific/Honolulu")); let second = try draft.freeze(actionID: "local")
        #expect(first.originalUTF8 == second.originalUTF8)
        #expect(first.command.changes.destination_timezone == nil && first.command.changes.departure == nil)
    }
}

@Suite struct AdditionalInputTests {
    @Test func coverageRetainsMultilineAndUnicodeValuesWhenMarkedChanged() throws {
        let values = ["hotels\nand local transport", "e\u{301}", "é"]
        let fields = NeedsSchema.NeedsFields(budget_includes: .NeedsCoverageObservationKnown(.init(state: .known, value: values)))
        var draft = NeedsDraft(needsID: "n", expectedVersion: 1, fields: fields); draft.sourceText = "confirm costs"
        draft.set(.includes, try #require(draft.observations[.includes]))
        let action = try draft.freeze(actionID: "costs")
        guard case .NeedsCoverageObservationKnown(let observation) = action.command.changes.budget_includes else { Issue.record("missing coverage"); return }
        #expect(observation.value.map { Data($0.utf8) } == values.map { Data($0.utf8) })
    }
    @Test func whitespaceAndDuplicateCoverageReject() throws {
        var draft = NeedsDraft(needsID: "n", expectedVersion: 0); draft.sourceText = " \n\t"
        draft.set(.pace, .init(state: .known, value: "slow"))
        #expect(throws: NeedsFailure.invalidInput) { try draft.freeze(actionID: "a") }
        draft.sourceText = "explicit"; draft.set(.includes, .init(state: .known, items: ["hotels", "hotels"]))
        #expect(throws: NeedsFailure.invalidInput) { try draft.freeze(actionID: "b") }
    }
}

@Suite struct ProducerFixtureTests {
    @Test func generatedFullCommandFixture() throws {
        var draft = NeedsDraft(needsID: "synthetic-needs:1", expectedVersion: 0)
        draft.sourceText = "Synthetic bilingual fixture / 合成样例；e\u{301}"
        draft.set(.partySize, .init(state: .known, value: "3"))
        draft.set(.total, .init(state: .known, value: "1234.5600"))
        draft.set(.perPerson, .init(state: .unknown))
        draft.set(.paid, .init(state: .missing))
        draft.set(.currency, .init(state: .known, value: "CNY"))
        draft.set(.basis, .init(state: .known, value: "total"))
        draft.set(.includes, .init(state: .known, items: ["includes hotels\nand local transport", "excludes international travel"]))
        draft.set(.pace, .init(state: .uncertain, note: "undecided / 未定"))
        var local = NeedsEventInput(); local.date = .init(state: .known, value: "2026-11-01")
        local.time = .init(state: .known, value: "01:30:00"); local.timezone = .init(state: .known, value: "America/New_York")
        local.place = .init(state: .unknown); draft.set(.overseasDeparture, local)
        draft.companions = [.init(id: "companion-1", label: "同行者")]
        var item = NeedsFixedInput(id: "fixed-1"); item.kind = .hotel; item.description = "Synthetic user booking claim"
        item.appliesTo = ["self", "companion:companion-1"]; item.locked = .init(state: .known, value: "true")
        item.booking = .init(state: .known, value: "booked"); item.start.markUnrecordedMissing(); item.end.markUnrecordedMissing()
        draft.fixedItems = [item]
        var condition = NeedsConditionInput(id: "condition-1"); condition.description = "本次临时条件"; condition.appliesTo = ["companion:companion-1"]
        draft.conditions = [condition]
        let action = try draft.freeze(actionID: "synthetic-action:1")
        try action.validate(); try validateFields(fields(action), complete: true)
        if let path = ProcessInfo.processInfo.environment["CJ_NEEDS_TEST_EXPORT"] {
            try action.originalUTF8.write(to: URL(fileURLWithPath: path))
        }
    }
}
