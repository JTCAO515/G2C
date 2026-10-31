import Foundation
import CJAPI
import CJSession
import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime

public enum ManualTripOutcome: Sendable {
    case prepared(ManualTripPreparation)
    case saved(ManualTripReceipt)
    case rejected(status: Int, code: String)
    case notObserved
}
public struct ManualTripPendingAction: Sendable, CustomStringConvertible, CustomReflectable {
    public let storageID: String
    public let originalID: String
    public let isSave: Bool
    public let tripID: String
    public let originalVersion: Int
    public let originalUTF8: Data
    public var description: String { "<retained manual Trip original>" }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}
public final class ManualTripWork: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    let owner: UUID
    let id = UUID()
    let editor: UUID?
    let nonce: UUID
    let binding: TripBinding
    let generation: UUID
    let original: ManualTripOriginal
    let prefix: ManualTripPrefix?
    let linkedPrepare: ManualTripOriginal?
    init(owner: UUID, editor: UUID?, nonce: UUID, binding: TripBinding, generation: UUID, original: ManualTripOriginal,
         prefix: ManualTripPrefix?, linkedPrepare: ManualTripOriginal?) {
        self.owner=owner; self.editor=editor; self.nonce=nonce; self.binding=binding; self.generation=generation
        self.original=original; self.prefix=prefix; self.linkedPrepare=linkedPrepare
    }
    public var description: String { "<manual Trip work>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}
struct ManualTripPrefix: Sendable {
    let legacy: [TripPending]
    let manual: [ManualTripOriginal]
    let rejections: [ManualTripRejection]
}

@MainActor final class ManualTripRuntime {
    typealias Factory = @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport
    unowned let client: TripClient
    let owner = UUID()
    let legacy: TripPendingStore
    let records: TripEncryptedRecords<ManualTripOriginal>
    let maximumBytes: Int
    let maximumRecords: Int
    let factory: Factory
    private enum Resolution { case known(String), rejected(String, ManualTripRejection) }
    private var resolved: [String: Resolution] = [:]
    private var performed = Set<UUID>()
    private var queryNonce = UUID()
    private var committed = Set<String>()

    init(client: TripClient, store: TripPendingStore, maximumBytes: Int, maximumRecords: Int, factory: @escaping Factory) throws {
        guard maximumBytes > 0, maximumBytes <= 8_000_000, maximumRecords > 0, maximumRecords <= 100,
              let records: TripEncryptedRecords<ManualTripOriginal> = try store.manualRecords(maximumBytes: maximumBytes, maximumRecords: maximumRecords, create: true) else { throw TripFailure.invalidInput }
        self.client=client; legacy=store; self.records=records; self.maximumBytes=maximumBytes; self.maximumRecords=maximumRecords; self.factory=factory
    }
    func invalidate() { resolved.removeAll(); performed.removeAll(); committed.removeAll(); queryNonce=UUID() }
    private func fingerprint(_ original: ManualTripOriginal) throws -> String {
        let encoder=JSONEncoder(); encoder.outputFormatting=[.sortedKeys,.withoutEscapingSlashes]
        return digest(try encoder.encode(original))
    }
    private func commitKey(_ original: ManualTripOriginal) -> String { original.sourceTripID+"|"+String(original.sourceVersion)+"|"+digest(original.sourceUTF8) }
    func wasCommitted(_ input: ManualTripInput) -> Bool {
        committed.contains(input.original.tripID+"|"+String(input.original.version)+"|"+input.original.document.contentSHA256)
    }
    private func rejections(create: Bool) throws -> TripEncryptedRecords<ManualTripRejection>? {
        try records.adjacent(suffix:"CJTripManualRejections",domain:"CJTripManualRejections",maximumBytes:maximumBytes,maximumRecords:maximumRecords,create:create)
    }
    func preflight(binding: TripBinding, generation: UUID, validate: () throws -> Void) throws -> ManualTripPrefix {
        try legacy.validate(binding); try validate()
        let old=try legacy.pending(); try validate()
        guard old.allSatisfy({ client.confirmed[Data($0.actionID.utf8)] == digest($0.originalUTF8) }) else { throw TripFailure.pendingRequiresQuery }
        let originals=try records.pending(); try validate()
        var rejected: [ManualTripRejection]=[]
        for original in originals {
            let hash=try fingerprint(original)
            switch resolved[original.storageID] {
            case .known(let expected): guard expected==hash else { throw TripFailure.pendingRequiresQuery }
            case .rejected(let expected,let proof):
                guard expected==hash else { throw TripFailure.pendingRequiresQuery }; rejected.append(proof)
            case nil: throw TripFailure.pendingRequiresQuery
            }
        }
        let prefix=ManualTripPrefix(legacy:old,manual:originals,rejections:rejected)
        try validatePrefix(prefix, current:nil, validate:validate); return prefix
    }
    func makeWrite(editor: UUID, nonce: UUID, binding: TripBinding, generation: UUID, original: ManualTripOriginal,
                   prefix: ManualTripPrefix, linkedPrepare: ManualTripOriginal?) -> ManualTripWork {
        .init(owner:owner,editor:editor,nonce:nonce,binding:binding,generation:generation,original:original,prefix:prefix,linkedPrepare:linkedPrepare)
    }
    func pending(binding: TripBinding) throws -> [ManualTripPendingAction] {
        let token=try client.capture(binding); try legacy.validate(binding)
        let all=try records.pending(); try client.check(binding,token)
        return all.map { .init(storageID:$0.storageID,originalID:$0.id,isSave:$0.stage == .save,tripID:$0.sourceTripID,originalVersion:$0.sourceVersion,originalUTF8:$0.originalUTF8) }
    }
    func query(storageID: String, binding: TripBinding) throws -> ManualTripWork {
        let nonce=UUID(); queryNonce=nonce
        let token=try client.capture(binding); try legacy.validate(binding)
        let all=try records.pending(); try client.check(binding,token)
        guard queryNonce==nonce, let original=all.first(where: { $0.storageID==storageID }) else { throw TripFailure.invalidInput }
        let linked=try linkedPreparation(original, in:all)
        return .init(owner:owner,editor:nil,nonce:nonce,binding:binding,generation:token,original:original,prefix:nil,linkedPrepare:linked)
    }
    func linkedPreparation(_ record: ManualTripOriginal, in all: [ManualTripOriginal]) throws -> ManualTripOriginal? {
        guard record.stage == .save else { return nil }
        guard let value=all.first(where: { $0.stage == .prepare && $0.id==record.prepareID }) else { throw TripFailure.storageUnavailable }
        _=try record.saveInput(preparation:value); return value
    }
    private func validatePrefix(_ prefix: ManualTripPrefix, current: ManualTripOriginal?, validate: () throws -> Void) throws {
        let old=try prefix.legacy.map { try legacy.requireOriginal($0) }
        let all=prefix.manual+(current.map { [$0] } ?? [])
        let proofs=try all.map { try records.requireOriginal($0) }
        let rejectionStore=try rejections(create:false)
        var rejectionProofs: [TripEncryptedRecords<ManualTripRejection>.Durability]=[]
        for rejection in prefix.rejections {
            guard let rejectionStore else { throw TripFailure.storageUnavailable }
            rejectionProofs.append(try rejectionStore.requireOriginal(rejection))
        }
        try validate() // The last host callback has returned.
        try legacy.validateInventory(prefix.legacy.map(\.actionID))
        try records.validateInventory(all.map(\.storageID))
        for proof in old { try legacy.validateDurability(proof) }
        for proof in proofs { try records.validateDurability(proof) }
        if let rejectionStore { for proof in rejectionProofs { try rejectionStore.validateDurability(proof) } }
    }
    func perform(_ work: ManualTripWork, validateEditor: @escaping @MainActor () throws -> Void) async throws -> (ManualTripOutcome, Data?) {
        func local() throws {
            guard work.owner==owner else { throw TripFailure.staleBinding }
            try client.check(work.binding,work.generation)
            if work.editor == nil { guard work.nonce==queryNonce else { throw TripFailure.staleBinding } }
            try validateEditor()
        }
        try local()
        guard performed.insert(work.id).inserted else { throw TripFailure.staleBinding }
        if let prefix=work.prefix {
            try validatePrefix(prefix,current:nil,validate:local)
            try records.append(work.original) { try self.validatePrefix(prefix,current:nil,validate:local) }
        }
        let validate: @MainActor @Sendable () throws -> Void = { [self] in
            if let prefix=work.prefix { try validatePrefix(prefix,current:work.original,validate:local) }
            else {
                let proof=try records.requireOriginal(work.original)
                var linkProof: TripEncryptedRecords<ManualTripOriginal>.Durability?
                if let link=work.linkedPrepare { linkProof=try records.requireOriginal(link) }
                try local(); try records.validateDurability(proof)
                if let linkProof { try records.validateDurability(linkProof) }
            }
        }
        let operation=try operation(work.original, query:work.prefix == nil)
        let (status,data,trace)=try await exchange(operation,original:work.original,binding:work.binding,validate:validate)
        if status != 200 {
            if work.prefix != nil {
                let rejection=ManualTripRejection(original:work.original,status:status,responseUTF8:data)
                do {
                    try rejection.validate()
                    guard let storage=try rejections(create:true) else { throw TripFailure.storageUnavailable }
                    try storage.append(rejection,validateBinding:validate)
                    try validate()
                    return (.rejected(status:status,code:try errorCode(data)),nil)
                } catch { try local(); throw TripFailure.exchangeUnknown }
            }
            throw TripFailure.rejected(status,try errorCode(data))
        }
        let outcome: ManualTripOutcome
        if work.original.stage == .prepare {
            let input=try work.original.prepareInput()
            if let prepared=try ManualTripReplies.preparation(data,original:input,requestID:trace) {
                // The explicit local producer derives this data identifier from
                // the full original input. It is a byte association, not authority.
                let prefix=input.needs == nil ? "manual." : "needs-manual."
                guard prepared.proposalID==prefix+digest(input.originalUTF8) else { throw TripFailure.invalidResponse }
                outcome = .prepared(prepared)
            } else { outcome = .notObserved }
        } else {
            guard let linked=work.linkedPrepare else { throw TripFailure.storageUnavailable }
            let input=try work.original.saveInput(preparation:linked)
            if let receipt=try ManualTripReplies.receipt(data,original:input,requestID:trace) { outcome = .saved(receipt) }
            else { outcome = .notObserved }
        }
        try validate()
        switch outcome {
        case .prepared: resolved[work.original.storageID] = .known(try fingerprint(work.original))
        case .saved:
            resolved[work.original.storageID] = .known(try fingerprint(work.original)); committed.insert(commitKey(work.original))
        case .notObserved:
            if let storage=try rejections(create:false), let rejection=try storage.pending().first(where: { $0.storageID==work.original.storageID }) {
                guard try fingerprint(rejection.original)==fingerprint(work.original) else { throw TripFailure.storageUnavailable }
                let proof=try storage.requireOriginal(rejection); try validate(); try storage.validateDurability(proof)
                resolved[work.original.storageID] = .rejected(try fingerprint(work.original),rejection)
                return (.rejected(status:rejection.status,code:try errorCode(rejection.responseUTF8)),nil)
            }
        case .rejected: break
        }
        return (outcome,data)
    }
    private func operation(_ record: ManualTripOriginal, query: Bool) throws -> LocalTripEditingOperation {
        let needs=try record.source().document.version == .needsBound
        if query { return record.stage == .prepare ? (needs ? .queryNeedsPrepare : .queryPrepare) : (needs ? .queryNeedsReceipt : .queryReceipt) }
        return record.stage == .prepare ? (needs ? .needsPrepare : .prepare) : (needs ? .needsSave : .save)
    }
    private func exchange(_ operation: LocalTripEditingOperation, original: ManualTripOriginal, binding: TripBinding,
        validate: @escaping @MainActor @Sendable () throws -> Void) async throws -> (Int,Data,String) {
        try validate()
        let bearer: String?
        do { bearer=try await client.credentials(binding) }
        catch { try validate(); throw TripFailure.unconfigured }
        try validate()
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0>32 && $0<127 }) else { throw TripFailure.unconfigured }
        let path: String
        if let field=operation.queryField {
            var q=URLComponents();q.queryItems=[.init(name:field,value:original.id)];path=operation.path+"?"+q.percentEncodedQuery!
        } else { path=operation.path }
        var request=HTTPRequest(method:operation.queryField == nil ? .post : .get,scheme:nil,authority:nil,path:path)
        request.headerFields[.authorization]="Bearer "+bearer
        if operation.queryField == nil { request.headerFields[.contentType]="application/octet-stream" }
        let transport=try factory(validate)
        let response: HTTPResponse,data: Data
        do {
            try validate()
            let (r,body)=try await transport.send(request,body:operation.queryField == nil ? HTTPBody(original.originalUTF8) : nil,
                baseURL:client.endpoint.url,operationID:operation.rawValue)
            try validate();guard let body else { throw TripFailure.invalidResponse }
            data=try await Data(collecting:body,upTo:client.endpoint.maximumResponseBytes);response=r;try validate()
        } catch { try validate();throw TripFailure.exchangeUnknown }
        let media=response.headerFields.filter { $0.name == .contentType },traces=response.headerFields.filter { $0.name.canonicalName=="x-request-id" }
        let cache=response.headerFields.filter { $0.name.canonicalName=="cache-control" }
        guard media.count==1, let mime=media.first?.value.lowercased(), mime=="application/json" || mime=="application/json; charset=utf-8",
              traces.count==1,let trace=traces.first?.value,UUID(uuidString:trace) != nil,
              cache.count==1,cache[0].value.lowercased().split(separator:",").contains(where: { $0.trimmingCharacters(in:.whitespaces)=="no-store" }) else { throw TripFailure.invalidResponse }
        if response.status.code != 200 {
            let error=try manualTripErrorResponse(data)
            guard same(error.request_id,trace) else { throw TripFailure.invalidResponse }
        }
        return (response.status.code,data,trace)
    }
    private func errorCode(_ bytes: Data) throws -> String {
        try manualTripErrorResponse(bytes).error.code
    }
}

