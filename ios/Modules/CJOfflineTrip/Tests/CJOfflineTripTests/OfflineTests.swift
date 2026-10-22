import Testing
import Foundation
import CryptoKit
import Darwin
@testable import CJOfflineTrip

private let boot = UUID()
private let keyID = UUID()
private func namespace() throws -> OfflineNamespace { try .init(account: UUID(), backend: UUID(), trip: "trip1") }
private func response(version: Int = 2) throws -> Data {
    // Synthetic canonical TripDetailResponse shape, not accepted-service evidence.
    let doc: [String: Any] = ["title": "北京 / Beijing", "items": [["id":"item1", "text":"天坛 / Temple of Heaven", "verification":"pending", "evidence":[]]]]
    let content = try JSONSerialization.data(withJSONObject: doc, options: [.sortedKeys, .withoutEscapingSlashes])
    return try JSONSerialization.data(withJSONObject: ["request_id": UUID().uuidString, "trip":["trip_id":"trip1", "version":version, "content_utf8_base64":content.base64EncodedString(), "document":doc]], options: [.sortedKeys])
}
private func snapshot(_ ns: OfflineNamespace, data: Data? = nil) throws -> OfflineSnapshot {
    try SnapshotCodec.capture(response: data ?? response(), namespace: ns, syncedAt: 1000, deadline: 1100, boot: boot, uptime: 50, keyID: keyID)
}
private func privateRoot() throws -> URL {
    let physical = try #require(realpath(FileManager.default.temporaryDirectory.path, nil))
    defer { free(physical) }
    let root = URL(fileURLWithPath: String(cString: physical)).appendingPathComponent("cj022-synthetic-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
    return root
}

@Test func exactBytesAndNonce() throws {
    let ns = try namespace(), s = try snapshot(ns), key = SymmetricKey(size: .bits256)
    let sealed = try SnapshotCodec.seal(s, key: key)
    #expect(sealed != (try SnapshotCodec.seal(s, key: key)))
    let reopened = try SnapshotCodec.open(sealed, namespace: ns, key: key, expectedKeyID: keyID, minimumVersion: 2)
    #expect(reopened.responseBytes == s.responseBytes)
    #expect(reopened.trip.document.title == "北京 / Beijing")
    #expect(!String(decoding: sealed, as: UTF8.self).contains("北京"))
    #expect(!SnapshotCodec.appFactoryAvailable)
}

@Test func wrongKeyNamespaceRollbackAndTruncation() throws {
    let ns = try namespace(), s = try snapshot(ns), key = SymmetricKey(size: .bits256)
    let sealed = try SnapshotCodec.seal(s, key: key)
    #expect(throws: (any Error).self) { try SnapshotCodec.open(sealed, namespace: ns, key: SymmetricKey(size:.bits256), expectedKeyID:keyID, minimumVersion:1) }
    #expect(throws: OfflineFailure.keyUnavailable) { try SnapshotCodec.open(sealed, namespace:ns, key:nil, expectedKeyID:keyID, minimumVersion:1) }
    #expect(throws: OfflineFailure.keyUnavailable) { try SnapshotCodec.open(sealed, namespace:ns, key:key, expectedKeyID:UUID(), minimumVersion:1) }
    #expect(throws: OfflineFailure.wrongNamespace) { try SnapshotCodec.open(sealed, namespace:namespace(), key:key, expectedKeyID:keyID, minimumVersion:1) }
    #expect(throws: OfflineFailure.rollback) { try SnapshotCodec.open(sealed, namespace:ns, key:key, expectedKeyID:keyID, minimumVersion:3) }
    #expect(throws: (any Error).self) { try SnapshotCodec.open(Data(sealed.dropLast()), namespace:ns, key:key, expectedKeyID:keyID, minimumVersion:1) }
}

@Test func metadataAADAndCiphertextTampering() throws {
    let ns = try namespace(), s = try snapshot(ns), key = SymmetricKey(size: .bits256)
    let sealed = try SnapshotCodec.seal(s, key: key)
    for field in ["syncedAt", "deadline", "version", "uptimeAtSync", "format", "source", "responseHash", "contentHash", "boot"] {
        var object = try #require(JSONSerialization.jsonObject(with: sealed) as? [String:Any])
        var m = try #require(object["metadata"] as? [String:Any])
        m[field] = m[field] is String ? "altered" : 900
        object["metadata"] = m
        let bad = try JSONSerialization.data(withJSONObject:object)
        #expect(throws: (any Error).self) { try SnapshotCodec.open(bad, namespace:ns, key:key, expectedKeyID:keyID, minimumVersion:1) }
    }
    let e = try JSONDecoder().decode(SnapshotEnvelope.self, from:sealed)
    var cipher = e.ciphertext; cipher[0] ^= 1 // nonce is authenticated by GCM tag
    let bad = try SnapshotCodec.encoder().encode(SnapshotEnvelope(metadata:e.metadata,ciphertext:cipher))
    #expect(throws: OfflineFailure.corrupt) { try SnapshotCodec.open(bad, namespace:ns, key:key, expectedKeyID:keyID, minimumVersion:1) }
}

@Test func rejectsDraftNullDuplicateAndMismatchedOriginal() throws {
    let ns = try namespace()
    for text in ["{\"request_id\":\"x\",\"proposal\":{}}", "{\"request_id\":\"x\",\"trip\":null}", "{\"trip\":{},\"trip\":{}}"] {
        #expect(throws: (any Error).self) { try snapshot(ns, data:Data(text.utf8)) }
    }
    var object = try #require(JSONSerialization.jsonObject(with:response()) as? [String:Any])
    var trip = try #require(object["trip"] as? [String:Any])
    trip["content_utf8_base64"] = Data("{}".utf8).base64EncodedString(); object["trip"] = trip
    #expect(throws: (any Error).self) { try snapshot(ns,data:JSONSerialization.data(withJSONObject:object)) }
    #expect(throws: (any Error).self) { try snapshot(ns,data:response(version:0)) }
}

@Test func validityBoundariesAndClock() throws {
    let ns = try namespace(), s = try snapshot(ns)
    func evaluate(now:Int64? = 1050, last:Int64? = 1040, uptime:Double = 100, currentBoot:UUID = boot,
                  policy:OfflinePolicy? = .init(maximumAge:100), active:OfflineNamespace? = nil, allowed:Bool = true, min:Int64 = 2) -> OfflineValidity {
        OfflineValidityEvaluator.evaluate(s,active:active ?? ns,policy:policy,clock:.init(trustedWallSeconds:now,boot:currentBoot,uptime:uptime),lastTrustedWall:last,minimumVersion:min,sessionAllowsOffline:allowed)
    }
    #expect(evaluate() == .readable(version:2,syncedAt:1000,deadline:1100))
    #expect(evaluate(now:1100) == .stale)
    #expect(evaluate(uptime:150) == .stale)
    #expect(evaluate(policy:nil) == .unavailable)
    #expect(evaluate(policy:.init(maximumAge:0)) == .unavailable)
    #expect(evaluate(now:nil) == .unavailable)
    #expect(evaluate(last:nil) == .unavailable)
    #expect(evaluate(now:1030) == .unavailable)
    #expect(evaluate(now:999,last:900) == .unavailable)
    #expect(evaluate(uptime:49) == .unavailable)
    #expect(evaluate(uptime:.nan) == .unavailable)
    #expect(evaluate(allowed:false) == .unavailable)
    #expect(evaluate(active:try namespace()) == .unavailable)
    #expect(evaluate(min:3) == .unavailable)
    #expect(evaluate(currentBoot:UUID()) == .readable(version:2,syncedAt:1000,deadline:1100))
    #expect(evaluate(now:nil,currentBoot:UUID()) == .unavailable)
    #expect(evaluate(policy:.init(maximumAge:40)) == .stale)
    #expect(evaluate(policy:.init(maximumAge:Int64.max)) == .unavailable)
}

@Test func atomicReopenClearAndUnknownReadback() throws {
    let root = try privateRoot(); defer { try? FileManager.default.removeItem(at:root) }
    let store = try AtomicSnapshotStore(existingPrivateDirectory:root)
    #expect(try store.read() == nil)
    let ns = try namespace(), key = SymmetricKey(size:.bits256)
    let first = try SnapshotCodec.seal(snapshot(ns),key:key)
    try store.write(first)
    #expect(try AtomicSnapshotStore(existingPrivateDirectory:root).read() == first)
    let second = try SnapshotCodec.seal(snapshot(ns),key:key)
    store.afterRename = { throw OfflineFailure.storageFailure }
    #expect(throws: OfflineFailure.writeUnknown) { try store.write(second) }
    #expect(throws: OfflineFailure.writeUnknown) { try store.write(first) }
    #expect(store.reconcileOriginalWrite() == .committed)
    #expect(try store.read() == second)
    try store.clearLocalEntry()
    #expect(try store.read() == nil)
}

@Test func refusesSymlinkHardlinkPermissionsTruncationAndRootReplacement() throws {
    let root = try privateRoot(); defer { try? FileManager.default.removeItem(at:root) }
    let store = try AtomicSnapshotStore(existingPrivateDirectory:root)
    let path = root.appendingPathComponent("snapshot.aesgcm")
    let other = root.appendingPathComponent("other")
    try Data("private".utf8).write(to:other); chmod(other.path,0o600)
    try FileManager.default.createSymbolicLink(at:path,withDestinationURL:other)
    #expect(throws:(any Error).self) { try store.read() }
    #expect(throws:(any Error).self) { try store.write(Data([1])) }
    try FileManager.default.removeItem(at:path)
    #expect(link(other.path,path.path) == 0)
    #expect(throws:OfflineFailure.corrupt) { try store.read() }
    try FileManager.default.removeItem(at:path)
    try Data([1]).write(to:path); chmod(path.path,0o644)
    #expect(throws:OfflineFailure.corrupt) { try store.read() }
    chmod(path.path,0o600); try Data().write(to:path)
    #expect(throws:OfflineFailure.corrupt) { try store.read() }
    let moved = root.appendingPathExtension("moved"); defer { try? FileManager.default.removeItem(at:moved) }
    try FileManager.default.moveItem(at:root,to:moved)
    try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
    #expect(throws:OfflineFailure.invalidPath) { try store.read() }
    #expect(throws:OfflineFailure.invalidPath) { try store.clearLocalEntry() }
    let symlink = root.appendingPathComponent("alias")
    try FileManager.default.createSymbolicLink(at:symlink,withDestinationURL:moved)
    #expect(throws:OfflineFailure.invalidPath) { try AtomicSnapshotStore(existingPrivateDirectory:symlink) }
}

@Test func unknownWriteNeverFallsBackOrReseals() throws {
    let root = try privateRoot(); defer { try? FileManager.default.removeItem(at:root) }
    let store = try AtomicSnapshotStore(existingPrivateDirectory:root)
    try store.write(Data([1,2,3]))
    let path = root.appendingPathComponent("snapshot.aesgcm")
    store.afterRename = { try Data([9,9]).write(to:path); throw OfflineFailure.storageFailure }
    #expect(throws:OfflineFailure.writeUnknown) { try store.write(Data([4,5,6])) }
    #expect(store.reconcileOriginalWrite() == .unknown)
    #expect(throws:OfflineFailure.writeUnknown) { try store.write(Data([7,8,9])) }
    #expect(throws:OfflineFailure.writeUnknown) { try store.clearLocalEntry() }
    #expect(try store.read() == Data([9,9])) // raw bytes only, never returned as validated content
}

@Test func unknownFieldsAndVersionZeroRejected() throws {
    let ns = try namespace(), s = try snapshot(ns), key = SymmetricKey(size:.bits256)
    var object = try #require(JSONSerialization.jsonObject(with:SnapshotCodec.seal(s,key:key)) as? [String:Any])
    object["ignored"] = true
    #expect(throws:OfflineFailure.invalidSnapshot) { try SnapshotCodec.open(JSONSerialization.data(withJSONObject:object),namespace:ns,key:key,expectedKeyID:keyID,minimumVersion:1) }
    var raw = try #require(JSONSerialization.jsonObject(with:response()) as? [String:Any])
    var record = try #require(raw["trip"] as? [String:Any])
    var doc = try #require(record["document"] as? [String:Any]); doc["proposal_only"] = true
    record["document"] = doc; raw["trip"] = record
    #expect(throws:(any Error).self) { try snapshot(ns,data:JSONSerialization.data(withJSONObject:raw)) }
}
