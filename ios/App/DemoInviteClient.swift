#if G2C_DEMO_BETA && os(iOS)
import Foundation
import CJShell
import CJSession
import CJLioUser

private final class DemoInviteRedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    nonisolated func urlSession(_ session: URLSession, task: URLSessionTask,
                                willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                                completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

enum DemoInviteClient {
    /// Rolling renewal is a credential operation only; starter selections and
    /// business originals are retained, never recreated or replayed here.
    static func renew(_ material: SessionMaterial) async throws -> SessionMaterial? {
        do {
            let previous = try material.withBytes { try DemoInviteSession.decode($0, now: Date()) }
            guard let request = try DemoBetaConfiguration.renewalRequest(grant: previous.grant, now: Date()) else { return nil }
            let configuration = URLSessionConfiguration.ephemeral
            configuration.httpCookieStorage = nil
            configuration.urlCache = nil
            configuration.urlCredentialStorage = nil
            configuration.timeoutIntervalForRequest = 15
            configuration.timeoutIntervalForResource = 25
            let session = URLSession(configuration: configuration, delegate: DemoInviteRedirectBlocker(), delegateQueue: nil)
            defer { session.invalidateAndCancel() }
            let (body, http) = try await read(request, session: session)
            let renewed = try DemoBetaConfiguration.verifyRenewalResponse(body, status: http.statusCode,
                contentType: http.value(forHTTPHeaderField: "Content-Type"), previous: previous, now: Date())
            try Task.checkCancellation()
            return try SessionMaterial(trustedSDKBytes: JSONEncoder().encode(renewed))
        } catch DemoBetaConfiguration.Failure.inviteDenied {
            throw DemoAccountExchangeFailure.rejected
        } catch DemoBetaConfiguration.Failure.expired {
            throw DemoAccountExchangeFailure.expired
        } catch {
            throw DemoAccountExchangeFailure.unavailable
        }
    }

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

        var status: Int?
        var reference: String?
        let observed: (HTTPURLResponse) -> Void = { response in
            status = response.statusCode
            reference = response.value(forHTTPHeaderField: "X-Request-ID").flatMap {
                UUID(uuidString: $0) == nil ? nil : $0
            }
        }
        do {
            let (body, http) = try await read(request, session: session, observed: observed)
            let grant = try DemoBetaConfiguration.verifyInviteResponse(body, status: http.statusCode,
                contentType: http.value(forHTTPHeaderField: "Content-Type"), now: Date())
            #if G2C_LIO_APP
            try Task.checkCancellation()
            return try SessionMaterial(trustedSDKBytes: JSONEncoder().encode(DemoInviteSession.lio(grant: grant)))
            #else
            let conversations: DemoStarterReads.Conversations = try await starter("/v1/conversations",
                query: .init(name: "limit", value: "20"), grant: grant, session: session, trace: \.request_id, observed: observed)
            let needs: DemoStarterReads.Needs = try await starter("/v1/needs",
                query: .init(name: "needs_id", value: language.needsID), grant: grant, session: session, trace: \.request_id, observed: observed)
            let travel: DemoStarterReads.Travel = try await starter("/v1/travel-context-actions/" + language.travelActionID,
                grant: grant, session: session, trace: \.request_id, observed: observed)
            let profile = try DemoStarterReads.profile(language: language, conversations: conversations, needs: needs, travel: travel)
            try Task.checkCancellation()
            try grant.validate(now: Date())
            return try SessionMaterial(trustedSDKBytes: JSONEncoder().encode(DemoInviteSession(grant: grant, composition: profile)))
            #endif
        } catch DemoBetaConfiguration.Failure.inviteDenied {
            throw DemoAccountExchangeFailure.rejected
        } catch DemoBetaConfiguration.Failure.invalidInput {
            throw DemoAccountExchangeFailure.rejected
        } catch DemoBetaConfiguration.Failure.expired {
            throw DemoAccountExchangeFailure.expired
        } catch DemoAccountExchangeFailure.rejected {
            throw DemoAccountExchangeFailure.rejected
        } catch DemoAccountExchangeFailure.expired {
            throw DemoAccountExchangeFailure.expired
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try Task.checkCancellation()
            let base = LioFailureDiagnosis.sessionCheck(httpStatus: status, error: error)
            LioDiagnosticLog.shared.record(.init(category: base.category, stage: .signIn, request: nil,
                httpStatus: status, serverReference: reference))
            throw base.category == .network ? DemoAccountExchangeFailure.unavailable : .responseUnavailable
        }
    }

    private static func starter<Value: Decodable>(_ path: String, query: URLQueryItem? = nil,
        grant: DemoInviteGrant, session: URLSession, trace: KeyPath<Value, String>,
        observed: @escaping (HTTPURLResponse) -> Void) async throws -> Value {
        var url = URLComponents(url: DemoBetaConfiguration.endpoint, resolvingAgainstBaseURL: false)!
        url.path = path
        url.queryItems = query.map { [$0] }
        var request = URLRequest(url: url.url!)
        request.setValue("Bearer " + grant.access_token, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (body, response) = try await read(request, session: session, observed: observed)
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

    private static func read(_ request: URLRequest, session: URLSession,
                             observed: ((HTTPURLResponse) -> Void)? = nil) async throws -> (Data, HTTPURLResponse) {
        let (stream, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse, http.url == request.url else { throw DemoAccountExchangeFailure.responseUnavailable }
        observed?(http)
        var body = Data()
        for try await byte in stream {
            guard body.count < 65536 else { throw DemoAccountExchangeFailure.responseUnavailable }
            body.append(byte)
        }
        return (body, http)
    }
}

#endif
