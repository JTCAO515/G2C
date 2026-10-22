import Foundation
import Auth
import CJSession
import Testing
import CJAuthSupabase
@MainActor private final class AdjacentSessionMemory:SessionPersistence {
 var material:SessionMaterial?
 var loadHook:(() throws -> Void)?
 var clearHook:(() throws -> Void)?
 func load() throws -> SessionMaterial? {let old=material;let hook=loadHook;loadHook=nil;try hook?();return old}
 func save(_ material:SessionMaterial) throws {self.material=material}
 func clearAndBlock() throws {material=nil;let hook=clearHook;clearHook=nil;try hook?()}
}
@Suite @MainActor struct AdjacentSessionCallbackTests {
 @Test func replacedLoadMustNotReturnOldBytesOrOverwriteNewSavedState() throws {
  let memory=AdjacentSessionMemory(),a=try SessionMaterial(trustedSDKBytes:Data("SYNTHETIC-A".utf8)),b=try SessionMaterial(trustedSDKBytes:Data("SYNTHETIC-B".utf8))
  let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
  try life.save(a,for:life.beginTrustedSDKSave());let old=try life.beginUserRestore();var latest:SessionOperation?;var returned=false
  memory.loadHook={try life.clear();let op=try life.beginTrustedSDKSave();latest=op;try life.save(b,for:op)}
  #expect(throws:SessionFailure.staleOperation){_ = try life.load(for:old);returned=true}
  #expect(!returned && life.state == .saved,"old load callback must not expose A or overwrite B state")
  #expect(life.isCurrent(try #require(latest)))
 }
 @Test func replacedLoadErrorMustNotBlockNewSave() throws {
  let memory=AdjacentSessionMemory(),a=try SessionMaterial(trustedSDKBytes:Data("SYNTHETIC-A".utf8)),b=try SessionMaterial(trustedSDKBytes:Data("SYNTHETIC-B".utf8))
  let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
  try life.save(a,for:life.beginTrustedSDKSave());let old=try life.beginUserRestore();var latest:SessionOperation?
  memory.loadHook={try life.clear();let op=try life.beginTrustedSDKSave();latest=op;try life.save(b,for:op);throw SessionFailure.storageUnavailable}
  #expect(throws:SessionFailure.staleOperation){_ = try life.load(for:old)}
  #expect(life.isCurrent(try #require(latest)) && life.state == .saved,"old load error must not block B")
 }
 @Test func invalidClearCallbackMustNotReportOrPublishClearedForNewSession() async throws {
  let id=UUID(),memory=AdjacentSessionMemory()
  let session=Session(accessToken:"SYNTHETIC-ACCESS",tokenType:"bearer",expiresIn:3600,expiresAt:Date().timeIntervalSince1970+3600,refreshToken:"SYNTHETIC-REFRESH",user:User(id:id,appMetadata:[:],userMetadata:[:],aud:"synthetic",createdAt:Date(),updatedAt:Date()))
  let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
  _ = SupabaseSessionBridge.saveTrustedSDKSession(session,lifecycle:life,operation:try life.beginTrustedSDKSave(),expectedUserID:id,uiIsCurrent:{true})
  let original=try life.beginUserRestore();let loaded=try #require(try life.load(for:original));var aIsCurrent=true;var latest:SessionOperation?
  let bridge=SupabaseSessionBridge(lifecycle:life,operation:original,expectedUserID:id,uiIsCurrent:{aIsCurrent},verify:{_,_ in .invalid})
  #expect(await bridge.revalidate(loaded,reason:.explicitRestore) == .identityInvalid)
  memory.clearHook={try life.clear();let op=try life.beginTrustedSDKSave();latest=op;try life.save(SessionMaterial(trustedSDKBytes:Data("SYNTHETIC-B".utf8)),for:op);aIsCurrent=false}
  #expect(bridge.clearAuthoritativelyInvalid() == .stale,"old invalid-session clear must not settle the replacement lifetime")
  #expect(life.isCurrent(try #require(latest)) && life.state == .saved,"old clear return must not overwrite B saved state")
 }
}

