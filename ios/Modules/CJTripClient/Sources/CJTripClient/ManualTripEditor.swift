import Foundation
import Observation

public enum ManualTripEditorState: Sendable { case editing, preparing, prepared, saving, saved, rejected, unknown }
public struct ManualTripDisplay: Sendable {
    public let draft: ManualTripDraft
    public let state: ManualTripEditorState
    public let preparation: ManualTripPreparation?
    public let receipt: ManualTripReceipt?
    public let canPrepare: Bool
    public let canSave: Bool
    public let busy: Bool
}

/// Owns one actual accepted source and one local editor. Public decoded DTOs and
/// serialized inputs cannot replace this original source/work/session binding.
@Observable @MainActor public final class ManualTripEditor: CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    nonisolated public var description: String { "<manual Trip editor>" }
    nonisolated public var debugDescription: String { description }
    nonisolated public var customMirror: Mirror { Mirror(self, children: [:]) }
    @ObservationIgnored private let client: TripClient
    @ObservationIgnored private let runtime: ManualTripRuntime
    @ObservationIgnored private let source: AcceptedStructuredTripSnapshot
    @ObservationIgnored private let binding: TripBinding
    @ObservationIgnored private let generation: UUID
    @ObservationIgnored private let owner = UUID()
    @ObservationIgnored private var nonce = UUID()
    @ObservationIgnored private var retired = false
    @ObservationIgnored private var draft: ManualTripDraft?
    @ObservationIgnored private var activeDraftRevision: UUID?
    @ObservationIgnored private var state: ManualTripEditorState = .editing
    @ObservationIgnored private var busy = false
    @ObservationIgnored private var prepared: ManualTripPreparation?
    @ObservationIgnored private var preparedInput: ManualTripInput?
    @ObservationIgnored private var preparedResponse: Data?
    @ObservationIgnored private var preparedRevision: UUID?
    @ObservationIgnored private var receipt: ManualTripReceipt?
    /// Notification only. Private state is settled first, so synchronous
    /// Observation reentry cannot make an older publication overwrite new data.
    public private(set) var displayRevision = UUID()

    init(client: TripClient, runtime: ManualTripRuntime, source: AcceptedStructuredTripSnapshot, needs: TripNeedsReference?) throws {
        let captured = try client.withCurrentStructuredSnapshot(source) { _, record, _, binding in (record, binding) }
        self.client=client; self.runtime=runtime; self.source=source; binding=captured.1
        generation=try client.capture(captured.1); draft=try .init(original:captured.0,needs:needs)
        try check()
    }
    private func check(nonce expected: UUID? = nil, revision: UUID? = nil) throws {
        func local() throws {
            guard !retired, draft != nil, expected == nil || expected == nonce,
                  revision == nil || revision == draft?.revision else { throw TripFailure.staleBinding }
        }
        try local(); try client.check(binding,generation); try client.validateStructuredSnapshot(source); try local()
    }
    public func display() -> ManualTripDisplay? {
        _=displayRevision
        let current=nonce
        do {
            try check(nonce:current)
            guard let draft else { return nil }
            let valid: Bool
            do { _=try draft.freeze(requestID:"local-validation-only");valid=true }
            catch TripFailure.invalidInput { valid=false }
            let committed = preparedInput.map(runtime.wasCommitted) ?? false
            let save = !busy && state == .prepared && prepared?.status == .pending && preparedRevision == draft.revision && !committed
                && (prepared?.expiresAt.map { $0 > Int(Date().timeIntervalSince1970) } ?? true)
            let result=ManualTripDisplay(draft:draft,state:state,preparation:prepared,receipt:receipt,
                canPrepare:!busy && valid && state != .saved && state != .unknown && !committed,canSave:save,busy:busy)
            try check(nonce:current);return result
        } catch { return nil }
    }
    public func updateDraft(_ value: ManualTripDraft) throws {
        let current=nonce;try check(nonce:current)
        guard let original=draft, value.editorID==original.editorID else { throw TripFailure.invalidInput }
        nonce=UUID();draft=value;prepared=nil;preparedInput=nil;preparedResponse=nil;preparedRevision=nil
        state = .editing;busy=false;displayRevision=UUID()
    }
    public func retire() {
        retired=true;nonce=UUID();draft=nil;prepared=nil;preparedInput=nil;preparedResponse=nil;preparedRevision=nil;receipt=nil;busy=false
        displayRevision=UUID()
    }
    public func prepareReview() throws -> ManualTripWork {
        guard !busy else { throw TripFailure.pendingRequiresQuery }
        let current=UUID();nonce=current
        guard let draft else { throw TripFailure.staleBinding }
        let revision=draft.revision
        try check(nonce:current,revision:revision)
        _=try draft.freeze(requestID:"local-validation-only") // No business ID, journal or network effect.
        let prefix=try runtime.preflight(binding:binding,generation:generation) { try self.check(nonce:current,revision:revision) }
        try check(nonce:current,revision:revision)
        let input=try draft.freeze(requestID:"mp-"+UUID().uuidString.lowercased())
        guard !runtime.wasCommitted(input) else { throw TripFailure.staleBinding }
        let work=runtime.makeWrite(editor:owner,nonce:current,binding:binding,generation:generation,
            original:.init(prepare:input),prefix:prefix,linkedPrepare:nil)
        preparedInput=input;prepared=nil;preparedResponse=nil;preparedRevision=nil;activeDraftRevision=revision;state = .preparing;busy=true
        displayRevision=UUID();return work
    }
    /// One explicit save confirms precisely the currently reviewed diff. There
    /// is no second confirmation request or implicit current-version adoption.
    public func prepareSave() throws -> ManualTripWork {
        guard !busy,let draft,let prepared,let input=preparedInput,let response=preparedResponse,
              state == .prepared, preparedRevision==draft.revision, !runtime.wasCommitted(input),
              prepared.expiresAt.map({ $0 > Int(Date().timeIntervalSince1970) }) ?? true else { throw TripFailure.invalidInput }
        let current=UUID();nonce=current;let revision=draft.revision
        try check(nonce:current,revision:revision)
        let prefix=try runtime.preflight(binding:binding,generation:generation) { try self.check(nonce:current,revision:revision) }
        try check(nonce:current,revision:revision)
        guard let linked=prefix.manual.first(where: { $0.stage == .prepare && $0.id==input.requestID }),
              linked.originalUTF8==input.originalUTF8 else { throw TripFailure.storageUnavailable }
        let save=try ManualTripSaveInput(actionID:"ms-"+UUID().uuidString.lowercased(),preparation:prepared,original:input)
        let work=runtime.makeWrite(editor:owner,nonce:current,binding:binding,generation:generation,
            original:.init(save:save,responseUTF8:response),prefix:prefix,linkedPrepare:linked)
        activeDraftRevision=revision;state = .saving;busy=true;displayRevision=UUID();return work
    }
    public func stopWaiting() {
        guard busy else { return }
        nonce=UUID();busy=false;state = .unknown;displayRevision=UUID()
    }
    public func perform(_ work: ManualTripWork) async throws -> ManualTripOutcome {
        guard work.editor==owner,let revision=activeDraftRevision else { throw TripFailure.staleBinding }
        do {
            try check(nonce:work.nonce,revision:revision)
            let (outcome,response)=try await runtime.perform(work) { try self.check(nonce:work.nonce,revision:revision) }
            try check(nonce:work.nonce,revision:revision)
            switch outcome {
            case .prepared(let value): prepared=value;preparedResponse=response;preparedRevision=revision;state = .prepared
            case .saved(let value): receipt=value;state = .saved
            case .rejected: state = .rejected
            case .notObserved: state = .unknown
            }
            busy=false;displayRevision=UUID();return outcome
        } catch {
            // An edited/replaced/retired view must never settle an old result
            // over its replacement. The durable original remains query-only.
            if !retired,nonce==work.nonce,draft?.revision==revision {
                busy=false;state = .unknown;displayRevision=UUID()
            }
            throw error
        }
    }
}

extension TripClient {
    public func openManualEditor(source: AcceptedStructuredTripSnapshot, needs: TripNeedsReference?) throws -> ManualTripEditor {
        guard let manualRuntime else { throw TripFailure.liveWriteUnavailable }
        return try .init(client:self,runtime:manualRuntime,source:source,needs:needs)
    }
}
