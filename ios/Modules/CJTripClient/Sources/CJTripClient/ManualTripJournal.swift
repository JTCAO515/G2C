import Foundation
import CJAPI

/// Local-only journal schema. The original remote wire is always retained as
/// immutable bytes; decoding this record grants query only, never POST access.
struct ManualTripOriginal: TripJournalRecord, Sendable {
    enum Stage: String, Codable, Sendable { case prepare, save }
    let version: String
    let stage: Stage
    let id: String
    let originalUTF8: Data
    let sourceTripID: String
    let sourceVersion: Int
    let sourceUTF8: Data
    let selectedIDs: [String]
    let prepareID: String?
    let prepareInputSHA256: String?
    let preparationResponseUTF8: Data?
    var storageID: String { (stage == .prepare ? "p:" : "s:") + digest(Data(id.utf8)) }

    init(prepare input: ManualTripInput) {
        version = "CJTripManualOriginal.1"; stage = .prepare; id = input.requestID; originalUTF8 = input.originalUTF8
        sourceTripID = input.original.tripID; sourceVersion = input.original.version; sourceUTF8 = input.original.document.originalUTF8
        selectedIDs = input.selectedIDs.sorted(); prepareID = nil; prepareInputSHA256 = nil; preparationResponseUTF8 = nil
    }
    init(save input: ManualTripSaveInput, responseUTF8: Data) {
        version = "CJTripManualOriginal.1"; stage = .save; id = input.actionID; originalUTF8 = input.originalUTF8
        sourceTripID = input.original.original.tripID; sourceVersion = input.original.original.version; sourceUTF8 = input.original.original.document.originalUTF8
        selectedIDs = input.original.selectedIDs.sorted(); prepareID = input.original.requestID
        prepareInputSHA256 = digest(input.original.originalUTF8); preparationResponseUTF8 = responseUTF8
    }
    private enum Keys: String, CodingKey, CaseIterable {
        case version, stage, id, originalUTF8, sourceTripID, sourceVersion, sourceUTF8, selectedIDs
        case prepareID, prepareInputSHA256, preparationResponseUTF8
    }
    private struct AnyKey: CodingKey {
        let stringValue: String
        var intValue: Int? { nil }
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { return nil }
    }
    init(from decoder: any Decoder) throws {
        let all = try decoder.container(keyedBy: AnyKey.self), c = try decoder.container(keyedBy: Keys.self)
        stage = try c.decode(Stage.self, forKey: .stage)
        var expected = Set(Keys.allCases.map(\.rawValue))
        if stage == .prepare { expected.subtract(["prepareID", "prepareInputSHA256", "preparationResponseUTF8"]) }
        guard Set(all.allKeys.map(\.stringValue)) == expected else { throw TripFailure.storageUnavailable }
        version = try c.decode(String.self, forKey: .version); id = try c.decode(String.self, forKey: .id)
        originalUTF8 = try c.decode(Data.self, forKey: .originalUTF8); sourceTripID = try c.decode(String.self, forKey: .sourceTripID)
        // String on disk prevents a JSON decoder from coercing 1.0/true into a version.
        let counter = try c.decode(String.self, forKey: .sourceVersion)
        sourceVersion = try tripWireVersion(.number(counter))
        sourceUTF8 = try c.decode(Data.self, forKey: .sourceUTF8); selectedIDs = try c.decode([String].self, forKey: .selectedIDs)
        prepareID = try c.decodeIfPresent(String.self, forKey: .prepareID)
        prepareInputSHA256 = try c.decodeIfPresent(String.self, forKey: .prepareInputSHA256)
        preparationResponseUTF8 = try c.decodeIfPresent(Data.self, forKey: .preparationResponseUTF8)
    }
    func encode(to encoder: any Encoder) throws {
        var c = encoder.container(keyedBy: Keys.self)
        try c.encode(version, forKey: .version); try c.encode(stage, forKey: .stage); try c.encode(id, forKey: .id)
        try c.encode(originalUTF8, forKey: .originalUTF8); try c.encode(sourceTripID, forKey: .sourceTripID)
        try c.encode(String(sourceVersion), forKey: .sourceVersion); try c.encode(sourceUTF8, forKey: .sourceUTF8)
        try c.encode(selectedIDs, forKey: .selectedIDs); try c.encodeIfPresent(prepareID, forKey: .prepareID)
        try c.encodeIfPresent(prepareInputSHA256, forKey: .prepareInputSHA256)
        try c.encodeIfPresent(preparationResponseUTF8, forKey: .preparationResponseUTF8)
    }
    func validate() throws {
        guard version == "CJTripManualOriginal.1", tripID(id), tripID(sourceTripID), sourceVersion > 0,
              !originalUTF8.isEmpty, originalUTF8.count <= 1_000_000,
              !sourceUTF8.isEmpty, sourceUTF8.count <= 1_000_000,
              selectedIDs.count <= 60, Set(selectedIDs).count == selectedIDs.count else { throw TripFailure.storageUnavailable }
        let record = try source()
        guard selectedIDs.allSatisfy({ id in record.document.items.contains { same($0.id, id) } }) else { throw TripFailure.storageUnavailable }
        switch stage {
        case .prepare:
            guard prepareID == nil, prepareInputSHA256 == nil, preparationResponseUTF8 == nil else { throw TripFailure.storageUnavailable }
            _ = try prepareInput()
        case .save:
            guard let prepareID, tripID(prepareID), let hash = prepareInputSHA256, tripHash(hash),
                  let response = preparationResponseUTF8, !response.isEmpty, response.count <= 1_000_000 else { throw TripFailure.storageUnavailable }
            var parser = StrictTripJSON(bytes: Array(originalUTF8)); let value = try parser.document()
            let f = try value.fields("version action_id proposal_id candidate_hash")
            guard tripCanonicalJSON(value) == originalUTF8, try same(f.required("action_id").text(), id),
                  try f.required("version").text() == (record.document.version == .first ? "TRIP-manual-save.1" : "TRIP-needs-save.1"),
                  try tripID(f.required("proposal_id").text()), try tripHash(f.required("candidate_hash").text()) else { throw TripFailure.storageUnavailable }
        }
    }
    func source() throws -> StructuredTripRecord {
        try .init(tripID: sourceTripID, version: sourceVersion, document: .decode(sourceUTF8))
    }
    func prepareInput() throws -> ManualTripInput {
        guard stage == .prepare else { throw TripFailure.storageUnavailable }
        return try ManualTripInput.restoring(original: source(), bytes: originalUTF8, selectedIDs: selectedIDs)
    }
    func saveInput(preparation original: ManualTripOriginal) throws -> ManualTripSaveInput {
        guard stage == .save, original.stage == .prepare, prepareID == original.id,
              prepareInputSHA256 == digest(original.originalUTF8), same(sourceTripID, original.sourceTripID),
              sourceVersion == original.sourceVersion, sourceUTF8 == original.sourceUTF8, selectedIDs == original.selectedIDs,
              let response = preparationResponseUTF8 else { throw TripFailure.storageUnavailable }
        let input = try original.prepareInput()
        // Extract only the stored HTTP trace; the normal reply decoder verifies
        // its exact envelope, diff and original command association below.
        var parser = StrictTripJSON(bytes: Array(response)); let root = try parser.document().object()
        let trace = try root.required("request_id").text()
        guard let prepared = try ManualTripReplies.preparation(response, original: input, requestID: trace) else { throw TripFailure.storageUnavailable }
        let saved = try ManualTripSaveInput(actionID: id, preparation: prepared, original: input)
        guard saved.originalUTF8 == originalUTF8 else { throw TripFailure.storageUnavailable }
        return saved
    }
}

