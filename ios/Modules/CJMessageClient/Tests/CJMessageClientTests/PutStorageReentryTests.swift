import Foundation
import Testing
import CJMessageClient
@MainActor private final class ReentrantPutStore: SecureMessageStorage {
 var value:Snapshot?
 var callback:(() throws -> Void)?
 func load(scope:StorageScope) throws -> Snapshot? {value}
 func save(_ snapshot:Snapshot,scope:StorageScope) throws {
  value=snapshot
  let action=callback;callback=nil
  try action?()
 }
}
@Suite @MainActor struct IndependentPutReentryTests {
 @Test func beginSaveMustKeepPendingDurableAndPreserveNewEditorAfterStoreCallback() throws {
  let store=ReentrantPutStore()
  let recovery=MessageRecovery(storage:store),scope=try StorageScope(environment:UUID().uuidString,account:"a")
  let lease=try recovery.activate(scope),original=Data("original CAS".utf8),newEdit=Data("new editor".utf8)
  try recovery.saveDraft(original,conversationID:"chat",lease:lease)
  store.callback={try recovery.saveDraft(newEdit,conversationID:"chat",lease:lease)}
  _=try recovery.beginDraftSave(conversationID:"chat",generation:"g",expectedRevision:0,originalUTF8:original,lease:lease)
  #expect(try recovery.draft(conversationID:"chat",lease:lease)==newEdit,"old begin-save persistence must not erase newer same-lease editor")
  let persisted=try #require(store.value)
  let object=try #require(try JSONSerialization.jsonObject(with:JSONEncoder().encode(persisted)) as? [String:Any])
  let pending=try #require(object["draftSaves"] as? [String:Any])
  #expect(pending.count==1,"beginDraftSave must not return send operation after callback removed durable pending CAS")
 }
 @Test func confirmationPersistenceCallbackMustNotOverwriteOrMarkNewEditorSaved() throws {
  let store=ReentrantPutStore()
  let state=MessageRecovery(storage:store),scope=try StorageScope(environment:UUID().uuidString,account:"a")
  let lease=try state.activate(scope),original=Data("original CAS".utf8),newEdit=Data("new editor".utf8)
  try state.saveDraft(original,conversationID:"chat",lease:lease)
  let operation=try state.beginDraftSave(conversationID:"chat",generation:"g",expectedRevision:0,originalUTF8:original,lease:lease)
  store.callback={try state.saveDraft(newEdit,conversationID:"chat",lease:lease)}
  let matches=try state.confirmDraftSave(operation,conversationID:"chat",generation:"g",revision:1,originalUTF8:original)
  #expect(try state.draft(conversationID:"chat",lease:lease)==newEdit,"old response persistence must not overwrite newer same-lease edit")
  #expect(!matches,"old response must not report newer editor saved")
  #expect(try !state.draftConfirmationMatchesEditor(conversationID:"chat",revision:1,lease:lease))
 }
}

@MainActor private final class UncertainNestedStore: SecureMessageStorage {
 var value:Snapshot?
 var callback:(() throws -> Void)?
 var failReadback=false
 var overwriteAfterCallback=false
 func load(scope:StorageScope) throws -> Snapshot? {
  if failReadback { throw RecoveryError.persistenceUnknown }
  return value
 }
 func save(_ snapshot:Snapshot,scope:StorageScope) throws {
  let action=callback;callback=nil
  if !overwriteAfterCallback { value=snapshot }
  try action?()
  if overwriteAfterCallback { value=snapshot }
 }
}
@Suite @MainActor struct PutReentryUncertaintyTests {
 @Test func readbackFailureDoesNotGrantOutboundOperation() throws {
  let store=UncertainNestedStore();let r=MessageRecovery(storage:store)
  let scope=try StorageScope(environment:UUID().uuidString,account:"a"), original=Data("original".utf8), edit=Data("new edit".utf8)
  let lease=try r.activate(scope);try r.saveDraft(original,conversationID:"chat",lease:lease)
  store.callback={try r.saveDraft(edit,conversationID:"chat",lease:lease);store.failReadback=true}
  #expect(throws:RecoveryError.self) {try r.beginDraftSave(conversationID:"chat",generation:"g",expectedRevision:0,originalUTF8:original,lease:lease)}
  #expect(throws:RecoveryError.self) {try r.draft(conversationID:"chat",lease:lease)}
  store.failReadback=false
  let next=try r.activate(scope)
  #expect(try r.draft(conversationID:"chat",lease:next)==edit)
  #expect(try r.draftSave(conversationID:"chat",lease:next)?.originalUTF8==original)
  #expect(throws:RecoveryError.self) {try r.beginDraftSave(conversationID:"chat",generation:"g",expectedRevision:1,originalUTF8:edit,lease:next)}
 }
 @Test func storeOverwritingNestedCommitCannotReportSuccess() throws {
  let store=UncertainNestedStore();let r=MessageRecovery(storage:store)
  let scope=try StorageScope(environment:UUID().uuidString,account:"a"), original=Data("original".utf8)
  let lease=try r.activate(scope);try r.saveDraft(original,conversationID:"chat",lease:lease)
  let operation=try r.beginDraftSave(conversationID:"chat",generation:"g",expectedRevision:0,originalUTF8:original,lease:lease)
  store.overwriteAfterCallback=true
  store.callback={try r.saveDraft(Data("new edit".utf8),conversationID:"chat",lease:lease)}
  #expect(throws:RecoveryError.self) {try r.confirmDraftSave(operation,conversationID:"chat",generation:"g",revision:1,originalUTF8:original)}
  #expect(throws:RecoveryError.self) {try r.draftConfirmationMatchesEditor(conversationID:"chat",revision:1,lease:lease)}
 }
}
