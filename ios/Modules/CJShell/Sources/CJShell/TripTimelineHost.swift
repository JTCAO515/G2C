import Foundation
import Observation
import CJTripClient
import CJMessageHTTP

/// Closed hand-off from this root's actual accepted structured read. The public
/// wire selection remains data; this local entry preserves its source lifetime.
@MainActor public final class TripDiscussionEntry: CustomStringConvertible, CustomReflectable {
    let selection: MessageTripSelection
    let content:MessageTripContent
    let title: String
    fileprivate let binding: TripBinding
    fileprivate let generation: ShellGeneration
    fileprivate let validateSource: @MainActor () throws -> Void
    fileprivate init(selection: MessageTripSelection,content:MessageTripContent,title: String, binding: TripBinding, generation: ShellGeneration,
                     validateSource: @escaping @MainActor () throws -> Void) {
        self.selection=selection;self.content=content; self.title=title; self.binding=binding; self.generation=generation; self.validateSource=validateSource
    }
    func validate(scopeEnvironment: String, scopeAccount: String, generation: ShellGeneration) throws {
        guard self.generation == generation, scopeEnvironment == binding.environment.uuidString,
              scopeAccount == binding.account.uuidString else { throw TripFailure.staleBinding }
        try validateSource()
    }
    public nonisolated var description: String { "<accepted Trip discussion choice>" }
    public nonisolated var customMirror: Mirror { Mirror(self, children: [:]) }
}

