// Used only by the generated actual-App simulator acceptance route.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
@testable import CJMessageHTTP
@testable import CJTripClient
private struct LioCalendarWireFixture: View {
 let shell: ShellState
 private var chinese: Bool { shell.language.lio == .chinese }
 @State private var host: CalendarHTTPHost?
 @State private var failed = false
 var body: some View {
  Group {
   if let host {
    LioHome(language: chinese ? .chinese : .english, service: host.service, isDemo: false,
            tripLibrary: host.library, tripHistory: host.history,
            savedMemory: AnyView(Text(chinese ? "还没有记忆" : "No memories yet"))) {
      CalendarCounters(wire: host.wire)
    }
   } else if failed { Text("Fixture unavailable").accessibilityIdentifier("fixture.failed") }
   else { ProgressView().task { do { host = try CalendarHTTPHost() } catch { failed = true } } }
  }
  .preferredColorScheme(.light)
 }
}
struct CalendarCounters: View {
 let wire: CalendarHTTPWire
 @State private var counts = ""
 var body: some View { Text(counts).accessibilityIdentifier("fixture.counts").task { counts = await wire.counts() } }
}
@MainActor final class CalendarStorage: SecureMessageStorage {
 private var value: Snapshot?
 func load(scope: StorageScope) throws -> Snapshot? { value }
 func save(_ snapshot: Snapshot, scope: StorageScope) throws { value = snapshot }
}
@MainActor final class CalendarCredentials: MessageCredentialsProvider {
 func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}
