import Foundation
#if os(iOS)
import CJMessageHTTP
#endif

@MainActor public struct LioTaxiRelayClient {
    typealias Exchange = @MainActor (URLRequest) async throws -> (Data, URLResponse)
    private enum Operation: String {
        case estimate, link
    }

    private let baseURL: URL
    private let isCurrent: @MainActor () -> Bool
    private let bearer: @MainActor () -> String?
    private let exchange: Exchange

    init(baseURL: URL, isCurrent: @escaping @MainActor () -> Bool,
         bearer: @escaping @MainActor () -> String?, exchange: @escaping Exchange) {
        self.baseURL = baseURL
        self.isCurrent = isCurrent
        self.bearer = bearer
        self.exchange = exchange
    }

    func estimate(_ route: LioTaxiRoute) async throws -> [LioTaxiFare] {
        let data = try await post(.estimate, route: route)
        return try LioTaxiWire.readFares(data)
    }

    func rideLink(_ route: LioTaxiRoute) async throws -> URL {
        let data = try await post(.link, route: route)
        return try LioTaxiWire.readLink(data, allowing: LioTaxiWire.approvesDiDiTarget)
    }

    private func post(_ operation: Operation, route: LioTaxiRoute) async throws -> Data {
        try Task.checkCancellation()
        guard isCurrent(), let token = bearer(), !token.isEmpty else {
            throw LioTaxiFailure.signInRequired
        }
        let url = baseURL.appending(path: "v1/tools/taxi").appending(path: operation.rawValue)
        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.httpBody = try LioTaxiWire.encode(route)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await exchange(request)
        } catch {
            guard isCurrent() else { throw CancellationError() }
            try Task.checkCancellation()
            if (error as? URLError)?.code == .timedOut {
                throw LioTaxiFailure.timedOut
            }
            throw error
        }

        guard isCurrent() else { throw CancellationError() }
        try Task.checkCancellation()
        guard let http = response as? HTTPURLResponse, http.url == url else {
            throw LioTaxiFailure.unavailable
        }
        guard http.statusCode == 200 else {
            throw LioTaxiWire.failure(status: http.statusCode, body: data)
        }
        return data
    }
}

#if os(iOS)
extension LioTaxiRelayClient {
    public static func internalBeta(endpoint: MessageEndpoint,
                                    isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioTaxiRelayClient? {
        guard endpoint.allowsDemoBetaActivation else { return nil }
        return LioTaxiRelayClient(baseURL: endpoint.url, isCurrent: isCurrent, bearer: bearer) { request in
            let policy = URLSessionConfiguration.ephemeral
            policy.timeoutIntervalForResource = 30
            policy.urlCache = nil
            policy.httpCookieStorage = nil
            policy.urlCredentialStorage = nil
            let delegate = LioRelayNoRedirect(bodyLength: 0, uploadFinished: nil)
            let session = URLSession(configuration: policy, delegate: delegate, delegateQueue: nil)
            defer { session.invalidateAndCancel() }

            let (stream, response) = try await session.bytes(for: request)
            let limit = endpoint.maximumResponseBytes
            guard response.expectedContentLength <= limit else { throw LioTaxiFailure.unavailable }
            var body = Data()
            for try await byte in stream {
                guard body.count < limit else { throw LioTaxiFailure.unavailable }
                body.append(byte)
            }
            return (body, response)
        }
    }
}
#endif
