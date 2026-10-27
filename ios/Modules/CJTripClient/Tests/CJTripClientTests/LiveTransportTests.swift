import Foundation
import Testing
import CJMessageHTTP
import CJSession
import HTTPTypes
import OpenAPIRuntime
@testable import CJTripClient

@MainActor struct LiveTransportTests {
    @Test func explicitLiveCapabilityUsesActualHTTPAndKeepsMessageWritesClosed() async throws {
        let h = try Harness(); defer { h.clean() }
        let proposal = try fixture().proposal
        let process = Process(), output = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", "-u", "-c", #"""
import os,json,base64
from http.server import HTTPServer,BaseHTTPRequestHandler
p=json.loads(os.environ['G2C_SYNTHETIC_PROPOSAL']); trace=os.environ['G2C_SYNTHETIC_TRACE']; calls=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_POST(self):
  body=self.rfile.read(int(self.headers['Content-Length'])); calls.append(self.path)
  if self.path=='/v1/trip-confirmations':
   value=json.loads(body); fields=[value['action_id'],value['kind'],p['proposal_id'],p['candidate_hash'],'tc1.1900000000.'+'ab'*32]
   raw=json.dumps(fields,separators=(',',':')).encode()
   response={'request_id':trace,'action_utf8_base64':base64.b64encode(raw).decode(),'expires_at':1900000000,'proposal':p}
  else:
   a=json.loads(body)
   response={'request_id':trace,'receipt':{'action_id':a[0],'kind':a[1],'proposal_id':a[2],'candidate_hash':a[3],'trip_id':p['trip_id'],'committed_version':p['expected_version']+1}}
  raw=json.dumps(response).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('X-Request-ID',trace); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
s=HTTPServer(('127.0.0.1',0),Handler);s.timeout=5; print(s.server_port,flush=True)
s.handle_request();s.handle_request();s.server_close();print(json.dumps(calls),flush=True)
"""#]
        process.environment = ProcessInfo.processInfo.environment.merging([
            "G2C_SYNTHETIC_PROPOSAL": try json(proposal), "G2C_SYNTHETIC_TRACE": trace
        ]) { _, new in new }
        process.standardOutput = output; process.standardError = FileHandle.nullDevice
        try process.run()
        defer { if process.isRunning { process.terminate() }; process.waitUntilExit() }
        var portBytes = Data()
        while let byte = try output.fileHandleForReading.read(upToCount: 1), !byte.isEmpty {
            if byte == Data([10]) { break }; portBytes.append(byte)
        }
        let port = try #require(Int(String(decoding: portBytes, as: UTF8.self)))
        let endpoint = try TripEndpoint(url: URL(string: "http://127.0.0.1:\(port)")!,
            maximumRequestBytes: 100_000, maximumResponseBytes: 100_000, allowLoopbackHTTP: true)
        let session = SessionLifecycle(persistence: SyntheticSessionPersistence(), restorePolicy: .userInitiatedOnly)
        let operation = try session.beginTrustedSDKSave()
        let read = try NoRedirectTransport(requestTimeout: 3, resourceTimeout: 5)
        let store = try h.store()
        let readonly = TripClient(endpoint: endpoint, credentials: { _ in "synthetic-test-token" },
            currentBinding: { h.current }, session: session, sessionOperation: operation,
            pendingStore: store, liveReadTransport: read)
        #expect(!readonly.acceptsUserActions)
        let client = TripClient(endpoint: endpoint, credentials: { _ in "synthetic-test-token" },
            currentBinding: { h.current }, session: session, sessionOperation: operation,
            pendingStore: store, liveTransport: read, liveWrites: TripLiveWrites())
        #expect(client.acceptsUserActions)
        let prepared = try await client.prepare(.accept, proposal: proposal, binding: h.binding)
        #expect(try store.pending().isEmpty)
        let result = try await client.confirm(prepared, binding: h.binding, now: 1_899_999_000)
        guard case .confirmed(let receipt) = result else { Issue.record("HTTP confirmation failed"); return }
        #expect(receipt.action_id == prepared.pending.actionID)
        #expect(try store.pending().first?.originalUTF8 == prepared.pending.originalUTF8)
        let callsData = try output.fileHandleForReading.readToEnd()
        let calls = try JSONDecoder().decode([String].self, from: try #require(callsData))
        #expect(calls == ["/v1/trip-confirmations", "/v1/trip-actions"])
        await #expect(throws: TripFailure.liveWriteUnavailable) {
            try await client.transport.send(HTTPRequest(method: .post, scheme: nil, authority: nil, path: "/v1/messages"),
                body: HTTPBody(Data()), baseURL: endpoint.url, operationID: "receiveMessage")
        }
    }
}
