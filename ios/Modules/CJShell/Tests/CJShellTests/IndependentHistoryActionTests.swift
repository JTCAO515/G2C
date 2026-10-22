import Foundation
import CryptoKit
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
import CJMessageHTTP
import CJAuth
import CJSession
@testable import CJShell
@MainActor private final class ActionStore:SecureMessageStorage {
 func load(scope:StorageScope) throws -> Snapshot? {nil}
 func save(_ snapshot:Snapshot,scope:StorageScope) throws {}
}
@MainActor private final class ActionCredentials:MessageCredentialsProvider {
 func bearer(for scope:StorageScope,lease:Lease) async throws -> String? {"synthetic"}
}
@MainActor private final class ActionSession:SessionPersistence {
 func load() throws -> SessionMaterial? {nil}
 func save(_ material:SessionMaterial) throws {}
 func clearAndBlock() throws {}
}
private actor ActionTransport:ClientTransport {
 var pages:[Data];var paths:[String?]=[]
 init(_ pages:[Data]) {self.pages=pages}
 func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
  paths.append(request.path)
  guard !pages.isEmpty else {throw MessageHTTPFailure.invalidResponse}
  var response=HTTPResponse(status:.ok);response.headerFields[HTTPField.Name("X-Request-ID")!]="00000000-0000-4000-8000-000000000001";response.headerFields[.contentType]="application/json"
  return (response,HTTPBody(pages.removeFirst()))
 }
}
@Suite @MainActor struct IndependentHistoryActionTests {
 private func json(_ fields:[String:Any]) throws -> Data {try JSONSerialization.data(withJSONObject:fields.merging(["request_id":"00000000-0000-4000-8000-000000000001"]){old,_ in old})}
 private func chat(_ id:String,_ sequence:Int)->[String:Any] {["conversation_id":id,"generation":"g1","epoch":0,"list_sequence":sequence]}
 private func bind(_ host:ServerHistoryHost,_ shell:ShellState,_ transport:ActionTransport) throws {
  let recovery=MessageRecovery(storage:ActionStore()),scope=try StorageScope(environment:UUID().uuidString,account:"synthetic")
  let lease=try recovery.activate(scope)
  let client=MessageHTTPClient(recovery:recovery,scope:scope,endpoint:try .init(url:URL(string:"https://synthetic.invalid")!,maximumRequestBytes:4096,maximumResponseBytes:16384),credentials:ActionCredentials(),interceptedTestTransport:transport)
  #expect(host.bind(.init(client:client,recovery:recovery,scope:scope,lease:lease,generation:shell.generation,limit:2,limits:try .init(maximumPageItems:2,maximumCursorBytes:128,maximumDecodedBytes:4096,maximumPages:5),synthetic:true,isCurrent:{true})))
 }
 @Test func oldSelectedConversationActionMustNotReadNewSelection() async throws {
  let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString))),host=ServerHistoryHost(shell:shell)
  let raw=Data("{\"message_id\":\"mb\",\"conversation_id\":\"b\",\"text\":\"private synthetic B\"}".utf8)
  let row:[String:Any]=["receipt":["message_id":"mb","conversation_id":"b","generation":"g1","run_id":"rb","sequence":1,"input_sha256":SHA256.hash(data:raw).map{String(format:"%02x",$0)}.joined()],"original_utf8_base64":raw.base64EncodedString(),"text":"private synthetic B"]
  let transport=ActionTransport([try json(["conversations":[chat("a",1),chat("b",2)],"next_cursor":NSNull()]),try json(["messages":[row],"next_cursor":NSNull()])])
  try bind(host,shell,transport);await host.loadConversations(context: host.captureReadContext())
  #expect(host.selectConversation(host.conversations[0],token:host.conversationSelectionToken))
  // Exact Task body used by ServerHistoryView's old A button; defer its start.
  let origin = host.captureReadContext()
  let oldAction:@MainActor () async -> Void = {await host.loadHistory(context: origin)}
  #expect(host.selectConversation(host.conversations[1],token:host.conversationSelectionToken))
  await oldAction()
  #expect(await transport.paths.count==1,"old A action must not issue a new B history GET")
  #expect(host.messages.isEmpty && host.historyStatus == .idle,"new B selection must remain explicitly unread")
 }
 @Test func oldAccountListActionMustNotReadReplacementBinding() async throws {
  let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString))),host=ServerHistoryHost(shell:shell)
  let oldTransport=ActionTransport([]);try bind(host,shell,oldTransport)
  let origin = host.captureReadContext()
  let oldAction:@MainActor () async -> Void = {await host.loadConversations(context: origin)}
  let account=AccountHost(shell:shell,session:SessionLifecycle(persistence:ActionSession(),restorePolicy:.userInitiatedOnly)){_,_ in UnconfiguredSDKAdapter()}
  account.clearLocalSession()
  let replacement=ActionTransport([try json(["conversations":[chat("private-new-account",1)],"next_cursor":NSNull()])])
  try bind(host,shell,replacement)
  await oldAction()
  #expect(await oldTransport.paths.isEmpty)
  #expect(await replacement.paths.isEmpty,"old account control must not issue a replacement-account GET")
  #expect(host.conversations.isEmpty && host.conversationsStatus == .idle,"new binding must stay unread until its own explicit action")
 }
 @Test(arguments: ["listFirst", "listMore", "historyFirst", "historyMore", "draft"])
 func allDeferredReadEntriesRejectChangedSelection(entry:String) async throws {
  let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString))),host=ServerHistoryHost(shell:shell)
  let raw=Data("{\"message_id\":\"ma\",\"conversation_id\":\"a\",\"text\":\"synthetic A\"}".utf8)
  let item:[String:Any]=["receipt":["message_id":"ma","conversation_id":"a","generation":"g1","run_id":"ra","sequence":1,"input_sha256":SHA256.hash(data:raw).map{String(format:"%02x",$0)}.joined()],"original_utf8_base64":raw.base64EncodedString(),"text":"synthetic A"]
  let transport=ActionTransport([try json(["conversations":[chat("a",1),chat("b",2)],"next_cursor":"list-next"]),
   try json(["messages":[item],"next_cursor":"history-next"])])
  try bind(host,shell,transport)
  await host.loadConversations(context:host.captureReadContext())
  #expect(host.selectConversation(host.conversations[0],token:host.conversationSelectionToken))
  await host.loadHistory(context:host.captureReadContext())
  #expect(host.hasMoreConversations && host.hasMoreMessages)
  let origin=host.captureReadContext()
  let oldAction:@MainActor () async -> Void = {
   switch entry {
   case "listFirst":await host.loadConversations(context:origin)
   case "listMore":await host.loadConversations(context:origin,more:true)
   case "historyFirst":await host.loadHistory(context:origin)
   case "historyMore":await host.loadHistory(context:origin,more:true)
   default:await host.loadServerDraft(context:origin)
   }
  }
  #expect(host.selectConversation(host.conversations[1],token:host.conversationSelectionToken))
  await oldAction()
  #expect(await transport.paths.count==2)
  #expect(host.selectedConversation?.conversation_id=="b" && host.historyStatus == .idle && host.draftStatus == .idle)
  #expect(host.messages.isEmpty && host.serverDraft==nil && host.conversations.count==2)
 }
 @Test func completedReadRetiresOldRetryContextWithoutTouchingNewPage() async throws {
  let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString))),host=ServerHistoryHost(shell:shell)
  let transport=ActionTransport([try json(["conversations":[chat("a",1)],"next_cursor":NSNull()])])
  try bind(host,shell,transport)
  let origin=host.captureReadContext()
  await host.loadConversations(context:origin)
  await host.loadConversations(context:origin)
  #expect(await transport.paths.count==1)
  #expect(host.conversationsStatus == .ready && host.conversations.map(\.conversation_id)==["a"])
 }

}
