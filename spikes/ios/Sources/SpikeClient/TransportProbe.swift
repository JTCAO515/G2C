import Foundation
import OpenAPIRuntime
import OpenAPIURLSession

public enum ProbeFailure: Error, Equatable {
    case interrupted
}

public enum TransportProbe {
    /// Construction proves the official URLSession transport API compiles; no request is made here.
    public static func urlSessionClient() -> Client {
        Client(serverURL: URL(string: "https://cj004.invalid")!, transport: URLSessionTransport())
    }

    /// EOF without an explicit local terminal marker stays unknown, never success.
    /// This marker belongs ONLY to this disposable probe; replace with formal C0/RUN semantics.
    public static func stream(client: Client) async throws -> [String] {
        let response = try await client.events()
        let body = try response.ok.body.text_event_hyphen_stream
        var values: [String] = []
        var ended = false
        for try await event in body.asDecodedServerSentEvents(while: { _ in true }) {
            try Task.checkCancellation()
            if event.data == "[DONE]" { ended = true; break }
            if let data = event.data { values.append(data) }
        }
        guard ended else { throw ProbeFailure.interrupted }
        return values
    }
}
