import Foundation
import Observation
import CJTripClient
import CJSession

public enum StructuredTripLoadState: Sendable { case idle, loading, loaded, missing, unavailable }
@MainActor public struct StructuredTripHostWork {
    fileprivate enum Payload {
        case page(StructuredTripPageRequest, Bool)
        case detail(StructuredTripDetailRequest)
        case current(AcceptedStructuredTripSnapshot)
        case edit(ManualTripEditor, ManualTripWork)
        case query(ManualTripWork)
        case needs
    }
    fileprivate let owner: UUID
    fileprivate let nonce: UUID
    fileprivate let payload: Payload
}
public struct StructuredTripDisplay: Sendable {
    public let trips: [StructuredTripSummary]
    public let hasNext: Bool
    public let selected: StructuredTripRecord?
    public let currentObservation: StructuredTripRecord?
    public let state: StructuredTripLoadState
    public let originals: [ManualTripPendingAction]
    public let originalOutcome: ManualTripOutcome?
    public let busy: Bool
}

/// Trusted root composition for the same client, session and Shell lifetime.
/// Historical queries never replace the selected Trip/editor or mint save work.
@Observable @MainActor public final class StructuredTripHost {
    @ObservationIgnored private let shell: ShellState
    @ObservationIgnored private let shellGeneration: ShellGeneration
    @ObservationIgnored private let client: TripClient
    @ObservationIgnored private let binding: TripBinding
    @ObservationIgnored private let session: SessionLifecycle
    @ObservationIgnored private let operation: SessionOperation
    @ObservationIgnored private let currentBinding: @MainActor () -> TripBinding?
    @ObservationIgnored private let needsSelection: @MainActor () throws -> TripNeedsReference?
    @ObservationIgnored private let readNeeds: @MainActor () async -> Void
    @ObservationIgnored private let owner = UUID()
    @ObservationIgnored private var nonce = UUID()
    @ObservationIgnored private var retired = false
    @ObservationIgnored private var foreground = true
    @ObservationIgnored private var rows: [StructuredTripSummary] = []
    @ObservationIgnored private var next: StructuredTripCursor?
    @ObservationIgnored private var source: AcceptedStructuredTripSnapshot?
    @ObservationIgnored private var selected: StructuredTripRecord?
    @ObservationIgnored private var observed: StructuredTripRecord?
    @ObservationIgnored private var editing: ManualTripEditor?
    @ObservationIgnored private var originals: [ManualTripPendingAction] = []
    @ObservationIgnored private var outcome: ManualTripOutcome?
    @ObservationIgnored private var state: StructuredTripLoadState = .idle
    @ObservationIgnored private var busy = false
    public private(set) var revision = UUID()

