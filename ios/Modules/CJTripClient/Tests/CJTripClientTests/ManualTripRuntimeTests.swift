import Foundation
import Testing
import CryptoKit
import HTTPTypes
import OpenAPIRuntime
import CJMessageHTTP
@testable import CJTripClient

/// Non-network L0 state-machine fixture. Native evidence must use the real C
/// factory/worker/private PG; this actor is never an acceptance API substitute.
private actor ManualFixtureServer: ClientTransport {
    let original: StructuredTripRecord
    let after: Data
    let template: Data
    let needs: Bool
    var version: Int
    var preparations: [String: Data] = [:]
    var proposals: [String: [String: String]] = [:]
    var receipts: [String: Data] = [:]
    var prepareBodies: [Data] = []
    var saveBodies: [Data] = []
    var dropSave = false
    var rejectPrepare = false
    var unknownPrepare = false
    var gate: Gate?
    init(original: StructuredTripRecord, after: Data, template: Data) {
        self.original=original;self.after=after;self.template=template;needs=original.document.version == .needsBound;version=original.version
    }
    func configure(dropSave: Bool = false, rejectPrepare: Bool = false,unknownPrepare:Bool=false,gate: Gate? = nil) {
        self.dropSave=dropSave;self.rejectPrepare=rejectPrepare;self.unknownPrepare=unknownPrepare;self.gate=gate
    }
    private func encode(_ object: [String: Any]) throws -> Data {
        let bytes=try JSONSerialization.data(withJSONObject:object);var parser=StrictTripJSON(bytes:Array(bytes));return try tripCanonicalJSON(parser.document())
    }
    private func envelope(_ field: String, _ value: Any) throws -> Data {
        try encode(["version":needs ? "TRIP-needs-result.1" : "TRIP-manual-result.1","request_id":trace,field:value])
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        var status=200;let data: Data
        if operationID == "readStructuredTripV1" {
            let content=version == original.version ? original.document.originalUTF8 : after
            data=try encode(["version":"TRIP-structured-read.1","request_id":trace,"trip":["trip_id":original.tripID,"version":version,"content_sha256":digest(content),"content":JSONSerialization.jsonObject(with:content)]])
        } else {
            let op=LocalTripEditingOperation(rawValue:operationID)!
            if op.queryField != nil {
                let id=URLComponents(string:request.path!)!.queryItems![0].value!
                if op == .queryPrepare || op == .queryNeedsPrepare { data=try preparations[id] ?? envelope("preparation",NSNull()) }
                else { data=try receipts[id] ?? envelope("receipt",NSNull()) }
            } else {
                let bytes=try await Data(collecting:body!,upTo:1_000_000)
                let command=try JSONSerialization.jsonObject(with:bytes) as! [String: Any]
                if op == .prepare || op == .needsPrepare {
                    prepareBodies.append(bytes)
                    if let gate { await gate.park() }
                    if rejectPrepare || unknownPrepare {
                        let unknown=unknownPrepare;rejectPrepare=false;unknownPrepare=false;status=unknown ? 503 : 409
                        data=try encode(["request_id":trace,"error":["code":unknown ? "TRIP_ACCESS_UNAVAILABLE" : "TRIP_CONFLICT","category":unknown ? "dependency" : "conflict","message_en":"Request unavailable","message_zh":"请求不可用","outcome":unknown ? "unknown" : "failed","recovery":unknown ? "reconcile_original" : "do_not_retry"]])
                    } else {
                        let edit=command["edit"] as? [String: Any] ?? command, id=edit["request_id"] as! String
                        var response=try JSONSerialization.jsonObject(with:template) as! [String: Any], prepared=response["preparation"] as! [String: Any]
                        let pid=(needs ? "needs-manual." : "manual.")+digest(bytes)
                        prepared["proposal_id"]=pid
                        var diff=prepared["diff"] as! [String: Any];diff["request_id"]=id;prepared["diff"]=diff
                        let basis=needs ? "needs-manual.1" : "manual-unbound.1"
                        let packed=try JSONSerialization.data(withJSONObject:["synthetic-L0-scope",pid,original.tripID,original.version,basis,1_900_000_000,String(decoding:after,as:UTF8.self)])
                        var parser=StrictTripJSON(bytes:Array(packed));let hash=digest(try tripCanonicalJSON(parser.document()))
                        prepared["candidate_hash"]=hash;response["preparation"]=prepared;response["request_id"]=trace
                        data=try encode(response);preparations[id]=data;proposals[pid]=["hash":hash,"prepare_id":id]
                    }
                } else {
                    saveBodies.append(bytes)
                    let id=command["action_id"] as! String,pid=command["proposal_id"] as! String,proposal=proposals[pid]!
                    #expect(command["candidate_hash"] as? String == proposal["hash"])
                    if let prior=receipts[id] { data=prior }
                    else {
                        version=original.version+1
                        data=try envelope("receipt",["action_id":id,"kind":"accept","proposal_id":pid,"candidate_hash":proposal["hash"]!,"trip_id":original.tripID,"committed_version":version]);receipts[id]=data
                    }
                    if dropSave { dropSave=false;throw URLError(.networkConnectionLost) }
                }
            }
        }
        var response=HTTPResponse(status:.init(code:status));response.headerFields[.contentType]="application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!]=trace;response.headerFields[HTTPField.Name("Cache-Control")!]="no-store"
        return (response,HTTPBody(data))
    }
}
private struct ManualValidatedFixture: ClientTransport {
    let server: ManualFixtureServer
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        try await validate();let value=try await server.send(request,body:body,baseURL:baseURL,operationID:operationID);try await validate();return value
    }
}

