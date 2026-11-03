import Foundation
import CryptoKit
import CJMessageClient
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes

public enum MessageHTTPFailure: Error { case invalidConfiguration, credentialsUnavailable, invalidResponse, redirectRejected, exchangeUnknown, productionActivationUnavailable }

public struct MessageEndpoint: Sendable {
    public let url: URL
    public let maximumRequestBytes: Int
    public let maximumResponseBytes: Int
    public init(url: URL, maximumRequestBytes: Int, maximumResponseBytes: Int, allowLoopbackHTTP: Bool = false) throws {
        let local = allowLoopbackHTTP && url.scheme == "http" && url.host == "127.0.0.1" && url.port != nil
        guard url.scheme == "https" || local, url.host != nil, url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil, ["", "/"].contains(url.path), maximumRequestBytes > 0, maximumResponseBytes > 0 else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        self.url = url; self.maximumRequestBytes = maximumRequestBytes; self.maximumResponseBytes = maximumResponseBytes
    }
}

@MainActor public protocol MessageCredentialsProvider: AnyObject {
    /// Trusted host provides only current credentials. No default or token persistence.
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String?
}

/// Injectable transport must not follow redirects. Live networking is explicitly created
/// via NoRedirectTransport, never defaulted. Tests inject an in-process interceptor only.
struct CheckedTransport: ClientTransport {
    let underlying: any ClientTransport
    let endpoint: MessageEndpoint
    let bearer: String
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard baseURL == endpoint.url,
              (operationID == "receiveMessage" && request.method == .post && request.path == "/v1/messages") ||
              (operationID == "queryMessageReceipt" && request.method == .get && request.path?.hasPrefix("/v1/message-receipts?") == true) ||
              (operationID == "getMessageSendStatus" && request.method == .get && request.path?.hasPrefix("/v1/message-send-status?") == true) ||
              (operationID == Operations.getMessageSendStatusV2.id && request.method == .get && request.path?.hasPrefix("/v2/message-send-status?") == true) ||
              (operationID == Operations.receiveMessageV2.id && request.method == .post && request.path == "/v2/messages") ||
              (operationID == "receiveTripDiscussionV3" && request.method == .post && request.path == "/v3/messages") ||
              (operationID == "readTripDiscussionStatusV3" && request.method == .get && request.path?.hasPrefix("/v3/message-send-status?") == true) ||
              (operationID == "readTripDiscussionHistoryV2" && request.method == .get && request.path?.hasPrefix("/v2/message-history?") == true) ||
              (operationID == "receiveTripEditV4" && request.method == .post && request.path == "/v4/messages") ||
              (operationID == "readTripEditStatusV4" && request.method == .get && request.path?.hasPrefix("/v4/message-send-status?") == true) ||
              (operationID == "readTripEditHistoryV3" && request.method == .get && request.path?.hasPrefix("/v3/message-history?") == true) ||
              (operationID == "readTripEditStatusV5" && request.method == .get && request.path?.hasPrefix("/v5/message-send-status?") == true) ||
              (operationID == "readTripEditHistoryV4" && request.method == .get && request.path?.hasPrefix("/v4/message-history?") == true) ||
              PreservedHistoryRoute.accepts(request, hasBody: body != nil, operationID: operationID) ||
              (operationID == Operations.openConversation.id && request.method == .put && request.path?.hasPrefix("/v1/conversations?") == true) ||
              (operationID == Operations.getTravelContext.id && request.method == .get && request.path?.hasPrefix("/v1/travel-contexts/") == true && request.path?.contains("?") == false) ||
              (operationID == "listConversations" && request.method == .get && request.path?.hasPrefix("/v1/conversations?") == true) ||
              (operationID == "readMessageHistory" && request.method == .get && request.path?.hasPrefix("/v1/message-history?") == true) ||
              (operationID == "readMessageDraft" && request.method == .get && request.path?.hasPrefix("/v1/message-drafts?") == true) ||
              (operationID == "saveMessageDraft" && request.method == .put && request.path?.hasPrefix("/v1/message-drafts?") == true) else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        var request = request
        request.headerFields[.authorization] = "Bearer " + bearer
        try await validate()
        let (response, body) = try await underlying.send(request, body: body, baseURL: baseURL, operationID: operationID)
        try await validate()
        guard !(300..<400).contains(response.status.code) else { throw MessageHTTPFailure.redirectRejected }
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        guard traces.count == 1, let header = traces.first?.value, UUID(uuidString: header) != nil,
              let body else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
        try await validate()
        var parser = StrictJSON(bytes: Array(bytes)); try parser.check()
        guard let json = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let trace = json["request_id"] as? String, trace == header else { throw MessageHTTPFailure.invalidResponse }
        return (response, HTTPBody(bytes))
    }
}

public final class NoRedirectTransport: ClientTransport, Sendable {
    private struct EndpointCapability: Sendable {
        let endpoint: MessageEndpoint
        let validate: @MainActor @Sendable () throws -> Void
    }
    private enum MessageWire {
        case legacy, travel, discussion, edit
        var path: String {
            switch self { case .legacy: "/v1/messages"; case .travel: "/v2/messages"; case .discussion: "/v3/messages"; case .edit: "/v4/messages" }
        }
        var operation: String {
            switch self { case .legacy: Operations.receiveMessage.id; case .travel: Operations.receiveMessageV2.id; case .discussion: "receiveTripDiscussionV3"; case .edit: "receiveTripEditV4" }
        }
    }
    private struct MessageCapability: Sendable {
        let endpoint: MessageEndpoint
        let validate: @MainActor @Sendable () throws -> Void
        let wire: MessageWire
        var boundary: EndpointCapability { EndpointCapability(endpoint:endpoint,validate:validate) }
    }
    private let session: URLSession?
    private let transport: any ClientTransport
    private let preview: EndpointCapability?
    private let messages: MessageCapability?
    private let memory: EndpointCapability?
    private let memoryManagement: EndpointCapability?
    private let typedMemory: EndpointCapability?
    private let needs: EndpointCapability?
    private let tripEditing: EndpointCapability?
    private let feedback: EndpointCapability?
    private let memoryHistory: EndpointCapability?
    private let accountCleanup: EndpointCapability?
    private let memoryCandidates: EndpointCapability?
    private let memoryProjection: EndpointCapability?
    private let memoryErasure: EndpointCapability?
    private let deviceCleanup: EndpointCapability?
    private let deviceCompletion: EndpointCapability?

    public convenience init(requestTimeout: TimeInterval, resourceTimeout: TimeInterval) throws {
        try self.init(requestTimeout:requestTimeout,resourceTimeout:resourceTimeout,preview:nil)
    }

    /// Explicit capability for ONE producer-defined readonly computation, never a caller
    /// boolean/label. Host validator must capture the actual current Trip/session binding.
    public static func readOnlyManualPreview(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        try NoRedirectTransport(requestTimeout:requestTimeout,resourceTimeout:resourceTimeout,
            preview:EndpointCapability(endpoint:endpoint,validate:validate))
    }

    /// ADR-0008 activation is only available to an explicit local development
    /// Simulator host whose validator captures the current account/session lease.
    public static func developmentMessages(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        try developmentMessageTransport(endpoint:endpoint,requestTimeout:requestTimeout,resourceTimeout:resourceTimeout,wire:.legacy,validate:validate)
    }

    /// Explicit local send.2 capability. No legacy endpoint or travel actions
    /// are enabled by this capability; selection is data in immutable originals.
    public static func developmentTravelMessages(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        try developmentMessageTransport(endpoint:endpoint,requestTimeout:requestTimeout,resourceTimeout:resourceTimeout,wire:.travel,validate:validate)
    }

    /// Frozen send.3 is discussion only, isolated from send.1/send.2 capabilities.
    /// Profile activation is an operator task; no App request upgrades a scope.
    public static func developmentTripDiscussions(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        try developmentMessageTransport(endpoint:endpoint,requestTimeout:requestTimeout,resourceTimeout:resourceTimeout,wire:.discussion,validate:validate)
    }

    /// Explicit send.4 capability. Source/namespace/profile activation remains
    /// the operator and canonical backend's responsibility.
    public static func developmentTripEdits(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        try developmentMessageTransport(endpoint:endpoint,requestTimeout:requestTimeout,resourceTimeout:resourceTimeout,wire:.edit,validate:validate)
    }