    public init(shell: ShellState, client: TripClient, binding: TripBinding, session: SessionLifecycle,
                sessionOperation: SessionOperation, currentBinding: @escaping @MainActor () -> TripBinding?,
                needsSelection: @escaping @MainActor () throws -> TripNeedsReference?, readNeeds: @escaping @MainActor () async -> Void) {
        self.shell=shell;shellGeneration=shell.generation;self.client=client;self.binding=binding;self.session=session
        operation=sessionOperation;self.currentBinding=currentBinding;self.needsSelection=needsSelection;self.readNeeds=readNeeds
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    private var current: Bool {
        guard !retired,foreground,!shell.messageBindingBlocked,shell.generation==shellGeneration,session.isCurrent(operation) else { return false }
        let value=currentBinding()
        return !retired && foreground && value==binding && !shell.messageBindingBlocked && shell.generation==shellGeneration && session.isCurrent(operation)
    }
    private func check(_ token: UUID) throws { guard current,nonce==token else { throw TripFailure.staleBinding } }
    public var editor: ManualTripEditor? { _=revision;return current ? editing : nil }
    public func display() -> StructuredTripDisplay? {
        _=revision;let token=nonce
        guard current else { return nil }
        let value=StructuredTripDisplay(trips:rows,hasNext:next != nil,selected:selected,currentObservation:observed,state:state,originals:originals,originalOutcome:outcome,busy:busy)
        guard current,nonce==token else { return nil };return value
    }
    public func selectedNeeds() throws -> TripNeedsReference? {
        let token=nonce;try check(token);let value=try needsSelection();try check(token);return value
    }
    public func page(more: Bool = false) throws -> StructuredTripHostWork {
        guard !busy, !more || next != nil else { throw TripFailure.invalidInput }
        let token=UUID();nonce=token;try check(token)
        let request=try client.prepareStructuredPage(limit:20,after:more ? next : nil,binding:binding);try check(token)
        busy=true;state = .loading;revision=UUID();return .init(owner:owner,nonce:token,payload:.page(request,more))
    }
    public func detail(id: String) throws -> StructuredTripHostWork {
        let token=UUID();nonce=token;try check(token)
        editing?.retire();editing=nil;source=nil;selected=nil;observed=nil
        let request=try client.prepareStructuredDetail(id:id,binding:binding);try check(token)
        busy=true;state = .loading;revision=UUID();return .init(owner:owner,nonce:token,payload:.detail(request))
    }
    public func openEditor() throws {
        let token=UUID();nonce=token;try check(token)
        guard let source,let record=selected else { throw TripFailure.invalidInput }
        let ref=record.document.version == .needsBound ? try needsSelection() : nil
        try check(token)
        let next=try client.openManualEditor(source:source,needs:ref);try check(token)
        editing?.retire();try check(token);editing=next;revision=UUID()
    }
    public func updateDraft(_ value: ManualTripDraft) throws {
        let token=nonce;try check(token);guard let editing else { throw TripFailure.invalidInput }
        try editing.updateDraft(value);try check(token);revision=UUID()
    }
    public func prepare(save: Bool) throws -> StructuredTripHostWork {
        guard !busy,let editing else { throw TripFailure.pendingRequiresQuery }
        let token=UUID();nonce=token;try check(token)
        let work=try save ? editing.prepareSave() : editing.prepareReview();try check(token)
        busy=true;revision=UUID();return .init(owner:owner,nonce:token,payload:.edit(editing,work))
    }
    public func currentRecord() throws -> StructuredTripHostWork {
        guard !busy,let source else { throw TripFailure.invalidInput }
        let token=UUID();nonce=token;try check(token);busy=true;revision=UUID()
        return .init(owner:owner,nonce:token,payload:.current(source))
    }
    public func needs() throws -> StructuredTripHostWork {
        guard !busy else { throw TripFailure.pendingRequiresQuery }
        let token=UUID();nonce=token;try check(token);busy=true;revision=UUID();return .init(owner:owner,nonce:token,payload:.needs)
    }
    public func loadOriginals() throws {
        let token=nonce;try check(token);let all=try client.pendingManualActions(binding:binding);try check(token)
        originals=all;revision=UUID()
    }
    public func query(storageID: String) throws -> StructuredTripHostWork {
        guard !busy else { throw TripFailure.pendingRequiresQuery }
        let token=UUID();nonce=token;try check(token)
        let work=try client.prepareManualQuery(storageID:storageID,binding:binding);try check(token)
        busy=true;revision=UUID();return .init(owner:owner,nonce:token,payload:.query(work))
    }
    public func stopWaiting() {
        guard current,busy else { return }
        nonce=UUID();editing?.stopWaiting();busy=false;revision=UUID()
    }
    public func setForeground(_ value: Bool) {
        foreground=value
        if !value { nonce=UUID();editing?.retire();editing=nil;source=nil;selected=nil;observed=nil;outcome=nil;busy=false;client.invalidateDetailSnapshots() }
        revision=UUID()
    }
    public func invalidate() {
        retired=true;nonce=UUID();editing?.retire();editing=nil;source=nil;selected=nil;observed=nil;rows=[];originals=[];outcome=nil;busy=false
        revision=UUID()
    }
    public func perform(_ work: StructuredTripHostWork) async {
        guard work.owner==owner else { return }
        do {
            try check(work.nonce)
            switch work.payload {
            case .page(let request,let more):
                let value=try await client.structuredPage(for:request);try check(work.nonce)
                if more { rows.append(contentsOf:value.trips) } else { rows=value.trips }
                next=value.next;state = .loaded
            case .detail(let request):
                let value=try await client.structuredDetail(for:request);try check(work.nonce)
                let record=try value.map { try client.withCurrentStructuredSnapshot($0) { _,record,_,_ in record } };try check(work.nonce)
                source=value;selected=record;state=record == nil ? .missing : .loaded
            case .current(let source):
                let value=try await client.readCurrentStructuredRecord(for:source);try check(work.nonce);observed=value
            case .edit(let editor,let request):
                _=try await editor.perform(request);try check(work.nonce)
            case .query(let request):
                let value=try await client.performManualQuery(request);try check(work.nonce);outcome=value
            case .needs: await readNeeds();try check(work.nonce)
            }
            busy=false;revision=UUID()
        } catch {
            guard current,nonce==work.nonce else { return }
            busy=false;state = .unavailable;revision=UUID()
        }
    }
}
