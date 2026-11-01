import Foundation
import CoreFoundation
import CJMessageHTTP

public struct ScopedDisplayDates: Sendable {
    public let known: [String]
    public let incomplete: Bool
}
public struct ScopedDisplayChange: Sendable {
    public let itemID: String?
    public let field: String
    /// Original bounded JSON values for display only; never an edit command.
    public let beforeUTF8: Data
    public let afterUTF8: Data
    public let beforeEnglish: String
    public let beforeChinese: String
    public let afterEnglish: String
    public let afterChinese: String
}
public struct ScopedRequiredSelection: Sendable {
    public let itemIDs: [String]
    public let dates: ScopedDisplayDates
    public let wholeTrip: Bool
    public let localSelectionSufficient: Bool
}
public struct ScopedClarificationFacts: Sendable {
    public let unknownDateItemIDs:[String]
    public let crossDayItemIDs:[String]
    public let unmatchedDates:[String]
    public let observedDates:ScopedDisplayDates
}
public struct ScopedDisplayExplanation: Sendable {
    public let resolvedItemIDs: [String]
    public let reasonCodes: [String]
    public let english: String
    public let chinese: String
    public let outsideItemIDs: [String]
    public let outsideDates: [String]
    public let changes: [ScopedDisplayChange]
    public let requiredSelection: ScopedRequiredSelection?
    /// Original clarification facts, including UNKNOWN observations.
    public let factsUTF8: Data?
    public let facts:ScopedClarificationFacts?
}
public struct ScopedDisplayFeasibility: Sendable {
    public let status: String
    public let checks: [ScopedFeasibilityCheck]
    public let outputAccepted: Bool
    public let outputCodes: [String]
    public let english: String
    public let chinese: String
}
public struct ScopedDisplayContent: Sendable {
    public let kind: ScopedRunResultKind
    public let reference: MessageEditReference
    public let explanation: ScopedDisplayExplanation
    public let feasibility: ScopedDisplayFeasibility?
}
/// Protected original display data. There is intentionally no action/hash/permit API.
public struct ScopedResultDisplay: Sendable {
    public enum State: String, Sendable { case current, stale }
    public let resultID: String
    public let state: State
    public let expectedVersion: Int64
    public let currentVersion: Int64
    public let result: ScopedDisplayContent?