    private static func developmentMessageTransport(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, wire: MessageWire, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port) else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, messages: MessageCapability(endpoint: endpoint, validate: validate, wire: wire))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// Existing #226 manual wire only, scoped to the explicit local simulator
    /// session. It grants neither MESSAGE sending nor lifecycle management.
    public static func developmentMemory(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port) else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, memory: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// Frozen local lifecycle APIs only; cannot send manual saves or MESSAGE.
    public static func developmentMemoryManagement(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port),
              endpoint.maximumRequestBytes <= 32768, endpoint.maximumResponseBytes <= 65536 else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, memoryManagement: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// Explicit compatible typed Memory host. Exact frozen V2 collection and
    /// lifecycle writes only; legacy and MESSAGE capabilities remain closed.
    public static func developmentTypedMemory(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http",endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port,(1...65535).contains(port),
              endpoint.maximumRequestBytes <= 32768,endpoint.maximumResponseBytes <= 1_000_000 else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout:requestTimeout,resourceTimeout:resourceTimeout,
            preview:nil,typedMemory:EndpointCapability(endpoint:endpoint,validate:validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// CJ-LOCAL-NEEDS@1 manual-v1 only. The per-work validator is captured
    /// before dispatch and rechecked after body collection at the live exit.
    public static func developmentNeeds(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port),
              endpoint.maximumRequestBytes <= 131072, endpoint.maximumResponseBytes <= 1048576 else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, needs: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// Per-work signed local Trip editing capability. Ordinary/Release construction
    /// never enables these routes, and no other write or remote host is admitted.
    public static func developmentTripEditing(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port),
              endpoint.maximumRequestBytes <= 1_000_000, endpoint.maximumResponseBytes <= 1_000_000 else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, tripEditing: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// FEEDBACK@1.0 local Simulator capability. No generic or Release write grant.
    public static func developmentFeedback(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port),
              endpoint.maximumRequestBytes <= 16384, endpoint.maximumResponseBytes <= 1_000_000 else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, feedback: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// Explicit MEMORY-HISTORY@1 consent only; never an organizer job dispatch grant.
    public static func developmentMemoryHistory(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port),
              endpoint.maximumRequestBytes <= 32768, endpoint.maximumResponseBytes <= 65536 else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, memoryHistory: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// Exact V5 discovery and V3 candidate review only. No consent, organizer,
    /// MESSAGE, account-cleanup or generic Memory write authority.
    public static func developmentMemoryCandidates(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port),
              endpoint.maximumRequestBytes <= 32768, endpoint.maximumResponseBytes <= 524288 else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, memoryCandidates: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// Non-network boundary-test seam, unavailable to App consumers.
    init(interceptedTransport: any ClientTransport, memoryCandidateEndpoint: MessageEndpoint,
         validateMemoryCandidates: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil
        typedMemory=nil;needs=nil;tripEditing=nil;feedback=nil;memoryHistory=nil;accountCleanup=nil
        memoryCandidates=EndpointCapability(endpoint:memoryCandidateEndpoint,validate:validateMemoryCandidates)
    }

    /// Explicit MEMORY-ERASURE@1 original POST/progress GET, not account deletion.
    public static func developmentMemoryErasure(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1", let port = endpoint.url.port,
              (1...65535).contains(port), endpoint.maximumRequestBytes <= 32768, endpoint.maximumResponseBytes <= 524288 else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, memoryErasure: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }
    /// Non-network unit seam, unavailable to App callers.
    init(interceptedTransport: any ClientTransport, memoryErasureEndpoint: MessageEndpoint,
         validateMemoryErasure: @escaping @MainActor @Sendable () throws -> Void) {
        deviceCleanup = nil; deviceCompletion = nil

        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil
        typedMemory=nil;needs=nil;tripEditing=nil;feedback=nil;memoryHistory=nil;accountCleanup=nil;memoryCandidates=nil
        memoryErasure=EndpointCapability(endpoint:memoryErasureEndpoint,validate:validateMemoryErasure)
    }

    /// Explicit canonical projection2 read with unchanged Action1/receipt exits.
    /// The older V5/V3 capability does not acquire this additive read authority.
    public static func developmentMemoryCandidateProjection(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port),
              endpoint.maximumRequestBytes <= 32768, endpoint.maximumResponseBytes <= 524288 else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, memoryProjection: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// Non-network boundary seam, never an App transport injection point.
    init(interceptedTransport: any ClientTransport, memoryProjectionEndpoint: MessageEndpoint,
         validateMemoryProjection: @escaping @MainActor @Sendable () throws -> Void) {
        memoryErasure = nil
        deviceCleanup = nil; deviceCompletion = nil

        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil
        typedMemory=nil;needs=nil;tripEditing=nil;feedback=nil;memoryHistory=nil;accountCleanup=nil;memoryCandidates=nil
        memoryProjection=EndpointCapability(endpoint:memoryProjectionEndpoint,validate:validateMemoryProjection)
    }

    /// Explicit CLEANUP-API@1 and device registration only. This grants no
    /// business access, device erase, receipt write or background job dispatch.
    public static func developmentAccountCleanup(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port),
              endpoint.maximumRequestBytes <= 16384, endpoint.maximumResponseBytes <= 65536 else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, accountCleanup: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }

    /// Non-network boundary-test seam; never an App factory bypass.
    init(interceptedTransport: any ClientTransport, accountCleanupEndpoint: MessageEndpoint,
         validateAccountCleanup: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil
        typedMemory=nil;needs=nil;tripEditing=nil;feedback=nil;memoryHistory=nil
        accountCleanup=EndpointCapability(endpoint:accountCleanupEndpoint,validate:validateAccountCleanup)
    }

    /// Bounded original-invocation completion representation only. It grants
    /// neither generic account progress nor any content/control erase or write.
    public static func developmentDeviceCompletion(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1", let port = endpoint.url.port,
              (1...65535).contains(port), endpoint.maximumRequestBytes <= 16384, endpoint.maximumResponseBytes <= 65536 else { throw MessageHTTPFailure.invalidConfiguration }
        let bounded = try MessageEndpoint(url: endpoint.url, maximumRequestBytes: endpoint.maximumRequestBytes,
            maximumResponseBytes: min(endpoint.maximumResponseBytes, 4096), allowLoopbackHTTP: true)
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, deviceCompletion: EndpointCapability(endpoint: bounded, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }
    /// Non-network boundary-test seam; not available to App consumers.
    init(interceptedTransport: any ClientTransport, deviceCompletionEndpoint: MessageEndpoint,
         validateDeviceCompletion: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil

        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil
        typedMemory=nil;needs=nil;tripEditing=nil;feedback=nil;memoryHistory=nil;accountCleanup=nil;memoryCandidates=nil;deviceCleanup=nil
        deviceCompletion=EndpointCapability(endpoint:deviceCompletionEndpoint,validate:validateDeviceCompletion)
    }

    /// Version-fixed V3 device control exits; no arbitrary business or domain write.
    public static func developmentDeviceCleanup(endpoint: MessageEndpoint, requestTimeout: TimeInterval,
        resourceTimeout: TimeInterval, validate: @escaping @MainActor @Sendable () throws -> Void) throws -> NoRedirectTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1", let port = endpoint.url.port,
              (1...65535).contains(port), endpoint.maximumRequestBytes <= 16384, endpoint.maximumResponseBytes <= 65536 else { throw MessageHTTPFailure.invalidConfiguration }
        return try NoRedirectTransport(requestTimeout: requestTimeout, resourceTimeout: resourceTimeout,
            preview: nil, deviceCleanup: EndpointCapability(endpoint: endpoint, validate: validate))
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }
    init(interceptedTransport: any ClientTransport, deviceCleanupEndpoint: MessageEndpoint,
         validateDeviceCleanup: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil

        deviceCompletion = nil
        memoryCandidates=nil
        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil
        typedMemory=nil;needs=nil;tripEditing=nil;feedback=nil;memoryHistory=nil;accountCleanup=nil
        deviceCleanup=EndpointCapability(endpoint:deviceCleanupEndpoint,validate:validateDeviceCleanup)
    }

    private init(requestTimeout: TimeInterval, resourceTimeout: TimeInterval, preview: EndpointCapability?, messages: MessageCapability? = nil, memory: EndpointCapability? = nil, memoryManagement: EndpointCapability? = nil, typedMemory: EndpointCapability? = nil, needs: EndpointCapability? = nil, tripEditing: EndpointCapability? = nil, feedback: EndpointCapability? = nil, memoryHistory: EndpointCapability? = nil, accountCleanup: EndpointCapability? = nil, memoryCandidates: EndpointCapability? = nil, deviceCleanup: EndpointCapability? = nil, deviceCompletion: EndpointCapability? = nil, memoryErasure: EndpointCapability? = nil, memoryProjection: EndpointCapability? = nil) throws {
        guard requestTimeout > 0, resourceTimeout > 0, requestTimeout.isFinite, resourceTimeout.isFinite else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        let config = URLSessionConfiguration.ephemeral
        config.httpCookieStorage = nil; config.urlCache = nil; config.urlCredentialStorage = nil
        config.timeoutIntervalForRequest = requestTimeout; config.timeoutIntervalForResource = resourceTimeout
        let session = URLSession(configuration: config, delegate: RedirectBlocker(), delegateQueue: nil)
        self.session = session; transport = URLSessionTransport(configuration: .init(session: session)); self.preview=preview; self.messages=messages; self.memory=memory; self.memoryManagement=memoryManagement;self.typedMemory=typedMemory;self.needs=needs;self.tripEditing=tripEditing;self.feedback=feedback;self.memoryHistory=memoryHistory;self.accountCleanup=accountCleanup;self.memoryCandidates=memoryCandidates;self.memoryErasure=memoryErasure;self.memoryProjection=memoryProjection;self.deviceCleanup=deviceCleanup;self.deviceCompletion=deviceCompletion
    }

    /// Internal non-network seam for module tests; never used by live callers.
    init(interceptedTransport: any ClientTransport, previewEndpoint: MessageEndpoint?,
         validatePreview: (@MainActor @Sendable () throws -> Void)?) throws {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        if let endpoint=previewEndpoint, let validate=validatePreview {
            preview=EndpointCapability(endpoint:endpoint,validate:validate)
        } else {
            guard previewEndpoint == nil && validatePreview == nil else {throw MessageHTTPFailure.invalidConfiguration}
            preview=nil
        }
        memoryHistory=nil;feedback=nil;tripEditing=nil;needs=nil;typedMemory=nil
        session=nil;transport=interceptedTransport;messages=nil;memory=nil;memoryManagement=nil
    }

    /// Module-test-only composition: the supplied transport must be non-network.
    init(interceptedTransport: any ClientTransport, messageEndpoint: MessageEndpoint,
         validateMessage: @escaping @MainActor @Sendable () throws -> Void) throws {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        memoryHistory = nil;feedback = nil;tripEditing = nil; needs = nil;typedMemory = nil
        session = nil; transport = interceptedTransport; preview = nil; memory = nil; memoryManagement = nil
        messages = MessageCapability(endpoint: messageEndpoint, validate: validateMessage, wire: .legacy)
    }

    /// Non-network typed MESSAGE transport seam for module boundary tests.
    init(interceptedTransport: any ClientTransport,travelMessageEndpoint: MessageEndpoint,
         validateMessage: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        memoryHistory=nil;feedback=nil;tripEditing=nil;needs=nil;typedMemory=nil
        session=nil;transport=interceptedTransport;preview=nil;memory=nil;memoryManagement=nil
        messages=MessageCapability(endpoint:travelMessageEndpoint,validate:validateMessage,wire:.travel)
    }

    /// Non-network boundary test seam; no live caller uses this initializer.
    init(interceptedTransport: any ClientTransport, tripDiscussionEndpoint: MessageEndpoint,
         validateDiscussion: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        memoryHistory=nil;feedback=nil;tripEditing=nil; needs=nil; typedMemory=nil; session=nil; transport=interceptedTransport
        preview=nil; memory=nil; memoryManagement=nil
        messages=MessageCapability(endpoint:tripDiscussionEndpoint, validate:validateDiscussion, wire:.discussion)
    }

    init(interceptedTransport: any ClientTransport, tripEditEndpoint: MessageEndpoint,
         validateEdit: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        memoryHistory=nil;feedback=nil;tripEditing=nil; needs=nil; typedMemory=nil; session=nil; transport=interceptedTransport
        preview=nil; memory=nil; memoryManagement=nil
        messages=MessageCapability(endpoint:tripEditEndpoint, validate:validateEdit, wire:.edit)
    }

    /// Non-network Memory boundary seam for deterministic transport tests.
    init(interceptedTransport: any ClientTransport, memoryEndpoint: MessageEndpoint,
         validateMemory: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        memoryHistory = nil;feedback = nil;tripEditing = nil; needs = nil;typedMemory = nil
        session = nil; transport = interceptedTransport; preview = nil; messages = nil; memoryManagement = nil
        memory = EndpointCapability(endpoint: memoryEndpoint, validate: validateMemory)
    }

    /// Non-network lifecycle capability seam for boundary tests.
    init(interceptedTransport: any ClientTransport, memoryManagementEndpoint: MessageEndpoint,
         validateManagement: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        memoryHistory = nil;feedback = nil;tripEditing = nil; needs = nil;typedMemory = nil
        session = nil; transport = interceptedTransport; preview = nil; messages = nil; memory = nil
        memoryManagement = EndpointCapability(endpoint: memoryManagementEndpoint, validate: validateManagement)
    }

    /// Non-network typed Memory boundary seam; never activated by normal init.
    init(interceptedTransport: any ClientTransport,typedMemoryEndpoint: MessageEndpoint,
         validateTypedMemory: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil
        memoryHistory=nil;feedback=nil;tripEditing=nil;needs=nil;typedMemory=EndpointCapability(endpoint:typedMemoryEndpoint,validate:validateTypedMemory)
    }

    /// Non-network seam for exact NEEDS operation/host/body boundary tests.
    init(interceptedTransport: any ClientTransport, needsEndpoint: MessageEndpoint,
         validateNeeds: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil;typedMemory=nil
        memoryHistory=nil;feedback=nil;tripEditing=nil;needs=EndpointCapability(endpoint:needsEndpoint,validate:validateNeeds)
    }

    /// Non-network boundary seam; no public intercepted write grant.
    init(interceptedTransport: any ClientTransport, feedbackEndpoint: MessageEndpoint,
         validateFeedback: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil;typedMemory=nil;needs=nil;tripEditing=nil
        memoryHistory=nil;feedback=EndpointCapability(endpoint:feedbackEndpoint,validate:validateFeedback)
    }

    /// Non-network boundary test seam, not an App activation switch.
    init(interceptedTransport: any ClientTransport, memoryHistoryEndpoint: MessageEndpoint,
         validateHistory: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil
        typedMemory=nil;needs=nil;tripEditing=nil;feedback=nil
        memoryHistory=EndpointCapability(endpoint:memoryHistoryEndpoint,validate:validateHistory)
    }

    @MainActor func validateMessageSending(to endpoint: MessageEndpoint) throws {
        guard let messages, messages.wire == .legacy, messages.endpoint.url == endpoint.url else { throw MessageHTTPFailure.productionActivationUnavailable }
        try messages.validate()
    }

    init(interceptedTransport: any ClientTransport, tripEditingEndpoint: MessageEndpoint,
         validateTripEditing: @escaping @MainActor @Sendable () throws -> Void) {
        memoryProjection = nil
        memoryErasure = nil
        deviceCompletion = nil
        deviceCleanup = nil
        memoryCandidates = nil
        accountCleanup = nil
        session=nil;transport=interceptedTransport;preview=nil;messages=nil;memory=nil;memoryManagement=nil;typedMemory=nil;needs=nil
        memoryHistory=nil;feedback=nil;tripEditing=EndpointCapability(endpoint:tripEditingEndpoint,validate:validateTripEditing)
    }

    @MainActor func validateTravelMessageSending(to endpoint: MessageEndpoint) throws {
        guard let messages,messages.wire == .travel,messages.endpoint.url == endpoint.url else { throw MessageHTTPFailure.productionActivationUnavailable }
        try messages.validate()
    }

    @MainActor func validateTripDiscussionSending(to endpoint: MessageEndpoint) throws {
        guard let messages, messages.wire == .discussion, messages.endpoint.url == endpoint.url else { throw MessageHTTPFailure.productionActivationUnavailable }
        try messages.validate()
    }
    @MainActor func validateTripEditSending(to endpoint: MessageEndpoint) throws {
        guard let messages, messages.wire == .edit, messages.endpoint.url == endpoint.url else { throw MessageHTTPFailure.productionActivationUnavailable }
        try messages.validate()
    }
    /// The ordinary send() entry stays closed to PUT. Only the client's sealed,
    /// once-staged work may enter this original-operation exit.
    func sendConversationOpening(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String,
        validateOriginal:@escaping @MainActor @Sendable () throws -> Void) async throws -> (HTTPResponse,HTTPBody?) {
        guard let messages,(messages.wire == .discussion || messages.wire == .edit),baseURL==messages.endpoint.url,
              operationID==Operations.openConversation.id,request.method == .put,body==nil,
              request.scheme==nil,request.authority==nil,
              !request.headerFields.contains(where:{ $0.name.canonicalName=="host" }),
              let path=request.path,path.hasPrefix("/v1/conversations?"),let parts=URLComponents(string:path),parts.path=="/v1/conversations",
              parts.scheme==nil,parts.host==nil,parts.fragment==nil,
              let query=parts.queryItems,query.count==1,query[0].name=="conversation_id",
              let id=query[0].value,id.hasPrefix("discussion."),
              UUID(uuidString:String(id.dropFirst("discussion.".count)))?.uuidString==String(id.dropFirst("discussion.".count)) else { throw MessageHTTPFailure.productionActivationUnavailable }
        try await messages.validate();try await validateOriginal();try Task.checkCancellation()
        let (response,body)=try await transport.send(request,body:nil,baseURL:baseURL,operationID:operationID)
        try await messages.validate();try await validateOriginal();try Task.checkCancellation()
        guard !(300..<400).contains(response.status.code),let body else { throw MessageHTTPFailure.invalidResponse }
        let raw=try await Data(collecting:body,upTo:messages.endpoint.maximumResponseBytes)
        try await messages.validate();try await validateOriginal();try Task.checkCancellation()
        return (response,HTTPBody(raw))
    }

    deinit { session?.invalidateAndCancel() }
    public func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        if let memoryProjection {
            guard baseURL == memoryProjection.endpoint.url,
                  LocalMemoryCandidateProjectionRoute.accepts(request, hasBody: body != nil, operationID: operationID) else {
                throw MessageHTTPFailure.productionActivationUnavailable
            }
            if let body {
                return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                    capability: memoryProjection, messageWire: nil)
            }
            return try await sendLocalRead(request, baseURL: baseURL, operationID: operationID, capability: memoryProjection)
        }
        if let memoryErasure {
            guard baseURL == memoryErasure.endpoint.url,
                  LocalMemoryErasureRoute.accepts(request, hasBody: body != nil, operationID: operationID) else { throw MessageHTTPFailure.productionActivationUnavailable }
            if let body {
                return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                    capability: memoryErasure, messageWire: nil)
            }
            return try await sendLocalRead(request, baseURL: baseURL, operationID: operationID, capability: memoryErasure)
        }
        if let deviceCompletion {
            guard baseURL == deviceCompletion.endpoint.url,
                  LocalDeviceCompletionRoute.accepts(request, hasBody: body != nil, operationID: operationID) else { throw MessageHTTPFailure.productionActivationUnavailable }
            try await deviceCompletion.validate(); try Task.checkCancellation()
            let (response, responseBody) = try await transport.send(request, body: nil, baseURL: baseURL, operationID: operationID)
            try await deviceCompletion.validate(); try Task.checkCancellation()
            guard !(300..<400).contains(response.status.code), let responseBody else { throw MessageHTTPFailure.invalidResponse }
            let bytes = try await Data(collecting: responseBody, upTo: deviceCompletion.endpoint.maximumResponseBytes)
            try await deviceCompletion.validate(); try Task.checkCancellation()
            return (response, HTTPBody(bytes))
        }
        if let deviceCleanup {
            guard baseURL == deviceCleanup.endpoint.url,
                  LocalDeviceCleanupRoute.accepts(request, hasBody: body != nil, operationID: operationID) else { throw MessageHTTPFailure.productionActivationUnavailable }
            if let body {
                return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                    capability: deviceCleanup, messageWire: nil)
            }
            try await deviceCleanup.validate(); try Task.checkCancellation()
            let (response, body) = try await transport.send(request, body: nil, baseURL: baseURL, operationID: operationID)
            try await deviceCleanup.validate(); try Task.checkCancellation()
            guard !(300..<400).contains(response.status.code), let body else { throw MessageHTTPFailure.invalidResponse }
            let bytes = try await Data(collecting: body, upTo: deviceCleanup.endpoint.maximumResponseBytes)
            try await deviceCleanup.validate(); try Task.checkCancellation()
            return (response, HTTPBody(bytes))
        }

        if let memoryCandidates {
            guard baseURL == memoryCandidates.endpoint.url,
                  LocalMemoryCandidateRoute.accepts(request, hasBody: body != nil, operationID: operationID) else {
                throw MessageHTTPFailure.productionActivationUnavailable
            }
            if let body {
                return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                    capability: memoryCandidates, messageWire: nil)
            }
            return try await sendLocalRead(request, baseURL: baseURL, operationID: operationID, capability: memoryCandidates)
        }
        if let accountCleanup {
            guard baseURL == accountCleanup.endpoint.url,
                  LocalAccountCleanupRoute.accepts(request, hasBody: body != nil, operationID: operationID) else {
                throw MessageHTTPFailure.productionActivationUnavailable
            }
            if let body {
                return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                    capability: accountCleanup, messageWire: nil)
            }
            return try await sendLocalRead(request, baseURL: baseURL, operationID: operationID, capability: accountCleanup)
        }

        if let tripEditing {
            guard let operation = LocalTripEditingOperation(rawValue: operationID), baseURL == tripEditing.endpoint.url,
                  request.scheme == nil, request.authority == nil,
                  !request.headerFields.contains(where: { $0.name.canonicalName == "host" }) else { throw MessageHTTPFailure.productionActivationUnavailable }
            if let field = operation.queryField {
                guard request.method == .get, body == nil, let path = request.path,
                      let parts = URLComponents(string: path), parts.scheme == nil, parts.host == nil,
                      parts.percentEncodedPath == operation.path, parts.fragment == nil,
                      let values = parts.queryItems, values.count == 1, values[0].name == field,
                      let id = values[0].value, id.range(of: "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$", options: .regularExpression) == id.startIndex..<id.endIndex else { throw MessageHTTPFailure.invalidConfiguration }
                try await tripEditing.validate(); try Task.checkCancellation()
                let (response, responseBody) = try await transport.send(request, body: nil, baseURL: baseURL, operationID: operationID)
                try await tripEditing.validate(); try Task.checkCancellation()
                guard !(300..<400).contains(response.status.code), let responseBody else { throw MessageHTTPFailure.invalidResponse }
                let bytes = try await Data(collecting: responseBody, upTo: tripEditing.endpoint.maximumResponseBytes)
                try await tripEditing.validate(); try Task.checkCancellation()
                return (response, HTTPBody(bytes))
            }
            guard request.method == .post, request.path == operation.path, let body else { throw MessageHTTPFailure.productionActivationUnavailable }
            // The save contract has a tighter ceiling than preparation.
            let bytes = try await Data(collecting: body, upTo: min(operation.maximumRequestBytes, tripEditing.endpoint.maximumRequestBytes))
            return try await sendLocalWrite(request, body: HTTPBody(bytes), baseURL: baseURL, operationID: operationID,
                capability: tripEditing, messageWire: nil)
        }
        if let memoryHistory, request.method == .get || request.method == .head {
            let routes = ["readMemoryHistorySettingsV1": ("/v3/memory-history-settings", "conversation_id", 256),
                          "queryMemoryHistoryReceiptV1": ("/v3/memory-history-receipts", "action_id", 4096)]
            guard let route = routes[operationID], request.method == .get, body == nil,
                  baseURL == memoryHistory.endpoint.url, request.scheme == nil, request.authority == nil,
                  !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
                  let path = request.path, let parts = URLComponents(string: path),
                  parts.scheme == nil, parts.host == nil, parts.fragment == nil, parts.percentEncodedPath == route.0,
                  let values = parts.queryItems, values.count == 1, values[0].name == route.1,
                  let value = values[0].value, !value.contains("\0"), value.utf8.count <= route.2,
                  !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw MessageHTTPFailure.productionActivationUnavailable }
            return try await sendLocalRead(request, baseURL: baseURL, operationID: operationID, capability: memoryHistory)
        }
        if request.method == .get || request.method == .head {
            return try await transport.send(request,body:body,baseURL:baseURL,operationID:operationID)
        }
        if let messages, request.method == .post, operationID == messages.wire.operation,
           request.path == messages.wire.path, request.scheme == nil, request.authority == nil,
           baseURL == messages.endpoint.url,
           !request.headerFields.contains(where: { $0.name.canonicalName == "host" }), let body {
            return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                                            capability: messages.boundary, messageWire: messages.wire)
        }
        if let memory, request.method == .post, operationID == Operations.saveMemory.id,
           request.path == "/v1/memories", request.scheme == nil, request.authority == nil,
           baseURL == memory.endpoint.url,
           !request.headerFields.contains(where: { $0.name.canonicalName == "host" }), let body {
            return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                                            capability: memory, messageWire: nil)
        }
        let managementPaths = [Operations.applyMemoryManagementAction.id: "/v1/memory-management-actions",
            Operations.applyMemoryEditAction.id: "/v1/memory-edit-actions",
            Operations.applyMemoryStopUseAction.id: "/v1/memory-withdrawal-actions"]
        if let memoryManagement, request.method == .post, let path = managementPaths[operationID],
           request.path == path, request.scheme == nil, request.authority == nil,
           baseURL == memoryManagement.endpoint.url,
           !request.headerFields.contains(where: { $0.name.canonicalName == "host" }), let body {
            return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                                            capability: memoryManagement, messageWire: nil)
        }
        let typedMemoryPaths = [Operations.saveTypedMemory.id:"/v2/memories",
            Operations.applyTypedMemoryManagement.id:"/v2/memory-management-actions",
            Operations.applyTypedMemoryStopUse.id:"/v2/memory-withdrawal-actions"]
        if let typedMemory,request.method == .post,let path = typedMemoryPaths[operationID],
           request.path == path,request.scheme == nil,request.authority == nil,baseURL == typedMemory.endpoint.url,
           !request.headerFields.contains(where:{ $0.name.canonicalName == "host" }),let body {
            return try await sendLocalWrite(request,body:body,baseURL:baseURL,operationID:operationID,
                                            capability:typedMemory,messageWire:nil)
        }
        if let needs, request.method == .post, operationID == Operations.actOnNeeds.id,
           request.path == "/v1/needs-actions", request.scheme == nil, request.authority == nil,
           baseURL == needs.endpoint.url,
           !request.headerFields.contains(where: { $0.name.canonicalName == "host" }), let body {
            return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                                            capability: needs, messageWire: nil)
        }
        if let feedback, request.method == .post, operationID == Operations.submitFeedback.id,
           request.path == "/v1/feedback", request.scheme == nil, request.authority == nil,
           baseURL == feedback.endpoint.url,
           !request.headerFields.contains(where: { $0.name.canonicalName == "host" }), let body {
            return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                                            capability: feedback, messageWire: nil)
        }
        if let memoryHistory, request.method == .post, operationID == "applyMemoryHistoryActionV1",
           request.path == "/v3/memory-history-actions", request.scheme == nil, request.authority == nil,
           baseURL == memoryHistory.endpoint.url,
           !request.headerFields.contains(where: { $0.name.canonicalName == "host" }), let body {
            return try await sendLocalWrite(request, body: body, baseURL: baseURL, operationID: operationID,
                                            capability: memoryHistory, messageWire: nil)
        }
        // No other write-shaped request is enabled. Exact official operation/path are
        // fixed here; calling an arbitrary request "readonly" cannot grant capability.
        guard let preview, request.method == .post, operationID == Operations.previewManualTripEdit.id,
              request.path == "/v1/trip-manual-previews", request.scheme == nil, request.authority == nil,
              baseURL == preview.endpoint.url,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              let body else {throw MessageHTTPFailure.productionActivationUnavailable}
        let media=request.headerFields.filter{$0.name == .contentType}
        guard media.count == 1, let value=media.first?.value,
              value == "application/json" || value.lowercased() == "application/json; charset=utf-8" else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        try Task.checkCancellation()
        let bytes=try await Data(collecting:body,upTo:preview.endpoint.maximumRequestBytes)
        try await preview.validate()
        try Task.checkCancellation()
        let (response,responseBody)=try await transport.send(request,body:HTTPBody(bytes),baseURL:baseURL,operationID:operationID)
        try await preview.validate()
        try Task.checkCancellation()
        guard !(300..<400).contains(response.status.code) else {throw MessageHTTPFailure.redirectRejected}
        guard let responseBody else {throw MessageHTTPFailure.invalidResponse}
        let result=try await Data(collecting:responseBody,upTo:preview.endpoint.maximumResponseBytes)
        try await preview.validate()
        try Task.checkCancellation()
        return (response,HTTPBody(result))
    }
    private func sendLocalRead(_ request: HTTPRequest, baseURL: URL, operationID: String,
                               capability: EndpointCapability) async throws -> (HTTPResponse, HTTPBody?) {
        try await capability.validate(); try Task.checkCancellation()
        let (response, responseBody) = try await transport.send(request, body: nil, baseURL: baseURL, operationID: operationID)
        try await capability.validate(); try Task.checkCancellation()
        guard !(300..<400).contains(response.status.code), let responseBody else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await Data(collecting: responseBody, upTo: capability.endpoint.maximumResponseBytes)
        try await capability.validate(); try Task.checkCancellation()
        return (response, HTTPBody(bytes))
    }
    private func sendLocalWrite(_ request: HTTPRequest, body: HTTPBody, baseURL: URL, operationID: String,
                                capability: EndpointCapability, messageWire: MessageWire?) async throws -> (HTTPResponse, HTTPBody?) {
        let media = request.headerFields.filter { $0.name == .contentType }
        guard media.count == 1, media.first?.value == "application/octet-stream" else { throw MessageHTTPFailure.invalidConfiguration }
        try Task.checkCancellation()
        let bytes = try await Data(collecting: body, upTo: capability.endpoint.maximumRequestBytes)
        switch messageWire {
        case .legacy: _ = try OriginalMessageSend(raw: bytes, maximumBytes: capability.endpoint.maximumRequestBytes)
        case .travel: _ = try OriginalTravelMessageSend(raw: bytes, maximumBytes: capability.endpoint.maximumRequestBytes)
        case .discussion: _ = try OriginalTripDiscussion(raw: bytes, maximumBytes: capability.endpoint.maximumRequestBytes)
        case .edit: _ = try OriginalTripEdit(raw: bytes, maximumBytes: capability.endpoint.maximumRequestBytes)
        case nil: break
        }
        try await capability.validate()
        try Task.checkCancellation()
        let (response, responseBody) = try await transport.send(request, body: HTTPBody(bytes), baseURL: baseURL, operationID: operationID)
        try await capability.validate()
        try Task.checkCancellation()
        guard !(300..<400).contains(response.status.code), let responseBody else { throw MessageHTTPFailure.invalidResponse }
        let result = try await Data(collecting: responseBody, upTo: capability.endpoint.maximumResponseBytes)
        try await capability.validate()
        try Task.checkCancellation()
        return (response, HTTPBody(result))
    }

}
private final class RedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest) async -> URLRequest? { nil }
}

