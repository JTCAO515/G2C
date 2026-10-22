import Foundation
import Testing
import Auth
import CJAuth
import CJAuthSupabase
import CJSession
@testable import CJShell

@MainActor private final class LoadMemory: SessionPersistence {
    var material: SessionMaterial?
    var onLoad: (() throws -> Void)?
    var failLoad = false
    var loadFailure:SessionFailure = .storageUnavailable
    func load() throws -> SessionMaterial? {
        let original = material
        let callback=onLoad;onLoad=nil;try callback?()
        if failLoad { throw loadFailure }
        return original
    }
    func save(_ value: SessionMaterial) throws { material=value }
    func clearAndBlock() throws { material=nil }
}
@MainActor private final class LoadVerifier: AccountSessionVerification {
    var generation=UUID()
    var verifiedUserID:UUID?
    init(_ id:UUID){verifiedUserID=id}
    func verifyInitialSession(_ candidate:Session,attempt:AuthAttempt) async -> SDKSessionCheck {.verified(candidate)}
    func revalidateSession(_ candidate:Session,reason:SessionRevalidationReason) async -> SDKSessionCheck {.verified(candidate)}
}
@Suite @MainActor struct IndependentSDKHostLoadTests {
    private func value(_ id:UUID,_ marker:String)->Session {
        Session(accessToken:"SYNTHETIC-"+marker,tokenType:"bearer",expiresIn:3600,
          expiresAt:Date().timeIntervalSince1970+3600,refreshToken:"SYNTHETIC-REFRESH-"+marker,
          user:User(id:id,appMetadata:[:],userMetadata:[:],aud:"synthetic",createdAt:Date(),updatedAt:Date()))
    }
    @Test(arguments:[false,true],[false,true]) func oldLoadSettlementCannotBlockReplacement(fails:Bool, changesVerification:Bool) throws {
        let aid=UUID(); let bid=changesVerification ? UUID():aid
        let memory=LoadMemory(),verification=LoadVerifier(aid)
        memory.material=try SessionMaterial(trustedSDKBytes:AuthClient.Configuration.jsonEncoder.encode(value(aid,"A")))
        let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
        let ui=ShellState(preferences:try #require(UserDefaults(suiteName:"cj-testing-sdk-load-"+UUID().uuidString)))
        let host=AccountHost(shell:ui,session:life,sdkConfiguration:.init(),verification:verification)
        var replacement:SessionOperation?
        var replacementBytes:SessionMaterial?
        memory.onLoad={
            try life.clear()
            if changesVerification { verification.generation=UUID();verification.verifiedUserID=bid }
            let op=try life.beginTrustedSDKSave();replacement=op
            #expect(SupabaseSessionBridge.saveTrustedSDKSession(value(bid,"B"),lifecycle:life,operation:op,
                expectedUserID:bid,uiIsCurrent:{true}) == .stored)
            replacementBytes=memory.material
            memory.failLoad=fails
        }
        host.restoreSession()
        let op=try #require(replacement)
        #expect(life.isCurrent(op) && life.state == .saved)
        let matches=try #require(memory.material).withBytes { stored in replacementBytes?.withBytes { stored == $0 } == true }
        #expect(matches)
        #expect(!host.isRestoring && host.localSessionStatus == .idle && host.sessionBridgeResult == .stale)
        #expect(!host.canUseRestrictedBusiness)
        if case .blocked=host.localSessionStatus {
            Issue.record("Old restore load settlement blocked host after replacement B became current")
        }
    }
    @Test func sameOriginalLoadFailureStillBlocks() throws {
        let id=UUID(),memory=LoadMemory(),verification=LoadVerifier(id)
        memory.failLoad=true
        let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
        let ui=ShellState(preferences:try #require(UserDefaults(suiteName:"cj-testing-sdk-load-control-"+UUID().uuidString)))
        let host=AccountHost(shell:ui,session:life,sdkConfiguration:.init(),verification:verification)
        host.restoreSession()
        #expect(host.localSessionStatus == .blocked(.storageUnavailable))
        #expect(life.state == .blocked(.storageUnavailable))
    }
    @Test func sameOriginalStaleNamedFailureIsStillARealBlock() throws {
        let id=UUID(),memory=LoadMemory(),verification=LoadVerifier(id)
        memory.failLoad=true;memory.loadFailure = .staleOperation
        let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
        let ui=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let host=AccountHost(shell:ui,session:life,sdkConfiguration:.init(),verification:verification)
        host.restoreSession()
        #expect(host.localSessionStatus == .blocked(.staleOperation))
        #expect(life.state == .blocked(.staleOperation) && !host.canUseRestrictedBusiness)
    }

    @Test func explicitHostClearDuringLoadKeepsItsClearResult() throws {
        let id=UUID(),memory=LoadMemory(),verification=LoadVerifier(id)
        memory.material=try SessionMaterial(trustedSDKBytes:AuthClient.Configuration.jsonEncoder.encode(value(id,"A")))
        let life=SessionLifecycle(persistence:memory,restorePolicy:.userInitiatedOnly)
        let ui=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let host=AccountHost(shell:ui,session:life,sdkConfiguration:.init(),verification:verification)
        memory.onLoad={ host.clearLocalSession() }
        host.restoreSession()
        #expect(host.localSessionStatus == .cleared && life.state == .cleared)
        #expect(!host.isRestoring && !host.canRestoreSession && memory.material == nil)
    }

}
