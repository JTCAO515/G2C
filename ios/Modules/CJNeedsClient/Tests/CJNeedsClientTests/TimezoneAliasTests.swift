import Testing
import Foundation
import CJAPI
@testable import CJNeedsClient

/// Formal wire only constrains timezone strings to minLength 1. Producer owns zone validity.
@MainActor @Suite struct TimezoneAliasTests {
    private func fixture(_ alias: String) throws -> (NeedsSchema.NeedsCommand, NeedsSchema.NeedsFields) {
        let known = NeedsSchema.NeedsTimezoneObservation.NeedsTimezoneObservationKnown(.init(state: .known, value: alias))
        var local = event(); local.timezone = known
        local.date = .NeedsLocalDateObservationKnown(.init(state: .known, value: "2026-11-01"))
        local.time = .NeedsLocalTimeObservationKnown(.init(state: .known, value: "01:30:00"))
        let changes = NeedsSchema.NeedsChanges(destination_timezone: known, overseas_timezone: known, arrival: local)
        let command = NeedsSchema.NeedsCommand(action_id: "alias-action", needs_id: "alias-needs", expected_version: 0,
                                               source: .init(kind: .manual, text: "Explicit timezone alias / 用户原样输入"), changes: changes)
        return (command, try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: encoded(changes)))
    }
    @Test(arguments: ["Etc/UTC", "US/Eastern", "PRC"])
    func formPreservesLegalAlias(alias: String) throws {
        let (command, fields) = try fixture(alias)
        var draft = NeedsDraft(needsID: command.needs_id, expectedVersion: 0, fields: fields)
        draft.sourceText = command.source.text
        draft.set(.destinationTimezone, try #require(draft.observations[.destinationTimezone]))
        draft.set(.overseasTimezone, try #require(draft.observations[.overseasTimezone]))
        draft.set(.arrival, try #require(draft.events[.arrival]))
        let action = try draft.freeze(actionID: command.action_id)
        #expect(action.originalUTF8 == (try encoded(command)))
    }
    @Test(arguments: ["Etc/UTC", "US/Eastern", "PRC"])
    func generatedDetailPreservesLegalAlias(alias: String) async throws {
        let (command, fields) = try fixture(alias)
        let snapshot = NeedsSchema.NeedsSnapshot(needs_id: command.needs_id, version: 1, source_kind: .user_provided,
                                                 content_utf8_base64: try encoded(fields).base64EncodedString(), fields: fields)
        let h = try Harness(); defer { h.clean() }
        let t = Interceptor { _, _, _ in Reply(try response("needs", snapshot)) }
        let client = try h.client(t)
        let result = try await client.perform(client.prepareDetail(id: command.needs_id, binding: h.binding))
        guard case .detail(let value?) = result else { Issue.record("missing detail"); return }
        #expect(try encoded(value.fields) == encoded(fields))
        #expect(await t.calls.map(\.operation) == ["getNeeds"])
    }
    @Test(arguments: ["Etc/UTC", "US/Eastern", "PRC"])
    func generatedRevisionPreservesOriginalAliasBytes(alias: String) async throws {
        let (command, fields) = try fixture(alias); let bytes = try encoded(command)
        let revision = NeedsSchema.NeedsRevision(needs_id: command.needs_id, version: 1, action_id: command.action_id,
                                                 source_kind: .user_provided, original_input_utf8_base64: bytes.base64EncodedString(),
                                                 content_utf8_base64: try encoded(fields).base64EncodedString(), fields: fields)
        let h = try Harness(); defer { h.clean() }
        let t = Interceptor { _, _, _ in Reply(try response("revision", revision)) }
        let client = try h.client(t)
        let result = try await client.perform(client.prepareRevision(id: command.needs_id, version: 1, binding: h.binding))
        guard case .revision(let value?) = result else { Issue.record("missing revision"); return }
        #expect(Data(base64Encoded: value.original_input_utf8_base64) == bytes)
        #expect(try encoded(value.fields) == encoded(fields))
        #expect(await t.calls.map(\.operation) == ["getNeedsRevision"])
    }
    @Test func absenceAndExplicitStatesRemainDistinct() throws {
        let fields = NeedsSchema.NeedsFields(destination_timezone: .NeedsUncertainObservation(.init(state: .uncertain, note: "尚未确定 / undecided")))
        var draft = NeedsDraft(needsID: "n", expectedVersion: 0, fields: fields); draft.sourceText = "explicit states"
        draft.set(.destinationTimezone, try #require(draft.observations[.destinationTimezone]))
        draft.set(.overseasTimezone, .init(state: .missing))
        var local = NeedsEventInput(); local.markUnrecordedMissing(); local.timezone = .init(state: .unknown)
        draft.set(.arrival, local)
        let action = try draft.freeze(actionID: "states")
        #expect(NeedsObservationInput(action.command.changes.destination_timezone).note == "尚未确定 / undecided")
        #expect(NeedsObservationInput(action.command.changes.overseas_timezone).state == .missing)
        #expect(NeedsObservationInput(action.command.changes.arrival?.timezone).state == .unknown)
        #expect(action.command.changes.overseas_departure == nil && action.command.changes.departure == nil)
        draft.set(.destinationTimezone, .init(state: .known, value: ""))
        #expect(throws: NeedsFailure.invalidInput) { try draft.freeze(actionID: "empty") }
    }
    @Test func nonemptyInputIsNotClaimedToBeProducerValidated() throws {
        var draft = NeedsDraft(needsID: "n", expectedVersion: 0); draft.sourceText = "unvalidated input"
        draft.set(.destinationTimezone, .init(state: .known, value: "Not/A_Real_Zone"))
        let action = try draft.freeze(actionID: "unvalidated")
        #expect(NeedsObservationInput(action.command.changes.destination_timezone).value == "Not/A_Real_Zone")
        // No local tzdb or alias allowlist is an authority. The producer rejects invalid zones.
    }
}