public enum MessageHTTPOutcome: Sendable {
    case accepted
    case notObserved
    case rejected(status: Int, error: Components.Schemas.ErrorResponse)
}

@MainActor public final class MessageHTTPClient {
    let recovery: MessageRecovery
    let scope: StorageScope
    let endpoint: MessageEndpoint
    private let credentials: any MessageCredentialsProvider
    private let transport: any ClientTransport
    let submissionEnabledForTest: Bool
    let readsScopedEditResults: Bool
    var tripEditStatusOperation: String { readsScopedEditResults ? "readTripEditStatusV5" : "readTripEditStatusV4" }
    var tripEditStatusVersion: Int { readsScopedEditResults ? 5 : 4 }
    let liveMessageTransport: NoRedirectTransport?
    var sendPermitState = SendPermitState()
    var travelSendPermitState = SendPermitState()
    var tripDiscussionPermitState = SendPermitState()
    var tripDiscussionSources:[Data:MessageTripContent]=[:]
    var tripEditPermitState = SendPermitState()
    var tripEditSources: [Data: MessageTripContent] = [:]
    let conversationOpeningOwner=UUID()
    private let readOwner = UUID()
    /// Test seam only: caller must supply a non-network interceptor, never a live transport.
    public init(recovery: MessageRecovery, scope: StorageScope, endpoint: MessageEndpoint,
                credentials: any MessageCredentialsProvider, interceptedTestTransport: any ClientTransport, readsScopedEditResults: Bool = false) {
        self.recovery = recovery; self.scope = scope; self.endpoint = endpoint
        self.credentials = credentials; self.transport = interceptedTestTransport
        self.readsScopedEditResults=readsScopedEditResults
        submissionEnabledForTest = true
        liveMessageTransport = nil
    }
    /// Production/default transports stay read-only. Only the explicit DEBUG Simulator
    /// message capability can send, through the current-process head/permit path.
    public init(recovery: MessageRecovery, scope: StorageScope, endpoint: MessageEndpoint,
                credentials: any MessageCredentialsProvider, liveReadTransport: NoRedirectTransport, readsScopedEditResults: Bool = false) {
        self.recovery = recovery; self.scope = scope; self.endpoint = endpoint
        self.credentials = credentials; self.transport = liveReadTransport
        self.readsScopedEditResults=readsScopedEditResults
        submissionEnabledForTest = false
        liveMessageTransport = liveReadTransport
    }
    func client(_ lease: Lease, configuration: Configuration = .init()) async throws -> Client {
        let checked = try await checkedTransport(lease)
        return Client(serverURL: endpoint.url, configuration: configuration, transport: checked)
    }
    func checkedTransport(_ lease: Lease) async throws -> CheckedTransport {
        try recovery.validateScope(scope, lease: lease)
        let value = try await credentials.bearer(for: scope, lease: lease)
        try recovery.validateScope(scope, lease: lease)
        guard let value, !value.isEmpty, value.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw MessageHTTPFailure.credentialsUnavailable }
        return CheckedTransport(underlying: transport, endpoint: endpoint, bearer: value,
            validate: { [recovery,scope] in try recovery.validateScope(scope,lease:lease) })
    }
    public func submit(messageID: String, lease: Lease) async throws -> MessageHTTPOutcome {
        if !submissionEnabledForTest { return try await submitPrepared(messageID: messageID, lease: lease) }
        let client = try await client(lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease),
              record.originalUTF8.count <= endpoint.maximumRequestBytes else { throw RecoveryError.invalidInput }
        var original = StrictJSON(bytes: Array(record.originalUTF8)); try original.check()
        guard let envelope = try JSONSerialization.jsonObject(with: record.originalUTF8) as? [String: Any],
              let originalID = envelope["message_id"] as? String, Data(originalID.utf8) == Data(messageID.utf8),
              let conversationID = envelope["conversation_id"] as? String, !conversationID.isEmpty else {
            throw RecoveryError.invalidInput
        }
        let submission = try recovery.beginSubmission(messageID: messageID, lease: lease)
        let output: Operations.receiveMessage.Output
        do { output = try await client.receiveMessage(.init(body: .binary(HTTPBody(submission.originalUTF8)))) }
        catch {
            try recovery.observeUnknown(submission.operation)
            // Generated ClientError may carry an Authorization-bearing request; do not
            // expose it through this public boundary or turn it into a retry instruction.
            throw MessageHTTPFailure.exchangeUnknown
        }
        switch output {
        case .ok(let response):
            let body = try response.body.json
            let receipt = body.receipt
            guard Data(receipt.conversation_id.utf8) == Data(conversationID.utf8), !receipt.generation.isEmpty, !receipt.run_id.isEmpty,
                  receipt.sequence > 0 else {
                try recovery.observeUnknown(submission.operation); throw MessageHTTPFailure.invalidResponse
            }
            try recovery.observeReceipt(submission.operation, messageID: receipt.message_id,
                                        inputSHA256: receipt.input_sha256, receipt: JSONEncoder().encode(receipt))
            return .accepted
        case .default(let status, let response):
            try recovery.observeUnknown(submission.operation)
            return .rejected(status: status, error: try response.body.json)
        }
    }
    public func query(messageID: String, lease: Lease) async throws -> MessageHTTPOutcome {
        let client = try await client(lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.invalidInput }
        var original = StrictJSON(bytes: Array(record.originalUTF8)); try original.check()
        guard let envelope = try JSONSerialization.jsonObject(with: record.originalUTF8) as? [String: Any],
              let originalID = envelope["message_id"] as? String, Data(originalID.utf8) == Data(messageID.utf8),
              let conversationID = envelope["conversation_id"] as? String, !conversationID.isEmpty else {
            throw RecoveryError.invalidInput
        }
        let operation = try recovery.beginQuery(messageID: messageID, lease: lease)
        let output: Operations.queryMessageReceipt.Output
        do { output = try await client.queryMessageReceipt(.init(query: .init(message_id: messageID))) }
        catch {
            try recovery.observeUnknown(operation)
            throw MessageHTTPFailure.exchangeUnknown
        }
        switch output {
        case .ok(let response):
            let body = try response.body.json
            switch body.receipt {
            case .MessageReceipt(let receipt):
                guard Data(receipt.conversation_id.utf8) == Data(conversationID.utf8),
                      !receipt.generation.isEmpty, !receipt.run_id.isEmpty, receipt.sequence > 0 else {
                    try recovery.observeUnknown(operation); throw MessageHTTPFailure.invalidResponse
                }
                try recovery.observeReceipt(operation, messageID: receipt.message_id,
                                            inputSHA256: receipt.input_sha256, receipt: JSONEncoder().encode(receipt))
                return .accepted
            case .case2(let container):
                // The generated fallback accepts arbitrary JSON. Only actual null is absence.
                guard container.value == nil else {
                    try recovery.observeUnknown(operation); throw MessageHTTPFailure.invalidResponse
                }
                try recovery.observeNotObserved(operation)
                return .notObserved
            }
        case .default(let status, let response):
            try recovery.observeUnknown(operation)
            return .rejected(status: status, error: try response.body.json)
        }
    }
}


