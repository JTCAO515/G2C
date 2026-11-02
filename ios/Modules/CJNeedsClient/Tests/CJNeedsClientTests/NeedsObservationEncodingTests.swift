import Foundation
import Testing
@testable import CJNeedsClient

@Suite struct NeedsObservationEncodingTests {
    private let encoders: [(String, (NeedsObservationInput) throws -> Void)] = [
        ("partySize", { _ = try $0.partySize() }), ("timezone", { _ = try $0.timezone() }),
        ("currency", { _ = try $0.currency() }), ("text", { _ = try $0.text() }),
        ("localDate", { _ = try $0.localDate() }), ("localTime", { _ = try $0.localTime() })
    ]

    @Test func absentObservationNeverBecomesAStatement() {
        for (name, encode) in encoders {
            #expect(throws: NeedsFailure.self, "\(name)") { try encode(NeedsObservationInput(state: .absent)) }
        }
    }

    @Test func nonValueStatesCarryNoValue() throws {
        guard case .NeedsMissingObservation = try NeedsObservationInput(state: .missing, value: "ignored").text() else {
            Issue.record("missing expected"); return
        }
        guard case .NeedsUnknownObservation = try NeedsObservationInput(state: .unknown, value: "ignored").text() else {
            Issue.record("unknown expected"); return
        }
        guard case .NeedsUncertainObservation(let uncertain) = try NeedsObservationInput(state: .uncertain, value: "ignored", note: "maybe").text() else {
            Issue.record("uncertain expected"); return
        }
        #expect(uncertain.note == "maybe")
    }

    @Test func knownValueUsesTheTypesOwnCase() throws {
        guard case .NeedsTextObservationKnown(let text) = try NeedsObservationInput(state: .known, value: "北京").text() else {
            Issue.record("known expected"); return
        }
        #expect(text.value == "北京")
        guard case .NeedsPartySizeObservationKnown(let size) = try NeedsObservationInput(state: .known, value: "3").partySize() else {
            Issue.record("known expected"); return
        }
        #expect(size.value == 3)
        #expect(throws: NeedsFailure.self) { try NeedsObservationInput(state: .known, value: "three").partySize() }
    }
}
