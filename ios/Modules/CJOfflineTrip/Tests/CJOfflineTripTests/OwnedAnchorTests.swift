import Foundation
import Testing
import Darwin
@testable import CJOfflineTrip

@Test func ownedContainerWalkRejectsOutsidePathsAndEveryOwnedSymlink() throws {
    let physical=try #require(realpath(FileManager.default.temporaryDirectory.path,nil))
    defer {free(physical)}
    let base=URL(fileURLWithPath:String(cString:physical)).appendingPathComponent("offline-anchor-"+UUID().uuidString)
    let owned=base.appendingPathComponent("home"),target=owned.appendingPathComponent("Library/Protected")
    let outside=base.appendingPathComponent("home-other")
    try FileManager.default.createDirectory(at:target,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
    try FileManager.default.createDirectory(at:outside,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
    defer {try? FileManager.default.removeItem(at:base)}
    let fd=try AtomicSnapshotStore.walkOwned(target.path,from:owned.path)
    #expect(close(fd)==0)
    #expect(throws:OfflineFailure.self) {try AtomicSnapshotStore.walkOwned(outside.path,from:owned.path)}
    let link=owned.appendingPathComponent("redirect")
    try FileManager.default.createSymbolicLink(at:link,withDestinationURL:outside)
    #expect(throws:OfflineFailure.self) {try AtomicSnapshotStore.walkOwned(link.path,from:owned.path)}
    #expect(throws:OfflineFailure.self) {try AtomicSnapshotStore.walkOwned(link.appendingPathComponent("child").path,from:owned.path)}
    #expect(throws:OfflineFailure.self) {try AtomicSnapshotStore.walkOwned(owned.path+"/../home-other",from:owned.path)}
}