extension ManualTripInput {
    /// Persistent bytes are a trust boundary. Reconstruct intent using the same
    /// explicit selection grammar, then require the exact original canonical wire.
    static func restoring(original: StructuredTripRecord, bytes: Data, selectedIDs: [String]) throws -> Self {
        guard !bytes.isEmpty, bytes.count <= 1_000_000, Set(selectedIDs).count == selectedIDs.count else { throw TripFailure.storageUnavailable }
        var parser = StrictTripJSON(bytes: Array(bytes)); let root = try parser.document()
        try factBounds(root, maxDepth: 32, maxNodes: 32768)
        guard tripCanonicalJSON(root) == bytes else { throw TripFailure.storageUnavailable }
        let edit: [String: TripJSONValue], needs: TripNeedsReference?
        if original.document.version == .needsBound {
            let f = try root.fields("version needs_reference edit"), ref = try f.required("needs_reference").fields("id expected_version")
            guard try f.required("version").text() == "TRIP-needs-edit.1" else { throw TripFailure.storageUnavailable }
            needs = try .init(id: ref.required("id").text(), expectedVersion: tripWireVersion(ref.required("expected_version")))
            edit = try f.required("edit").fields("version request_id trip_id expected_version original_hash title changes order")
        } else {
            edit = try root.fields("version request_id trip_id expected_version original_hash title changes order"); needs = nil
        }
        guard try edit.required("version").text() == (needs == nil ? "TRIP-manual-edit.1" : "TRIP-manual-edit.2"),
              try same(edit.required("trip_id").text(), original.tripID),
              try tripWireVersion(edit.required("expected_version")) == original.version,
              try same(edit.required("original_hash").text(), original.document.contentSHA256) else { throw TripFailure.storageUnavailable }
        var draft = try ManualTripDraft(original: original, needs: needs)
        for id in selectedIDs { try draft.selectItem(id, selected: true) }
        if let title = try edit.required("title").nullable({ try $0.text() }) { draft.setTitle(title) }
        var fields = Set<String>()
        let changes = try edit.required("changes").elements()
        guard changes.count <= 60 else { throw TripFailure.storageUnavailable }
        for node in changes {
            let f = try node.fields("item_id field value"), id = try tripWireID(f.required("item_id")), field = try f.required("field").text()
            guard fields.insert(id+"|"+field).inserted else { throw TripFailure.storageUnavailable }
            switch field {
            case "text": try draft.setText(f.required("value").text(), itemID: id)
            case "fixed":
                let v = try f.required("value").fields("state value")
                guard try v.required("state").text() == "known", case .boolean(let lock) = try v.required("value") else { throw TripFailure.storageUnavailable }
                try draft.setFixed(lock, itemID: id)
            case "schedule":
                let v = try f.required("value").fields("start end")
                let schedule = try ManualTripScheduleInput(start: .init(snapshot: .read(v.required("start"), version: original.document.version)),
                    end: .init(snapshot: .read(v.required("end"), version: original.document.version)))
                try draft.setSchedule(schedule, itemID: id)
            default: throw TripFailure.storageUnavailable
            }
        }
        if let ids = try edit.required("order").nullable({ try $0.elements().map(tripWireID) }) { try draft.setOrder(ids) }
        let input = try draft.freeze(requestID: tripWireID(edit.required("request_id")))
        guard input.originalUTF8 == bytes else { throw TripFailure.storageUnavailable }
        return input
    }
}

struct ManualTripRejection: TripJournalRecord, Sendable {
    let original: ManualTripOriginal
    let status: Int
    let responseUTF8: Data
    var storageID: String { original.storageID }
    func validate() throws {
        try original.validate()
        var parser = StrictTripJSON(bytes: Array(responseUTF8)); let root = try parser.document().fields("request_id error")
        let e = try root.required("error").fields("code category outcome recovery")
        let codes = [400: "INVALID_INPUT", 401: "ACCESS_DENIED", 409: "TRIP_CONFLICT", 413: "BODY_TOO_LARGE", 415: "UNSUPPORTED_MEDIA_TYPE"]
        guard UUID(uuidString: try root.required("request_id").text()) != nil, try e.required("outcome").text() == "failed",
              try e.required("recovery").text() == "do_not_retry", try codes[status] == e.required("code").text() else { throw TripFailure.storageUnavailable }
        _ = try e.required("category").text()
    }
}