public struct MessageReadLimits: Sendable {
    public let maximumPageItems: Int
    public let maximumCursorBytes: Int
    public let maximumDecodedBytes: Int
    public let maximumPages: Int
    public init(maximumPageItems: Int, maximumCursorBytes: Int, maximumDecodedBytes: Int, maximumPages: Int) throws {
        guard (1...100).contains(maximumPageItems), maximumCursorBytes > 0,
              maximumDecodedBytes > 0, maximumPages > 0 else { throw MessageHTTPFailure.invalidConfiguration }
        self.maximumPageItems = maximumPageItems; self.maximumCursorBytes = maximumCursorBytes
        self.maximumDecodedBytes = maximumDecodedBytes; self.maximumPages = maximumPages
    }
}
/// Local, non-Codable continuation; server cursor remains opaque, never an authority.
public struct MessageReadCursor: Sendable {
    fileprivate let owner: UUID
    fileprivate let lease: Lease
    fileprivate let purpose: Data
    fileprivate let opaque: String
    fileprivate let last: Int64
    fileprivate let generation: String?
    fileprivate let seenCursors: Set<Data>
    fileprivate let seenIDs: Set<Data>
}
/// Wrapper around official generated values, not a second wire schema.
public struct MessageReadResult<Value: Sendable>: Sendable {
    public let value: Value
    public let next: MessageReadCursor?
    public let requestID: String
    fileprivate let owner: UUID
    fileprivate let lease: Lease
}
public enum MessageReadFailure: Error {
    case resyncRequired
    case rejected(status: Int, error: Components.Schemas.ErrorResponse)
}