@MainActor public struct TripTimelineWork {
    fileprivate enum Payload { case page(StructuredTripPageRequest,Bool), detail(StructuredTripDetailRequest) }
    fileprivate let owner: UUID
    fileprivate let nonce: UUID
    fileprivate let payload: Payload
}
public enum TripTimelineLoadState: Sendable { case idle,loading,loaded,missing,unavailable }
public struct TripTimelineDiscussionContext:Sendable,CustomReflectable {
    fileprivate let owner:UUID
    fileprivate let nonce:UUID
    fileprivate let source:AcceptedStructuredTripSnapshot
    public var customMirror:Mirror { Mirror(self,children:[:]) }
}
public struct TripTimelineDisplay: Sendable {
    public let trips: [StructuredTripSummary]
    public let hasNext: Bool
    public let record: StructuredTripRecord?
    public let timeline: TripTimeline?
    public let state: TripTimelineLoadState
    public let busy: Bool
    public let discussion:TripTimelineDiscussionContext?
}
/// Minted by the original Trip container. Uses that same client and original
/// root/session; no caller DTO, copied binding or new session activates it.
@Observable @MainActor public final class TripTimelineHost {
    @ObservationIgnored private let client: TripClient
    @ObservationIgnored private let binding: TripBinding
    @ObservationIgnored private let current: @MainActor ()->Bool
    @ObservationIgnored private let generation: ShellGeneration
    @ObservationIgnored private let owner=UUID()
    @ObservationIgnored private var nonce=UUID()
    @ObservationIgnored private var retired=false
    @ObservationIgnored private var rows: [StructuredTripSummary]=[]
    @ObservationIgnored private var next: StructuredTripCursor?
    @ObservationIgnored private var source: AcceptedStructuredTripSnapshot?
    @ObservationIgnored private var record: StructuredTripRecord?
    @ObservationIgnored private var timeline: TripTimeline?
    @ObservationIgnored private var state: TripTimelineLoadState = .idle
    @ObservationIgnored private var busy=false
    public private(set) var revision=UUID()
    init(client: TripClient,binding: TripBinding,generation: ShellGeneration,current: @escaping @MainActor ()->Bool) {
        self.client=client;self.binding=binding;self.generation=generation;self.current=current
    }
    private func check(_ token: UUID) throws { guard !retired,current(),!retired,nonce==token else { throw TripFailure.staleBinding } }
    public func display() -> TripTimelineDisplay? {
        _=revision;let token=nonce
        do {
            try check(token)
            let context=source.map { TripTimelineDiscussionContext(owner:owner,nonce:token,source:$0) }
            let value=TripTimelineDisplay(trips:rows,hasNext:next != nil,record:record,timeline:timeline,state:state,busy:busy,discussion:context)
            try check(token);return value
        } catch { return nil }
    }
    public func page(more: Bool=false) throws -> TripTimelineWork {
        guard !busy,!more || next != nil else { throw TripFailure.invalidInput }
        let token=UUID();nonce=token;try check(token)
        let request=try client.prepareStructuredPage(limit:20,after:more ? next : nil,binding:binding);try check(token)
        busy=true;state = .loading;revision=UUID();return .init(owner:owner,nonce:token,payload:.page(request,more))
    }
    public func select(_ id: String) throws -> TripTimelineWork {
        let token=UUID();nonce=token;try check(token)
        source=nil;record=nil;timeline=nil
        let request=try client.prepareStructuredDetail(id:id,binding:binding);try check(token)
        busy=true;state = .loading;revision=UUID();return .init(owner:owner,nonce:token,payload:.detail(request))
    }
    public func invalidate() {
        retired=true;nonce=UUID();source=nil;record=nil;timeline=nil;rows=[];next=nil;busy=false;revision=UUID()
    }
    /// Only explicit rendered choices may cross into the assistant. Day entries
    /// are known start-day groups; an unknown date/zone never acquires a day ID.
    public func discussion(context:TripTimelineDiscussionContext?,day: MessageTripSelection.Day?, itemID: String?) throws -> TripDiscussionEntry {
        guard let context else { throw TripFailure.invalidInput }
        let token=context.nonce;try check(token)
        guard context.owner==owner,!busy,let source,source === context.source else { throw TripFailure.staleBinding }
        let value=try client.withCurrentStructuredSnapshot(source) { _,record,_,_ in record };try check(token)
        let candidates=value.document.items.filter { itemID == nil || $0.id == itemID }
        guard !candidates.isEmpty || (itemID == nil && day == nil) else { throw TripFailure.invalidInput }
        if let day {
            // The UI selects declared start groups. Broader interval membership
            // remains the producer's check; no inferred date is offered here.
            guard candidates.contains(where:{ item in
                if case .known(let date)=item.start.date,case .known(let zone)=item.start.timezone {
                    return date==day.date && zone==day.timezone
                }
                return false
            }) else { throw TripFailure.invalidInput }
        }
        let choice=try MessageTripSelection(id:value.tripID,expectedVersion:Int64(value.version),day:day,itemID:itemID)
        let validate: @MainActor () throws -> Void = { [client,current] in
            guard current() else { throw TripFailure.staleBinding }
            try client.withCurrentStructuredSnapshot(source) { _,_,_,_ in () }
            guard current() else { throw TripFailure.staleBinding }
        }
        try validate();try check(token)
        return try TripDiscussionEntry(selection:choice,content:MessageTripContent(version:value.document.version.rawValue,sha256:value.document.contentSHA256),title:value.document.title,binding:binding,generation:generation,validateSource:validate)
    }
    public func perform(_ work: TripTimelineWork) async {
        guard work.owner==owner else { return }
        do {
            try check(work.nonce)
            switch work.payload {
            case .page(let request,let more):
                let page=try await client.structuredPage(for:request);try check(work.nonce)
                if more { rows.append(contentsOf:page.trips) } else { rows=page.trips }
                next=page.next;state = .loaded
            case .detail(let request):
                let accepted=try await client.structuredDetail(for:request);try check(work.nonce)
                let value=try accepted.map { try client.withCurrentStructuredSnapshot($0) { _,record,_,_ in record } };try check(work.nonce)
                source=accepted;record=value;timeline=value.map { TripTimeline(document:$0.document) };state=value == nil ? .missing : .loaded
            }
            busy=false;revision=UUID()
        } catch {
            guard !retired,current(),nonce==work.nonce else { return }
            busy=false;state = .unavailable;revision=UUID()
        }
    }
}
