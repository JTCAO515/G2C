import Foundation
import Testing
import CJAuth
import CJSession
import CJMessageClient
@testable import CJShell
@MainActor private final class CallbackMessageStore: SecureMessageStorage {
 var callback:(() -> Void)?
 var throwsAfterCallback = true
 func load(scope:StorageScope) throws -> Snapshot? { nil }
 func save(_ snapshot:Snapshot,scope:StorageScope) throws { callback?(); if throwsAfterCallback { throw RecoveryError.persistenceUnknown } }
}
@MainActor private final class EmptySession: SessionPersistence {
 func load() throws -> SessionMaterial? { nil }
 func save(_ material:SessionMaterial) throws {}
 func clearAndBlock() throws {}
}
@MainActor private final class EmptyMessages: SecureMessageStorage {
 func load(scope:StorageScope) throws -> Snapshot? { nil }
 func save(_ snapshot:Snapshot,scope:StorageScope) throws {}
}
@MainActor private final class CallbackLoadStore: SecureMessageStorage {
 var callback:(() -> Void)?
 func load(scope:StorageScope) throws -> Snapshot? { callback?(); throw RecoveryError.persistenceUnknown }
 func save(_ snapshot:Snapshot,scope:StorageScope) throws {}
}
@Suite @MainActor struct IndependentHostReentryTests {
 @Test(arguments: [true, false]) func oldDraftFailureMustNotInvalidateNewAccountBinding(storageThrows: Bool) throws {
  let shell=ShellState(preferences:try #require(UserDefaults(suiteName:"independent-"+UUID().uuidString)))
  let host=AssistantMessageHost(shell:shell), store=CallbackMessageStore()
  store.throwsAfterCallback = storageThrows
  let a=MessageRecovery(storage:store), b=MessageRecovery(storage:EmptyMessages())
  let sa=try StorageScope(environment:"synthetic",account:"a"), sb=try StorageScope(environment:"synthetic",account:"b")
  let la=try a.activate(sa), lb=try b.activate(sb)
  let account=AccountHost(shell:shell,session:SessionLifecycle(persistence:EmptySession(),restorePolicy:.userInitiatedOnly)) { _,_ in UnconfiguredSDKAdapter() }
  #expect(host.bind(AssistantMessageBinding(recovery:a,scope:sa,lease:la,generation:shell.generation,conversationID:"chat",messageID:nil,synthetic:true,isCurrent:{true},invalidateResources:{})))
  var rebound=false
  store.callback = {
   account.clearLocalSession()
   rebound=host.bind(AssistantMessageBinding(recovery:b,scope:sb,lease:lb,generation:shell.generation,conversationID:"new-chat",messageID:nil,synthetic:true,isCurrent:{true},invalidateResources:{}))
   shell.draft="new B editor"
  }
  shell.draft="old-account draft";host.saveDraft()
  #expect(rebound)
  #expect(host.isConfigured, "old save failure must not clear current B binding")
  try b.validateScope(sb,lease:lb)
  #expect(shell.draft == "new B editor" && !host.draftStored)
 }
 @Test func oldQueryFailureCannotInvalidateNewBinding() async throws {
  let shell=ShellState(preferences:try #require(UserDefaults(suiteName:"query-reentry-"+UUID().uuidString)))
  let host=AssistantMessageHost(shell:shell)
  let a=MessageRecovery(storage:EmptyMessages()), b=MessageRecovery(storage:EmptyMessages())
  let sa=try StorageScope(environment:UUID().uuidString,account:"a"), sb=try StorageScope(environment:UUID().uuidString,account:"b")
  let la=try a.activate(sa), lb=try b.activate(sb)
  try a.stage(messageID:"original",originalUTF8:Data("synthetic".utf8),lease:la)
  let submit=try a.beginSubmission(messageID:"original",lease:la);try a.observeUnknown(submit.operation)
  var resume:CheckedContinuation<Void, any Error>?
  #expect(host.bind(AssistantMessageBinding(recovery:a,scope:sa,lease:la,generation:shell.generation,conversationID:"chat",messageID:"original",synthetic:true,isCurrent:{true},invalidateResources:{},queryOriginal:{_,_ in
   try await withCheckedThrowingContinuation { resume=$0 }
  })))
  host.queryOriginal()
  for _ in 0..<1000 { if resume != nil { break }; await Task.yield() }
  let account=AccountHost(shell:shell,session:SessionLifecycle(persistence:EmptySession(),restorePolicy:.userInitiatedOnly)) { _,_ in UnconfiguredSDKAdapter() }
  account.clearLocalSession()
  #expect(host.bind(AssistantMessageBinding(recovery:b,scope:sb,lease:lb,generation:shell.generation,conversationID:"b-chat",messageID:nil,synthetic:true,isCurrent:{true},invalidateResources:{})))
  let pending=try #require(resume);pending.resume(throwing:RecoveryError.persistenceUnknown)
  for _ in 0..<20 { await Task.yield() }
  #expect(host.isConfigured && host.activity == .ready)
  try b.validateScope(sb,lease:lb)
 }
 @Test func oldBindReadAdmissionCannotOverrideReentrantNewBinding() throws {
  let shell=ShellState(preferences:try #require(UserDefaults(suiteName:"bind-reentry-"+UUID().uuidString)))
  let host=AssistantMessageHost(shell:shell)
  let a=MessageRecovery(storage:EmptyMessages()), b=MessageRecovery(storage:EmptyMessages())
  let sa=try StorageScope(environment:UUID().uuidString,account:"a"), sb=try StorageScope(environment:UUID().uuidString,account:"b")
  let la=try a.activate(sa), lb=try b.activate(sb)
  let oldGeneration=shell.generation
  let account=AccountHost(shell:shell,session:SessionLifecycle(persistence:EmptySession(),restorePolicy:.userInitiatedOnly)) { _,_ in UnconfiguredSDKAdapter() }
  var rebound=false
  let result=host.bind(AssistantMessageBinding(recovery:a,scope:sa,lease:la,generation:oldGeneration,conversationID:"old",messageID:nil,synthetic:true,isCurrent:{
   account.clearLocalSession()
   rebound=host.bind(AssistantMessageBinding(recovery:b,scope:sb,lease:lb,generation:shell.generation,conversationID:"new",messageID:nil,synthetic:true,isCurrent:{true},invalidateResources:{}))
   return true
  },invalidateResources:{}))
  #expect(!result && rebound && host.isConfigured && host.activity == .ready)
  try b.validateScope(sb,lease:lb)
 }

 @Test func failedOldClientLoadLeavesReentrantBHostUntouched() throws {
  let shell=ShellState(preferences:try #require(UserDefaults(suiteName:"load-reentry-"+UUID().uuidString)))
  let host=AssistantMessageHost(shell:shell), store=CallbackLoadStore()
  let a=MessageRecovery(storage:store), b=MessageRecovery(storage:EmptyMessages())
  let sa=try StorageScope(environment:UUID().uuidString,account:"a"), sb=try StorageScope(environment:UUID().uuidString,account:"b")
  let lb=try b.activate(sb)
  let account=AccountHost(shell:shell,session:SessionLifecycle(persistence:EmptySession(),restorePolicy:.userInitiatedOnly)) { _,_ in UnconfiguredSDKAdapter() }
  var rebound=false
  store.callback = {
   account.clearLocalSession()
   rebound=host.bind(AssistantMessageBinding(recovery:b,scope:sb,lease:lb,generation:shell.generation,conversationID:"b",messageID:nil,synthetic:true,isCurrent:{true},invalidateResources:{}))
  }
  #expect(throws: (any Error).self) { try a.activate(sa) }
  #expect(rebound && host.isConfigured && host.activity == .ready)
  try b.validateScope(sb,lease:lb)
 }

}
