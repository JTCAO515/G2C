import Foundation

/// Explicit selection data for TRIP-needs-edit.1, not a NEEDS lease.
public struct TripNeedsReference: Sendable, Equatable {
    public let id: String
    public let expectedVersion: Int
    public init(id: String, expectedVersion: Int) throws {
        guard tripID(id), id.utf8.count <= 96, expectedVersion > 0 else { throw TripFailure.invalidInput }
        self.id = id; self.expectedVersion = expectedVersion
    }
}

/// Unvalidated, in-progress user input. Validation happens when freezing a command.
public struct ManualTripEventInput: Sendable {
    public var date: TripObservation<String>
    public var time: TripObservation<String>
    public var timezone: TripObservation<String>
    public var utcOffset: TripObservation<String>
    public init(snapshot: StructuredTripEvent) {
        date = snapshot.date; time = snapshot.time; timezone = snapshot.timezone; utcOffset = snapshot.utcOffset
    }
    public init(date: TripObservation<String>, time: TripObservation<String>, timezone: TripObservation<String>, utcOffset: TripObservation<String>) {
        self.date = date; self.time = time; self.timezone = timezone; self.utcOffset = utcOffset
    }
    var wire: TripJSONValue {
        .object(["date": tripObservationWire(date, TripJSONValue.string), "time": tripObservationWire(time, TripJSONValue.string),
                 "timezone": tripObservationWire(timezone, TripJSONValue.string), "utc_offset": tripObservationWire(utcOffset, TripJSONValue.string)])
    }
}
public struct ManualTripScheduleInput: Sendable {
    public var start: ManualTripEventInput
    public var end: ManualTripEventInput
    public init(item: StructuredTripItem) {
        start = .init(snapshot: item.start); end = .init(snapshot: item.end)
    }
    public init(start: ManualTripEventInput, end: ManualTripEventInput) { self.start = start; self.end = end }
    var wire: TripJSONValue { .object(["start": start.wire, "end": end.wire]) }
}
public enum ManualTripField: String, Sendable { case text, schedule, fixed }

/// Pure local intent. No initializer, field, revision or serialized command
/// grants transport access, source authority, confirmation or a second writer.
public struct ManualTripDraft: Sendable {
    public let original: StructuredTripRecord
    public let editorID = UUID()
    public private(set) var revision = UUID() // Local UI lifetime, not a business ID.
    public private(set) var selectedIDs: Set<String> = []
    public private(set) var title: String?
    public private(set) var texts: [String: String] = [:]
    public private(set) var schedules: [String: ManualTripScheduleInput] = [:]
    public private(set) var fixed: [String: Bool] = [:]
    public private(set) var order: [String]?
    public let needs: TripNeedsReference?

    public init(original: StructuredTripRecord, needs: TripNeedsReference?) throws {
        guard (original.document.version == .needsBound) == (needs != nil) else { throw TripFailure.invalidInput }
        self.original = original; self.needs = needs
    }
    public mutating func selectItem(_ id: String, selected: Bool) throws {
        _ = try item(id)
        if selected { selectedIDs.insert(id) } else { selectedIDs.remove(id) }
        // Keep local input. Deselected values are omitted, never sent implicitly.
        revision = UUID()
    }
    public mutating func setTitle(_ value: String?) { title = value; revision = UUID() }
    public mutating func setText(_ value: String, itemID: String) throws {
        try contentSelection(itemID); texts[itemID] = value; revision = UUID()
    }
    public mutating func setSchedule(_ value: ManualTripScheduleInput, itemID: String) throws {
        try contentSelection(itemID); schedules[itemID] = value; revision = UUID()
    }
    public mutating func setFixed(_ value: Bool, itemID: String) throws {
        _ = try item(itemID)
        guard selectedIDs.contains(itemID), texts[itemID] == nil, schedules[itemID] == nil else { throw TripFailure.invalidInput }
        fixed[itemID] = value; revision = UUID()
    }
    public mutating func leaveUnchanged(_ field: ManualTripField, itemID: String) throws {
        _ = try item(itemID)
        switch field {
        case .text: texts.removeValue(forKey: itemID)
        case .schedule: schedules.removeValue(forKey: itemID)
        case .fixed: fixed.removeValue(forKey: itemID)
        }
        revision = UUID()
    }
    public mutating func setOrder(_ ids: [String]?) throws {
        if let ids { try validateOrder(ids) }
        order = ids; revision = UUID()
    }
    private func item(_ id: String) throws -> StructuredTripItem {
        guard let item = original.document.items.first(where: { same($0.id, id) }) else { throw TripFailure.invalidInput }; return item
    }
    private func contentSelection(_ id: String) throws {
        guard selectedIDs.contains(id), try item(id).fixed == .known(false), fixed[id] == nil else { throw TripFailure.invalidInput }
    }
    private func validateOrder(_ ids: [String]) throws {
        let originalIDs = original.document.items.map(\.id)
        guard ids.count == originalIDs.count, Set(ids) == Set(originalIDs) else { throw TripFailure.invalidInput }
        for (before, after) in zip(originalIDs, ids) where before != after {
            guard selectedIDs.contains(after), try item(after).fixed == .known(false) else { throw TripFailure.invalidInput }
        }
    }

