import Foundation
import Observation
import CJTripClient

@MainActor public struct TripTimelineWork {
    fileprivate enum Payload { case page(StructuredTripPageRequest,Bool), detail(StructuredTripDetailRequest) }
    fileprivate let owner: UUID
    fileprivate let nonce: UUID
    fileprivate let payload: Payload
}
public enum TripTimelineLoadState: Sendable { case idle,loading,loaded,missing,unavailable }
public struct TripTimelineDisplay: Sendable {
    public let trips: [StructuredTripSummary]
    public let hasNext: Bool
    public let record: StructuredTripRecord?
    public let timeline: TripTimeline?
    public let state: TripTimelineLoadState
    public let busy: Bool
}
/// Minted by the original Trip container. Uses that same client and original
/// root/session; no caller DTO, copied binding or new session activates it.
@Observable @MainActor public final class TripTimelineHost {
    @ObservationIgnored private let client: TripClient
    @ObservationIgnored private let binding: TripBinding
    @ObservationIgnored private let current: @MainActor ()->Bool
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
    init(client: TripClient,binding: TripBinding,current: @escaping @MainActor ()->Bool) { self.client=client;self.binding=binding;self.current=current }
    private func check(_ token: UUID) throws { guard !retired,current(),!retired,nonce==token else { throw TripFailure.staleBinding } }
    public func display() -> TripTimelineDisplay? {
        _=revision;let token=nonce
        do {
            try check(token)
            let value=TripTimelineDisplay(trips:rows,hasNext:next != nil,record:record,timeline:timeline,state:state,busy:busy)
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
