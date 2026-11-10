// Intercepted transport for the actual signed chat library in simulator acceptance.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJMessageClient
@testable import CJMessageHTTP
import CryptoKit
import HTTPTypes
import OpenAPIRuntime

private struct LioChatHistoryFixture: View {
    let shell: ShellState
    @State private var clients: Result<ChatHistoryClients, any Error>?

    var body: some View {
        Group {
            switch clients {
            case .success(let clients):
                LioHome(language: shell.language.lio, service: clients.original, isDemo: false,
                        chatLibrary: clients.library) { LioLanguagePicker(shell: shell) }
            case .failure(let error):
                Text("Synthetic chat setup failed: \(String(reflecting: error))")
            case nil:
                ProgressView()
            }
        }
        .task {
            if clients == nil { clients = Result { try ChatHistoryClients(shell: shell) } }
        }
    }
}

@MainActor
private struct ChatHistoryClients {
    let original: LioService
    let library: LioChatLibrary

    init(shell: ShellState) throws {
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: JourneyStorage())
        let lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: URL(string: "https://synthetic.invalid")!,
                                           maximumRequestBytes: 16_384, maximumResponseBytes: 65_536)
        let locale: LioTimelineWire.Locale = shell.language == .chinese ? .chinese : .english
        let transport = try NoRedirectTransport(interceptedTransport: ChatHistoryTransport(locale: locale), messageEndpoint: endpoint,
                                                validateMessage: {}, lio: true)
        let client = LioTimelineHTTP(scope: scope, lease: lease, credentials: JourneyCredentials(),
                                     transport: transport, firstChatRecovery: recovery)
        let original = LioService.signedTimeline(client)
        self.original = original
        library = .signed(client: client, defaultService: original, language: { shell.language.lio }) { id in
            LioTripHistoryClient(timeline: client, recovery: recovery, scope: scope, lease: lease, conversationID: id)
        }
    }
}

private actor ChatHistoryTransport: ClientTransport {
    private let originalID = "lio-dialogue-0123456789abcdef0123456789abcdef"
    private let newID = "lio-dialogue-abcdef0123456789abcdef0123456789"
    private let locale: LioTimelineWire.Locale
    private var first: (id: String, text: String, digest: String)?
    private var receiptRead = false

    init(locale: LioTimelineWire.Locale) { self.locale = locale }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard request.headerFields[.authorization] == "Bearer SYNTHETIC",
              let path = request.path, let route = URLComponents(string: path) else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        let query = route.queryItems ?? []
        func value(_ name: String) -> String? { query.first { $0.name == name }?.value }
        switch (request.method, route.path) {
        case (.get, "/v1/lio/timeline") where value("conversation_id").map({ $0 == originalID }) ?? true:
            return try page(version: 1, conversation: originalID, id: "sample-old", text: "An earlier question",
                            answer: "An earlier reply.")
        case (.post, "/v2/lio/messages"):
            guard first == nil, let body else {
                receiptRead = false
                throw MessageHTTPFailure.invalidConfiguration
            }
            let bytes = try await Data(collecting: body, upTo: 16_384)
            guard let fields = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                  fields["version"] as? String == "LIO-message.2", fields["new_conversation"] as? Bool == true,
                  fields["locale"] as? String == locale.rawValue,
                  fields["conversation_id"] == nil, let id = fields["message_id"] as? String,
                  let question = fields["text"] as? String else { throw MessageHTTPFailure.invalidConfiguration }
            first = (id, question, SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined())
            throw URLError(.networkConnectionLost)
        case (.get, "/v2/lio/messages"):
            guard let first, value("message_id") == first.id, value("input_sha256") == first.digest else {
                throw MessageHTTPFailure.invalidConfiguration
            }
            receiptRead = true
            return try response(["version": "LIO-message-lookup.2", "receipt": [
                "version": "LIO-message-receipt.2", "message_id": first.id, "conversation_id": newID
            ]])
        case (.get, "/v2/lio/timeline") where value("conversation_id") == newID:
            guard receiptRead, let first else { throw MessageHTTPFailure.invalidConfiguration }
            return try page(version: 2, conversation: newID, id: first.id, text: first.text, answer: "A separate reply.")
        case (.get, "/v2/lio/trip") where value("conversation_id") == newID:
            return try response(["version": "LIO-trip-history.2", "conversation_id": newID,
                                 "current": NSNull(), "history": [], "undo_target": NSNull(), "next_before": NSNull()])
        default:
            throw MessageHTTPFailure.invalidConfiguration
        }
    }

    private func page(version: Int, conversation: String, id: String, text: String,
                      answer: String) throws -> (HTTPResponse, HTTPBody?) {
        try response(["version": "LIO-timeline.\(version)", "conversation_id": conversation, "next_before": NSNull(),
                      "messages": [["message_id": id, "text": text, "answer": answer,
                                    "status": "completed", "sources": []]]])
    }

    private func response(_ value: [String: Any]) throws -> (HTTPResponse, HTTPBody?) {
        var reply = HTTPResponse(status: .ok)
        reply.headerFields[.contentType] = "application/json"
        return (reply, HTTPBody(try JSONSerialization.data(withJSONObject: value)))
    }
}
#endif