@Suite @MainActor struct ManualTripRuntimeTests {
    private func setup(_ name: String = "text", harness: Harness? = nil) async throws -> (Harness,TripClient,ManualFixtureServer,AcceptedStructuredTripSnapshot,ManualTripEditor) {
        let h=try harness ?? Harness(), f=try ManualTripInputTests().fixture(name), record=try f.record()
        let server=ManualFixtureServer(original:record,after:Data(base64Encoded:f.after_utf8_base64)!,template:Data(base64Encoded:f.preparation_utf8_base64)!)
        let client=TripClient(endpoint:h.endpoint,credentials:{ _ in "synthetic-test-token" },currentBinding:{ h.current },pendingStore:try h.store(),interceptedTransport:server)
        try client.enableManualFixture(maximumBytes:4_000_000,maximumRecords:100,factory:{ ManualValidatedFixture(server:server,validate:$0) })
        let request=try client.prepareStructuredDetail(id:record.tripID,binding:h.binding), value=try await client.structuredDetail(for:request)
        let source=try #require(value), ref=record.document.version == .needsBound ? try TripNeedsReference(id:"needs-1",expectedVersion:3) : nil
        let editor=try client.openManualEditor(source:source,needs:ref)
        var draft=try #require(editor.display()).draft;try draft.selectItem("item-1",selected:true)
        let root=try JSONSerialization.jsonObject(with:f.request) as! [String: Any], edit=root["edit"] as? [String: Any] ?? root
        let text=(edit["changes"] as! [[String: Any]])[0]["value"] as! String
        try draft.setText(text,itemID:"item-1");try editor.updateDraft(draft)
        return (h,client,server,source,editor)
    }
    @Test func actualOwnedWorkJournalsPrepareThenOneExplicitSaveForBothVersions() async throws {
        for name in ["text","needs_text"] {
            let (h,client,server,_,editor)=try await setup(name);defer { h.clean() }
            let work=try editor.prepareReview()
            #expect(throws: TripFailure.pendingRequiresQuery) { try editor.prepareReview() }
            guard case .prepared = try await editor.perform(work) else { Issue.record("missing diff");return }
            #expect(editor.display()?.canSave == true)
            let save=try editor.prepareSave()
            guard case .saved(let receipt)=try await editor.perform(save) else { Issue.record("missing original receipt");return }
            #expect(receipt.committedVersion==3 && editor.display()?.draft.original.version==2)
            #expect(editor.display()?.canPrepare==false && editor.display()?.canSave==false)
            #expect(try client.pendingManualActions(binding:h.binding).count==2)
            let prepares=await server.prepareBodies, saves=await server.saveBodies
            #expect(prepares.count==1 && saves.count==1)
        }
    }
    @Test func lostCommitACKReopenIsQueryOnlyAndDoesNotResendOrGuessFromVersion() async throws {
        let (h,client,server,_,editor)=try await setup();defer { h.clean() }
        _=try await editor.perform(editor.prepareReview());await server.configure(dropSave:true)
        let save=try editor.prepareSave()
        do { _=try await editor.perform(save);Issue.record("lost ACK escaped as success") } catch { }
        #expect(editor.display()?.state == .unknown && editor.display()?.canSave==false)
        let originals=try client.pendingManualActions(binding:h.binding), retained=try #require(originals.first { $0.isSave })
        let before=await server.saveBodies
        client.invalidate();editor.retire()
        let reopened=TripClient(endpoint:h.endpoint,credentials:{ _ in "synthetic-test-token" },currentBinding:{ h.current },pendingStore:try h.store(),interceptedTransport:server)
        try reopened.enableManualFixture(maximumBytes:4_000_000,maximumRecords:100,factory:{ ManualValidatedFixture(server:server,validate:$0) })
        let query=try reopened.prepareManualQuery(storageID:retained.storageID,binding:h.binding)
        guard case .saved(let receipt)=try await reopened.performManualQuery(query) else { Issue.record("original query not reconciled");return }
        #expect(receipt.actionID==retained.originalID && receipt.committedVersion==3)
        #expect(await server.saveBodies==before)
        #expect(try reopened.pendingManualActions(binding:h.binding).first { $0.isSave }?.originalUTF8==retained.originalUTF8)
    }
    @Test func canonicalFailedPrepareRequiresOriginalNullReconciliationBeforeNewID() async throws {
        let (h,client,server,_,editor)=try await setup();defer { h.clean() }
        await server.configure(rejectPrepare:true)
        guard case .rejected(status:409,code:"TRIP_CONFLICT")=try await editor.perform(editor.prepareReview()) else { Issue.record("missing canonical conflict");return }
        #expect(throws: TripFailure.pendingRequiresQuery) { try editor.prepareReview() }
        let pending=try client.pendingManualActions(binding:h.binding), original=try #require(pending.first)
        let query=try client.prepareManualQuery(storageID:original.storageID,binding:h.binding)
        guard case .rejected(status:409,code:"TRIP_CONFLICT")=try await client.performManualQuery(query) else { Issue.record("null+durable failure not reconciled");return }
        _=try await editor.perform(editor.prepareReview())
        let bodies=await server.prepareBodies
        #expect(bodies.count==2 && bodies[0] != bodies[1])
    }
    @Test func completeBaseUnknownPlusNullReadStillCannotMintAnotherIDOrResend() async throws {
        let (h,client,server,_,editor)=try await setup();defer { h.clean() }
        await server.configure(unknownPrepare:true)
        await #expect(throws:TripFailure.exchangeUnknown) { try await editor.perform(editor.prepareReview()) }
        let pending=try client.pendingManualActions(binding:h.binding),original=try #require(pending.first)
        let query=try client.prepareManualQuery(storageID:original.storageID,binding:h.binding)
        guard case .notObserved=try await client.performManualQuery(query) else { Issue.record("unknown incorrectly settled");return }
        #expect(throws:TripFailure.pendingRequiresQuery) { try editor.prepareReview() }
        let retained=try client.pendingManualActions(binding:h.binding)
        #expect(retained.count==1 && retained.first?.originalUTF8==original.originalUTF8)
        #expect(await server.prepareBodies.count==1)
    }
    @Test func changingLocalIntentWithholdsLatePreparationAndKeepsTheNewDraft() async throws {
        let (h,client,server,_,editor)=try await setup();defer { h.clean() }
        let gate=Gate();await server.configure(gate:gate)
        let work=try editor.prepareReview(), task=Task { try await editor.perform(work) }
        await gate.waitForEntry()
        var draft=try #require(editor.display()).draft;try draft.setText("newer unsaved input",itemID:"item-1");try editor.updateDraft(draft)
        await gate.release()
        do { _=try await task.value;Issue.record("late preparation became save authority") } catch { }
        #expect(editor.display()?.draft.texts["item-1"]=="newer unsaved input" && editor.display()?.canSave==false)
        #expect(throws: TripFailure.pendingRequiresQuery) { try editor.prepareReview() }
        #expect(try client.pendingManualActions(binding:h.binding).count==1)
    }
}
