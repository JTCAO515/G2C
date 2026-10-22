import Foundation
import CryptoKit
import CJAPI

public enum OfflineFailure: Error, Equatable, Sendable {
    case unavailable, invalidSnapshot, unsupportedFormat, wrongNamespace, rollback, keyUnavailable
    case invalidPath, storageFailure, writeUnknown, corrupt
}

/// Host-supplied identity, never derived from a JWT and never an authorization grant.
public struct OfflineNamespace: Codable, Equatable, Sendable {
    public let account: UUID
    public let backend: UUID
    public let trip: String
    public init(account: UUID, backend: UUID, trip: String) throws {
        guard validID(trip) else { throw OfflineFailure.invalidSnapshot }
        self.account = account; self.backend = backend; self.trip = trip
    }
}

struct SnapshotMetadata: Codable, Equatable, Sendable {
    let format: Int
    let source: String
    let namespace: OfflineNamespace
    let version: Int64
    let syncedAt: Int64
    let deadline: Int64
    let boot: UUID
    let uptimeAtSync: Double
    let responseHash: String
    let contentHash: String
    let keyID: UUID
}

/// No public constructor: the accepted-source byte hook is not yet provided by TripClient.
public struct OfflineSnapshot: Sendable {
    let metadata: SnapshotMetadata
    let responseBytes: Data
    let trip: Components.Schemas.TripRecord
    public var version: Int64 { metadata.version }
    public var syncedAt: Int64 { metadata.syncedAt }
}

struct SnapshotEnvelope: Codable {
    let metadata: SnapshotMetadata
    let ciphertext: Data
}

public enum SnapshotCodec {
    public static let appFactoryAvailable = false
    static let maximumBytes = 4 * 1024 * 1024
    static let source = "GET /v1/trip-details;TRIP@c02cf08e52a0d8ffc2fefac99226654a7e01539c"

