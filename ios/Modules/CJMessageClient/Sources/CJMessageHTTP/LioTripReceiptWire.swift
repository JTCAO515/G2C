import CryptoKit
import Foundation

/// `rich.trip_receipt` of LIO-answer-rich.1 (#1984, T-1 #1994): what the automatic save of this answer did, as the App reads it.
///
/// Only the fields the App uses are kept. A receipt that fails any rule is dropped whole and never fails the page. The
/// server computes `first_autosave` (the account's first automatic save); the App never infers it. Unknown keys are
/// ignored; no place name or user text is in a receipt (the summary is counts only).
extension LioTimelineWire {
    public struct TripReceipt: Sendable, Equatable {
        public enum Status: Sendable, Equatable { case saved, notSaved, unknown }

        /// Why a save did not happen. A reason the App does not know reads as no reason: still "not saved".
        public enum Reason: Sendable, Equatable { case conflict, protected, tooLarge }

        /// Structure only, as the contract says: the App writes the sentence.
        public struct Summary: Sendable, Equatable {
            public struct Day: Sendable, Equatable {
                public let day: Int
                public let city: CardCity?
                public let added: Int
                public let updated: Int
                public let removed: Int
                public init(day: Int, city: CardCity? = nil, added: Int, updated: Int = 0, removed: Int = 0) {
                    self.day = day; self.city = city; self.added = added; self.updated = updated; self.removed = removed
                }
            }
            public let days: [Day]
            public let wishlistAdded: Int
            public let legsUpdated: Int
            public init(days: [Day], wishlistAdded: Int = 0, legsUpdated: Int = 0) {
                self.days = days; self.wishlistAdded = wishlistAdded; self.legsUpdated = legsUpdated
            }
            public var added: Int { days.reduce(0) { $0 + $1.added } }
            public var updated: Int { days.reduce(0) { $0 + $1.updated } }
            public var removed: Int { days.reduce(0) { $0 + $1.removed } }
        }

        /// The snapshot the undo is checked against (`UndoTarget` of `LIO-trip-history.4` for `restore`, the four fields of
        /// version 1 for `withdraw_created`). A snapshot, not an authorisation: the server rechecks all of it. Only the ids,
        /// versions and hashes the receipt carried; no place name or user text.
        public struct UndoTarget: Sendable, Equatable {
            /// What is restored: the version right before the committed one.
            public struct Restore: Sendable, Equatable {
                public let version: Int
                public let hash: String
                public let contentVersion: String
                public init(version: Int, hash: String, contentVersion: String) {
                    self.version = version; self.hash = hash; self.contentVersion = contentVersion
                }
            }
            public let tripID: String
            public let expectedVersion: Int
            public let originalHash: String
            public let contentVersion: String
            /// Nil for `withdraw_created`: there is nothing before version 1 to restore.
            public let restore: Restore?
            public init(tripID: String, expectedVersion: Int, originalHash: String, contentVersion: String, restore: Restore? = nil) {
                self.tripID = tripID; self.expectedVersion = expectedVersion; self.originalHash = originalHash
                self.contentVersion = contentVersion; self.restore = restore
            }
        }

        /// Whether the traveller can still undo this save, as the server computed it at this read.
        public struct Undo: Sendable, Equatable {
            public enum State: Sendable, Equatable { case available, expired, superseded, undone, unavailable }
            /// `restore` appends the version before; `withdrawCreated` marks the trip this save created as withdrawn.
            public enum Kind: Sendable, Equatable { case restore, withdrawCreated }
            public let state: State
            /// Only in `available`.
            public let kind: Kind?
            /// `undo-` and 40 hex characters; only in `available`.
            public let actionID: String?
            /// UTC with milliseconds; in every state but `unavailable`.
            public let until: String?
            /// Only in `available`.
            public let target: UndoTarget?
            public init(state: State, kind: Kind? = nil, actionID: String? = nil, until: String? = nil, target: UndoTarget? = nil) {
                self.state = state; self.kind = kind; self.actionID = actionID; self.until = until; self.target = target
            }
        }

        public let status: Status
        public let actionID: String
        /// Only on `notSaved`.
        public let reason: Reason?
        /// Only on `saved`.
        public let tripID: String?
        public let committedVersion: Int?
        /// `first_autosave` on a saved receipt: the server says this is the account's first automatic save.
        public let firstAutosave: Bool
        public let summary: Summary?
        public let undo: Undo?

        public init(status: Status, actionID: String, reason: Reason? = nil, tripID: String? = nil, committedVersion: Int? = nil,
                    firstAutosave: Bool = false, summary: Summary? = nil, undo: Undo? = nil) {
            self.status = status; self.actionID = actionID; self.reason = reason; self.tripID = tripID
            self.committedVersion = committedVersion; self.firstAutosave = firstAutosave; self.summary = summary; self.undo = undo
        }

