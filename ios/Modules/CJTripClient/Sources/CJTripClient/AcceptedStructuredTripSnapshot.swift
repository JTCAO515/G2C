import Foundation
import CJAPI
import OpenAPIRuntime
import HTTPTypes

public struct StructuredTripDetailRequest: Sendable, CustomStringConvertible, CustomReflectable {
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let source: UUID
    fileprivate let binding: TripBinding
    fileprivate let tripID: String
    public var description: String { "<structured Trip detail read>" }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}
public final class AcceptedStructuredTripSnapshot: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    fileprivate let request: StructuredTripDetailRequest
    fileprivate let responseUTF8: Data
    fileprivate let record: StructuredTripRecord
    fileprivate let requestID: String
    fileprivate init(request: StructuredTripDetailRequest, responseUTF8: Data, record: StructuredTripRecord, requestID: String) {
        self.request = request; self.responseUTF8 = responseUTF8; self.record = record; self.requestID = requestID
    }
    public var description: String { "<accepted structured Trip source>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}
public struct StructuredTripCursor: Sendable {
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let epoch: UUID
    fileprivate let binding: TripBinding
    fileprivate let after: String
}
public struct StructuredTripPageRequest: Sendable {
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let epoch: UUID
    fileprivate let work: UUID
    fileprivate let binding: TripBinding
    fileprivate let after: String?
    fileprivate let limit: Int
}
public struct StructuredTripList: Sendable {
    public let trips: [StructuredTripSummary]
    public let next: StructuredTripCursor?
}

extension TripClient {
    public func prepareStructuredDetail(id: String, binding: TripBinding) throws -> StructuredTripDetailRequest {
        guard tripID(id) else { throw TripFailure.invalidInput }
        let previous = detailSnapshotSource, token = try capture(binding)
        guard previous == detailSnapshotSource else { throw TripFailure.staleBinding }
        invalidateDetailSnapshots()
        let request = StructuredTripDetailRequest(owner: owner, generation: token, source: detailSnapshotSource, binding: binding, tripID: id)
        try checkStructuredDetail(request); return request
    }
    private func checkStructuredDetail(_ request: StructuredTripDetailRequest) throws {
        guard request.owner == owner, request.source == detailSnapshotSource else { throw TripFailure.staleBinding }
        try check(request.binding, request.generation)
        guard request.owner == owner, request.source == detailSnapshotSource else { throw TripFailure.staleBinding }
    }
    public func structuredDetail(for request: StructuredTripDetailRequest) async throws -> AcceptedStructuredTripSnapshot? {
        try checkStructuredDetail(request)
        guard startedDetailSnapshotSource != request.source else { throw TripFailure.staleBinding }
        startedDetailSnapshotSource = request.source
        let (bytes, trace) = try await structuredGET(path: "/v5/trip-structured", query: [.init(name: "trip_id", value: request.tripID)],
            operation: "readStructuredTripV1", binding: request.binding, validate: { [self] in try checkStructuredDetail(request) })
        let record: StructuredTripRecord?
        do { record = try StructuredTripReadV1.detail(bytes, requestID: trace) }
        catch { try checkStructuredDetail(request); throw TripFailure.invalidResponse }
        try checkStructuredDetail(request)
        guard let record else { return nil }
        guard same(record.tripID, request.tripID) else { throw TripFailure.invalidResponse }
        return .init(request: request, responseUTF8: bytes, record: record, requestID: trace)
    }
    public func validateStructuredSnapshot(_ source: AcceptedStructuredTripSnapshot) throws { try checkStructuredDetail(source.request) }
    /// A newer observation does not replace the editor's original basis or mint
    /// a fresh source. Replacing a basis requires an explicit new detail request.
    public func readCurrentStructuredRecord(for source: AcceptedStructuredTripSnapshot) async throws -> StructuredTripRecord? {
        let request = source.request; try checkStructuredDetail(request)
        let (bytes, trace) = try await structuredGET(path: "/v5/trip-structured", query: [.init(name: "trip_id", value: request.tripID)],
            operation: "readStructuredTripV1", binding: request.binding, validate: { [self] in try checkStructuredDetail(request) })
        let record: StructuredTripRecord?
        do { record = try StructuredTripReadV1.detail(bytes, requestID: trace) }
        catch { try checkStructuredDetail(request); throw TripFailure.invalidResponse }
        try checkStructuredDetail(request)
        if let record, !same(record.tripID, request.tripID) { throw TripFailure.invalidResponse }
        return record
    }
    public func withCurrentStructuredSnapshot<T>(_ source: AcceptedStructuredTripSnapshot,
        _ read: (Data, StructuredTripRecord, String, TripBinding) throws -> T) throws -> T {
        try validateStructuredSnapshot(source)
        do {
            let value = try read(source.responseUTF8, source.record, source.requestID, source.request.binding)
            try validateStructuredSnapshot(source); return value
        } catch { try validateStructuredSnapshot(source); throw error }
    }
    func invalidateStructuredPages() {
        structuredPageEpoch = UUID(); structuredPageWork = UUID(); startedStructuredPageWork = nil
    }
    public func prepareStructuredPage(limit: Int, after: StructuredTripCursor? = nil, binding: TripBinding) throws -> StructuredTripPageRequest {
        guard (1...100).contains(limit) else { throw TripFailure.invalidInput }
        let previous = structuredPageEpoch, work = UUID()
        structuredPageWork = work // Reserve before the host binding callback can reenter.
        let token = try capture(binding)
        guard previous == structuredPageEpoch, structuredPageWork == work else { throw TripFailure.staleBinding }
        if let after {
            guard after.owner == owner, after.binding == binding, after.generation == token, after.epoch == structuredPageEpoch else { throw TripFailure.staleBinding }
        } else { structuredPageEpoch = UUID() }
        let request = StructuredTripPageRequest(owner: owner, generation: token, epoch: structuredPageEpoch, work: work,
            binding: binding, after: after?.after, limit: limit)
        try checkStructuredPage(request); return request
    }
    private func checkStructuredPage(_ request: StructuredTripPageRequest) throws {
        func local() throws {
            guard request.owner == owner, request.epoch == structuredPageEpoch, request.work == structuredPageWork else { throw TripFailure.staleBinding }
        }
        try local(); try check(request.binding, request.generation); try local()
    }
    public func structuredPage(for request: StructuredTripPageRequest) async throws -> StructuredTripList {
        try checkStructuredPage(request)
        guard startedStructuredPageWork != request.work else { throw TripFailure.staleBinding }
        startedStructuredPageWork = request.work
        var query = [URLQueryItem(name: "limit", value: String(request.limit))]
        if let after = request.after { query.append(.init(name: "after", value: after)) }
        let (bytes, trace) = try await structuredGET(path: "/v1/trip-structured-list", query: query, operation: "listStructuredTripsV1",
            binding: request.binding, validate: { [self] in try checkStructuredPage(request) })
        let page: StructuredTripPage
        do { page = try StructuredTripReadV1.page(bytes, requestID: trace) }
        catch { try checkStructuredPage(request); throw TripFailure.invalidResponse }
        try checkStructuredPage(request)
        guard page.trips.count <= request.limit else { throw TripFailure.invalidResponse }
        var previous = request.after
        for item in page.trips {
            if let previous, !previous.utf8.lexicographicallyPrecedes(item.tripID.utf8) { throw TripFailure.invalidResponse }
            previous = item.tripID
        }
        if let next = page.nextAfter {
            if let after = request.after, !after.utf8.lexicographicallyPrecedes(next.utf8) { throw TripFailure.invalidResponse }
            if let last = page.trips.last, next.utf8.lexicographicallyPrecedes(last.tripID.utf8) { throw TripFailure.invalidResponse }
        }
        let next = page.nextAfter.map { StructuredTripCursor(owner: owner, generation: request.generation, epoch: request.epoch, binding: request.binding, after: $0) }
        return .init(trips: page.trips, next: next)
    }

    private func structuredGET(path: String, query: [URLQueryItem], operation: String, binding: TripBinding,
        validate: @MainActor () throws -> Void) async throws -> (Data, String) {
        try validate()
        let bearer: String?
        do { bearer = try await credentials(binding) }
        catch { try validate(); throw TripFailure.unconfigured }
        try validate()
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw TripFailure.unconfigured }
        var components = URLComponents(); components.queryItems = query
        var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: path + "?" + components.percentEncodedQuery!)
        request.headerFields[.authorization] = "Bearer " + bearer
        let response: HTTPResponse, data: Data
        do {
            try validate()
            let (received, body) = try await transport.send(request, body: nil, baseURL: endpoint.url, operationID: operation)
            try validate()
            guard !(300..<400).contains(received.status.code), let body else { throw TripFailure.invalidResponse }
            data = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes); response = received
            try validate()
        } catch { try validate(); throw TripFailure.exchangeUnknown }
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let media = response.headerFields.filter { $0.name == .contentType }
        let cache = response.headerFields.filter { $0.name.canonicalName == "cache-control" }
        guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
              media.count == 1, let mime = media.first?.value.lowercased(),
              mime == "application/json" || mime == "application/json; charset=utf-8",
              cache.count == 1, cache[0].value.lowercased().split(separator: ",").contains(where: { $0.trimmingCharacters(in: .whitespaces) == "no-store" }) else { throw TripFailure.invalidResponse }
        if response.status.code != 200 {
            let error: Components.Schemas.ErrorResponse
            do {
                var parser = StrictTripJSON(bytes: Array(data)); try parser.check()
                error = try JSONDecoder().decode(Components.Schemas.ErrorResponse.self, from: data)
            } catch { throw TripFailure.invalidResponse }
            let pairs = [401: "ACCESS_DENIED", 400: "INVALID_INPUT", 503: "TRIP_UNAVAILABLE"]
            guard same(error.request_id, trace), pairs[response.status.code] == error.error.code else { throw TripFailure.invalidResponse }
            throw TripFailure.rejected(response.status.code, error.error.code)
        }
        try validate(); return (data, trace)
    }
}
