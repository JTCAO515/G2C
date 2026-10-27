// Only referenced by the external acceptance project, never the shipping App target.
import SwiftUI
import CJShell
import CJMemoryClient
import CJMessageHTTP

@MainActor @main
struct ShellFixtureApp: App {
    @State private var shell: ShellState
    private let memory: MemoryContainerHost
    private let mode: String

    init() {
        let env = ProcessInfo.processInfo.environment
        let run = env["SHELL_FIXTURE_RUN"]!
        let mode = env["SHELL_FIXTURE_MEMORY"]!
        self.mode = mode
        let preferences = UserDefaults(suiteName: "g2c.shell.acceptance." + run)!
        preferences.register(defaults: [ShellState.languageKey: env["SHELL_FIXTURE_LANGUAGE"] ?? "en"])
        let shell = ShellState(preferences: preferences)
        shell.tripPath = [.proposal]
        _ = shell.apply(ShellPresentation(context: ShellContext(
            conversationReference: "synthetic-chat-157", tripReference: "synthetic-trip-157")), for: shell.generation)
        let host = MemoryContainerHost(shell: shell)
        if mode != "unconfigured" {
            let binding = MemoryBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
            let endpoint = try! MemoryEndpoint(url: URL(string: env["SHELL_FIXTURE_URL"]!)!,
                maximumRequestBytes: 100_000, maximumResponseBytes: 100_000, allowLoopbackHTTP: true)
            let client = MemoryClient(endpoint: endpoint,
                credentials: { _ in "SYNTHETIC-" + mode + "-" + run }, currentBinding: { binding },
                pendingStore: nil, liveReadTransport: try! NoRedirectTransport(requestTimeout: 3, resourceTimeout: 5))
            precondition(host.bind(MemoryContainerBinding(client: client, memory: binding,
                shellGeneration: shell.generation, pageSize: 10, synthetic: true, currentBinding: { binding })))
        }
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
            ShellView(state: shell, memoryContainerHost: memory)
                .safeAreaInset(edge: .top) {
                    Text("SYNTHETIC UI TEST / 合成界面测试")
                        .font(.caption2)
                        .accessibilityIdentifier("shell.fixture.observation")
                        .accessibilityValue(observation)
                }
                .task {
                    if mode != "unconfigured" { await memory.loadGroups(context: memory.captureAction()) }
                }
        }
    }
}
