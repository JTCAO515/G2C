import Foundation
import Testing
import Darwin
@testable import CJOfflineTrip

private final class Kernel: OfflineBootSemaphore {
    var names=Set<String>(), created=[String](), removed=[String]()
    var denied=false
    func exists(_ name:String) throws -> Bool {
        if denied {throw OfflineFailure.unavailable}
        return names.contains(name)
    }
    func createExclusive(_ name:String) throws {
        guard !denied,!names.contains(name) else {throw OfflineFailure.unavailable}
        names.insert(name);created.append(name)
    }
    func removeCreated(_ name:String) throws {names.remove(name);removed.append(name)}
}

@MainActor struct BootContinuityTests {
    private func directory() throws -> URL {
        let physical=try #require(realpath(FileManager.default.temporaryDirectory.path,nil))
        defer {free(physical)}
        let url=URL(fileURLWithPath:String(cString:physical)).appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:url,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        return url
    }
    private func store(_ root:URL) throws -> AtomicSnapshotStore {
        try AtomicSnapshotStore(existingPrivateDirectory:root,name:"boot-continuity.v1")
    }
    @Test func processReopenKeepsDomainButMissingKernelObjectRotatesWithoutRecreatingOldName() throws {
        let root=try directory();defer {try? FileManager.default.removeItem(at:root)}
        let kernel=Kernel(),firstStore=try store(root)
        let first=try OfflineBootContinuity.prepare(store:firstStore,group:"group.g2c.offline",kernel:kernel)
        #expect(first.name.utf8.count==30)
        let bytes=try firstStore.read()
        let reopened=try OfflineBootContinuity.prepare(store:store(root),group:"group.g2c.offline",kernel:kernel)
        #expect(first.boot==reopened.boot);#expect(first.name==reopened.name)
        #expect(kernel.created==[first.name]);#expect(try store(root).read()==bytes)
        kernel.names=[] // Kernel reboot, rather than an App process restart.
        #expect(try !first.isCurrent())
        let rebooted=try OfflineBootContinuity.prepare(store:store(root),group:"group.g2c.offline",kernel:kernel)
        #expect(rebooted.boot != first.boot);#expect(rebooted.name != first.name)
        #expect(!kernel.names.contains(first.name));#expect(kernel.created==[first.name,rebooted.name])
        #expect(try rebooted.isCurrent())
    }
    @Test func deniedAuthorityAndCorruptMarkerCannotCreateAReplacementDomain() throws {
        let root=try directory();defer {try? FileManager.default.removeItem(at:root)}
        let kernel=Kernel(),storage=try store(root)
        let first=try OfflineBootContinuity.prepare(store:storage,group:"group.g2c.offline",kernel:kernel)
        let bytes=try storage.read();kernel.denied=true
        #expect(throws:OfflineFailure.self) {try OfflineBootContinuity.prepare(store:store(root),group:"group.g2c.offline",kernel:kernel)}
        #expect(try store(root).read()==bytes);#expect(kernel.created==[first.name])
        kernel.denied=false
        for bad in [Data("{".utf8),Data("{\"version\":1,\"version\":1,\"boot\":\"\(UUID())\"}".utf8),Data("{\"version\":2,\"boot\":\"\(UUID())\"}".utf8)] {
            let replacement=try store(root);try replacement.write(bad)
            #expect(throws:(any Error).self) {try OfflineBootContinuity.prepare(store:store(root),group:"group.g2c.offline",kernel:kernel)}
            #expect(kernel.created==[first.name])
        }
    }
    @Test func uncertainMarkerCommitNeverMakesTheOldNameTrustedOrLeavesTheNewObjectUsable() throws {
        let root=try directory();defer {try? FileManager.default.removeItem(at:root)}
        let kernel=Kernel(),storage=try store(root)
        storage.afterRename={throw OfflineFailure.storageFailure}
        #expect(throws:OfflineFailure.self) {try OfflineBootContinuity.prepare(store:storage,group:"group.g2c.offline",kernel:kernel)}
        #expect(kernel.created.count==1);#expect(kernel.names.isEmpty);#expect(kernel.removed==kernel.created)
        let uncertainName=try #require(kernel.created.first)
        let recovered=try OfflineBootContinuity.prepare(store:store(root),group:"group.g2c.offline",kernel:kernel)
        #expect(recovered.name != uncertainName);#expect(try recovered.isCurrent())
        #expect(!kernel.names.contains(uncertainName))
    }
    @Test func creationDenialCannotPersistAMarkerOrBorrowAnotherAuthority() throws {
        let root=try directory();defer {try? FileManager.default.removeItem(at:root)}
        let kernel=Kernel(),storage=try store(root);kernel.denied=true
        #expect(throws:OfflineFailure.self) {try OfflineBootContinuity.prepare(store:storage,group:"group.g2c.offline",kernel:kernel)}
        #expect(try storage.read()==nil);#expect(kernel.created.isEmpty)
        #expect(kernel.names.isEmpty)
    }
    #if os(macOS)
    @Test func actualDarwinSemaphoreAcceptsThePreparedNameAndSurvivesCloseReopen() throws {
        let root=try directory();defer {try? FileManager.default.removeItem(at:root)}
        let kernel=POSIXOfflineBootSemaphore()
        let first=try OfflineBootContinuity.prepare(store:store(root),group:"group.g2c.offline",kernel:kernel)
        defer {try? kernel.removeCreated(first.name)}
        #expect(first.name.utf8.count==30);#expect(try first.isCurrent())
        #expect(throws:OfflineFailure.self) {try kernel.createExclusive(first.name)}
        let reopened=try OfflineBootContinuity.prepare(store:store(root),group:"group.g2c.offline",kernel:kernel)
        #expect(first.boot==reopened.boot);#expect(first.name==reopened.name)
        #expect(try reopened.isCurrent())
    }
    #endif
}
