// Only referenced by the external acceptance project, never the shipping App target.
import SwiftUI
import CJShell
import CJMemoryClient
import CJMessageHTTP
import CJTripClient
import CJSession

@MainActor private final class FixtureSessionPersistence: SessionPersistence {
    private var material: SessionMaterial?
    func load() throws -> SessionMaterial? { material }
    func save(_ material: SessionMaterial) throws { self.material = material }
    func clearAndBlock() throws { material = nil }
}

@MainActor private final class ReadOnlyTripFixture {
    let host: TripContainerHost
    init(shell: ShellState, endpoint: MessageEndpoint, mode: String, run: String) throws {
        let session = SessionLifecycle(persistence: FixtureSessionPersistence(), restorePolicy: .userInitiatedOnly)
        let operation = try session.beginTrustedSDKSave()
        try session.save(SessionMaterial(trustedSDKBytes: Data("SYNTHETIC-UI-ONLY".utf8)), for: operation)
        let binding = TripBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
        let client = TripClient(endpoint: endpoint, credentials: { _ in "SYNTHETIC-" + mode + "-" + run },
            currentBinding: { binding }, session: session, sessionOperation: operation,
            liveReadTransport: try NoRedirectTransport(requestTimeout: 30, resourceTimeout: 30))
        precondition(!client.acceptsUserActions)
        host = TripContainerHost(shell: shell)
        precondition(host.bind(TripContainerBinding(client: client, trip: binding, shellGeneration: shell.generation,
            session: session, sessionOperation: operation, pageSize: 10, synthetic: true, currentBinding: { binding })))
    }
}

@MainActor @main
struct ShellFixtureApp: App {
    @State private var shell: ShellState
    private let memory: MemoryContainerHost
    private let trips: ReadOnlyTripFixture?
    private let mode: String
    private let textSize: String?

    init() {
        let env = ProcessInfo.processInfo.environment
        let run = env["SHELL_FIXTURE_RUN"]!
        let mode = env["SHELL_FIXTURE_MEMORY"]!
        self.mode = mode
        textSize = env["SHELL_FIXTURE_SIZE"]
        let preferences = UserDefaults(suiteName: "g2c.shell.acceptance." + run)!
        preferences.register(defaults: [ShellState.languageKey: env["SHELL_FIXTURE_LANGUAGE"] ?? "en"])
        let shell = ShellState(preferences: preferences)
        shell.tripPath = env["SHELL_FIXTURE_TRIPS"] == nil ? [.proposal] : []
        let state = env["SHELL_FIXTURE_ASSISTANT"].flatMap(ShellPageState.init(rawValue:)) ?? .notConnected
        let longText = env["SHELL_FIXTURE_LONG_TEXT"] == "1" ? (1...20).map {
            "Synthetic paragraph \($0) / 合成段落 \($0): Beijing 北京 is sample text for layout only. This is not a real itinerary or service result. 此内容仅用于界面排版测试，不是真实行程或服务结果。"
        }.joined(separator: "\n\n") : nil
        _ = shell.apply(ShellPresentation(context: ShellContext(
            conversationReference: "synthetic-chat-157", tripReference: "synthetic-trip-157"),
            assistantBody: longText, assistant: state), for: shell.generation)
        let host = MemoryContainerHost(shell: shell)
        func endpoint() -> MessageEndpoint {
            let url = URL(string: env["SHELL_FIXTURE_URL"]!)!
            precondition(url.scheme == "http" && url.host == "127.0.0.1" && url.port != nil)
            return try! MessageEndpoint(url: url, maximumRequestBytes: 100_000,
                maximumResponseBytes: 100_000, allowLoopbackHTTP: true)
        }
        if mode != "unconfigured" {
            let binding = MemoryBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
            let client = MemoryClient(endpoint: endpoint(),
                credentials: { _ in "SYNTHETIC-" + mode + "-" + run }, currentBinding: { binding },
                pendingStore: nil, liveReadTransport: try! NoRedirectTransport(requestTimeout: 30, resourceTimeout: 30))
            precondition(host.bind(MemoryContainerBinding(client: client, memory: binding,
                shellGeneration: shell.generation, pageSize: 10, synthetic: true, currentBinding: { binding })))
        }
        if let tripMode = env["SHELL_FIXTURE_TRIPS"], tripMode != "unconfigured" {
            trips = try! ReadOnlyTripFixture(shell: shell, endpoint: endpoint(), mode: tripMode, run: run)
        } else { trips = nil }
        memory = host
        _shell = State(initialValue: shell)
    }

    private var observation: String {
        let value: [String: String] = [
            "conversation": shell.context.conversationReference ?? "",
            "trip": shell.context.tripReference ?? "", "draft": shell.draft,
            "draftRevision": shell.draftRevision.uuidString,
            "generation": String(describing: shell.generation),
            "memoryPath": String(describing: shell.memoryPath),
            "tripPath": String(describing: shell.tripPath),
            "tab": shell.selectedTab.rawValue, "language": shell.language.rawValue
        ]
        return String(decoding: try! JSONSerialization.data(withJSONObject: value, options: .sortedKeys), as: UTF8.self)
    }

    var body: some Scene {
        WindowGroup {
            ShellView(state: shell, memoryContainerHost: memory, tripContainerHost: trips?.host)
                .transformEnvironment(\.dynamicTypeSize) { size in
                    if textSize == "maximum" { size = .accessibility5 }
                    else if textSize == "large" { size = .accessibility3 }
                }
                .safeAreaInset(edge: .top) {
                    Text("SYNTHETIC / 合成")
                        .font(.caption2)
                        .accessibilityIdentifier("shell.fixture.observation")
                        .accessibilityValue(observation)
                }
                .task {
                    if mode != "unconfigured" { await memory.loadGroups(context: memory.captureAction()) }
                }
                .task {
                    if let trips, let work = trips.host.prepareTrips(context: trips.host.captureAction()) {
                        await trips.host.perform(work)
                    }
                }
        }
    }
}
