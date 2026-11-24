import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LioTaxiRelayTests {
    private let base = URL(string: "https://example.invalid")!
    private let route = LioTaxiRoute(
        pickup: .init(nameZH: "示例起点", nameEN: "Pickup", addressZH: nil,
                      coordinate: .init(latitude: 39.9, longitude: 116.4, referenceSystem: .wgs84)),
        destination: .init(nameZH: "示例终点", nameEN: "Destination", addressZH: nil,
                           coordinate: .init(latitude: 40.05, longitude: 116.3, referenceSystem: .gcj02))
    )
    private let quote = Data("""
    {"version":"TAXI.1","observed_at":"2026-11-23T00:00:00Z","vehicles":[
      {"category":"1","name":"快车","currency":"CNY","price_display":"约¥35"}
    ]}
    """.utf8)
    private let link = "https://v.didi.cn/XvYQEWe?slat=39.9&slng=116.4&dlat=40.05&dlng=116.3"

    @Test func estimateAndHandoffUseOnlyTheTwoAuthorizedPosts() async throws {
        var paths = [String]()
        let relay = LioTaxiRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" }) { request in
            let url = try #require(request.url)
            paths.append(url.path)
            #expect(url.host == base.host)
            #expect(request.httpMethod == "POST")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer fixture-only")
            #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
            #expect(request.httpBody == (try LioTaxiWire.encode(route)))
            let body = url.path.hasSuffix("/estimate") ? quote : linkBody(link)
            return (body, response(url, status: 200))
        }

        #expect(try await relay.estimate(route).first?.priceDisplay == "约¥35")
        #expect(try await relay.rideLink(route).absoluteString == link)
        #expect(paths == ["/v1/tools/taxi/estimate", "/v1/tools/taxi/link"])
    }

    @Test func missingCredentialAndRetiredSessionProtectTheRequestAndResponse() async throws {
        var sends = 0
        var current = true
        var token: String?
        let relay = LioTaxiRelayClient(baseURL: base, isCurrent: { current }, bearer: { token }) { request in
            sends += 1
            current = false
            return (quote, response(try #require(request.url), status: 200))
        }
        await #expect(throws: LioTaxiFailure.signInRequired) { try await relay.estimate(route) }
        #expect(sends == 0)
        token = "fixture-only"
        await #expect(throws: CancellationError.self) { try await relay.estimate(route) }
        #expect(sends == 1)
        await #expect(throws: LioTaxiFailure.signInRequired) { try await relay.rideLink(route) }
        #expect(sends == 1)
    }

    @Test func expiredSessionSuppressesDelayedTransportErrors() async throws {
        var current = true
        var sends = 0
        let relay = LioTaxiRelayClient(baseURL: base, isCurrent: { current }, bearer: { "fixture-only" }) { _ in
            sends += 1
            current = false
            throw URLError(.timedOut)
        }
        await #expect(throws: CancellationError.self) { try await relay.estimate(route) }
        #expect(sends == 1)
    }

    @Test func activeSessionReportsATransportTimeoutAndDoesNotRetry() async throws {
        var sends = 0
        let relay = LioTaxiRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" }) { _ in
            sends += 1
            throw URLError(.timedOut)
        }
        await #expect(throws: LioTaxiFailure.timedOut) { try await relay.estimate(route) }
        #expect(sends == 1)
    }

    @Test func rejectsAResponseFromADifferentOrigin() async throws {
        let foreign = URL(string: "https://other.example.invalid/v1/tools/taxi/estimate")!
        let relay = LioTaxiRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" }) { _ in
            (quote, response(foreign, status: 200))
        }
        await #expect(throws: LioTaxiFailure.unavailable) { try await relay.estimate(route) }
    }

    @Test func redirectAndInvalidHandoffNeverReturnAURL() async throws {
        let invalid = [
            (link, "https", 302),
            (link, "app_scheme", 200),
            (link.replacingOccurrences(of: "v.didi.cn", with: "v.didi.cn.example.invalid"), "https", 200),
            (link.replacingOccurrences(of: "v.didi.cn", with: "v.didi.cn:444"), "https", 200),
            (link.replacingOccurrences(of: "XvYQEWe", with: "other"), "https", 200),
            (link + "#fragment", "https", 200),
            (link + "&slat=39.9", "https", 200),
            (link.replacingOccurrences(of: "dlng=116.3", with: "dlng=nan"), "https", 200),
        ]
        for (url, type, status) in invalid {
            let relay = LioTaxiRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" }) { request in
                (linkBody(url, type: type), response(try #require(request.url), status: status))
            }
            await #expect(throws: LioTaxiFailure.unavailable) { try await relay.rideLink(route) }
        }
    }

    @Test func serverFailuresPreserveTheirMeaningWithoutRetrying() async throws {
        for (status, code, failure) in [
            (401, "sign_in_required", LioTaxiFailure.signInRequired),
            (403, "not_enabled", .notEnabled),
            (422, "out_of_service_area", .outOfService),
            (429, "quota_exceeded", .quotaExceeded),
            (429, "rate_limited", .rateLimited),
            (503, "unavailable", .unavailable),
            (504, "supplier_timeout", .timedOut),
        ] {
            var sends = 0
            let relay = LioTaxiRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" }) { request in
                sends += 1
                return (Data(#"{"error":"\#(code)"}"#.utf8), response(try #require(request.url), status: status))
            }
            await #expect(throws: failure) { try await relay.estimate(route) }
            #expect(sends == 1)
        }
    }

    private func response(_ url: URL, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
    }

    private func linkBody(_ url: String, type: String = "https") -> Data {
        Data(#"{"version":"TAXI.1","url":"\#(url)","link_type":"\#(type)"}"#.utf8)
    }
}