    /// The trusted client supplies a business request ID only after its original
    /// source/session and all retained actions have passed the outflow preflight.
    public func freeze(requestID: String) throws -> ManualTripInput {
        guard tripID(requestID) else { throw TripFailure.invalidInput }
        if let order { try validateOrder(order) }
        var changes: [TripJSONValue] = [], captured: [ManualTripChange] = [], changed = false
        if let title {
            try inputText(title, maximum: 120); changed = !same(title, original.document.title)
        }
        for item in original.document.items where selectedIDs.contains(item.id) {
            func change(_ field: ManualTripField, _ value: TripJSONValue) -> TripJSONValue {
                captured.append(.init(itemID: item.id, field: field, valueUTF8: tripCanonicalJSON(value)))
                return .object(["item_id": .string(item.id), "field": .string(field.rawValue), "value": value])
            }
            if let lock = fixed[item.id] {
                guard texts[item.id] == nil, schedules[item.id] == nil else { throw TripFailure.invalidInput }
                changes.append(change(.fixed, tripObservationWire(.known(lock), TripJSONValue.boolean)))
                if item.fixed != .known(lock) { changed = true }
            }
            if let text = texts[item.id] {
                try contentSelection(item.id); try inputText(text, maximum: 500)
                changes.append(change(.text, .string(text)))
                if !same(text, item.text) { changed = true }
            }
            if let schedule = schedules[item.id] {
                try contentSelection(item.id)
                do {
                    _ = try StructuredTripEvent.read(schedule.start.wire, version: original.document.version)
                    _ = try StructuredTripEvent.read(schedule.end.wire, version: original.document.version)
                } catch TripFailure.invalidResponse { throw TripFailure.invalidInput }
                changes.append(change(.schedule, schedule.wire))
                if tripCanonicalJSON(schedule.wire) != tripCanonicalJSON(ManualTripScheduleInput(item: item).wire) { changed = true }
            }
        }
        if let order, order != original.document.items.map(\.id) { changed = true }
        guard changed, changes.count <= 60 else { throw TripFailure.invalidInput }
        let edit: TripJSONValue = .object([
            "version": .string(original.document.version == .first ? "TRIP-manual-edit.1" : "TRIP-manual-edit.2"),
            "request_id": .string(requestID), "trip_id": .string(original.tripID), "expected_version": .number(String(original.version)),
            "original_hash": .string(original.document.contentSHA256), "title": title.map(TripJSONValue.string) ?? .null,
            "changes": .array(changes), "order": order.map { .array($0.map(TripJSONValue.string)) } ?? .null])
        let command: TripJSONValue
        if let needs {
            command = .object(["version": .string("TRIP-needs-edit.1"), "edit": edit,
                "needs_reference": .object(["id": .string(needs.id), "expected_version": .number(String(needs.expectedVersion))])])
        } else { command = edit }
        let bytes = tripCanonicalJSON(command)
        guard bytes.count <= 1_000_000 else { throw TripFailure.invalidInput }
        return .init(requestID: requestID, original: original, needs: needs, editorID: editorID, revision: revision,
                     selectedIDs: selectedIDs, changes: captured, title: title, order: order, originalUTF8: bytes)
    }
}

/// Frozen intent bytes are not a work capability. An opaque, current client work
/// is still required for any real prepare or save operation.
public struct ManualTripInput: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let requestID: String
    public let original: StructuredTripRecord
    public let needs: TripNeedsReference?
    let editorID: UUID
    let revision: UUID
    let selectedIDs: Set<String>
    let changes: [ManualTripChange]
    let title: String?
    let order: [String]?
    public let originalUTF8: Data
    public var description: String { "<manual trip input>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}

struct ManualTripChange: Sendable {
    let itemID: String
    let field: ManualTripField
    let valueUTF8: Data
}

func tripObservationWire<Value>(_ observation: TripObservation<Value>, _ encode: (Value) -> TripJSONValue) -> TripJSONValue {
    switch observation {
    case .known(let value): .object(["state": .string("known"), "value": encode(value)])
    case .missing: .object(["state": .string("missing")])
    case .unknown: .object(["state": .string("unknown")])
    case .uncertain(let note): .object(["state": .string("uncertain"), "note": .string(note)])
    }
}
private func inputText(_ text: String, maximum: Int) throws {
    guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.unicodeScalars.count <= maximum else { throw TripFailure.invalidInput }
}
