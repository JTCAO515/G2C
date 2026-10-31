import Foundation
import Testing
@testable import CJTripClient

/// Synthetic L0 bytes parsed/prepared by the official Python implementations.
/// They are not accepted API records, a source lease, or native evidence.
@Suite @MainActor struct ManualTripInputTests {
    struct Fixture: Decodable {
        let name: String
        let trip_id: String
        let trip_version: Int
        let original_utf8_base64: String
        let request_utf8_base64: String
        let after_utf8_base64: String
        let diff_utf8_base64: String
        let preparation_utf8_base64: String
        let save_utf8_base64: String
        let receipt_utf8_base64: String
        var request: Data { Data(base64Encoded: request_utf8_base64)! }
        func record() throws -> StructuredTripRecord {
            try .init(tripID: trip_id, version: trip_version,
                      document: .decode(Data(base64Encoded: original_utf8_base64)!))
        }
    }
    func fixtures() throws -> [Fixture] {
        let url = try #require(Bundle.module.url(forResource: "MANUAL-TRIP-V1", withExtension: "json", subdirectory: "Fixtures"))
        return try JSONDecoder().decode([Fixture].self, from: Data(contentsOf: url))
    }
    func fixture(_ name: String = "text") throws -> Fixture {
        let all = try fixtures(); return try #require(all.first { $0.name == name })
    }
    func base(_ name: String = "text") throws -> ManualTripDraft {
        let f = try fixture(name), record = try f.record()
        let needs = record.document.version == .needsBound ? try TripNeedsReference(id: "needs-1", expectedVersion: 3) : nil
        return try .init(original: record, needs: needs)
    }
    func inputSchedule(_ value: Any, version: StructuredTripVersion) throws -> ManualTripScheduleInput {
        let bytes = try JSONSerialization.data(withJSONObject: value)
        var parser = StrictTripJSON(bytes: Array(bytes))
        let fields = try parser.document().fields("start end")
        return try .init(start: .init(snapshot: .read(fields.required("start"), version: version)),
                         end: .init(snapshot: .read(fields.required("end"), version: version)))
    }

