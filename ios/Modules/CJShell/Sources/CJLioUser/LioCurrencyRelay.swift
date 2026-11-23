import Foundation
#if os(iOS)
import CJMessageHTTP
#endif

enum LioCurrencyRelayFailure: Error, Equatable {
    case signInRequired
    case unavailableForAccount
    case offline
    case timedOut
    case unavailable
}

@MainActor public struct LioCurrencyRelayClient {
    typealias Exchange = @MainActor (URLRequest) async throws -> (Data, URLResponse)

    private static let maximumResponseBytes = 65_536
    private let url: URL
    private let isCurrent: @MainActor () -> Bool
    private let bearer: @MainActor () -> String?
    private let exchange: Exchange

    init(baseURL: URL, isCurrent: @escaping @MainActor () -> Bool,
         bearer: @escaping @MainActor () -> String?, exchange: @escaping Exchange) {
        url = baseURL.appending(path: "v1/tools/currency/rates")
        self.isCurrent = isCurrent
        self.bearer = bearer
        self.exchange = exchange
    }

    func load() async throws -> LioCurrencyRates {
        try Task.checkCancellation()
        guard isCurrent(), let token = bearer(), !token.isEmpty else {
            throw LioCurrencyRelayFailure.signInRequired
        }

        var request = URLRequest(url: url, timeoutInterval: 20)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.httpBody = Data(#"{"version":"CURRENCY.1"}"#.utf8)

        let body: Data
        let response: URLResponse
        do {
            (body, response) = try await exchange(request)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try requireCurrentSession()
            switch (error as? URLError)?.code {
            case .notConnectedToInternet, .networkConnectionLost:
                throw LioCurrencyRelayFailure.offline
            case .timedOut:
                throw LioCurrencyRelayFailure.timedOut
            default:
                throw LioCurrencyRelayFailure.unavailable
            }
        }

        try requireCurrentSession()
        guard let http = response as? HTTPURLResponse, http.url == url,
              body.count <= Self.maximumResponseBytes else {
            throw LioCurrencyRelayFailure.unavailable
        }
        switch http.statusCode {
        case 200:
            do {
                return try JSONDecoder().decode(LioCurrencyRates.self, from: body)
            } catch {
                throw LioCurrencyRelayFailure.unavailable
            }
        case 401:
            throw LioCurrencyRelayFailure.signInRequired
        case 403:
            throw LioCurrencyRelayFailure.unavailableForAccount
        default:
            throw LioCurrencyRelayFailure.unavailable
        }
    }

    private func requireCurrentSession() throws {
        try Task.checkCancellation()
        guard isCurrent() else { throw CancellationError() }
    }
}

#if os(iOS)
extension LioCurrencyRelayClient {
    public static func internalBeta(endpoint: MessageEndpoint,
                                    isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioCurrencyRelayClient? {
        guard endpoint.allowsDemoBetaActivation,
              Bundle.main.object(forInfoDictionaryKey: "G2CCurrencyEnabled") as? String == "YES" else {
            return nil
        }

        return LioCurrencyRelayClient(baseURL: endpoint.url, isCurrent: isCurrent, bearer: bearer) { request in
            let policy = URLSessionConfiguration.ephemeral
            policy.timeoutIntervalForResource = 20
            policy.urlCache = nil
            policy.httpCookieStorage = nil
            policy.urlCredentialStorage = nil
            let delegate = LioRelayNoRedirect(bodyLength: 0, uploadFinished: nil)
            let session = URLSession(configuration: policy, delegate: delegate, delegateQueue: nil)
            defer { session.invalidateAndCancel() }

            let (stream, response) = try await session.bytes(for: request)
            let limit = min(endpoint.maximumResponseBytes, Self.maximumResponseBytes)
            guard response.expectedContentLength <= limit else { throw LioCurrencyRelayFailure.unavailable }
            var body = Data()
            for try await byte in stream {
                guard body.count < limit else { throw LioCurrencyRelayFailure.unavailable }
                body.append(byte)
            }
            return (body, response)
        }
    }
}
#endif