        /// A save that happened and the server marked as the account's first.
        public var isFirstSave: Bool { status == .saved && firstAutosave }
    }

    static let maximumReceiptDays = 14
    static let maximumReceiptCount = 99

    /// `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`
    static func validReceiptID(_ value: String) -> Bool {
        let bytes = Array(value.utf8)
        guard (1...128).contains(bytes.count), isAlphanumeric(bytes[0]) else { return false }
        return bytes.allSatisfy { isAlphanumeric($0) || $0 == 95 || $0 == 46 || $0 == 58 || $0 == 45 }
    }

    private static func isAlphanumeric(_ byte: UInt8) -> Bool {
        (48...57).contains(byte) || (65...90).contains(byte) || (97...122).contains(byte)
    }

    /// `^undo-[0-9a-f]{40}$`
    static func validUndoActionID(_ value: String) -> Bool {
        let bytes = Array(value.utf8)
        guard bytes.count == 45, bytes.prefix(5).elementsEqual("undo-".utf8) else { return false }
        return bytes.dropFirst(5).allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }

    /// `YYYY-MM-DDTHH:MM:SS.mmm+00:00`
    static func validReceiptUntil(_ value: String) -> Bool {
        let template = Array("dddd-dd-ddTdd:dd:dd.ddd+00:00".utf8)
        let bytes = Array(value.utf8)
        guard bytes.count == template.count else { return false }
        return zip(template, bytes).allSatisfy { $0 == UInt8(ascii: "d") ? (48...57).contains($1) : $0 == $1 }
    }

    /// The receipt the App will use, or nil when any field it reads fails its rule.
    static func validTripReceipt(_ wire: TripReceiptWire?) -> TripReceipt? {
        guard let wire, case .value(let status) = wire.status, case .value(let actionID) = wire.actionID,
              validReceiptID(actionID) else { return nil }
        switch status {
        case "unknown":
            return TripReceipt(status: .unknown, actionID: actionID)
        case "not_saved":
            let reason: TripReceipt.Reason? = switch wire.reason.value {
            case "conflict": .conflict
            case "protected": .protected
            case "too_large": .tooLarge
            default: nil
            }
            return TripReceipt(status: .notSaved, actionID: actionID, reason: reason)
        case "saved":
            guard case .value(let tripID) = wire.tripID, validReceiptID(tripID),
                  case .value(let version) = wire.committedVersion, (1...Int.max - 1).contains(version),
                  case .value(let undoWire) = wire.undo, let undo = validReceiptUndo(undoWire, version: version, saveActionID: actionID) else { return nil }
            // Only ever `true`: `false`, a string or a number is a broken receipt, not "not first".
            let first: Bool
            switch wire.firstAutosave {
            case .absent: first = false
            case .value(true): first = true
            default: return nil
            }
            let summary: TripReceipt.Summary?
            switch wire.summary {
            case .absent: summary = nil
            case .value(let value):
                guard let checked = validReceiptSummary(value) else { return nil }
                summary = checked
            case .invalid: return nil
            }
            return TripReceipt(status: .saved, actionID: actionID, tripID: tripID, committedVersion: version,
                               firstAutosave: first, summary: summary, undo: undo)
        default:
            return nil
        }
    }

    private static func validReceiptUndo(_ wire: TripReceiptWire.UndoWire, version: Int, saveActionID: String) -> TripReceipt.Undo? {
        let state: TripReceipt.Undo.State
        switch wire.state {
        case "available": state = .available
        case "expired": state = .expired
        case "superseded": state = .superseded
        case "undone": state = .undone
        case "unavailable": state = .unavailable
        default: return nil
        }
        let until: String?
        switch wire.until {
        case .absent: until = nil
        case .value(let value) where validReceiptUntil(value): until = value
        default: return nil
        }
        if state != .unavailable, until == nil { return nil }
        guard state == .available else { return TripReceipt.Undo(state: state, until: until) }
        let kind: TripReceipt.Undo.Kind
        switch wire.kind {
        case .absent, .value("restore"): kind = .restore
        case .value("withdraw_created"): kind = .withdrawCreated
        default: return nil
        }
        // A save that created the trip (version 1) has nothing before it to restore, and only it can be withdrawn.
        guard kind == .withdrawCreated ? version == 1 : version >= 2,
              case .value(let actionID) = wire.actionID, validUndoActionID(actionID),
              // The server derives it from the save's id, so two devices tapping undo send the same one.
              actionID == undoActionID(forSave: saveActionID),
              case .value(let targetWire) = wire.target,
              let target = validUndoTarget(targetWire, kind: kind, version: version) else { return nil }
        return TripReceipt.Undo(state: .available, kind: kind, actionID: actionID, until: until, target: target)
    }