    public static func decode(_ bytes: Data, requestID: String, pointer: RunScopedResultReference, original: MessageEditReference) throws -> Self {
        guard pointer.messageID.utf8.elementsEqual(original.messageID.utf8), pointer.runID.utf8.elementsEqual(original.runID.utf8), pointer.inputSHA256 == original.inputSHA256 else { throw PreviewFailure.invalidResponse }
        let json = try ScopedWireJSON(bytes, maximumBytes: 4_000_000)
        let envelope = try ScopedWireJSON.fields(json.object, "version request_id display")
        guard envelope["version"] as? String == "TRIP-scoped-display.1", envelope["request_id"] as? String == requestID, UUID(uuidString: requestID) != nil else { throw PreviewFailure.invalidResponse }
        let d = try ScopedWireJSON.fields(envelope["display"], "result_id state expected_version current_version result")
        guard d["result_id"] as? String == pointer.resultID, let state = State(rawValue: try ScopedWireJSON.text(d["state"])) else { throw PreviewFailure.invalidResponse }
        let expected = try json.integer(["display", "expected_version"], minimum: 1), current = try json.integer(["display", "current_version"], minimum: 1)
        guard expected == original.trip.expectedVersion else { throw PreviewFailure.invalidResponse }
        if state == .stale {
            guard current != expected, d["result"] is NSNull else { throw PreviewFailure.invalidResponse }
            return .init(resultID: pointer.resultID, state: state, expectedVersion: expected, currentVersion: current, result: nil)
        }
        guard current == expected else { throw PreviewFailure.invalidResponse }
        let r = try ScopedWireJSON.fields(d["result"], "result_id kind reference explanation feasibility")
        let reference = try MessageEditReference.decodeResponseReference(canonical(["reference": r["reference"]!]), maximumBytes: 65536)
        guard r["result_id"] as? String == pointer.resultID, r["kind"] as? String == pointer.kind.rawValue, reference == original else { throw PreviewFailure.invalidResponse }
        let explanation = try decodeExplanation(r["explanation"], json: json, kind: pointer.kind, original: original)
        let feasibility: ScopedDisplayFeasibility?
        switch pointer.kind {
        case .clarificationRequired:
            guard r["feasibility"] is NSNull else { throw PreviewFailure.invalidResponse }; feasibility = nil
        case .expansionRequired: feasibility = try decodeFeasibility(r["feasibility"])
        }
        return .init(resultID: pointer.resultID, state: state, expectedVersion: expected, currentVersion: current, result: .init(kind: pointer.kind, reference: reference, explanation: explanation, feasibility: feasibility))
    }
    private static func boolean(_ value: Any?) throws -> Bool {
        guard let number = value as? NSNumber, CFGetTypeID(number) == CFBooleanGetTypeID() else { throw PreviewFailure.invalidResponse }
        return number.boolValue
    }
    private static func identifiers(_ value: Any?) throws -> [String] {
        guard let values = value as? [String], Set(values).count == values.count else { throw PreviewFailure.invalidResponse }
        return try values.map { try ScopedWireJSON.identifier($0) }
    }
    private static func strings(_ value: Any?) throws -> [String] {
        guard let values = value as? [String] else { throw PreviewFailure.invalidResponse }
        return try values.map { try ScopedWireJSON.text($0) }
    }
    private static func dates(_ value: Any?) throws -> [String] {
        guard let values = value as? [String], Set(values).count == values.count else { throw PreviewFailure.invalidResponse }
        for date in values { _ = try MessageTripSelection.Day(date: date, timezone: "UTC") } // Calendar validation only; preserves each declared date.
        return values
    }
    private static func dateObservations(_ value: Any?) throws -> ScopedDisplayDates {
        let d = try ScopedWireJSON.fields(value, "known incomplete")
        return try .init(known: dates(d["known"]), incomplete: boolean(d["incomplete"]))
    }
    private static func decodeExplanation(_ value: Any?, json: ScopedWireJSON, kind: ScopedRunResultKind, original: MessageEditReference) throws -> ScopedDisplayExplanation {
        let common = "version trip_id expected_version original_selection resolved_item_ids status reason_codes reason outside_item_ids outside_dates changes required_selection"
        let e = try ScopedWireJSON.fields(value, kind == .clarificationRequired ? common + " facts" : common)
        guard e["version"] as? String == "TRIP-scoped-explanation.1", e["trip_id"] as? String == original.trip.id,
              try json.integer(["display", "result", "explanation", "expected_version"], minimum: 1) == original.trip.expectedVersion,
              e["status"] as? String == (kind == .clarificationRequired ? "CLARIFICATION_REQUIRED" : "EXPANSION_REQUIRED") else { throw PreviewFailure.invalidResponse }
        let selected: [String: Any]
        if let day = original.trip.day { selected = ["kind": "dates", "dates": [day.date]] }
        else { selected = ["kind": "items", "item_ids": original.trip.itemIDs] }
        guard try canonical(e["original_selection"]) == canonical(selected) else { throw PreviewFailure.invalidResponse }
        let resolved = try identifiers(e["resolved_item_ids"]), outside = try identifiers(e["outside_item_ids"]), outsideDates = try dates(e["outside_dates"])
        let codes = try strings(e["reason_codes"]), reason = try ScopedWireJSON.fields(e["reason"], "en zh")
        guard !codes.isEmpty, let rawChanges = e["changes"] as? [Any] else { throw PreviewFailure.invalidResponse }
        let changes = try rawChanges.map { raw -> ScopedDisplayChange in
            let c = try ScopedWireJSON.fields(raw, "item_id field before after"), field = try ScopedWireJSON.text(c["field"])
            guard ["text", "schedule", "order", "title"].contains(field) else { throw PreviewFailure.invalidResponse }
            let id: String?
            if ["order", "title"].contains(field) { guard c["item_id"] is NSNull else { throw PreviewFailure.invalidResponse }; id = nil }
            else { id = try ScopedWireJSON.identifier(c["item_id"]) }
            if ["text", "title"].contains(field) { _ = try ScopedWireJSON.text(c["before"]); _ = try ScopedWireJSON.text(c["after"]) }
            if field == "order" { _ = try identifiers(c["before"]); _ = try identifiers(c["after"]) }
            if field == "schedule" { _ = try ScopedWireJSON.fields(c["before"], "start end"); _ = try ScopedWireJSON.fields(c["after"], "start end") }
            let before=try displayValue(c["before"],field:field),after=try displayValue(c["after"],field:field)
            return try .init(itemID:id,field:field,beforeUTF8:canonical(c["before"]),afterUTF8:canonical(c["after"]),beforeEnglish:before.0,beforeChinese:before.1,afterEnglish:after.0,afterChinese:after.1)
        }
        let required: ScopedRequiredSelection?, facts: Data?, factsValue:ScopedClarificationFacts?
        switch kind {
        case .clarificationRequired:
            guard resolved.isEmpty, outside.isEmpty, outsideDates.isEmpty, changes.isEmpty, e["required_selection"] is NSNull, codes == ["EXPLICIT_SELECTION_UNRESOLVED"] else { throw PreviewFailure.invalidResponse }
            let f = try ScopedWireJSON.fields(e["facts"], "unknown_date_item_ids cross_day_item_ids unmatched_dates observed_dates")
            factsValue=try .init(unknownDateItemIDs:identifiers(f["unknown_date_item_ids"]),crossDayItemIDs:identifiers(f["cross_day_item_ids"]),unmatchedDates:dates(f["unmatched_dates"]),observedDates:dateObservations(f["observed_dates"]))
            required = nil; facts = try canonical(f)
        case .expansionRequired:
            guard Set(resolved) == Set(original.resolvedItemIDs), Set(codes).isSubset(of: ["ITEMS_OUTSIDE_SELECTION", "DATES_OUTSIDE_SELECTION", "WHOLE_TRIP_TITLE"]) else { throw PreviewFailure.invalidResponse }
            let r = try ScopedWireJSON.fields(e["required_selection"], "item_ids dates whole_trip local_selection_sufficient")
            let ids = try identifiers(r["item_ids"]), whole = try boolean(r["whole_trip"]), sufficient = try boolean(r["local_selection_sufficient"])
            guard whole != sufficient, Set(resolved + outside).isSubset(of: Set(ids)) else { throw PreviewFailure.invalidResponse }
            required = try .init(itemIDs: ids, dates: dateObservations(r["dates"]), wholeTrip: whole, localSelectionSufficient: sufficient); facts = nil;factsValue=nil
        }
        return try .init(resolvedItemIDs: resolved, reasonCodes: codes, english: ScopedWireJSON.text(reason["en"]), chinese: ScopedWireJSON.text(reason["zh"]), outsideItemIDs: outside, outsideDates: outsideDates, changes: changes, requiredSelection: required, factsUTF8: facts,facts:factsValue)
    }
    private static func displayValue(_ value:Any?,field:String) throws -> (String,String) {
        if field == "text" || field == "title" { let text=try ScopedWireJSON.text(value);return (text,text) }
        if field == "order" { let ids=try identifiers(value).joined(separator:" → ");return (ids,ids) }
        let schedule=try ScopedWireJSON.fields(value,"start end")
        var en:[String]=[],zh:[String]=[]
        let fields=["date","time","timezone","utc_offset"]
        for (edge,english,chinese) in [("start","Start","开始"),("end","End","结束")] {
            let event=try ScopedWireJSON.fields(schedule[edge],fields.joined(separator:" "))
            var values:[String]=[]
            for field in fields {
                guard let observation=event[field] as? [String:Any],let state=observation["state"] as? String else { throw PreviewFailure.invalidResponse }
                switch state {
                case "known":let known=try ScopedWireJSON.fields(observation,"state value");values.append(try ScopedWireJSON.text(known["value"]))
                case "unknown","missing":_ = try ScopedWireJSON.fields(observation,"state");values.append(state == "unknown" ? "UNKNOWN" : "MISSING")
                default:throw PreviewFailure.invalidResponse
                }
            }
            let declared=values.joined(separator:" · ");en.append(english+": "+declared);zh.append(chinese+"："+declared)
        }
        return (en.joined(separator:"\n"),zh.joined(separator:"\n"))
    }
    private static func decodeFeasibility(_ value: Any?) throws -> ScopedDisplayFeasibility {
        let f = try ScopedWireJSON.fields(value, "status checks output_check"), status = try ScopedWireJSON.text(f["status"])
        guard ["PASS", "UNKNOWN", "CONFLICT", "INVALID", "NOT_APPLICABLE"].contains(status), let values = f["checks"] as? [Any] else { throw PreviewFailure.invalidResponse }
        let checks = try values.map { raw -> ScopedFeasibilityCheck in
            let c = try ScopedWireJSON.fields(raw, "code status missing zh en"), state = try ScopedWireJSON.text(c["status"])
            guard ["PASS", "UNKNOWN", "CONFLICT", "INVALID", "NOT_APPLICABLE"].contains(state) else { throw PreviewFailure.invalidResponse }
            return try .init(code: ScopedWireJSON.text(c["code"]), status: state, missing: strings(c["missing"]), english: ScopedWireJSON.text(c["en"]), chinese: ScopedWireJSON.text(c["zh"]))
        }
        let output = try ScopedWireJSON.fields(f["output_check"], "accepted codes zh en")
        return try .init(status: status, checks: checks, outputAccepted: boolean(output["accepted"]), outputCodes: strings(output["codes"]), english: ScopedWireJSON.text(output["en"]), chinese: ScopedWireJSON.text(output["zh"]))
    }
}
