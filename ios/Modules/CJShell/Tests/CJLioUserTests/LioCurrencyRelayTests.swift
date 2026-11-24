import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LioCurrencyRelayTests {
    private let origin = URL(string: "https://api-beta.go2china.space")!
    private let route = URL(string: "https://api-beta.go2china.space/v1/tools/currency/rates")!
    private let snapshot = Data("""
        {"version":"CURRENCY.1","source":"ECB","base":"EUR","date":"2026-11-20","rates":{"EUR":"1","CNY":"8","USD":"1.25"}}
        """.utf8)

    @Test func sendsOnlyCurrencyVersionToTheFixedRoute() async throws {
        var sent: [URLRequest] = []
        let relay = LioCurrencyRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { request in
            sent.append(request)
            return (snapshot, response(route, 200))
        }
        let rates = try await relay.load()
        let request = try #require(sent.first)
        #expect(sent.count == 1)
        #expect(request.url == route)
        #expect(request.httpMethod == "POST")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer synthetic-owner")
        #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
        let bytes = try #require(request.httpBody)
        let body = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: String])
        #expect(body == ["version": "CURRENCY.1"])
        #expect(rates.date == "2026-11-20")
        #expect(rates.convert(100, from: .cny, to: .usd) == Decimal(string: "15.63"))
    }

    @Test func missingCredentialOrSessionDoesNotSend() async {
        var calls = 0
        let exchange: LioCurrencyRelayClient.Exchange = { _ in
            calls += 1
            return (snapshot, response(route, 200))
        }
        let missing = LioCurrencyRelayClient(baseURL: origin, isCurrent: { true }, bearer: { nil }, exchange: exchange)
        let retired = LioCurrencyRelayClient(baseURL: origin, isCurrent: { false }, bearer: { "synthetic-owner" }, exchange: exchange)
        await #expect(throws: LioCurrencyRelayFailure.signInRequired) { try await missing.load() }
        await #expect(throws: LioCurrencyRelayFailure.signInRequired) { try await retired.load() }
        #expect(calls == 0)
    }

    @Test func lostSessionDiscardsEvenAValidResponse() async {
        var active = true
        let relay = LioCurrencyRelayClient(baseURL: origin, isCurrent: { active }, bearer: { "synthetic-owner" }) { _ in
            active = false
            return (snapshot, response(route, 200))
        }
        await #expect(throws: CancellationError.self) { try await relay.load() }
    }

    @Test func rejectsForeignSourceAndOversize() async {
        let foreign = URL(string: "https://example.invalid/v1/tools/currency/rates")!
        for (url, data) in [(foreign, snapshot), (route, Data(repeating: 0, count: 65_537))] {
            let relay = LioCurrencyRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
                (data, response(url, 200))
            }
            await #expect(throws: LioCurrencyRelayFailure.unavailable) { try await relay.load() }
        }
    }

    @Test func reportsServerAndNetworkFailuresWithoutRetrying() async {
        let cases: [(Int, LioCurrencyRelayFailure)] = [(401, .signInRequired), (403, .unavailableForAccount),
                                                      (302, .unavailable), (503, .unavailable)]
        for (status, failure) in cases {
            var requests = 0
            let relay = LioCurrencyRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
                requests += 1
                return (Data(), response(route, status))
            }
            await #expect(throws: failure) { try await relay.load() }
            #expect(requests == 1)
        }
        let offline = LioCurrencyRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
            throw URLError(.notConnectedToInternet)
        }
        await #expect(throws: LioCurrencyRelayFailure.offline) { try await offline.load() }
    }

    private func response(_ url: URL, _ status: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: nil)!
    }
}