extension MessageHTTPClient {
    public func validateRead<Value>(_ result: MessageReadResult<Value>, lease: Lease) throws {
        try recovery.validateScope(scope, lease: lease)
        guard result.owner == readOwner, result.lease == lease else { throw RecoveryError.inactive }
    }
    public func originalSendVersion(messageID: String,lease: Lease) throws -> MessageSendWireVersion {
        try recovery.validateScope(scope,lease:lease)
        guard let record = try recovery.action(messageID:messageID,lease:lease) else { throw RecoveryError.invalidInput }
        var parser = StrictJSON(bytes:Array(record.originalUTF8));try parser.check()
        guard let object = try JSONSerialization.jsonObject(with:record.originalUTF8) as? [String:Any],
              let raw = object["version"] as? String,let version = MessageSendWireVersion(rawValue:raw) else { throw RecoveryError.invalidSnapshot }
        return version
    }
    private func acceptedTravelSource(messageID:String,lease:Lease) throws -> (OriginalTravelMessageSend,Components.Schemas.MessageReceiveV2Response) {
        try recovery.validateScope(scope,lease:lease)
        guard let record = try recovery.action(messageID:messageID,lease:lease),record.phase == .accepted,
              let bytes = record.receipt else { throw RecoveryError.queryOnly }
        let original = try OriginalTravelMessageSend(raw:record.originalUTF8,maximumBytes:endpoint.maximumRequestBytes,expectedMessageID:messageID)
        let value = try JSONDecoder().decode(Components.Schemas.MessageReceiveV2Response.self,from:bytes)
        _ = try ValidatedTravelMessageReceipt(receipt:value.receipt,reference:value.reference,original:original)
        try recovery.validateScope(scope,lease:lease)
        return (original,value)
    }
    public func acceptedTravelMessage(messageID: String,lease: Lease) throws -> MessageReadResult<Components.Schemas.MessageReceiveV2Response> {
        let (_,value)=try acceptedTravelSource(messageID:messageID,lease:lease)
        return MessageReadResult(value:value,next:nil,requestID:value.request_id,owner:readOwner,lease:lease)
    }
    public func acceptedTravelMessageSource(messageID:String,lease:Lease) throws -> MessageReadResult<AcceptedTravelMessageSource> {
        let (original,value)=try acceptedTravelSource(messageID:messageID,lease:lease)
        let source=AcceptedTravelMessageSource(receipt:value.receipt,reference:value.reference,creationIntent:original.creationIntent,
            needsID:original.needsReference?.id,needsVersion:original.needsReference?.expectedVersion)
        return MessageReadResult(value:source,next:nil,requestID:value.request_id,owner:readOwner,lease:lease)
    }
    /// Real owned B data under the current client/lease. This result never
    /// substitutes for B's original accepted-message reference or effect lease.
    public func readTravelContext(id: String, lease: Lease) async throws -> MessageReadResult<Components.Schemas.TravelContextReadResponse.travel_contextPayload> {
        try recovery.validateScope(scope, lease: lease)
        guard id.utf8.count == 32,id.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { throw RecoveryError.invalidInput }
        let api = try await client(lease, configuration: .memory)
        let output: Operations.getTravelContext.Output
        do { output = try await api.getTravelContext(.init(path: .init(context_id: id))) }
        catch { try recovery.validateScope(scope, lease: lease);throw MessageHTTPFailure.exchangeUnknown }
        try recovery.validateScope(scope, lease: lease)
        switch output {
        case .ok(let response):
            let body = try response.body.json
            guard Data(body.travel_context.id.utf8) == Data(id.utf8),body.travel_context.version > 0 else { throw MessageHTTPFailure.invalidResponse }
            return MessageReadResult(value: body.travel_context,next: nil,requestID: body.request_id,owner: readOwner,lease: lease)
        case .default(let status,let response):throw MessageReadFailure.rejected(status: status,error: try response.body.json)
        }
    }
    private func readCursor(_ cursor: MessageReadCursor?, purpose: Data, limit: Int, limits: MessageReadLimits, lease: Lease) throws {
        try recovery.validateScope(scope, lease: lease)
        guard (1...limits.maximumPageItems).contains(limit) else { throw MessageHTTPFailure.invalidConfiguration }
        if let cursor {
            guard cursor.owner == readOwner, cursor.lease == lease, cursor.purpose == purpose,
                  cursor.opaque.utf8.count <= limits.maximumCursorBytes else { throw MessageReadFailure.resyncRequired }
        }
    }
    private func nextRead(_ text: String?, previous: MessageReadCursor?, purpose: Data, last: Int64,
                          generation: String?, ids: Set<Data>, limits: MessageReadLimits, lease: Lease) throws -> MessageReadCursor? {
        guard let text else { return nil }
        var seen = previous?.seenCursors ?? []
        guard !text.isEmpty, text.utf8.count <= limits.maximumCursorBytes,
              seen.count + 1 < limits.maximumPages, seen.insert(Data(text.utf8)).inserted else { throw MessageReadFailure.resyncRequired }
        return MessageReadCursor(owner: readOwner, lease: lease, purpose: purpose, opaque: text,
                                 last: last, generation: generation, seenCursors: seen, seenIDs: ids)
    }
    private func readError(_ status: Int, _ body: Components.Schemas.ErrorResponse) throws -> Never {
        if status == 409 && body.error.code == "HISTORY_RESYNC_REQUIRED" { throw MessageReadFailure.resyncRequired }
        throw MessageReadFailure.rejected(status: status, error: body)
    }
    private func decoded(_ base64: String, maximum: Int) throws -> Data {
        guard let data = Data(base64Encoded: base64), data.count <= maximum,
              data.base64EncodedString() == base64, String(data: data, encoding: .utf8) != nil else { throw MessageHTTPFailure.invalidResponse }
        return data
    }
    public func conversations(limit: Int, after: MessageReadCursor? = nil, limits: MessageReadLimits, lease: Lease) async throws -> MessageReadResult<[Components.Schemas.ConversationSummary]> {
        let purpose = Data("conversations".utf8)
        try readCursor(after, purpose: purpose, limit: limit, limits: limits, lease: lease)
        let client = try await client(lease)
        let output: Operations.listConversations.Output
        do { output = try await client.listConversations(.init(query: .init(limit: limit, cursor: after?.opaque))) }
        catch { try recovery.validateScope(scope, lease: lease); throw MessageHTTPFailure.exchangeUnknown }
        try recovery.validateScope(scope, lease: lease)
        switch output {
        case .ok(let response):
            let body = try response.body.json
            let cursor: String?
            switch body.next_cursor {
            case .case1(let text): cursor = text
            case .case2(let container): guard container.value == nil else { throw MessageHTTPFailure.invalidResponse }; cursor = nil
            }
            guard body.conversations.count <= limit, !body.conversations.isEmpty || (after == nil && cursor == nil) else { throw MessageHTTPFailure.invalidResponse }
            var last = after?.last ?? 0; var ids = after?.seenIDs ?? []
            for row in body.conversations {
                guard !row.conversation_id.isEmpty, !row.generation.isEmpty, row.epoch >= 0,
                      row.list_sequence > last, ids.insert(Data(row.conversation_id.utf8)).inserted else { throw MessageReadFailure.resyncRequired }
                last = row.list_sequence
            }
            let next = try nextRead(cursor, previous: after, purpose: purpose, last: last, generation: nil, ids: ids, limits: limits, lease: lease)
            return MessageReadResult(value: body.conversations, next: next, requestID: body.request_id, owner: readOwner, lease: lease)
        case .default(let status, let response): try readError(status, response.body.json)
        }
    }
    public func history(conversationID: String, limit: Int, after: MessageReadCursor? = nil, limits: MessageReadLimits, lease: Lease) async throws -> MessageReadResult<[Components.Schemas.MessageHistoryItem]> {
        guard !conversationID.isEmpty else { throw MessageHTTPFailure.invalidConfiguration }
        try checkSendLease(lease)
        let historyKey = Data(conversationID.utf8)
        let historyEpoch = sendPermitState.historyEpochs[historyKey]
        let purpose = Data("history:".utf8) + Data(conversationID.utf8)
        try readCursor(after, purpose: purpose, limit: limit, limits: limits, lease: lease)
        let client = try await client(lease)
        let output: Operations.readMessageHistory.Output
        do { output = try await client.readMessageHistory(.init(query: .init(conversation_id: conversationID, limit: limit, cursor: after?.opaque))) }
        catch { try recovery.validateScope(scope, lease: lease); throw MessageHTTPFailure.exchangeUnknown }
        try recovery.validateScope(scope, lease: lease)
        switch output {
        case .ok(let response):
            let body = try response.body.json
            let cursor: String?
            switch body.next_cursor {
            case .case1(let text): cursor = text
            case .case2(let container): guard container.value == nil else { throw MessageHTTPFailure.invalidResponse }; cursor = nil
            }
            guard body.messages.count <= limit, !body.messages.isEmpty || (after == nil && cursor == nil) else { throw MessageHTTPFailure.invalidResponse }
            var last = after?.last ?? 0; var generation = after?.generation; var ids = after?.seenIDs ?? []; var remaining = limits.maximumDecodedBytes
            for row in body.messages {
                let r = row.receipt
                guard Data(r.conversation_id.utf8) == Data(conversationID.utf8), !r.message_id.isEmpty,
                      !r.generation.isEmpty, !r.run_id.isEmpty, last < Int64.max,
                      Int64(exactly:r.sequence) == last + 1, ids.insert(Data(r.message_id.utf8)).inserted,
                      generation.map({ Data($0.utf8) == Data(r.generation.utf8) }) ?? true else { throw MessageReadFailure.resyncRequired }
                let raw = try decoded(row.original_utf8_base64, maximum: remaining); remaining -= raw.count
                var parser = StrictJSON(bytes: Array(raw)); try parser.check()
                guard let original = try JSONSerialization.jsonObject(with: raw) as? [String:Any],
                      let mid = original["message_id"] as? String, Data(mid.utf8) == Data(r.message_id.utf8),
                      let cid = original["conversation_id"] as? String, Data(cid.utf8) == Data(conversationID.utf8),
                      let text = original["text"] as? String, Data(text.utf8) == Data(row.text.utf8),
                      SHA256.hash(data:raw).map({String(format:"%02x",$0)}).joined() == r.input_sha256 else { throw MessageHTTPFailure.invalidResponse }
                generation = r.generation; last = Int64(r.sequence)
            }
            let next = try nextRead(cursor, previous: after, purpose: purpose, last: last, generation: generation, ids: ids, limits: limits, lease: lease)
            try checkSendLease(lease)
            if sendPermitState.historyEpochs[historyKey] == historyEpoch, let generation {
                sendPermitState.historyHeads[historyKey] = .init(conversation_id: conversationID, generation: generation, last_sequence: last)
            }
            return MessageReadResult(value:body.messages,next:next,requestID:body.request_id,owner:readOwner,lease:lease)
        case .default(let status, let response): try readError(status, response.body.json)
        }
    }
    public func draft(conversationID: String, generation: String, limits: MessageReadLimits, lease: Lease) async throws -> MessageReadResult<Components.Schemas.MessageDraftSnapshot?> {
        guard !conversationID.isEmpty, !generation.isEmpty else { throw MessageHTTPFailure.invalidConfiguration }
        let client = try await client(lease)
        let output: Operations.readMessageDraft.Output
        do { output = try await client.readMessageDraft(.init(query:.init(conversation_id:conversationID,generation:generation))) }
        catch { try recovery.validateScope(scope, lease: lease); throw MessageHTTPFailure.exchangeUnknown }
        try recovery.validateScope(scope, lease: lease)
        switch output {
        case .ok(let response):
            let body = try response.body.json
            let value: Components.Schemas.MessageDraftSnapshot?
            switch body.draft {
            case .MessageDraftSnapshot(let snapshot):
                guard Data(snapshot.conversation_id.utf8) == Data(conversationID.utf8), Data(snapshot.generation.utf8) == Data(generation.utf8), snapshot.revision > 0 else { throw MessageHTTPFailure.invalidResponse }
                _ = try decoded(snapshot.original_utf8_base64, maximum:limits.maximumDecodedBytes); value = snapshot
            case .case2(let container): guard container.value == nil else { throw MessageHTTPFailure.invalidResponse }; value = nil
            }
            return MessageReadResult(value:value,next:nil,requestID:body.request_id,owner:readOwner,lease:lease)
        case .default(let status, let response): try readError(status, response.body.json)
        }
    }
    /// Current human-history projection only. It deliberately does not update
    /// send permits, accepted action recovery or any current Trip selection.
    public func preservedHistory(conversationID: String, limit: Int, after: MessageReadCursor? = nil,
        limits: MessageReadLimits, lease: Lease) async throws -> MessageReadResult<[MessageHumanHistoryItem]> {
        guard !conversationID.isEmpty, conversationID.utf8.count <= 256, !conversationID.utf8.contains(0) else { throw MessageHTTPFailure.invalidConfiguration }
        try checkSendLease(lease)
        let purpose = Data("preserved-history5:".utf8) + Data(conversationID.utf8)
        try readCursor(after, purpose: purpose, limit: limit, limits: limits, lease: lease)
        var query = URLComponents(); query.path = "/v5/message-history"
        query.queryItems = [.init(name: "conversation_id", value: conversationID), .init(name: "limit", value: String(limit))]
        if let after { query.queryItems!.append(.init(name: "cursor", value: after.opaque)) }
        query.percentEncodedQuery = query.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        guard let path = query.string else { throw MessageHTTPFailure.invalidConfiguration }
        let (status, bytes, trace) = try await versionedMessageExchange(path: path, operation: "readPreservedMessageHistoryV5", raw: nil, lease: lease)
        guard status == 200 else { try readError(status, JSONDecoder().decode(Components.Schemas.ErrorResponse.self, from: bytes)) }
        let page = try PreservedHistoryPage(raw: bytes, maximumBytes: endpoint.maximumResponseBytes,
            decodedLimit: limits.maximumDecodedBytes, limit: limit, requestID: trace)
        guard !page.rows.isEmpty || (after == nil && page.next == nil) else { throw MessageHTTPFailure.invalidResponse }
        var last = after?.last ?? 0, generation = after?.generation, ids = after?.seenIDs ?? []
        for row in page.rows {
            let r = row.receipt
            guard DiscussionJSON.same(r.conversation_id, conversationID), !r.message_id.isEmpty, !r.generation.isEmpty, !r.run_id.isEmpty,
                  last < Int64.max, Int64(exactly: r.sequence) == last + 1, ids.insert(Data(r.message_id.utf8)).inserted,
                  generation.map({ DiscussionJSON.same($0, r.generation) }) ?? true else { throw MessageReadFailure.resyncRequired }
            generation = r.generation; last = Int64(r.sequence)
        }
        let next = try nextRead(page.next, previous: after, purpose: purpose, last: last, generation: generation, ids: ids, limits: limits, lease: lease)
        try checkSendLease(lease)
        return MessageReadResult(value: page.rows, next: next, requestID: trace, owner: readOwner, lease: lease)
    }
    /// A row must belong to this exact live page/client/lease. The result carries
    /// only display state; it cannot recover an input or stage a RUN/Trip write.
    public func preservedRun(for row: MessageHumanHistoryItem, page: MessageReadResult<[MessageHumanHistoryItem]>,
        limits: MessageReadLimits, lease: Lease) async throws -> MessageReadResult<MessageHumanRun> {
        try validateRead(page, lease: lease); try checkSendLease(lease)
        guard page.value.contains(where: { $0.id == row.id }) else { throw RecoveryError.inactive }
        var query = URLComponents(); query.path = "/v6/run-display"
        query.queryItems = [.init(name: "message_id", value: row.receipt.message_id)]
        query.percentEncodedQuery = query.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        guard let path = query.string else { throw MessageHTTPFailure.invalidConfiguration }
        let (status, bytes, trace) = try await versionedMessageExchange(path: path, operation: "readPreservedRunDisplayV6", raw: nil, lease: lease)
        guard status == 200 else { try readError(status, JSONDecoder().decode(Components.Schemas.ErrorResponse.self, from: bytes)) }
        let value = try decodePreservedRun(bytes, maximumBytes: endpoint.maximumResponseBytes,
            textLimit: limits.maximumDecodedBytes, trace: trace, row: row)
        try validateRead(page, lease: lease); try checkSendLease(lease)
        return MessageReadResult(value: value, next: nil, requestID: trace, owner: readOwner, lease: lease)
    }
    public func tripDiscussionHistory(conversationID:String,limit:Int,after:MessageReadCursor?=nil,limits:MessageReadLimits,lease:Lease) async throws -> MessageReadResult<[MessageTripHistoryItem]> {
        try await versionedTripHistory(conversationID:conversationID,limit:limit,after:after,limits:limits,lease:lease,edit:false)
    }
    public func tripEditHistory(conversationID:String,limit:Int,after:MessageReadCursor?=nil,limits:MessageReadLimits,lease:Lease) async throws -> MessageReadResult<[MessageTripHistoryItem]> {
        try await versionedTripHistory(conversationID:conversationID,limit:limit,after:after,limits:limits,lease:lease,edit:true)
    }
    private func versionedTripHistory(conversationID:String,limit:Int,after:MessageReadCursor?,limits:MessageReadLimits,lease:Lease,edit:Bool) async throws -> MessageReadResult<[MessageTripHistoryItem]> {
        guard !conversationID.isEmpty else { throw MessageHTTPFailure.invalidConfiguration }
        try checkSendLease(lease)
        let key=Data(conversationID.utf8),historyEpoch=sendPermitState.historyEpochs[Data(conversationID.utf8)]
        let scopedResults=edit && readsScopedEditResults
        let purpose=Data((scopedResults ? "trip-edit-result-history:" : edit ? "trip-edit-history:" : "trip-discussion-history:").utf8)+key
        try readCursor(after,purpose:purpose,limit:limit,limits:limits,lease:lease)
        var query=URLComponents();query.path=scopedResults ? "/v4/message-history" : edit ? "/v3/message-history" : "/v2/message-history"
        query.queryItems=[.init(name:"conversation_id",value:conversationID),.init(name:"limit",value:String(limit))]
        if let after { query.queryItems!.append(.init(name:"cursor",value:after.opaque)) }
        query.percentEncodedQuery=query.percentEncodedQuery?.replacingOccurrences(of:"+",with:"%2B")
        guard let path=query.string else { throw MessageHTTPFailure.invalidConfiguration }
        let (status,bytes,trace)=try await versionedMessageExchange(path:path,operation:scopedResults ? "readTripEditHistoryV4" : edit ? "readTripEditHistoryV3" : "readTripDiscussionHistoryV2",raw:nil,lease:lease)
        guard status==200 else { try readError(status,JSONDecoder().decode(Components.Schemas.ErrorResponse.self,from:bytes)) }
        let page=try TripDiscussionHistory(raw:bytes,maximumBytes:endpoint.maximumResponseBytes,decodedLimit:limits.maximumDecodedBytes,limit:limit,requestID:trace,edit:edit,scopedResults:scopedResults)
        guard !page.rows.isEmpty || (after==nil && page.next==nil) else { throw MessageHTTPFailure.invalidResponse }
        var last=after?.last ?? 0,generation=after?.generation,ids=after?.seenIDs ?? []
        for row in page.rows {
            let r=row.receipt
            guard DiscussionJSON.same(r.conversation_id,conversationID),!r.message_id.isEmpty,!r.generation.isEmpty,!r.run_id.isEmpty,last<Int64.max,
                  Int64(exactly:r.sequence)==last+1,ids.insert(Data(r.message_id.utf8)).inserted,
                  generation.map({DiscussionJSON.same($0,r.generation)}) ?? true else { throw MessageReadFailure.resyncRequired }
            generation=r.generation;last=Int64(r.sequence)
        }
        let next=try nextRead(page.next,previous:after,purpose:purpose,last:last,generation:generation,ids:ids,limits:limits,lease:lease)
        try checkSendLease(lease)
        if sendPermitState.historyEpochs[key]==historyEpoch,let generation {
            sendPermitState.historyHeads[key] = .init(conversation_id:conversationID,generation:generation,last_sequence:last)
        }
        return MessageReadResult(value:page.rows,next:next,requestID:trace,owner:readOwner,lease:lease)
    }
}