extension TripClient {
    public var acceptsManualUserActions: Bool { manualRuntime != nil }
    public convenience init(developmentManual endpoint: TripEndpoint, credentials: @escaping TripCredentialCallback,
        currentBinding: @escaping @MainActor () -> TripBinding?, session: SessionLifecycle, sessionOperation: SessionOperation,
        pendingStore: TripPendingStore, requestTimeout: TimeInterval, resourceTimeout: TimeInterval,
        maximumJournalBytes: Int, maximumJournalRecords: Int) throws {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme=="http",endpoint.url.host=="127.0.0.1",let port=endpoint.url.port,(1...65535).contains(port),
              endpoint.maximumRequestBytes<=1_000_000,endpoint.maximumResponseBytes<=1_000_000 else { throw TripFailure.invalidInput }
        let reads=try NoRedirectTransport(requestTimeout:requestTimeout,resourceTimeout:resourceTimeout)
        self.init(endpoint:endpoint,credentials:credentials,currentBinding:currentBinding,session:session,sessionOperation:sessionOperation,pendingStore:pendingStore,liveReadTransport:reads)
        manualRuntime=try ManualTripRuntime(client:self,store:pendingStore,maximumBytes:maximumJournalBytes,maximumRecords:maximumJournalRecords,
            factory: { validate in try NoRedirectTransport.developmentTripEditing(endpoint:endpoint,requestTimeout:requestTimeout,resourceTimeout:resourceTimeout,validate:validate) })
        #else
        throw TripFailure.liveWriteUnavailable
        #endif
    }
    func enableManualFixture(maximumBytes: Int, maximumRecords: Int, factory: @escaping ManualTripRuntime.Factory) throws {
        guard testWrites,let store else { throw TripFailure.liveWriteUnavailable }
        manualRuntime=try ManualTripRuntime(client:self,store:store,maximumBytes:maximumBytes,maximumRecords:maximumRecords,factory:factory)
    }
    public func pendingManualActions(binding: TripBinding) throws -> [ManualTripPendingAction] {
        guard let manualRuntime else { throw TripFailure.liveWriteUnavailable };return try manualRuntime.pending(binding:binding)
    }
    public func prepareManualQuery(storageID: String, binding: TripBinding) throws -> ManualTripWork {
        guard let manualRuntime else { throw TripFailure.liveWriteUnavailable };return try manualRuntime.query(storageID:storageID,binding:binding)
    }
    public func performManualQuery(_ work: ManualTripWork) async throws -> ManualTripOutcome {
        guard let manualRuntime,work.editor==nil else { throw TripFailure.liveWriteUnavailable }
        return try await manualRuntime.perform(work,validateEditor:{}).0
    }
}
