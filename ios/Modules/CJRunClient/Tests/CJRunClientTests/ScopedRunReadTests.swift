import Foundation
import Testing
import CJAPI
import CJMessageHTTP
import CJSession
import OpenAPIRuntime
import HTTPTypes
@testable import CJRunClient

private let scopedTrace = "00000000-0000-4000-8000-000000000336"
private actor ScopedRunWire: ClientTransport {
    let display: Data
    let draft: Data
    var mutation = ""
    var operations: [String] = []
    var returned: (@MainActor @Sendable () -> Void)?
    init(display: Data, draft: Data) { self.display=display; self.draft=draft }
    func configure(_ value: String) { mutation=value }
    func onReturn(_ callback: @escaping @MainActor @Sendable () -> Void) { returned=callback }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        operations.append(operationID)
        #expect(request.method == .get && body == nil && request.headerFields[.authorization] == "Bearer synthetic-only")
        let raw: Data
        if operationID == "getTripEditRunDisplayV5" { #expect(request.path == "/v5/run-display?message_id=edit-original"); raw=display }
        else if operationID == "getTripEditRunDraftStatusV6" { #expect(request.path == "/v6/run-draft-status?message_id=edit-original"); raw=draft }
        else { throw RunDisplayFailure.invalidReference }
        var value = try #require(JSONSerialization.jsonObject(with: raw) as? [String: Any])
        value["request_id"] = scopedTrace
        if mutation == "pointerMismatch" && operationID == "getTripEditRunDraftStatusV6" {
            var pointer = value["scoped_result"] as! [String: Any]; pointer["result_id"]="different-original-result"; value["scoped_result"]=pointer
        }
        if mutation == "runningPointer" && operationID == "getTripEditRunDisplayV5" {
            var snapshot = value["snapshot"] as! [String: Any]; snapshot["status"]="running"; snapshot["text_state"]="partial"; value["snapshot"]=snapshot
        }
        let encoded = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
        if let returned { await returned() }
        var headers=HTTPFields(); headers[.contentType]="application/json"; headers[.cacheControl]="no-store"; headers[.init("x-request-id")!]=scopedTrace
        return (HTTPResponse(status:.ok,headerFields:headers),HTTPBody(encoded))
    }
}
@MainActor private struct ScopedRunStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
@MainActor private final class ScopedRunFixture {
    let session=SessionLifecycle(persistence:ScopedRunStore(),restorePolicy:.userInitiatedOnly)
    let model: RunDisplayModel
    let wire: ScopedRunWire
    var current=true
    init(kind: String) throws {
        var root=URL(fileURLWithPath:#filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let object=try #require(JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("contracts/message/edit-result-examples.1.json"))) as? [String:Any])
        let rows=try #require(object["read_positive"] as? [[String:Any]])
        func envelope(_ schema:String) throws -> Data {
            let row=try #require(rows.first { row in
                guard row["schema"] as? String == schema,let value=row["value"] as? [String:Any],let pointer=value["scoped_result"] as? [String:Any] else { return false }
                return pointer["kind"] as? String == kind
            })
            return try JSONSerialization.data(withJSONObject:#require(row["value"] as? [String:Any]),options:[.sortedKeys])
        }
        let display=try envelope("RunDisplay5"), draft=try envelope("RunDraftStatus6")
        wire=ScopedRunWire(display:display,draft:draft)
        let reference=try MessageEditReference.decodeResponseReference(display,maximumBytes:65536)
        let operation=try session.beginTrustedSDKSave()
        let endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        model=try RunDisplayModel(endpoint:endpoint,maximumMessageIDBytes:16384,maximumTextBytes:10000,credentials:{ _ in "synthetic-only" },transport:wire,readsDraftStatus:true,draftStatusVersion:.v6)
        let receipt=Components.Schemas.MessageReceipt(message_id:reference.messageID,conversation_id:reference.conversationID,generation:reference.generation,run_id:reference.runID,sequence:Int(reference.sequence),input_sha256:reference.inputSHA256)
        let source=try RunDisplaySource(receipt:receipt,editReference:reference,session:session,operation:operation,isCurrent:{ [weak self] in self?.current == true })
        #expect(model.select(source))
    }
    func read() async { await model.perform(model.prepareRead()) }
}
@MainActor struct ScopedRunReadTests {
    @Test(arguments:["clarification_required","expansion_required"])
    func explicitNewReadsKeepTheExactOriginalAndNeverWrite(kind:String) async throws {
        let f=try ScopedRunFixture(kind:kind); await f.read()
        guard case .loaded(let display)=f.model.state,case .loadedScoped(let draft)=f.model.draftStatus else { Issue.record("new original read missing");return }
        #expect(display.scopedResult == draft.scopedResult && draft.scopedResult?.kind.rawValue == kind)
        #expect(display.snapshot.status == .completed && display.snapshot.text.isEmpty)
        #expect(await f.wire.operations == ["getTripEditRunDisplayV5","getTripEditRunDraftStatusV6"])
    }
    @Test func contradictoryCompletedPointersWithholdTheDraftResult() async throws {
        let f=try ScopedRunFixture(kind:"clarification_required"); await f.wire.configure("pointerMismatch"); await f.read()
        guard case .unavailable=f.model.draftStatus else { Issue.record("contradictory original pointer accepted");return }
        #expect(f.model.draftStatus.scopedResult == nil)
    }
    @Test func aNonterminalSnapshotCannotCarryACommittedResult() async throws {
        let f=try ScopedRunFixture(kind:"expansion_required"); await f.wire.configure("runningPointer"); await f.read()
        guard case .unavailable=f.model.state else { Issue.record("running result accepted");return }
        #expect(await f.wire.operations == ["getTripEditRunDisplayV5"])
    }
    @Test func retirementDuringTheAwaitWithholdsTheLatePointer() async throws {
        let f=try ScopedRunFixture(kind:"clarification_required"); await f.wire.onReturn { f.current=false }; await f.read()
        if case .loaded=f.model.state { Issue.record("retired original was displayed") }
        #expect(f.model.draftStatus.scopedResult == nil)
    }
}
