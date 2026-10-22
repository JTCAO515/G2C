import Foundation
import Auth
import CJSession
import Testing
@testable import CJAuthSupabase

@MainActor private final class ReentrantSessionMemory: SessionPersistence {
    var material: SessionMaterial?
    var beforeSave: (() throws -> Void)?
    var fail = false
    func load() throws -> SessionMaterial? { material }
    func save(_ material: SessionMaterial) throws {
        if let hook = beforeSave { beforeSave = nil; try hook(); throw SessionFailure.storageUnavailable }
        if fail { throw SessionFailure.storageUnavailable }
        self.material = material
    }
    func clearAndBlock() throws { material = nil }
}
@Suite @MainActor struct SessionSaveReentryTests {
    func session(_ id: UUID) -> Session {
        Session(accessToken: "SYNTHETIC-ACCESS", tokenType: "bearer", expiresIn: 3600,
                expiresAt: Date().timeIntervalSince1970+3600, refreshToken: "SYNTHETIC-REFRESH",
                user: User(id: id, appMetadata: [:], userMetadata: [:], aud: "synthetic", createdAt: Date(), updatedAt: Date()))
    }
    private func storedUser(_ memory: ReentrantSessionMemory) throws -> UUID {
        let material = try #require(memory.material)
        return try material.withBytes { try AuthClient.Configuration.jsonDecoder.decode(Session.self, from: $0).user.id }
    }
    @Test func oldInitialSaveFailureCannotBlockSuccessfulNewAccount() throws {
        let memory = ReentrantSessionMemory(); let life = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let a = UUID(), b = UUID(); var bOperation: SessionOperation?
        let aOperation = try life.beginTrustedSDKSave()
        memory.beforeSave = {
            try life.clear()
            let op = try life.beginTrustedSDKSave(); bOperation = op
            #expect(SupabaseSessionBridge.saveTrustedSDKSession(session(b), lifecycle: life, operation: op,
                    expectedUserID: b, uiIsCurrent: { true }) == .stored)
        }
        let result = SupabaseSessionBridge.saveTrustedSDKSession(session(a), lifecycle: life, operation: aOperation,
                        expectedUserID: a, uiIsCurrent: { true })
        let currentB = try #require(bOperation)
        #expect(result == .stale)
        #expect(life.isCurrent(currentB) && life.state == .saved)
        #expect(try storedUser(memory) == b)
    }
    @Test func oldVerifiedPersistFailureCannotBlockSuccessfulNewAccount() async throws {
        let memory = ReentrantSessionMemory(); let life = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly)
        let a = UUID(), b = UUID(); var bOperation: SessionOperation?
        _ = SupabaseSessionBridge.saveTrustedSDKSession(session(a), lifecycle: life, operation: try life.beginTrustedSDKSave(), expectedUserID: a, uiIsCurrent: { true })
        let restore = try life.beginUserRestore(); let loaded = try life.load(for: restore); let material = try #require(loaded)
        let bridge = SupabaseSessionBridge(lifecycle: life, operation: restore, expectedUserID: a, uiIsCurrent: { true }, verify: { _,_ in .verified(session(a)) })
        #expect(await bridge.revalidate(material, reason: .refresh) == .readyToSave)
        memory.beforeSave = {
            try life.clear()
            let op = try life.beginTrustedSDKSave(); bOperation = op
            #expect(SupabaseSessionBridge.saveTrustedSDKSession(session(b), lifecycle: life, operation: op, expectedUserID: b, uiIsCurrent: { true }) == .stored)
        }
        #expect(bridge.persistVerified() == .stale)
        let currentB = try #require(bOperation)
        #expect(life.isCurrent(currentB) && life.state == .saved)
        #expect(try storedUser(memory) == b)
        #expect(bridge.committedOperation == nil)
    }
    @Test func sameOriginalSaveFailureStillBlocks() throws {
        let memory = ReentrantSessionMemory(); memory.fail = true
        let life = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly); let id = UUID()
        let operation = try life.beginTrustedSDKSave()
        #expect(SupabaseSessionBridge.saveTrustedSDKSession(session(id), lifecycle: life, operation: operation, expectedUserID: id,
                uiIsCurrent: { true }) == .storageFailure(.storageUnavailable))
        #expect(life.state == .blocked(.storageUnavailable) && !life.isCurrent(operation))
        #expect(throws: SessionFailure.restorationBlocked) { try life.beginUserRestore() }
    }
    @Test func sameVerifiedPersistFailureStillBlocksWithoutDeletingOriginal() async throws {
        let memory = ReentrantSessionMemory(); let life = SessionLifecycle(persistence: memory, restorePolicy: .userInitiatedOnly); let id = UUID()
        _ = SupabaseSessionBridge.saveTrustedSDKSession(session(id), lifecycle: life, operation: try life.beginTrustedSDKSave(), expectedUserID: id, uiIsCurrent: { true })
        let restore = try life.beginUserRestore(); let loaded = try life.load(for: restore); let material = try #require(loaded)
        let bridge = SupabaseSessionBridge(lifecycle: life, operation: restore, expectedUserID: id, uiIsCurrent: { true }, verify: { _,_ in .verified(session(id)) })
        #expect(await bridge.revalidate(material, reason: .refresh) == .readyToSave)
        memory.fail = true
        #expect(bridge.persistVerified() == .storageFailure(.storageUnavailable))
        #expect(life.state == .blocked(.storageUnavailable))
        #expect(try storedUser(memory) == id)
    }
}
