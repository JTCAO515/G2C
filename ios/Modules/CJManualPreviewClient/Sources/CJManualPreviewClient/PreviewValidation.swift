import Foundation
import CJAPI

private func decodedBytes(_ value: String) throws -> Data {
    guard let bytes = Data(base64Encoded: value), bytes.base64EncodedString() == value,
          String(data: bytes, encoding: .utf8) != nil else { throw PreviewFailure.invalidResponse }
    var parser = StrictPreviewJSON(bytes: Array(bytes)); try parser.check()
    return bytes
}
private func matches<T: Codable>(_ bytes: String, _ value: T) throws -> Bool {
    let raw = try decodedBytes(bytes)
    let decoded = try JSONDecoder().decode(T.self, from: raw)
    return try encoded(decoded) == encoded(value)
}

/// Consumer consistency checks only. Does not compute or apply a patch or infer lock/feasibility.
func validatePreview(_ p: Components.Schemas.ManualPreview,
                     request r: Components.Schemas.ManualPreviewRequest,
                     original: Components.Schemas.TripRecord) throws {
    guard !p.can_save, p.preview_status == .LOCAL, p.protection_status == .UNKNOWN,
          try encoded(p.original) == encoded(original),
          exact(p.original.content_utf8_base64, r.original_content_utf8_base64),
          exact(p.original.trip_id, r.trip_id), p.original.version == r.expected_version,
          try encoded(p.selected_ids) == encoded(r.selected_ids), p.title_selected == r.title_selected,
          try matches(p.content_utf8_base64, p.document) else { throw PreviewFailure.invalidResponse }
    let before = original.document; let after = p.document
    let wantedTitle: String
    switch r.title {
    case .case1(let title): guard r.title_selected else { throw PreviewFailure.invalidResponse }; wantedTitle = title
    case .case2(let null): guard null.value == nil else { throw PreviewFailure.invalidResponse }; wantedTitle = before.title
    }
    guard exact(after.title, wantedTitle), !after.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
          after.items.count == before.items.count else { throw PreviewFailure.invalidResponse }
    let beforeIDs = before.items.map(\.id); let afterIDs = after.items.map(\.id)
    guard Set(afterIDs.map { Data($0.utf8) }).count == afterIDs.count,
          Set(beforeIDs.map { Data($0.utf8) }) == Set(afterIDs.map { Data($0.utf8) }) else { throw PreviewFailure.invalidResponse }
    switch r.order {
    case .case1(let order): guard try encoded(afterIDs) == encoded(order) else { throw PreviewFailure.invalidResponse }
    case .case2(let null): guard null.value == nil, try encoded(afterIDs) == encoded(beforeIDs) else { throw PreviewFailure.invalidResponse }
    }
    for (index, old) in before.items.enumerated() {
        guard let new = after.items.first(where: { exact($0.id, old.id) }) else { throw PreviewFailure.invalidResponse }
        let selected = r.selected_ids.contains(where: { exact($0, old.id) })
        let update = r.text_updates.first(where: { exact($0.item_id, old.id) })
        if !selected {
            guard exact(afterIDs[index], old.id), try encoded(old) == encoded(new), update == nil else { throw PreviewFailure.invalidResponse }
        } else if let update, !exact(update.text, old.text) {
            guard exact(new.text, update.text), new.verification == .pending, new.evidence.isEmpty,
                  !new.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw PreviewFailure.invalidResponse }
        } else {
            guard try encoded(old) == encoded(new) else { throw PreviewFailure.invalidResponse }
        }
    }
    // Check server-declared display entries against their source values. Require completeness,
    // but retain and display the server's original bytes and ordering unchanged.
    var paths = Set<Data>()
    for change in p.diff {
        let key = try encoded(change.path)
        guard paths.insert(key).inserted else { throw PreviewFailure.invalidResponse }
        if change.path == ["title"] {
            guard !exact(before.title, after.title), try matches(change.before_utf8_base64, before.title),
                  try matches(change.after_utf8_base64, after.title) else { throw PreviewFailure.invalidResponse }
        } else if change.path == ["items", "order"] {
            guard try encoded(beforeIDs) != encoded(afterIDs), try matches(change.before_utf8_base64, beforeIDs),
                  try matches(change.after_utf8_base64, afterIDs) else { throw PreviewFailure.invalidResponse }
        } else if change.path.count == 3, change.path[0] == "items", change.path[1] == "id",
                  let old = before.items.first(where: { exact($0.id, change.path[2]) }),
                  let new = after.items.first(where: { exact($0.id, change.path[2]) }) {
            guard try encoded(old) != encoded(new), try matches(change.before_utf8_base64, old),
                  try matches(change.after_utf8_base64, new) else { throw PreviewFailure.invalidResponse }
        } else { throw PreviewFailure.invalidResponse }
    }
    if !exact(before.title, after.title) { guard try paths.contains(encoded(["title"])) else { throw PreviewFailure.invalidResponse } }
    if try encoded(beforeIDs) != encoded(afterIDs) { guard try paths.contains(encoded(["items", "order"])) else { throw PreviewFailure.invalidResponse } }
    for old in before.items {
        guard let new = after.items.first(where: { exact($0.id, old.id) }) else { throw PreviewFailure.invalidResponse }
        if try encoded(old) != encoded(new) { guard try paths.contains(encoded(["items", "id", old.id])) else { throw PreviewFailure.invalidResponse } }
    }
}