    func frozen(_ f: Fixture) throws -> ManualTripInput {
            let value = try JSONSerialization.jsonObject(with: f.request) as! [String: Any]
            let edit = value["edit"] as? [String: Any] ?? value
            var draft = try base(f.name)
            if let title = edit["title"] as? String { draft.setTitle(title) }
            for change in edit["changes"] as! [[String: Any]] {
                let id = change["item_id"] as! String
                try draft.selectItem(id, selected: true)
                switch change["field"] as! String {
                case "text": try draft.setText(change["value"] as! String, itemID: id)
                case "fixed": try draft.setFixed((change["value"] as! [String: Any])["value"] as! Bool, itemID: id)
                case "schedule": try draft.setSchedule(inputSchedule(change["value"]!, version: draft.original.document.version), itemID: id)
                default: Issue.record("unexpected fixture field")
                }
            }
            if let order = edit["order"] as? [String] {
                for id in order { try draft.selectItem(id, selected: true) }
                try draft.setOrder(order)
            }
            return try draft.freeze(requestID: edit["request_id"] as! String)
    }
    @Test func frozenRequestsMatchPythonCanonicalGoldensIncludingNeedsV2() throws {
        for f in try fixtures() {
            let frozen = try frozen(f)
            #expect(frozen.originalUTF8 == f.request)
            #expect(frozen.original.version == f.trip_version)
            #expect(try self.frozen(f).originalUTF8 == f.request)
        }
    }
    @Test func unselectedAndLockedInputsCannotEnterTheCommand() throws {
        var draft = try base()
        #expect(throws: TripFailure.invalidInput) { try draft.setText("not selected", itemID: "item-1") }
        try draft.selectItem("item-1", selected: true); try draft.setText("kept local", itemID: "item-1")
        try draft.selectItem("item-1", selected: false); draft.setTitle("SYNTHETIC explicit title")
        let value = try JSONSerialization.jsonObject(with: draft.freeze(requestID: "deselected").originalUTF8) as! [String: Any]
        #expect((value["changes"] as! [Any]).isEmpty)
        #expect(draft.texts["item-1"] == "kept local")
        #expect(draft.original.version == 2)
        var unknown = try base("explicit_unlock")
        try unknown.selectItem("item-1", selected: true)
        #expect(throws: TripFailure.invalidInput) { try unknown.setText("cannot assume unlocked", itemID: "item-1") }
        try unknown.setFixed(false, itemID: "item-1")
        _ = try unknown.freeze(requestID: "explicit-known-unlock")
    }
    @Test func lockChangesNeverSmuggleTextOrTimeEdits() throws {
        var draft = try base(); try draft.selectItem("item-1", selected: true)
        try draft.setText("explicit change", itemID: "item-1")
        #expect(throws: TripFailure.invalidInput) { try draft.setFixed(true, itemID: "item-1") }
        try draft.leaveUnchanged(.text, itemID: "item-1"); try draft.setFixed(true, itemID: "item-1")
        #expect(throws: TripFailure.invalidInput) { try draft.setText("incidental", itemID: "item-1") }
        let schedule = ManualTripScheduleInput(item: draft.original.document.items[0])
        #expect(throws: TripFailure.invalidInput) { try draft.setSchedule(schedule, itemID: "item-1") }
    }
    @Test func reorderPreservesIDsAndUnselectedPositions() throws {
        var draft = try base(); try draft.selectItem("item-1", selected: true)
        #expect(throws: TripFailure.invalidInput) { try draft.setOrder(["item-2", "item-1"]) }
        try draft.selectItem("item-2", selected: true); try draft.setOrder(["item-2", "item-1"])
        #expect(throws: TripFailure.invalidInput) { try draft.setOrder(["item-1", "item-1"]) }
        try draft.selectItem("item-2", selected: false)
        #expect(draft.order == ["item-2", "item-1"])
        #expect(throws: TripFailure.invalidInput) { try draft.freeze(requestID: "unselected-move") }
    }
    @Test func invalidInProgressDatesStayLocalAndDoNotFreeze() throws {
        var draft = try base(); try draft.selectItem("item-1", selected: true)
        var schedule = ManualTripScheduleInput(item: draft.original.document.items[0])
        schedule.start.date = .known("2026-")
        try draft.setSchedule(schedule, itemID: "item-1")
        #expect(draft.schedules["item-1"]?.start.date == .known("2026-"))
        #expect(throws: TripFailure.invalidInput) { try draft.freeze(requestID: "unfinished") }
    }
    @Test func noOpAndOversizedTitlesDoNotCreateCommands() throws {
        var draft = try base()
        #expect(throws: TripFailure.invalidInput) { try draft.freeze(requestID: "no-op") }
        draft.setTitle(draft.original.document.title)
        #expect(throws: TripFailure.invalidInput) { try draft.freeze(requestID: "same-title") }
        draft.setTitle(String(repeating: "旅", count: 121))
        #expect(throws: TripFailure.invalidInput) { try draft.freeze(requestID: "oversized") }
    }
    @Test func needsReferenceIsExplicitBoundedAndCannotFallbackToUnbound() throws {
        let f = try fixture("needs_text"), record = try f.record()
        #expect(throws: TripFailure.invalidInput) { try ManualTripDraft(original: record, needs: nil) }
        let unbound = try fixture().record(), ref = try TripNeedsReference(id: "needs-1", expectedVersion: 3)
        #expect(throws: TripFailure.invalidInput) { try ManualTripDraft(original: unbound, needs: ref) }
        #expect(throws: TripFailure.invalidInput) { try TripNeedsReference(id: String(repeating: "n", count: 97), expectedVersion: 1) }
        #expect(throws: TripFailure.invalidInput) { try TripNeedsReference(id: "needs-1", expectedVersion: 0) }
    }
    @Test func frozenOriginalIsImmutableAndDefaultDiagnosticsAreRedacted() throws {
        var draft = try base(); try draft.selectItem("item-1", selected: true)
        try draft.setText("SYNTHETIC_PRIVATE_TRIP_SENTINEL", itemID: "item-1")
        let original = try draft.freeze(requestID: "original-only")
        try draft.setText("different later local input", itemID: "item-1")
        #expect(String(decoding: original.originalUTF8, as: UTF8.self).contains("SYNTHETIC_PRIVATE_TRIP_SENTINEL"))
        #expect(!String(describing: original).contains("SYNTHETIC_PRIVATE_TRIP_SENTINEL"))
        #expect(!String(reflecting: original).contains("SYNTHETIC_PRIVATE_TRIP_SENTINEL"))
        #expect(Mirror(reflecting: original).children.isEmpty)
    }
}
