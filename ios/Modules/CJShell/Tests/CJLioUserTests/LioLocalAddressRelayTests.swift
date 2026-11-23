import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LioLocalAddressRelayTests {
    private let endpoint = URL(string: "https://example.invalid")!
    private let attempt = UUID(uuidString: "54D4A309-60E8-403D-A4DF-83D3EC023B0E")!
    private let position = LioTaxiPlace.Coordinate(latitude: 39.92, longitude: 116.39, referenceSystem: .wgs84)

    @Test func lookupSendsOnlyCoordinatesAndOriginalRequestID() async throws {
        let client = LioLocalAddressRelayClient(baseURL: endpoint, isCurrent: { true }, bearer: { "fixture" }) { request in
            #expect(request.url?.path == "/v1/tools/nearby/reverse")
            #expect(request.httpMethod == "POST")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer fixture")
            let requestBytes = try #require(request.httpBody)
            let body = try #require(JSONSerialization.jsonObject(with: requestBytes) as? [String: Any])
            #expect(Set(body.keys) == ["version", "request_id", "center"])
            #expect(body["version"] as? String == "NEARBY.1")
            #expect(body["request_id"] as? String == attempt.uuidString.lowercased())
            let center = try #require(body["center"] as? [String: Any])
            #expect(Set(center.keys) == ["lat", "lng", "coordinate_system"])
            #expect(center["lat"] as? Double == 39.92)
            #expect(center["lng"] as? Double == 116.39)
            #expect(center["coordinate_system"] as? String == "WGS-84")
            let data = Data(#"{"version":"NEARBY.1","source":"Gaode","address_zh":"北京市示例路"}"#.utf8)
            return (data, HTTPURLResponse(url: try #require(request.url), statusCode: 200, httpVersion: nil, headerFields: nil)!)
        }
        #expect(try await client.lookup(position, requestID: attempt) == "北京市示例路")
    }

    @Test(arguments: [401, 403, 409, 429, 502])
    func unsuccessfulLookupNeverAutomaticallyResends(status: Int) async throws {
        var exchanges = 0
        let client = LioLocalAddressRelayClient(baseURL: endpoint, isCurrent: { true }, bearer: { "fixture" }) { request in
            exchanges += 1
            return (Data(), HTTPURLResponse(url: try #require(request.url), statusCode: status, httpVersion: nil, headerFields: nil)!)
        }
        let expected: LioLocalAddressRelayFailure = switch status {
        case 401: .signInRequired
        case 403: .notEnabled
        case 409: .previousAttempt
        case 429: .rateLimited
        default: .outcomeUnknown
        }
        await #expect(throws: expected) { try await client.lookup(position, requestID: attempt) }
        #expect(exchanges == 1)
    }

    @Test func refusesStaleAccountAndDiscardsResponseAfterRetirement() async throws {
        var current = true
        var exchanges = 0
        let client = LioLocalAddressRelayClient(baseURL: endpoint, isCurrent: { current }, bearer: { "fixture" }) { request in
            exchanges += 1
            current = false
            let data = Data(#"{"version":"NEARBY.1","source":"Gaode","address_zh":"北京市示例路"}"#.utf8)
            return (data, HTTPURLResponse(url: try #require(request.url), statusCode: 200, httpVersion: nil, headerFields: nil)!)
        }
        await #expect(throws: CancellationError.self) { try await client.lookup(position, requestID: attempt) }
        await #expect(throws: LioLocalAddressRelayFailure.signInRequired) { try await client.lookup(position, requestID: attempt) }
        #expect(exchanges == 1)
    }

    @Test func malformedSuccessDoesNotDisplayAnAddress() async throws {
        let client = LioLocalAddressRelayClient(baseURL: endpoint, isCurrent: { true }, bearer: { "fixture" }) { request in
            let data = Data(#"{"version":"NEARBY.1","source":"Gaode","address_zh":" "}"#.utf8)
            return (data, HTTPURLResponse(url: try #require(request.url), statusCode: 200, httpVersion: nil, headerFields: nil)!)
        }
        await #expect(throws: LioLocalAddressRelayFailure.outcomeUnknown) { try await client.lookup(position, requestID: attempt) }
    }
}
