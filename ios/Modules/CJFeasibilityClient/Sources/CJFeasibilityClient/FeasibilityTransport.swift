import Foundation
import CoreFoundation
import CryptoKit
import CJMessageHTTP
import CJAPI
import HTTPTypes
import OpenAPIRuntime

struct FeasibilityTransport: ClientTransport {
    let underlying: any ClientTransport
    let endpoint: MessageEndpoint
    let limits: FeasibilityLimits
    let binding: FeasibilityBinding
    let bearer: String
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard baseURL == endpoint.url, request.method == .get, body == nil,
              request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              operationID == Operations.evaluateCurrentNeedsFeasibility.id,
              let path = request.path, path.utf8.count <= endpoint.maximumRequestBytes,
              let components = URLComponents(string: path), components.path == "/v1/needs-feasibility",
              components.fragment == nil, components.queryItems?.count == 1,
              components.queryItems?.first?.name == "needs_id",
              components.queryItems?.first?.value == binding.needsID else { throw FeasibilityFailure.unavailable }
        try await validate()
        var request = request
        request.headerFields[.authorization] = "Bearer " + bearer
        request.headerFields[.cacheControl] = "no-store"
        let (response, body) = try await underlying.send(request, body: nil, baseURL: baseURL, operationID: operationID)
        try await validate()
        guard !(300..<400).contains(response.status.code), let body else { throw FeasibilityFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
        try await validate()
        let media = response.headerFields.filter { $0.name == .contentType }
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let cache = response.headerFields.filter { $0.name == .cacheControl }
        guard media.count == 1, let type = media.first?.value.lowercased(),
              type == "application/json" || type == "application/json; charset=utf-8",
              cache.count == 1, cache.first?.value.lowercased() == "no-store",
              traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil else { throw FeasibilityFailure.invalidResponse }
        let root = try strictObject(bytes, limits: limits)
        guard let bodyTrace = root["request_id"] as? String, same(trace, bodyTrace) else { throw FeasibilityFailure.invalidResponse }
        if response.status.code == 200 { try validateReport(root, binding: binding, limits: limits) }
        else { try validateError(root) }
        try await validate()
        return (response, HTTPBody(bytes)) // Original bytes, no lossy reserialization.
    }
}
func strictObject(_ data: Data, limits: FeasibilityLimits) throws -> [String: Any] {
    var parser = StrictFeasibilityJSON(bytes: Array(data)); try parser.check()
    guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw FeasibilityFailure.invalidResponse }
    func bounded(_ value: Any) throws {
        if let object = value as? [String: Any] {
            guard object.count <= limits.maximumCollectionItems else { throw FeasibilityFailure.invalidResponse }
            for child in object.values { try bounded(child) }
        } else if let array = value as? [Any] {
            guard array.count <= limits.maximumCollectionItems else { throw FeasibilityFailure.invalidResponse }
            for child in array { try bounded(child) }
        }
    }
    try bounded(object)
    return object
}
func keys(_ object: [String: Any], _ expected: Set<String>) throws {
    guard Set(object.keys) == expected else { throw FeasibilityFailure.invalidResponse }
}
func integer(_ value: Any?) -> Int? {
    guard let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID(),
          !["d", "f"].contains(String(cString: number.objCType)) else { return nil }
    return Int(exactly: number.int64Value)
}
func text(_ value: Any?, maximum: Int = 4096, nonempty: Bool = false) -> Bool {
    guard let string = value as? String else { return false }
    return string.unicodeScalars.count <= maximum && (!nonempty || !string.isEmpty)
}
func digest(_ bytes: Data) -> String { SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() }
func validateReport(_ root: [String: Any], binding: FeasibilityBinding, limits: FeasibilityLimits) throws {
    try keys(root, ["request_id", "evaluation"])
    guard let report = root["evaluation"] as? [String: Any] else { throw FeasibilityFailure.invalidResponse }
    try keys(report, ["version","evaluator_version","status","needs_id","revision","content_sha256","overall","checks","sources"])
    guard let id = report["needs_id"] as? String, validID(id), same(id, binding.needsID),
          let revision = integer(report["revision"]), (1...128).contains(revision),
          let hash = report["content_sha256"] as? String, validHash(hash),
          binding.acceptedRevision.map({ $0 == revision }) ?? true,
          binding.acceptedContentSHA256.map({ same($0, hash) }) ?? true,
          let sources = report["sources"] as? [[String: Any]], sources.count == revision,
          let checks = report["checks"] as? [[String: Any]], !checks.isEmpty else { throw FeasibilityFailure.invalidResponse }
    // Official generated decoder owns the enums and required nonnull shape.
    _ = try JSONDecoder().decode(Components.Schemas.FeasibilityCurrentResponse.self,
                                from: JSONSerialization.data(withJSONObject: root))
    var actions = Set<String>(); var consumed = 0
    for (index, source) in sources.enumerated() {
        try keys(source, ["revision","action_id","original_input_utf8","original_input_sha256"])
        guard integer(source["revision"]) == index + 1,
              let action = source["action_id"] as? String, validID(action), actions.insert(action).inserted,
              let original = source["original_input_utf8"] as? String, text(original, maximum: 131072),
              let hash = source["original_input_sha256"] as? String, validHash(hash) else { throw FeasibilityFailure.invalidResponse }
        let bytes = Data(original.utf8); consumed += bytes.count
        guard consumed <= limits.maximumSourceBytes, same(digest(bytes), hash) else { throw FeasibilityFailure.invalidResponse }
        let input = try strictObject(bytes, limits: limits)
        guard let needs = input["needs_id"] as? String, same(needs, id),
              let actionID = input["action_id"] as? String, same(actionID, action),
              integer(input["expected_version"]) == index else { throw FeasibilityFailure.invalidResponse }
    }
    for check in checks {
        try keys(check, ["code","status","missing","zh","en","details","evidence"])
        guard text(check["code"], maximum: 96, nonempty: true), text(check["zh"]), text(check["en"]),
              let missing = check["missing"] as? [String], missing.allSatisfy({ text($0) }),
              let details = check["details"] as? [[String]], details.allSatisfy({ $0.count == 2 && $0.allSatisfy({ text($0) }) }),
              let evidence = check["evidence"] as? [[String: Any]] else { throw FeasibilityFailure.invalidResponse }
        for item in evidence {
            try keys(item, ["path","declaration","revision","action_id","original_input_sha256"])
            guard text(item["path"]) else { throw FeasibilityFailure.invalidResponse }
            if item["revision"] is NSNull {
                guard item["action_id"] is NSNull, item["original_input_sha256"] is NSNull else { throw FeasibilityFailure.invalidResponse }
            } else {
                guard let version = integer(item["revision"]), (1...revision).contains(version),
                      let action = item["action_id"] as? String, let hash = item["original_input_sha256"] as? String,
                      let sourceAction = sources[version - 1]["action_id"] as? String,
                      let sourceHash = sources[version - 1]["original_input_sha256"] as? String,
                      same(action, sourceAction), same(hash, sourceHash) else { throw FeasibilityFailure.invalidResponse }
            }
            // Declaration is original arbitrary JSON, including null; no local interpretation.
        }
    }
}
func validateError(_ root: [String: Any]) throws {
    try keys(root, ["request_id", "error"])
    guard let error = root["error"] as? [String: Any] else { throw FeasibilityFailure.invalidResponse }
    try keys(error, ["code","category","message_en","message_zh","outcome","recovery"])
    guard text(error["category"], maximum: 96, nonempty: true), text(error["message_en"]), text(error["message_zh"]) else { throw FeasibilityFailure.invalidResponse }
    // Decode BASE strictly with its generated required fields; never coerce to an empty report.
    _ = try JSONDecoder().decode(Components.Schemas.ErrorResponse.self, from: JSONSerialization.data(withJSONObject: root))
    guard text(error["code"], maximum: 96, nonempty: true) else { throw FeasibilityFailure.invalidResponse }
}
