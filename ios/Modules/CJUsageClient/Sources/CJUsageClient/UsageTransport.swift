import Foundation
import CoreFoundation
import CJMessageHTTP
import CJAPI
import HTTPTypes
import OpenAPIRuntime

struct UsageTransport: ClientTransport {
    let underlying: any ClientTransport
    let endpoint: MessageEndpoint
    let bearer: String
    var association = false
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard baseURL == endpoint.url, request.method == .get, body == nil,
              request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              operationID == (association ? Operations.getOriginalUsageAssociation.id : Operations.getUsageAttemptStatus.id),
              request.path?.split(separator: "?", maxSplits: 1).first == (association ? "/v1/message-usage-association" : "/v1/usage-attempt-status"),
              let path = request.path, path.utf8.count <= endpoint.maximumRequestBytes else { throw UsageFailure.unavailable }
        try await validate()
        var request = request
        request.headerFields[.authorization] = "Bearer " + bearer
        request.headerFields[.cacheControl] = "no-store"
        let (response, body) = try await underlying.send(request, body: nil, baseURL: baseURL, operationID: operationID)
        try await validate()
        guard !(300..<400).contains(response.status.code), let body else { throw UsageFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
        try await validate()
        let media = response.headerFields.filter { $0.name == .contentType }
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let cache = response.headerFields.filter { $0.name == .cacheControl }
        guard media.count == 1, let type = media.first?.value.lowercased(),
              type == "application/json" || type == "application/json; charset=utf-8",
              cache.count == 1, cache.first?.value.lowercased() == "no-store",
              traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil else { throw UsageFailure.invalidResponse }
        var parser = StrictUsageJSON(bytes: Array(bytes)); try parser.check()
        guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let bodyTrace = object["request_id"] as? String, Data(trace.utf8) == Data(bodyTrace.utf8) else { throw UsageFailure.invalidResponse }
        if response.status.code == 200 {
            if association { try validateAssociationWire(object) } else { try validateUsageWire(object) }
        }
        try await validate()
        return (response, HTTPBody(bytes))
    }
}

func decimal(_ text: String, positive: Bool = false) -> Bool {
    let bytes = Array(text.utf8)
    guard !bytes.isEmpty, bytes.allSatisfy({ (48...57).contains($0) }) else { return false }
    return bytes[0] != 48 || (!positive && bytes.count == 1)
}
func validateUsageWire(_ root: [String: Any]) throws {
    let keys: Set<String> = ["attempt_id","operation_id","run_id","status","unit","reserved_units","confirmed_units","confirmed_output","receipt_id","cancelled","exceeded","message_en","message_zh"]
    guard Set(root.keys) == ["request_id", "attempt"], let row = root["attempt"] as? [String: Any], Set(row.keys) == keys else { throw UsageFailure.invalidResponse }
    for key in ["attempt_id","operation_id","run_id","unit"] {
        guard let value = row[key] as? String, validID(value) else { throw UsageFailure.invalidResponse }
    }
    for key in ["message_en","message_zh"] {
        guard let value = row[key] as? String, !value.isEmpty else { throw UsageFailure.invalidResponse }
    }
    guard let reserved = row["reserved_units"] as? String, decimal(reserved, positive: true),
          let status = row["status"] as? String, UsageSnapshot.Status(rawValue: status) != nil,
          let cancelled = row["cancelled"] as? NSNumber, CFGetTypeID(cancelled) == CFBooleanGetTypeID(),
          let exceeded = row["exceeded"] as? NSNumber, CFGetTypeID(exceeded) == CFBooleanGetTypeID() else { throw UsageFailure.invalidResponse }
    for key in ["confirmed_units", "confirmed_output"] {
        guard row[key] is NSNull || (row[key] as? String).map({ decimal($0) }) == true else { throw UsageFailure.invalidResponse }
    }
    guard row["receipt_id"] is NSNull || (row["receipt_id"] as? String).map(validID) == true else { throw UsageFailure.invalidResponse }
    let settled = status == "settled"
    guard ["confirmed_units","confirmed_output","receipt_id"].allSatisfy({ settled ? !(row[$0] is NSNull) : row[$0] is NSNull }),
          status != "released" || cancelled.boolValue,
          !exceeded.boolValue || settled,
          status != "reserved" || !cancelled.boolValue else { throw UsageFailure.invalidResponse }
}

func snapshot(_ body: Components.Schemas.UsageAttemptStatusResponse, source: UsageSource) throws -> UsageSnapshot {
    let row = body.attempt
    guard Data(row.attempt_id.utf8) == Data(source.attemptID.utf8),
          source.operationID.map({ Data($0.utf8) == Data(row.operation_id.utf8) }) ?? true,
          source.runID.map({ Data($0.utf8) == Data(row.run_id.utf8) }) ?? true,
          let status = UsageSnapshot.Status(rawValue: row.status.rawValue) else { throw UsageFailure.invalidResponse }
    let units: String?; let output: String?; let receipt: String?
    switch row.confirmed_units { case .case1(let text): units = text; case .case2: units = nil }
    switch row.confirmed_output { case .case1(let text): output = text; case .case2: output = nil }
    switch row.receipt_id { case .case1(let text): receipt = text; case .case2: receipt = nil }
    return UsageSnapshot(attemptID: row.attempt_id, operationID: row.operation_id, runID: row.run_id, status: status,
        unit: row.unit, reservedUnits: row.reserved_units, confirmedUnits: units, confirmedOutput: output, receiptID: receipt,
        cancelled: row.cancelled, exceeded: row.exceeded, requestID: body.request_id)
}

func validateAssociationWire(_ root: [String: Any]) throws {
    let keys: Set<String> = ["conversation_id", "generation", "message_id", "run_id", "message_sequence", "attempt_id", "operation_id"]
    guard Set(root.keys) == ["request_id", "association"],
          let row = root["association"] as? [String: Any], Set(row.keys) == keys else { throw UsageFailure.invalidResponse }
    for key in keys.subtracting(["message_sequence"]) {
        guard let text = row[key] as? String, !text.isEmpty else { throw UsageFailure.invalidResponse }
        // MESSAGE references have no scalar cap; the response/body budget bounds them.
        // The stored RUN usage binding and USAGE IDs retain their own 200-scalar cap.
        if ["attempt_id", "operation_id", "run_id"].contains(key), !validID(text) { throw UsageFailure.invalidResponse }
    }
    guard let sequence = row["message_sequence"] as? NSNumber,
          CFGetTypeID(sequence) != CFBooleanGetTypeID(),
          !["d", "f"].contains(String(cString: sequence.objCType)), sequence.int64Value > 0 else { throw UsageFailure.invalidResponse }
}
