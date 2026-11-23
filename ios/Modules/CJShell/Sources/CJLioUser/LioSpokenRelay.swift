import Foundation
#if os(iOS)
import CJMessageHTTP
#endif

enum LioSpokenRelayFailure: Error, Equatable {
    case invalidText
    case signInRequired
    case quota
    case unavailable
    case offline
    case timedOut
}

@MainActor struct LioSpokenRelayClient {
    typealias Exchange = @MainActor (URLRequest) async throws -> (Data, URLResponse)
    static let maximumAudioBytes = 2_500_000

    private struct Payload: Encodable {
        let version = "TTS.1"
        let requestID: String
        let language: String
        let text: String

        enum CodingKeys: String, CodingKey {
            case version, language, text
            case requestID = "request_id"
        }
    }

    private let url: URL
    private let isCurrent: @MainActor () -> Bool
    private let bearer: @MainActor () -> String?
    private let exchange: Exchange

    init(baseURL: URL, isCurrent: @escaping @MainActor () -> Bool,
         bearer: @escaping @MainActor () -> String?, exchange: @escaping Exchange) {
        url = baseURL.appending(path: "v1/tools/tts")
        self.isCurrent = isCurrent
        self.bearer = bearer
        self.exchange = exchange
    }

    func audio(for phrase: LioSpokenClip.Phrase, requestID: UUID) async throws -> Data {
        try Task.checkCancellation()
        guard isCurrent(), let token = bearer(), !token.isEmpty else {
            throw LioSpokenRelayFailure.signInRequired
        }
        guard !phrase.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              phrase.text.unicodeScalars.count <= 280, !phrase.text.utf8.contains(0) else {
            throw LioSpokenRelayFailure.invalidText
        }

        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let payload = Payload(requestID: requestID.uuidString,
                              language: phrase.language == .chinese ? "zh" : "en",
                              text: phrase.text)
        var request = URLRequest(url: url, timeoutInterval: 50)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("audio/wav", forHTTPHeaderField: "Accept")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.httpBody = try encoder.encode(payload)

        let response: URLResponse
        let bytes: Data
        do {
            (bytes, response) = try await exchange(request)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try requireCurrentSession()
            switch (error as? URLError)?.code {
            case .notConnectedToInternet, .networkConnectionLost:
                throw LioSpokenRelayFailure.offline
            case .timedOut:
                throw LioSpokenRelayFailure.timedOut
            default:
                throw LioSpokenRelayFailure.unavailable
            }
        }

        try requireCurrentSession()
        guard let http = response as? HTTPURLResponse, http.url == url,
              bytes.count <= LioSpokenRelayClient.maximumAudioBytes else {
            throw LioSpokenRelayFailure.unavailable
        }
        switch http.statusCode {
        case 200:
            guard bytes.count >= 44, http.mimeType?.lowercased() == "audio/wav" else {
                throw LioSpokenRelayFailure.unavailable
            }
            return bytes
        case 401:
            throw LioSpokenRelayFailure.signInRequired
        case 429:
            throw LioSpokenRelayFailure.quota
        default:
            throw LioSpokenRelayFailure.unavailable
        }
    }

    private func requireCurrentSession() throws {
        try Task.checkCancellation()
        guard isCurrent() else { throw CancellationError() }
    }
}

#if os(iOS)
extension LioSpokenClip {
    public static func internalBeta(endpoint: MessageEndpoint,
                                    isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioSpokenClip? {
        guard endpoint.allowsDemoBetaActivation,
              Bundle.main.object(forInfoDictionaryKey: "G2CSpokenRelayEnabled") as? String == "YES" else {
            return nil
        }
        let relay = LioSpokenRelayClient(baseURL: endpoint.url, isCurrent: isCurrent, bearer: bearer) { request in
            let policy = URLSessionConfiguration.ephemeral
            policy.timeoutIntervalForResource = 50
            policy.urlCache = nil
            policy.httpCookieStorage = nil
            policy.urlCredentialStorage = nil
            let delegate = LioRelayNoRedirect(bodyLength: 0, uploadFinished: nil)
            let session = URLSession(configuration: policy, delegate: delegate, delegateQueue: nil)
            defer { session.invalidateAndCancel() }

            let (stream, response) = try await session.bytes(for: request)
            guard response.expectedContentLength <= LioSpokenRelayClient.maximumAudioBytes else {
                throw LioSpokenRelayFailure.unavailable
            }
            var data = Data()
            for try await byte in stream {
                guard data.count < LioSpokenRelayClient.maximumAudioBytes else { throw LioSpokenRelayFailure.unavailable }
                data.append(byte)
            }
            return (data, response)
        }
        return LioSpokenClip(isCurrent: isCurrent) { phrase, id in
            try await relay.audio(for: phrase, requestID: id)
        }
    }
}
#endif