    /// `"undo-" + first 40 hex of sha256(the save's action_id)` (LIO-answer-rich.1).
    static func undoActionID(forSave id: String) -> String {
        let hex = SHA256.hash(data: Data(id.utf8)).map { String(format: "%02x", $0) }.joined()
        return "undo-" + String(hex.prefix(40))
    }

    private static let contentVersions: Set<String> = ["structured.1", "structured.2", "structured.3", "structured.4"]

    /// `^[0-9a-f]{64}$`
    static func validReceiptHash(_ value: String) -> Bool {
        let bytes = Array(value.utf8)
        return bytes.count == 64 && bytes.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }

    /// `restore`: exactly the seven fields of `UndoTarget` with `expected_version` the committed version and
    /// `restore_version` the one before it. `withdraw_created`: exactly the four fields of version 1. Anything else
    /// (a missing, extra or mistyped field) drops the receipt.
    private static func validUndoTarget(_ wire: TripReceiptWire.TargetWire, kind: TripReceipt.Undo.Kind, version: Int) -> TripReceipt.UndoTarget? {
        let current: Set<String> = ["trip_id", "expected_version", "original_hash", "content_version"]
        let previous: Set<String> = ["restore_version", "restore_hash", "restore_content_version"]
        guard wire.keys == (kind == .restore ? current.union(previous) : current),
              case .value(let tripID) = wire.tripID, validReceiptID(tripID),
              case .value(let expected) = wire.expectedVersion, expected == version,
              case .value(let hash) = wire.originalHash, validReceiptHash(hash),
              case .value(let content) = wire.contentVersion, contentVersions.contains(content) else { return nil }
        guard kind == .restore else {
            return TripReceipt.UndoTarget(tripID: tripID, expectedVersion: expected, originalHash: hash, contentVersion: content)
        }
        guard case .value(let restoreVersion) = wire.restoreVersion, restoreVersion == version - 1, restoreVersion >= 1,
              case .value(let restoreHash) = wire.restoreHash, validReceiptHash(restoreHash),
              case .value(let restoreContent) = wire.restoreContentVersion, contentVersions.contains(restoreContent) else { return nil }
        return TripReceipt.UndoTarget(tripID: tripID, expectedVersion: expected, originalHash: hash, contentVersion: content,
                                      restore: .init(version: restoreVersion, hash: restoreHash, contentVersion: restoreContent))
    }

    private static func validReceiptSummary(_ wire: TripReceiptWire.SummaryWire) -> TripReceipt.Summary? {
        guard wire.days.count <= maximumReceiptDays, (0...maximumReceiptCount).contains(wire.wishlistAdded),
              (0...maximumReceiptCount).contains(wire.legsUpdated) else { return nil }
        var days: [TripReceipt.Summary.Day] = []
        for entry in wire.days {
            guard (1...60).contains(entry.day), days.last.map({ $0.day < entry.day }) ?? true,
                  [entry.added, entry.updated, entry.removed].allSatisfy({ (0...maximumReceiptCount).contains($0) }),
                  entry.added + entry.updated + entry.removed > 0 else { return nil }
            var city: CardCity?
            if let wireCity = entry.city {
                guard validReceiptCity(wireCity) else { return nil }
                city = CardCity(id: wireCity.id, zh: wireCity.zh, en: wireCity.en)
            }
            days.append(.init(day: entry.day, city: city, added: entry.added, updated: entry.updated, removed: entry.removed))
        }
        return TripReceipt.Summary(days: days, wishlistAdded: wire.wishlistAdded, legsUpdated: wire.legsUpdated)
    }

    /// `id` `^[a-z]{3,20}$`; `zh` 1-12 and `en` 1-24 characters on one line with no control, separator, zero-width or
    /// bidirectional characters.
    private static func validReceiptCity(_ city: TripReceiptWire.CityWire) -> Bool {
        let id = Array(city.id.utf8)
        guard (3...20).contains(id.count), id.allSatisfy({ (97...122).contains($0) }) else { return false }
        return validReceiptLine(city.zh, limit: 12) && validReceiptLine(city.en, limit: 24)
    }

    private static func validReceiptLine(_ value: String, limit: Int) -> Bool {
        guard (1...limit).contains(value.unicodeScalars.count), value == value.trimmingCharacters(in: .whitespaces) else { return false }
        return !value.unicodeScalars.contains { scalar in
            switch scalar.value {
            case 0x00...0x1F, 0x7F...0x9F, 0x200B...0x200F, 0x2028...0x202E, 0x2060...0x2064, 0xFEFF: true
            default: false
            }
        }
    }
}