// Additional success/error boundaries beyond Testing's original three fixed counterexamples.
extension AdjacentSessionCallbackTests {
 @Test func replacedMissingLoadMustNotPublishMissingOverNewSession() throws {
  let memory=AdjacentSessionMemory();let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
  let old=try life.beginUserRestore();var latest:SessionOperation?
  memory.loadHook={try life.clear();let op=try life.beginTrustedSDKSave();latest=op;try life.save(SessionMaterial(trustedSDKBytes:Data("SYNTHETIC-B".utf8)),for:op)}
  #expect(throws:SessionFailure.staleOperation){_ = try life.load(for:old)}
  #expect(life.isCurrent(try #require(latest)) && life.state == .saved)
 }
 @Test func replacedClearErrorMustNotBlockNewSavedSession() throws {
  let memory=AdjacentSessionMemory();let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly);var latest:SessionOperation?
  memory.clearHook={try life.clear();let op=try life.beginTrustedSDKSave();latest=op;try life.save(SessionMaterial(trustedSDKBytes:Data("SYNTHETIC-B".utf8)),for:op);throw SessionFailure.storageUnavailable}
  #expect(throws:SessionFailure.staleOperation){try life.clear()}
  #expect(life.isCurrent(try #require(latest)) && life.state == .saved)
  #expect(memory.material?.withBytes { $0 == Data("SYNTHETIC-B".utf8) } == true)
 }
 @Test func sameOriginalLoadAndClearFailuresRemainBlocked() throws {
  for clearing in [false,true] {
   let memory=AdjacentSessionMemory();let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
   if clearing {
    memory.clearHook={throw SessionFailure.storageUnavailable}
    #expect(throws:SessionFailure.storageUnavailable){try life.clear()}
   } else {
    memory.loadHook={throw SessionFailure.storageUnavailable}
    #expect(throws:SessionFailure.storageUnavailable){_ = try life.load(for:life.beginUserRestore())}
   }
   #expect(life.state == .blocked(.storageUnavailable))
   #expect(throws:SessionFailure.restorationBlocked){try life.beginUserRestore()}
  }
 }
}

@MainActor private final class SuccessfulSaveReentryMemory: SessionPersistence {
 var material: SessionMaterial?
 var saveHook: (() throws -> Void)?
 func load() throws -> SessionMaterial? { material }
 func save(_ value: SessionMaterial) throws { material=value;let hook=saveHook;saveHook=nil;try hook?() }
 func clearAndBlock() throws { material=nil }
}
extension AdjacentSessionCallbackTests {
 @Test func replacedSuccessfulSaveMustReportStaleWithoutChangingB() throws {
  let memory=SuccessfulSaveReentryMemory();let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
  let original=try life.beginTrustedSDKSave();var latest:SessionOperation?
  memory.saveHook={try life.clear();let op=try life.beginTrustedSDKSave();latest=op;try life.save(SessionMaterial(trustedSDKBytes:Data("SYNTHETIC-B".utf8)),for:op)}
  #expect(throws:SessionFailure.staleOperation){try life.save(SessionMaterial(trustedSDKBytes:Data("SYNTHETIC-A".utf8)),for:original)}
  #expect(life.isCurrent(try #require(latest)) && life.state == .saved)
  #expect(memory.material?.withBytes { $0 == Data("SYNTHETIC-B".utf8) } == true)
 }
 @Test func currentAuthoritativeInvalidClearStillCompletes() async throws {
  let id=UUID(),memory=AdjacentSessionMemory()
  let session=Session(accessToken:"SYNTHETIC-ACCESS",tokenType:"bearer",expiresIn:3600,expiresAt:Date().timeIntervalSince1970+3600,refreshToken:"SYNTHETIC-REFRESH",user:User(id:id,appMetadata:[:],userMetadata:[:],aud:"synthetic",createdAt:Date(),updatedAt:Date()))
  let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
  _ = SupabaseSessionBridge.saveTrustedSDKSession(session,lifecycle:life,operation:try life.beginTrustedSDKSave(),expectedUserID:id,uiIsCurrent:{true})
  let operation=try life.beginUserRestore();let loaded=try #require(try life.load(for:operation))
  let bridge=SupabaseSessionBridge(lifecycle:life,operation:operation,expectedUserID:id,uiIsCurrent:{true},verify:{_,_ in .invalid})
  #expect(await bridge.revalidate(loaded,reason:.explicitRestore) == .identityInvalid)
  #expect(bridge.clearAuthoritativelyInvalid() == .invalidated)
  #expect(life.state == .cleared && memory.material == nil)
 }
}
