import Foundation
import Testing
@testable import CJAPI

private var examples: URL {
    URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().appendingPathComponent("contracts/api/examples")
}

@Test func decodesPublishedExamples() throws {
    let normal = try JSONDecoder().decode(Components.Schemas.ProbeResponse.self,
        from: Data(contentsOf: examples.appendingPathComponent("normal.json")))
    #expect(normal.status == .ok)
    for name in ["failure", "unknown", "conflict"] {
        let body = try JSONDecoder().decode(Components.Schemas.ErrorResponse.self,
            from: Data(contentsOf: examples.appendingPathComponent(name + ".json")))
        #expect(!body.error.code.isEmpty)
        if name == "unknown" {
            #expect(body.error.outcome == .unknown)
            #expect(body.error.recovery == .reconcile_original)
        }
    }
}

@Test func missingRequiredAndFutureEnumFailVisibly() throws {
    let data = try Data(contentsOf: examples.appendingPathComponent("normal.json"))
    var object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    object.removeValue(forKey: "request_id")
    let missing = try JSONSerialization.data(withJSONObject: object)
    #expect(throws: DecodingError.self) {
        try JSONDecoder().decode(Components.Schemas.ProbeResponse.self, from: missing)
    }
    object["request_id"] = "00000000-0000-4000-8000-000000000001"
    object["status"] = "future-status"
    let future = try JSONSerialization.data(withJSONObject: object)
    #expect(throws: DecodingError.self) {
        try JSONDecoder().decode(Components.Schemas.ProbeResponse.self, from: future)
    }
}

@Test func oldClientAcceptsAdditionalOptionalField() throws {
    let data = try Data(contentsOf: examples.appendingPathComponent("normal.json"))
    var object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    object["optional_future_field"] = "ignored"
    let additive = try JSONSerialization.data(withJSONObject: object)
    let decoded = try JSONDecoder().decode(Components.Schemas.ProbeResponse.self, from: additive)
    #expect(decoded.status == .ok)
}

@Test func explicitConfigurationRejectsExternalOrMissingTargets() throws {
    for environment in [[:], ["CJ_ENV": "local"],
                        ["CJ_ENV": "production", "CJ_API_BASE_URL": "http://127.0.0.1:18765"],
                        ["CJ_ENV": "local", "CJ_API_BASE_URL": "https://example.com"],
                        ["CJ_ENV": "local", "CJ_API_BASE_URL": "http://user:password@127.0.0.1:18765"],
                        ["CJ_ENV": "local", "CJ_API_BASE_URL": "http://127.0.0.1:18765?secret=value"]] {
        #expect(throws: ProbeFailure.self) { try ProbeConnection(environment: environment) }
    }
    _ = try ProbeConnection(environment: ["CJ_ENV": "local", "CJ_API_BASE_URL": "http://127.0.0.1:18765"])
}
