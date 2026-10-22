import Foundation
import Testing
import CJMessageClient
@MainActor private final class ChangedGenerationStore:SecureMessageStorage {
 var value:Snapshot?
 var onSave:(() throws -> Void)?
 var changeOnLoad=false
 var changedExactBytes=false
 func load(scope:StorageScope) throws -> Snapshot? {
  guard let value else {return nil}
  guard changeOnLoad else {return value}
  var object=try JSONSerialization.jsonObject(with:JSONEncoder().encode(value)) as! [String:Any]
  var saves=object["draftSaves"] as! [String:[String:Any]]
  for key in saves.keys {
   let before=saves[key]!["generation"] as! String
   saves[key]!["generation"]="e\u{301}"
   changedExactBytes=Data(before.utf8) != Data("e\u{301}".utf8)
  }
  object["draftSaves"]=saves
  let modified=try JSONDecoder().decode(Snapshot.self,from:JSONSerialization.data(withJSONObject:object))
  let roundtrip=try JSONSerialization.jsonObject(with:JSONEncoder().encode(modified)) as! [String:Any]
  let typedSaves=roundtrip["draftSaves"] as! [String:[String:Any]]
  changedExactBytes=typedSaves.values.contains { Data(($0["generation"] as! String).utf8) != Data("é".utf8) }
  self.value=modified
  return modified
 }
 func save(_ snapshot:Snapshot,scope:StorageScope) throws {
  value=snapshot;let hook=onSave;onSave=nil;try hook?()
 }
}
@Suite @MainActor struct ReadbackByteIdentityTests {
 @Test func canonicallyEquivalentButByteDifferentDurableGenerationMustRefuseOperation() throws {
  let store=ChangedGenerationStore(),original=Data("original CAS".utf8)
  let recovery=MessageRecovery(storage:store),scope=try StorageScope(environment:UUID().uuidString,account:"a")
  let lease=try recovery.activate(scope);try recovery.saveDraft(original,conversationID:"chat",lease:lease)
  store.onSave={try recovery.saveDraft(Data("new editor".utf8),conversationID:"chat",lease:lease);store.changeOnLoad=true}
  var returned=false
  #expect(throws:RecoveryError.self){_ = try recovery.beginDraftSave(conversationID:"chat",generation:"é",expectedRevision:0,originalUTF8:original,lease:lease);returned=true}
  #expect(store.changedExactBytes,"injected durable mismatch must differ in UTF8")
  #expect(!returned,"durable original generation changed; no outbound operation may escape")
 }
}

extension ReadbackByteIdentityTests {
 @Test func byteDifferentConfirmationReadbackCannotReportSaved() throws {
  let store=ChangedGenerationStore(),original=Data("original CAS".utf8)
  let recovery=MessageRecovery(storage:store),scope=try StorageScope(environment:UUID().uuidString,account:"a")
  let lease=try recovery.activate(scope);try recovery.saveDraft(original,conversationID:"chat",lease:lease)
  let operation=try recovery.beginDraftSave(conversationID:"chat",generation:"é",expectedRevision:0,originalUTF8:original,lease:lease)
  store.onSave={try recovery.saveDraft(Data("new editor".utf8),conversationID:"chat",lease:lease);store.changeOnLoad=true}
  var returned=false
  #expect(throws:RecoveryError.self){_ = try recovery.confirmDraftSave(operation,conversationID:"chat",generation:"é",revision:1,originalUTF8:original);returned=true}
  #expect(store.changedExactBytes && !returned)
  let persisted=try #require(store.value)
  let object=try JSONSerialization.jsonObject(with:JSONEncoder().encode(persisted)) as! [String:Any]
  let saves=object["draftSaves"] as! [String:[String:Any]]
  #expect(saves.values.allSatisfy { ($0["originalUTF8"] as? String)==original.base64EncodedString() })
 }
}
