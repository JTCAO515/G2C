#if DEBUG && G2C_DEMO_BETA && targetEnvironment(simulator)
import SwiftUI
import Foundation

@main
struct DemoCleanupRenewalFixture: App {
    @State private var status = "UNRUN"
    var body: some Scene {
        WindowGroup {
            Text(status).accessibilityIdentifier("b691.status")
                .task {
                    do {
                        guard let raw = ProcessInfo.processInfo.environment["B691_LOCAL_ENDPOINT"],
                              let endpoint = URL(string: raw), endpoint.host == "127.0.0.1" else {
                            throw URLError(.badURL)
                        }
                        for scenario in DemoCleanupRenewalProbe.scenarios {
                            let result = try await DemoCleanupRenewalProbe.run(endpoint: endpoint, scenario: scenario)
                            var request = URLRequest(url: endpoint.appendingPathComponent("probe-result"))
                            request.httpMethod = "POST"
                            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                            request.httpBody = try JSONEncoder().encode(result)
                            let (_, response) = try await URLSession.shared.data(for: request)
                            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
                        }
                        status = "PASS"
                    } catch {
                        status = "FAIL: " + String(describing: error)
                    }
                }
        }
    }
}
#endif