@MainActor final class CalendarHTTPHost {
 let wire: CalendarHTTPWire
 let service: LioService
 let history: LioTripHistoryClient
 let library: LioTripLibrary
 init() throws {
  let exit = try CalendarHTTPWire(); wire = exit
  let recovery = MessageRecovery(storage: CalendarStorage())
  let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
  let lease = try recovery.activate(scope)
  let endpoint = try MessageEndpoint(url: URL(string:"https://synthetic.invalid")!, maximumRequestBytes:16384, maximumResponseBytes:4500000)
  let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint, validateMessage: {}, lio:true)
  let timeline = LioTimelineHTTP(scope: scope, lease: lease, credentials: CalendarCredentials(), transport: transport, firstChatRecovery: recovery)
  service = .signedConversation(timeline, destination:.defaultChat, version:.v3) { _ in }
  history = LioTripHistoryClient(timeline:timeline, recovery:recovery, scope:scope, lease:lease, version:.v3)
  let binding = TripBinding(environment:UUID(), account:UUID(), generation:UUID(), selection:UUID())
  let trips = TripClient(endpoint: try TripEndpoint(url:URL(string:"https://synthetic.invalid")!, maximumRequestBytes:16384, maximumResponseBytes:4500000), credentials:{ _ in "synthetic-only" }, currentBinding:{ binding }, interceptedTransport:exit)
  library = LioTripLibrary(calendarList: {
   let request = try trips.prepareCalendarStructuredPage(limit:20, binding:binding)
   return try await trips.calendarStructuredPage(for:request).trips
  }, calendarDetail: { id in
   let request = try trips.prepareCalendarStructuredDetail(id:id, binding:binding)
   guard let snapshot = try await trips.calendarStructuredDetail(for:request) else { return nil }
   return try trips.withCurrentCalendarStructuredSnapshot(snapshot) { _, record, _, _ in record }
  })
 }
}
actor CalendarHTTPWire: ClientTransport {
 static let conversation = "lio-dialogue-00000000000000000000000000000000"
 static let trace = "00000000-0000-4000-8000-000000000001"
 private let samples: [Data]
 private var messages: [[String:Any]] = []
 private var current: Int?
 private var undoID: String?
 private var sends = 0, undoPosts = 0, undoReads = 0, details = 0
 init() throws {
  samples = ["eyJ2ZXJzaW9uIjoiTElPLXRyaXAtY2FyZC4yIiwidHJpcF9pZCI6ImRlbW8tdHJpcCIsInRyaXBfdmVyc2lvbiI6MSwiY29udGVudF92ZXJzaW9uIjoic3RydWN0dXJlZC4zIiwiY29udGVudF9zaGEyNTYiOiIxOGM3NmVjMWJiZjNhNWM4Y2YwOGFjMzEzODc4Nzg3MzNlZGJiMjhkNWU5NWQxNmEwOWUxNjNkZWRiN2U2YjEwIiwidGl0bGUiOiLmiJDpg73kuInml6UgLyBDaGVuZ2R1IHRocmVlIGRheXMiLCJjYWxlbmRhciI6eyJzdGF0ZSI6InVuZGF0ZWQifSwiZGF5cyI6W3siZGF5X2luZGV4IjoxLCJpdGVtcyI6W3siaXRlbV9pZCI6ImhvdGVsLW1lZXR1cCIsImxhYmVsIjoi6YWS5bqX6ZuG5ZCIIC8gaG90ZWwgbWVldHVwIiwic3RhcnRfdGltZSI6IjA5OjAwIiwiZW5kX3RpbWUiOiIxMDowMCIsImZpeGVkIjp0cnVlfV19LHsiZGF5X2luZGV4IjoyLCJpdGVtcyI6W119LHsiZGF5X2luZGV4IjozLCJpdGVtcyI6W119XSwiZGF0ZV9jaGVja3MiOlt7ImtpbmQiOiJ3ZWF0aGVyIiwic3RhdGUiOiJub3RfY2hlY2tlZCIsImRheV9pbmRpY2VzIjpbMSwyLDNdLCJpdGVtX2lkcyI6W10sInJlYXNvbiI6ImRhdGVfbm90X3NldCIsImV2aWRlbmNlX3JlZnMiOltdfSx7ImtpbmQiOiJkYXlfb3BlbmluZyIsInN0YXRlIjoibm90X2NoZWNrZWQiLCJkYXlfaW5kaWNlcyI6WzEsMiwzXSwiaXRlbV9pZHMiOltdLCJyZWFzb24iOiJkYXRlX25vdF9zZXQiLCJldmlkZW5jZV9yZWZzIjpbXX1dfQ==",
"eyJ2ZXJzaW9uIjoiTElPLXRyaXAtY2FyZC4yIiwidHJpcF9pZCI6ImRlbW8tdHJpcCIsInRyaXBfdmVyc2lvbiI6MiwiY29udGVudF92ZXJzaW9uIjoic3RydWN0dXJlZC4zIiwiY29udGVudF9zaGEyNTYiOiI0YWVjYjFiYzJjMWQ1MjBjN2FhZmUyMjYxMDc1MTMwMTllMzZmOWM0ZmYzNDg4OWI1NGM3MTBkNTE3MjcxZTE1IiwidGl0bGUiOiLmiJDpg73kuInml6UgLyBDaGVuZ2R1IHRocmVlIGRheXMiLCJjYWxlbmRhciI6eyJzdGF0ZSI6ImRhdGVkIiwic3RhcnRfZGF0ZSI6IjIwMjYtMTItMDEifSwiZGF5cyI6W3siZGF5X2luZGV4IjoxLCJkYXRlIjoiMjAyNi0xMi0wMSIsIml0ZW1zIjpbeyJpdGVtX2lkIjoiaG90ZWwtbWVldHVwIiwibGFiZWwiOiLphZLlupfpm4blkIggLyBob3RlbCBtZWV0dXAiLCJzdGFydF90aW1lIjoiMDk6MDAiLCJlbmRfdGltZSI6IjEwOjAwIiwiZml4ZWQiOnRydWV9XX0seyJkYXlfaW5kZXgiOjIsImRhdGUiOiIyMDI2LTEyLTAyIiwiaXRlbXMiOltdfSx7ImRheV9pbmRleCI6MywiZGF0ZSI6IjIwMjYtMTItMDMiLCJpdGVtcyI6W119XSwiZGF0ZV9jaGVja3MiOlt7ImtpbmQiOiJ3ZWF0aGVyIiwic3RhdGUiOiJ1bmtub3duIiwiZGF5X2luZGljZXMiOlsxLDIsM10sIml0ZW1faWRzIjpbXSwicmVhc29uIjoiZXZpZGVuY2VfdW5hdmFpbGFibGUiLCJldmlkZW5jZV9yZWZzIjpbXX0seyJraW5kIjoiZGF5X29wZW5pbmciLCJzdGF0ZSI6InVua25vd24iLCJkYXlfaW5kaWNlcyI6WzEsMiwzXSwiaXRlbV9pZHMiOltdLCJyZWFzb24iOiJldmlkZW5jZV91bmF2YWlsYWJsZSIsImV2aWRlbmNlX3JlZnMiOltdfV19",
"eyJ2ZXJzaW9uIjoiVFJJUC1zdHJ1Y3R1cmVkLXJlYWQuMiIsInJlcXVlc3RfaWQiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJ0cmlwIjp7InRyaXBfaWQiOiJkZW1vLXRyaXAiLCJ2ZXJzaW9uIjoxLCJjb250ZW50X3NoYTI1NiI6IjE4Yzc2ZWMxYmJmM2E1YzhjZjA4YWMzMTM4Nzg3ODczM2VkYmIyOGQ1ZTk1ZDE2YTA5ZTE2M2RlZGI3ZTZiMTAiLCJjb250ZW50Ijp7ImNvbnRlbnRfdmVyc2lvbiI6InN0cnVjdHVyZWQuMyIsInRpdGxlIjoi5oiQ6YO95LiJ5pelIC8gQ2hlbmdkdSB0aHJlZSBkYXlzIiwiY2FsZW5kYXIiOnsic3RhdGUiOiJ1bmRhdGVkIn0sImRheXMiOlt7ImRheV9pbmRleCI6MX0seyJkYXlfaW5kZXgiOjJ9LHsiZGF5X2luZGV4IjozfV0sIml0ZW1zIjpbeyJpZCI6ImhvdGVsLW1lZXR1cCIsInRleHQiOiLphZLlupfpm4blkIggLyBob3RlbCBtZWV0dXAiLCJ2ZXJpZmljYXRpb24iOiJwZW5kaW5nIiwiZXZpZGVuY2UiOltdLCJzY2hlZHVsZSI6eyJzdGFydCI6eyJkYXlfaW5kZXgiOjEsInRpbWUiOnsic3RhdGUiOiJrbm93biIsInZhbHVlIjoiMDk6MDAifSwidGltZXpvbmUiOnsic3RhdGUiOiJrbm93biIsInZhbHVlIjoiQXNpYS9TaGFuZ2hhaSJ9LCJ1dGNfb2Zmc2V0Ijp7InN0YXRlIjoidW5rbm93biJ9fSwiZW5kIjp7ImRheV9pbmRleCI6MSwidGltZSI6eyJzdGF0ZSI6Imtub3duIiwidmFsdWUiOiIxMDowMCJ9LCJ0aW1lem9uZSI6eyJzdGF0ZSI6Imtub3duIiwidmFsdWUiOiJBc2lhL1NoYW5naGFpIn0sInV0Y19vZmZzZXQiOnsic3RhdGUiOiJ1bmtub3duIn19fSwiZml4ZWQiOnsic3RhdGUiOiJrbm93biIsInZhbHVlIjp0cnVlfSwic291cmNlX2NhdGVnb3J5IjoidXNlcl9wcm92aWRlZCIsInNvdXJjZV9yZWZzIjpbXX1dLCJzb3VyY2VzIjpbXSwiZGF0ZV9jaGVja3MiOlt7ImtpbmQiOiJ3ZWF0aGVyIiwic3RhdGUiOiJub3RfY2hlY2tlZCIsImRheV9pbmRpY2VzIjpbMSwyLDNdLCJpdGVtX2lkcyI6W10sInJlYXNvbiI6ImRhdGVfbm90X3NldCIsImV2aWRlbmNlX3JlZnMiOltdfSx7ImtpbmQiOiJkYXlfb3BlbmluZyIsInN0YXRlIjoibm90X2NoZWNrZWQiLCJkYXlfaW5kaWNlcyI6WzEsMiwzXSwiaXRlbV9pZHMiOltdLCJyZWFzb24iOiJkYXRlX25vdF9zZXQiLCJldmlkZW5jZV9yZWZzIjpbXX1dfX19",
"eyJ2ZXJzaW9uIjoiVFJJUC1zdHJ1Y3R1cmVkLXJlYWQuMiIsInJlcXVlc3RfaWQiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJ0cmlwIjp7InRyaXBfaWQiOiJkZW1vLXRyaXAiLCJ2ZXJzaW9uIjoyLCJjb250ZW50X3NoYTI1NiI6IjRhZWNiMWJjMmMxZDUyMGM3YWFmZTIyNjEwNzUxMzAxOWUzNmY5YzRmZjM0ODg5YjU0YzcxMGQ1MTcyNzFlMTUiLCJjb250ZW50Ijp7ImNvbnRlbnRfdmVyc2lvbiI6InN0cnVjdHVyZWQuMyIsInRpdGxlIjoi5oiQ6YO95LiJ5pelIC8gQ2hlbmdkdSB0aHJlZSBkYXlzIiwiY2FsZW5kYXIiOnsic3RhdGUiOiJkYXRlZCIsInN0YXJ0X2RhdGUiOiIyMDI2LTEyLTAxIn0sImRheXMiOlt7ImRheV9pbmRleCI6MSwiZGF0ZSI6IjIwMjYtMTItMDEifSx7ImRheV9pbmRleCI6MiwiZGF0ZSI6IjIwMjYtMTItMDIifSx7ImRheV9pbmRleCI6MywiZGF0ZSI6IjIwMjYtMTItMDMifV0sIml0ZW1zIjpbeyJpZCI6ImhvdGVsLW1lZXR1cCIsInRleHQiOiLphZLlupfpm4blkIggLyBob3RlbCBtZWV0dXAiLCJ2ZXJpZmljYXRpb24iOiJwZW5kaW5nIiwiZXZpZGVuY2UiOltdLCJzY2hlZHVsZSI6eyJzdGFydCI6eyJkYXlfaW5kZXgiOjEsInRpbWUiOnsic3RhdGUiOiJrbm93biIsInZhbHVlIjoiMDk6MDAifSwidGltZXpvbmUiOnsic3RhdGUiOiJrbm93biIsInZhbHVlIjoiQXNpYS9TaGFuZ2hhaSJ9LCJ1dGNfb2Zmc2V0Ijp7InN0YXRlIjoidW5rbm93biJ9fSwiZW5kIjp7ImRheV9pbmRleCI6MSwidGltZSI6eyJzdGF0ZSI6Imtub3duIiwidmFsdWUiOiIxMDowMCJ9LCJ0aW1lem9uZSI6eyJzdGF0ZSI6Imtub3duIiwidmFsdWUiOiJBc2lhL1NoYW5naGFpIn0sInV0Y19vZmZzZXQiOnsic3RhdGUiOiJ1bmtub3duIn19fSwiZml4ZWQiOnsic3RhdGUiOiJrbm93biIsInZhbHVlIjp0cnVlfSwic291cmNlX2NhdGVnb3J5IjoidXNlcl9wcm92aWRlZCIsInNvdXJjZV9yZWZzIjpbXX1dLCJzb3VyY2VzIjpbXSwiZGF0ZV9jaGVja3MiOlt7ImtpbmQiOiJ3ZWF0aGVyIiwic3RhdGUiOiJ1bmtub3duIiwiZGF5X2luZGljZXMiOlsxLDIsM10sIml0ZW1faWRzIjpbXSwicmVhc29uIjoiZXZpZGVuY2VfdW5hdmFpbGFibGUiLCJldmlkZW5jZV9yZWZzIjpbXX0seyJraW5kIjoiZGF5X29wZW5pbmciLCJzdGF0ZSI6InVua25vd24iLCJkYXlfaW5kaWNlcyI6WzEsMiwzXSwiaXRlbV9pZHMiOltdLCJyZWFzb24iOiJldmlkZW5jZV91bmF2YWlsYWJsZSIsImV2aWRlbmNlX3JlZnMiOltdfV19fX0=",
"eyJ2ZXJzaW9uIjoiVFJJUC1zdHJ1Y3R1cmVkLXJlYWQuMiIsInJlcXVlc3RfaWQiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJ0cmlwcyI6W3sidHJpcF9pZCI6ImRlbW8tdHJpcCIsInZlcnNpb24iOjEsImNvbnRlbnRfdmVyc2lvbiI6InN0cnVjdHVyZWQuMyIsInRpdGxlIjoi5oiQ6YO95LiJ5pelIC8gQ2hlbmdkdSB0aHJlZSBkYXlzIiwiY29udGVudF9zaGEyNTYiOiIxOGM3NmVjMWJiZjNhNWM4Y2YwOGFjMzEzODc4Nzg3MzNlZGJiMjhkNWU5NWQxNmEwOWUxNjNkZWRiN2U2YjEwIiwiY2FsZW5kYXIiOnsic3RhdGUiOiJ1bmRhdGVkIn0sImRheV9jb3VudCI6M31dLCJuZXh0X2FmdGVyIjpudWxsfQ==",
"eyJ2ZXJzaW9uIjoiVFJJUC1zdHJ1Y3R1cmVkLXJlYWQuMiIsInJlcXVlc3RfaWQiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJ0cmlwcyI6W3sidHJpcF9pZCI6ImRlbW8tdHJpcCIsInZlcnNpb24iOjIsImNvbnRlbnRfdmVyc2lvbiI6InN0cnVjdHVyZWQuMyIsInRpdGxlIjoi5oiQ6YO95LiJ5pelIC8gQ2hlbmdkdSB0aHJlZSBkYXlzIiwiY29udGVudF9zaGEyNTYiOiI0YWVjYjFiYzJjMWQ1MjBjN2FhZmUyMjYxMDc1MTMwMTllMzZmOWM0ZmYzNDg4OWI1NGM3MTBkNTE3MjcxZTE1IiwiY2FsZW5kYXIiOnsic3RhdGUiOiJkYXRlZCIsInN0YXJ0X2RhdGUiOiIyMDI2LTEyLTAxIn0sImRheV9jb3VudCI6M31dLCJuZXh0X2FmdGVyIjpudWxsfQ=="].map { Data(base64Encoded:$0)! }
 }
 func counts() -> String { "sends=\(sends) undoPosts=\(undoPosts) undoReads=\(undoReads) details=\(details)" }
 private func sample(_ index:Int) throws -> [String:Any] { try JSONSerialization.jsonObject(with:samples[index]) as! [String:Any] }
 func send(_ request:HTTPRequest, body:HTTPBody?, baseURL:URL, operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
  let path = request.path!, null = NSNull()
  let value: [String:Any]
  if request.method == .post {
   let input = try JSONSerialization.jsonObject(with:try await Data(collecting:body!, upTo:16384)) as! [String:Any]
   if path == "/v3/lio/messages" {
    precondition(input["version"] as? String == "LIO-message.3")
    let index = sends == 0 ? 0 : 1; current = index; sends += 1
    let text = input["text"] as! String, zh = input["locale"] as? String == "zh"
    messages.append(["message_id":input["message_id"]!, "text":text,
      "answer":zh ? "先按三天来安排。" : "Here is a three-day outline.", "status":"completed",
      "failure":null,"activity":null,"sources":[],"trip":try sample(index),"memory":null])
    value = ["version":"LIO-message-receipt.3","message_id":input["message_id"]!,"conversation_id":Self.conversation]
   } else if path == "/v3/lio/trip-undos" {
    precondition(input["version"] as? String == "LIO-trip-undo.3")
    precondition(current == 1)
    precondition(input["target"] as? String == "synthetic-target")
    undoPosts += 1; undoID = input["action_id"] as? String; current = 0
    throw URLError(.networkConnectionLost)
   } else { throw URLError(.unsupportedURL) }
  } else if path.hasPrefix("/v3/lio/trip-undo-receipts?") {
   let query = URLComponents(string:path)!.queryItems!
   precondition(query.first { $0.name == "action_id" }?.value == undoID)
   undoReads += 1
   value = ["version":"LIO-trip-undo-receipt.3","action_id":undoID!,"conversation_id":Self.conversation,"committed":true]
  } else if path.hasPrefix("/v3/lio/trip?") {
   value = ["version":"LIO-trip-history.3","conversation_id":Self.conversation,
     "current":try current.map { try sample($0) } ?? null,
     "history":try current == 1 ? [sample(0)] : [],
     "undo_target":current == 1 ? "synthetic-target" : null,"next_before":null]
  } else if path.hasPrefix("/v3/lio/timeline") {
   value = ["version":"LIO-timeline.3","conversation_id":Self.conversation,"messages":messages,"next_before":null]
  } else if path.hasPrefix("/v6/trip-structured?") {
   details += 1; value = try sample(current == 1 ? 3 : 2)
  } else if path.hasPrefix("/v2/trip-structured-list?") {
   value = try sample(current == 1 ? 5 : 4)
  } else { throw URLError(.unsupportedURL) }
  let bytes = try JSONSerialization.data(withJSONObject:value,options:[.sortedKeys,.withoutEscapingSlashes])
  var response = HTTPResponse(status:.ok)
  response.headerFields[.contentType] = "application/json"
  response.headerFields[HTTPField.Name("Cache-Control")!] = "no-store"
  response.headerFields[HTTPField.Name("X-Request-ID")!] = Self.trace
  return (response, HTTPBody(bytes))
 }
}

#endif
