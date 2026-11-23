#if os(iOS)
import CJMessageHTTP
import Foundation

extension LioRelayTranslationClient {
    public static func internalBeta(endpoint: MessageEndpoint,
                                    isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioRelayTranslationClient? {
        guard endpoint.allowsDemoBetaActivation else { return nil }
        return LioRelayTranslationClient(requiresOriginalStore: true) { path, body, uploadFinished in
            guard path == "/v1/tools/translate",
                  let url = URL(string: path, relativeTo: endpoint.url)?.absoluteURL,
                  isCurrent(), let token = bearer() else {
                throw LioRelayTranslationFailure.signInRequired
            }
            var request = URLRequest(url: url, timeoutInterval: 60)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
            request.httpBody = body

            let policy = URLSessionConfiguration.ephemeral
            policy.timeoutIntervalForResource = 60
            policy.urlCache = nil
            policy.httpCookieStorage = nil
            policy.urlCredentialStorage = nil
            let delegate = LioRelayNoRedirect(bodyLength: body.count, uploadFinished: uploadFinished)
            let session = URLSession(configuration: policy, delegate: delegate, delegateQueue: nil)
            defer { session.invalidateAndCancel() }
            let (stream, response) = try await session.bytes(for: request)

            guard isCurrent() else { throw CancellationError() }
            guard let response = response as? HTTPURLResponse, response.url == url,
                  !(300..<400).contains(response.statusCode) else {
                throw LioTranslationFailure.service
            }
            guard response.expectedContentLength <= 256 * 1024 else { throw LioTranslationFailure.service }
            var result = Data()
            for try await byte in stream {
                guard result.count < 256 * 1024 else { throw LioTranslationFailure.service }
                result.append(byte)
            }
            guard isCurrent() else { throw CancellationError() }
            try Task.checkCancellation()
            return (response.statusCode, result)
        }
    }
}

final class LioRelayNoRedirect: NSObject, URLSessionTaskDelegate {
    let bodyLength: Int64
    let uploadFinished: LioRelayTranslationClient.UploadFinished?

    init(bodyLength: Int, uploadFinished: LioRelayTranslationClient.UploadFinished?) {
        self.bodyLength = Int64(bodyLength)
        self.uploadFinished = uploadFinished
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64,
                    totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
        guard totalBytesSent >= bodyLength, let uploadFinished else { return }
        Task { @MainActor in uploadFinished() }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
#endif
