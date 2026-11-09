#if G2C_DEMO_BETA && os(iOS)
import Foundation
import CJShell
import CJSession

private final class DemoInviteRedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    nonisolated func urlSession(_ session: URLSession, task: URLSessionTask,
                                willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                                completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

enum DemoInviteClient {
    static func exchange(code: String, consent: Bool, language: DemoStarterLanguage) async throws -> SessionMaterial {
        let request: URLRequest
        do { request = try DemoBetaConfiguration.inviteRequest(code: code, consent: consent) }
        catch { throw DemoAccountExchangeFailure.rejected }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = nil
        configuration.urlCache = nil
        configuration.urlCredentialStorage = nil
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 25
        let session = URLSession(configuration: configuration, delegate: DemoInviteRedirectBlocker(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }

        do {
            let (body, http) = try await read(request, session: session)
            let grant = try DemoBetaConfiguration.verifyInviteResponse(body, status: http.statusCode,
                contentType: http.value(forHTTPHeaderField: "Content-Type"), now: Date())
            let conversations: DemoStarterReads.Conversations = try await starter("/v1/conversations",
                query: .init(name: "limit", value: "20"), grant: grant, session: session, trace: \.request_id)
            let needs: DemoStarterReads.Needs = try await starter("/v1/needs",
                query: .init(name: "needs_id", value: language.needsID), grant: grant, session: session, trace: \.request_id)
            let travel: DemoStarterReads.Travel = try await starter("/v1/travel-context-actions/" + language.travelActionID,
                grant: grant, session: session, trace: \.request_id)
            let profile = try DemoStarterReads.profile(language: language, conversations: conversations, needs: needs, travel: travel)
            try Task.checkCancellation()
            try grant.validate(now: Date())
            return try SessionMaterial(trustedSDKBytes: JSONEncoder().encode(DemoInviteSession(grant: grant, composition: profile)))
        } catch DemoBetaConfiguration.Failure.inviteDenied {
            throw DemoAccountExchangeFailure.rejected
        } catch DemoBetaConfiguration.Failure.invalidInput {
            throw DemoAccountExchangeFailure.rejected
        } catch DemoBetaConfiguration.Failure.expired {
            throw DemoAccountExchangeFailure.expired
        } catch let failure as DemoAccountExchangeFailure {
            throw failure
        } catch {
            throw DemoAccountExchangeFailure.unavailable
        }
    }

    private static func starter<Value: Decodable>(_ path: String, query: URLQueryItem? = nil,
        grant: DemoInviteGrant, session: URLSession, trace: KeyPath<Value, String>) async throws -> Value {
        var url = URLComponents(url: DemoBetaConfiguration.endpoint, resolvingAgainstBaseURL: false)!
        url.path = path
        url.queryItems = query.map { [$0] }
        var request = URLRequest(url: url.url!)
        request.setValue("Bearer " + grant.access_token, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (body, response) = try await read(request, session: session)
        if response.statusCode == 401 || response.statusCode == 403 { throw DemoAccountExchangeFailure.rejected }
        guard response.statusCode == 200,
              response.value(forHTTPHeaderField: "Content-Type")?.split(separator: ";").first?.lowercased() == "application/json" else {
            throw DemoAccountExchangeFailure.unavailable
        }
        let value = try JSONDecoder().decode(Value.self, from: body)
        let requestID = value[keyPath: trace]
        guard UUID(uuidString: requestID) != nil, requestID == response.value(forHTTPHeaderField: "X-Request-ID") else {
            throw DemoAccountExchangeFailure.unavailable
        }
        return value
    }

    private static func read(_ request: URLRequest, session: URLSession) async throws -> (Data, HTTPURLResponse) {
        let (stream, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse, http.url == request.url else { throw DemoAccountExchangeFailure.unavailable }
        var body = Data()
        for try await byte in stream {
            guard body.count < 65536 else { throw DemoAccountExchangeFailure.unavailable }
            body.append(byte)
        }
        return (body, http)
    }
}

#endif