    // Module-only candidate capture. NOT proof that a server accepted a Trip.
    static func capture(response: Data, namespace: OfflineNamespace, syncedAt: Int64,
                        deadline: Int64, boot: UUID, uptime: Double, keyID: UUID) throws -> OfflineSnapshot {
        let trip = try validateResponse(response, namespace: namespace)
        guard syncedAt > 0, deadline > syncedAt, uptime.isFinite, uptime >= 0 else { throw OfflineFailure.invalidSnapshot }
        guard let content = Data(base64Encoded: trip.content_utf8_base64) else { throw OfflineFailure.invalidSnapshot }
        return OfflineSnapshot(metadata: .init(format: 1, source: source, namespace: namespace,
            version: Int64(trip.version), syncedAt: syncedAt, deadline: deadline, boot: boot,
            uptimeAtSync: uptime, responseHash: digest(response), contentHash: digest(content), keyID: keyID),
            responseBytes: response, trip: trip)
    }
    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]; return encoder
    }
    // Raw SymmetricKey calls are isolated test fixtures; canonical composition uses MessageEncryptionKey.withSymmetricKey.
    static func seal(_ snapshot: OfflineSnapshot, key: SymmetricKey) throws -> Data {
        guard key.bitCount == 256 else { throw OfflineFailure.keyUnavailable }
        let aad = try encoder().encode(snapshot.metadata)
        let box = try AES.GCM.seal(snapshot.responseBytes, using: key, authenticating: aad)
        guard let combined = box.combined else { throw OfflineFailure.corrupt }
        return try encoder().encode(SnapshotEnvelope(metadata: snapshot.metadata, ciphertext: combined))
    }
    static func open(_ data: Data, namespace: OfflineNamespace, key: SymmetricKey?, expectedKeyID: UUID,
                     minimumVersion: Int64) throws -> OfflineSnapshot {
        guard let key, key.bitCount == 256 else { throw OfflineFailure.keyUnavailable }
        guard data.count <= maximumBytes, minimumVersion > 0 else { throw OfflineFailure.corrupt }
        var strict = StrictSnapshotJSON(bytes: Array(data)); try strict.check()
        let envelope = try JSONDecoder().decode(SnapshotEnvelope.self, from: data)
        guard let object = try JSONSerialization.jsonObject(with: data) as? NSDictionary,
              object.isEqual(try JSONSerialization.jsonObject(with: encoder().encode(envelope))) else {
            throw OfflineFailure.invalidSnapshot
        }
        let m = envelope.metadata
        guard m.format == 1, m.source == source else { throw OfflineFailure.unsupportedFormat }
        guard m.namespace == namespace else { throw OfflineFailure.wrongNamespace }
        guard m.keyID == expectedKeyID else { throw OfflineFailure.keyUnavailable }
        let original: Data
        do { original = try AES.GCM.open(.init(combined: envelope.ciphertext), using: key, authenticating: encoder().encode(m)) }
        catch { throw OfflineFailure.corrupt }
        let result = try capture(response: original, namespace: namespace, syncedAt: m.syncedAt,
                                 deadline: m.deadline, boot: m.boot, uptime: m.uptimeAtSync, keyID: m.keyID)
        guard result.metadata == m else { throw OfflineFailure.corrupt }
        guard m.version >= minimumVersion else { throw OfflineFailure.rollback }
        return result
    }
    static func validateResponse(_ data: Data, namespace: OfflineNamespace) throws -> Components.Schemas.TripRecord {
        guard data.count <= maximumBytes / 2 else { throw OfflineFailure.invalidSnapshot }
        var strict = StrictSnapshotJSON(bytes: Array(data)); try strict.check()
        // Additional keys cannot turn a proposal into a formal record.
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              Set(object.keys) == ["request_id", "trip"],
              let request = object["request_id"] as? String, UUID(uuidString: request) != nil,
              let record = object["trip"] as? [String: Any],
              Set(record.keys) == ["trip_id", "version", "content_utf8_base64", "document"] else { throw OfflineFailure.invalidSnapshot }
        let response = try JSONDecoder().decode(Components.Schemas.TripDetailResponse.self, from: data)
        guard let raw = try JSONSerialization.jsonObject(with: data) as? NSDictionary,
              raw.isEqual(try JSONSerialization.jsonObject(with: encoder().encode(response))) else {
            throw OfflineFailure.invalidSnapshot
        }
        guard case .TripRecord(let trip) = response.trip,
              Data(trip.trip_id.utf8) == Data(namespace.trip.utf8), trip.version > 0,
              let bytes = Data(base64Encoded: trip.content_utf8_base64),
              bytes.base64EncodedString() == trip.content_utf8_base64,
              String(data: bytes, encoding: .utf8) != nil else { throw OfflineFailure.invalidSnapshot }
        var content = StrictSnapshotJSON(bytes: Array(bytes)); try content.check()
        let document = try JSONDecoder().decode(Components.Schemas.TripDocument.self, from: bytes)
        guard try encoder().encode(document) == encoder().encode(trip.document),
              !document.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !document.items.isEmpty else { throw OfflineFailure.invalidSnapshot }
        var ids = Set<Data>()
        for item in document.items {
            guard validID(item.id), ids.insert(Data(item.id.utf8)).inserted,
                  !item.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  item.evidence.allSatisfy({ !$0.isEmpty }),
                  item.verification != .verified || !item.evidence.isEmpty else { throw OfflineFailure.invalidSnapshot }
        }
        return trip
    }
}
func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
func validID(_ text: String) -> Bool {
    let b = Array(text.utf8)
    func alnum(_ c: UInt8) -> Bool { (48...57).contains(c) || (65...90).contains(c) || (97...122).contains(c) }
    return (1...128).contains(b.count) && alnum(b[0]) && b.allSatisfy { alnum($0) || [95,46,58,45].contains($0) }
}
