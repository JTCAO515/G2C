import Foundation
import Testing
import Darwin
@testable import CJCleanupClient

private func ownedNativeRoot() throws -> URL {
    let physical = try #require(realpath(FileManager.default.temporaryDirectory.path, nil))
    defer { free(physical) }
    let path = URL(fileURLWithPath: String(cString: physical)).appendingPathComponent("device-native-" + UUID().uuidString)
    try FileManager.default.createDirectory(at:path,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
    return path
}
@MainActor struct DeviceCleanupDirectoryTests {
    @Test func searchOnlyAncestorDoesNotRequireDirectoryListingAccess() throws {
        let root=try ownedNativeRoot()
        let ancestor=root.appendingPathComponent("search-only"),leaf=ancestor.appendingPathComponent("owned-leaf")
        defer { chmod(ancestor.path,0o700);try? FileManager.default.removeItem(at:root) }
        try FileManager.default.createDirectory(at:leaf,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        #expect(chmod(ancestor.path,0o111)==0)
        let capture=try DeviceCleanupDirectory(existingPrivateDirectory:leaf)
        #expect(try capture.identityReference().hasPrefix("directory:"))
        try capture.requireEmpty()
    }
    @Test func searchOnlyTraversalStillRejectsAnAncestorSymlink() throws {
        let root=try ownedNativeRoot();defer{try? FileManager.default.removeItem(at:root)}
        let actual=root.appendingPathComponent("actual"),leaf=actual.appendingPathComponent("leaf")
        try FileManager.default.createDirectory(at:leaf,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        let alias=root.appendingPathComponent("alias")
        try FileManager.default.createSymbolicLink(at:alias,withDestinationURL:actual)
        #expect(throws:CleanupFailure.unavailable){try DeviceCleanupDirectory(existingPrivateDirectory:alias.appendingPathComponent("leaf"))}
        #expect(try FileManager.default.contentsOfDirectory(atPath:leaf.path).isEmpty)
    }
    @Test func anAncestorWithoutSearchPermissionStillFailsClosed() throws {
        let root=try ownedNativeRoot()
        let ancestor=root.appendingPathComponent("no-search"),leaf=ancestor.appendingPathComponent("leaf")
        defer{chmod(ancestor.path,0o700);try? FileManager.default.removeItem(at:root)}
        try FileManager.default.createDirectory(at:leaf,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        #expect(chmod(ancestor.path,0o600)==0)
        #expect(throws:CleanupFailure.unavailable){try DeviceCleanupDirectory(existingPrivateDirectory:leaf)}
    }
    @Test func theFinalPrivateDirectoryStillRequiresReadAccess() throws {
        let root=try ownedNativeRoot();let leaf=root.appendingPathComponent("leaf")
        defer{chmod(leaf.path,0o700);try? FileManager.default.removeItem(at:root)}
        try FileManager.default.createDirectory(at:leaf,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        #expect(chmod(leaf.path,0o300)==0)
        #expect(throws:CleanupFailure.unavailable){try DeviceCleanupDirectory(existingPrivateDirectory:leaf)}
    }
    @Test func unknownEntryDoesNotCountAsEmptyAndReadDoesNotEraseIt() throws {
        let root=try ownedNativeRoot();defer{try? FileManager.default.removeItem(at:root)}
        let capture=try DeviceCleanupDirectory(existingPrivateDirectory:root)
        let before=try capture.identityReference();try capture.requireEmpty()
        let file=root.appendingPathComponent("unknown");try Data([1]).write(to:file)
        #expect(throws:CleanupFailure.unavailable){try capture.requireEmpty()}
        #expect(try Data(contentsOf:file)==Data([1]))
        try FileManager.default.removeItem(at:file);try capture.requireEmpty()
        #expect(try capture.identityReference()==before)
    }
    @Test func heldDirectoryDoesNotAdoptReplacementOrSymlink() throws {
        let root=try ownedNativeRoot(),retired=root.appendingPathExtension("retired")
        defer{try? FileManager.default.removeItem(at:root);try? FileManager.default.removeItem(at:retired)}
        let capture=try DeviceCleanupDirectory(existingPrivateDirectory:root)
        try FileManager.default.moveItem(at:root,to:retired)
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        #expect(throws:CleanupFailure.stale){try capture.requireEmpty()}
        try FileManager.default.removeItem(at:root);try FileManager.default.createSymbolicLink(at:root,withDestinationURL:retired)
        #expect(throws:(any Error).self){try capture.requireEmpty()}
        try FileManager.default.removeItem(at:root);try FileManager.default.moveItem(at:retired,to:root);try capture.requireEmpty()
    }
    @Test func absentDescendantIsPinnedWithoutCreatingAnyDirectory() throws {
        let root=try ownedNativeRoot();defer{try? FileManager.default.removeItem(at:root)}
        let parent=try DeviceCleanupDirectory(existingOwnedAncestor:root)
        let missing=try DeviceCleanupDirectory(absentChild:"not-provided",of:parent)
        let child=try DeviceCleanupDirectory(absentChild:"account",of:missing)
        try child.requireEmpty();#expect(try FileManager.default.contentsOfDirectory(atPath:root.path).isEmpty)
        try FileManager.default.createDirectory(at:root.appendingPathComponent("not-provided"),withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        #expect(throws:CleanupFailure.stale){try child.requireEmpty()}
    }
    @Test func malformedChildSelectorsNeverEscapeTrustedParent() throws {
        let root=try ownedNativeRoot();defer{try? FileManager.default.removeItem(at:root)}
        let parent=try DeviceCleanupDirectory(existingPrivateDirectory:root)
        for name in ["", ".", "..", "../other-account", "/absolute", "bad\0name"] {
            #expect(throws:CleanupFailure.unavailable){try DeviceCleanupDirectory(absentChild:name,of:parent)}
        }
        #expect(try FileManager.default.contentsOfDirectory(atPath:root.path).isEmpty)
    }
}
