import Testing
import Foundation
import Darwin
@testable import CJOfflineTrip

private func residueRoot() throws -> URL {
    let physical = try #require(realpath(FileManager.default.temporaryDirectory.path, nil))
    defer { free(physical) }
    let root = URL(fileURLWithPath: String(cString: physical)).appendingPathComponent("cj447-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
    return root
}
private func residue(_ root: URL, bytes: Data = Data([1, 2, 3])) throws -> URL {
    let url = root.appendingPathComponent(".write-" + UUID().uuidString)
    try bytes.write(to: url)
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    return url
}
@Test func knownPartialAndEmptyResiduesClearWithoutTouchingSnapshotOrOtherAccount() throws {
    let root = try residueRoot(), other = try residueRoot()
    defer { try? FileManager.default.removeItem(at: root); try? FileManager.default.removeItem(at: other) }
    let store = try AtomicSnapshotStore(existingPrivateDirectory: root)
    let snapshot = Data([4, 5, 6]); try store.write(snapshot)
    _ = try residue(root); _ = try residue(root, bytes: Data())
    let retained = try residue(other)
    try store.clearLocalTemporaryWrites(); try store.clearLocalTemporaryWrites()
    #expect(try store.read() == snapshot)
    #expect(try FileManager.default.contentsOfDirectory(atPath: root.path) == ["snapshot.aesgcm"])
    #expect(try Data(contentsOf: retained) == Data([1, 2, 3]))
    try store.clearLocalEntry()
    #expect(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
}
@Test(arguments: [".write-not-a-uuid", ".write-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "unknown", "snapshot.aesgcm.extra"])
func noncanonicalOrUnknownNameRefusesBeforeAnyErase(filename: String) throws {
    let root = try residueRoot(); defer { try? FileManager.default.removeItem(at: root) }
    let store = try AtomicSnapshotStore(existingPrivateDirectory: root), valid = try residue(root)
    let bad = root.appendingPathComponent(filename); try Data([9]).write(to: bad)
    #expect(throws: OfflineFailure.invalidPath) { try store.clearLocalTemporaryWrites() }
    #expect(try Data(contentsOf: valid) == Data([1, 2, 3]))
    #expect(try Data(contentsOf: bad) == Data([9]))
    try FileManager.default.removeItem(at: bad)
    try store.clearLocalTemporaryWrites()
    #expect(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
}
@Test(arguments: ["symlink", "hardlink", "directory"])
func temporaryLinksAndSubdirectoriesNeverAuthorizeRemoval(kind: String) throws {
    let root = try residueRoot(); defer { try? FileManager.default.removeItem(at: root) }
    let store = try AtomicSnapshotStore(existingPrivateDirectory: root), valid = try residue(root)
    let bad = root.appendingPathComponent(".write-" + UUID().uuidString)
    switch kind {
    case "symlink": try FileManager.default.createSymbolicLink(at: bad, withDestinationURL: valid)
    case "hardlink": try FileManager.default.linkItem(at: valid, to: bad)
    default: try FileManager.default.createDirectory(at: bad, withIntermediateDirectories: false)
    }
    #expect(throws: OfflineFailure.invalidPath) { try store.clearLocalTemporaryWrites() }
    #expect(try Data(contentsOf: valid) == Data([1, 2, 3]))
    try FileManager.default.removeItem(at: bad)
    try store.clearLocalTemporaryWrites()
    #expect(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
}
@Test func retainedDirectoryIdentityDoesNotAdoptReplacementAccount() throws {
    let root = try residueRoot(), retired = root.appendingPathExtension("retired")
    defer { try? FileManager.default.removeItem(at: root); try? FileManager.default.removeItem(at: retired) }
    let store = try AtomicSnapshotStore(existingPrivateDirectory: root), original = try residue(root)
    try FileManager.default.moveItem(at: root, to: retired)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
    let replacement = try residue(root, bytes: Data([8]))
    #expect(throws: OfflineFailure.invalidPath) { try store.clearLocalTemporaryWrites() }
    #expect(try Data(contentsOf: replacement) == Data([8]))
    #expect(try Data(contentsOf: retired.appendingPathComponent(original.lastPathComponent)) == Data([1, 2, 3]))
    try FileManager.default.removeItem(at: root); try FileManager.default.moveItem(at: retired, to: root)
    try store.clearLocalTemporaryWrites()
    #expect(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
}
@Test func pendingWriteStillRequiresOriginalReconciliationBeforeResidueCleanup() throws {
    let root = try residueRoot(); defer { try? FileManager.default.removeItem(at: root) }
    let store = try AtomicSnapshotStore(existingPrivateDirectory: root)
    store.afterRename = { try store.clearLocalTemporaryWrites() }
    #expect(throws: OfflineFailure.writeUnknown) { try store.write(Data([7, 7])) }
    store.afterRename = nil
    let temporary = try residue(root)
    #expect(throws: OfflineFailure.writeUnknown) { try store.clearLocalTemporaryWrites() }
    #expect(try Data(contentsOf: temporary) == Data([1, 2, 3]))
    #expect(store.reconcileOriginalWrite() == .committed)
    try store.clearLocalTemporaryWrites()
    #expect(try store.read() == Data([7, 7]))
    #expect(try FileManager.default.contentsOfDirectory(atPath: root.path) == ["snapshot.aesgcm"])
}