public struct DraftSaveConfirmation: Sendable {
    public let snapshot: Components.Schemas.MessageDraftSnapshot
    public let matchesCurrentEditor: Bool
    fileprivate let owner: UUID
    fileprivate let lease: Lease
}
extension MessageHTTPClient {
    public func validateDraftConfirmation(_ result: DraftSaveConfirmation, lease: Lease) throws -> Bool {
        try recovery.validateScope(scope,lease:lease)
        guard result.owner == readOwner, result.lease == lease else { throw RecoveryError.inactive }
        guard result.matchesCurrentEditor else { return false }
        return try recovery.draftConfirmationMatchesEditor(
            conversationID:result.snapshot.conversation_id,revision:result.snapshot.revision,lease:lease)
    }
    public func saveDraft(conversationID: String, generation: String, expectedRevision: Int64, originalUTF8: Data,
                          limits: MessageReadLimits, lease: Lease) async throws -> DraftSaveConfirmation {
        guard submissionEnabledForTest else { throw MessageHTTPFailure.productionActivationUnavailable }
        guard originalUTF8.count <= endpoint.maximumRequestBytes else { throw RecoveryError.invalidInput }
        let client = try await client(lease)
        try Task.checkCancellation()
        let operation = try recovery.beginDraftSave(conversationID:conversationID,generation:generation,
            expectedRevision:expectedRevision,originalUTF8:originalUTF8,lease:lease)
        let output: Operations.saveMessageDraft.Output
        do {
            output = try await client.saveMessageDraft(.init(query:.init(conversation_id:conversationID,generation:generation,expected_revision:expectedRevision),body:.binary(HTTPBody(originalUTF8))))
            try Task.checkCancellation()
        } catch {
            try recovery.validateScope(scope,lease:lease)
            // The immutable pending CAS record already exists; never infer rollback/retry.
            throw MessageHTTPFailure.exchangeUnknown
        }
        try recovery.validateScope(scope,lease:lease)
        switch output {
        case .ok(let response):
            let saved = try response.body.json.draft
            let bytes = try decoded(saved.original_utf8_base64,maximum:limits.maximumDecodedBytes)
            let matches = try recovery.confirmDraftSave(operation,conversationID:saved.conversation_id,
                generation:saved.generation,revision:saved.revision,originalUTF8:bytes)
            return DraftSaveConfirmation(snapshot:saved,matchesCurrentEditor:matches,owner:readOwner,lease:lease)
        case .default(let status, let response): try readError(status,response.body.json)
        }
    }
    /// Read original CAS target only. Equal bytes/revision or null never settle its write.
    public func reconcileDraft(conversationID: String, limits: MessageReadLimits, lease: Lease) async throws -> MessageReadResult<Components.Schemas.MessageDraftSnapshot?> {
        try recovery.validateScope(scope,lease:lease)
        guard let pending = try recovery.draftSave(conversationID:conversationID,lease:lease) else { throw RecoveryError.invalidInput }
        return try await draft(conversationID:pending.conversationID,generation:pending.generation,limits:limits,lease:lease)
    }
}