/// A field that can be missing, fine, or there but of the wrong type. A wrong type is not "missing": the receipt
/// that carries it is dropped.
enum LioWireField<Value: Decodable & Sendable>: Sendable {
    case absent
    case value(Value)
    case invalid

    init<Key: CodingKey>(_ container: KeyedDecodingContainer<Key>, _ key: Key) {
        guard container.contains(key) else { self = .absent; return }
        if let value = try? container.decode(Value.self, forKey: key) { self = .value(value) } else { self = .invalid }
    }

    var value: Value? { if case .value(let value) = self { value } else { nil } }
}

/// The receipt as sent, before any rule is applied. Every field is read on its own, so the checks in
/// `LioTimelineWire.validTripReceipt` see exactly what was there.
struct TripReceiptWire: Decodable, Sendable {
    let status: LioWireField<String>
    let actionID: LioWireField<String>
    let reason: LioWireField<String>
    let tripID: LioWireField<String>
    let committedVersion: LioWireField<Int>
    let firstAutosave: LioWireField<Bool>
    let summary: LioWireField<SummaryWire>
    let undo: LioWireField<UndoWire>

    struct CityWire: Decodable, Sendable { let id: String; let zh: String; let en: String }

    struct SummaryWire: Decodable, Sendable {
        struct DayWire: Decodable, Sendable {
            let day: Int
            let city: CityWire?
            let added: Int
            let updated: Int
            let removed: Int
        }
        let days: [DayWire]
        let wishlistAdded: Int
        let legsUpdated: Int
        enum CodingKeys: String, CodingKey { case days, wishlistAdded = "wishlist_added", legsUpdated = "legs_updated" }
    }

    struct UndoWire: Decodable, Sendable {
        let state: String
        let kind: LioWireField<String>
        let actionID: LioWireField<String>
        let until: LioWireField<String>
        let target: LioWireField<TargetWire>
        enum CodingKeys: String, CodingKey { case state, kind, actionID = "action_id", until, target }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            state = try c.decode(String.self, forKey: .state)
            kind = LioWireField(c, .kind)
            actionID = LioWireField(c, .actionID)
            until = LioWireField(c, .until)
            target = LioWireField(c, .target)
        }
    }

    /// The undo target as sent. The key set is kept, because a target with a missing or extra field is not the contract's.
    struct TargetWire: Decodable, Sendable {
        let keys: Set<String>
        let tripID: LioWireField<String>
        let expectedVersion: LioWireField<Int>
        let originalHash: LioWireField<String>
        let contentVersion: LioWireField<String>
        let restoreVersion: LioWireField<Int>
        let restoreHash: LioWireField<String>
        let restoreContentVersion: LioWireField<String>
        enum CodingKeys: String, CodingKey {
            case tripID = "trip_id", expectedVersion = "expected_version", originalHash = "original_hash"
            case contentVersion = "content_version", restoreVersion = "restore_version", restoreHash = "restore_hash"
            case restoreContentVersion = "restore_content_version"
        }
        private struct AnyKey: CodingKey {
            let stringValue: String
            var intValue: Int? { nil }
            init?(stringValue: String) { self.stringValue = stringValue }
            init?(intValue: Int) { nil }
        }
        init(from decoder: Decoder) throws {
            keys = Set(try decoder.container(keyedBy: AnyKey.self).allKeys.map(\.stringValue))
            let c = try decoder.container(keyedBy: CodingKeys.self)
            tripID = LioWireField(c, .tripID)
            expectedVersion = LioWireField(c, .expectedVersion)
            originalHash = LioWireField(c, .originalHash)
            contentVersion = LioWireField(c, .contentVersion)
            restoreVersion = LioWireField(c, .restoreVersion)
            restoreHash = LioWireField(c, .restoreHash)
            restoreContentVersion = LioWireField(c, .restoreContentVersion)
        }
    }

    enum CodingKeys: String, CodingKey {
        case status, reason, summary, undo
        case actionID = "action_id", tripID = "trip_id", committedVersion = "committed_version", firstAutosave = "first_autosave"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = LioWireField(c, .status)
        actionID = LioWireField(c, .actionID)
        reason = LioWireField(c, .reason)
        tripID = LioWireField(c, .tripID)
        committedVersion = LioWireField(c, .committedVersion)
        firstAutosave = LioWireField(c, .firstAutosave)
        summary = LioWireField(c, .summary)
        undo = LioWireField(c, .undo)
    }
}
