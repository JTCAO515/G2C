#if os(iOS)
import SwiftUI

/// Host owns the state for the window lifetime. No language-based .id or recreation.
public struct ShellView: View {
    @Bindable private var state: ShellState
    @State private var accountHost: AccountHost
    @State private var messageHost: AssistantMessageHost
    @State private var serverHistoryHost: ServerHistoryHost
    @State private var tripContainerHost: TripContainerHost
    @State private var memoryContainerHost: MemoryContainerHost
    @Environment(\.scenePhase) private var scenePhase

    public init(state: ShellState, accountHost: AccountHost? = nil, messageHost: AssistantMessageHost? = nil, serverHistoryHost: ServerHistoryHost? = nil, memoryContainerHost: MemoryContainerHost? = nil, tripContainerHost: TripContainerHost? = nil) {
        if let accountHost { precondition(accountHost.belongs(to: state), "AccountHost must own the same ShellState") }
        if let messageHost { precondition(messageHost.belongs(to: state), "Message host must own the same ShellState") }
        if let serverHistoryHost { precondition(serverHistoryHost.belongs(to: state)) }
        if let memoryContainerHost { precondition(memoryContainerHost.belongs(to: state)) }
        if let tripContainerHost { precondition(tripContainerHost.belongs(to: state)) }
        self.state = state
        self._accountHost = State(initialValue: accountHost ?? AccountHost(shell: state))
        self._messageHost = State(initialValue: messageHost ?? state.messageHost ?? AssistantMessageHost(shell: state))
        self._serverHistoryHost = State(initialValue: serverHistoryHost ?? state.serverHistoryHost ?? ServerHistoryHost(shell: state))
        self._tripContainerHost = State(initialValue: tripContainerHost ?? state.tripContainerHost ?? TripContainerHost(shell: state))
        self._memoryContainerHost = State(initialValue: memoryContainerHost ?? state.memoryContainerHost ?? MemoryContainerHost(shell: state))
    }

    public var body: some View {
        TabView(selection: $state.selectedTab) {
            NavigationStack { AssistantShell(state: state, messageHost: messageHost, serverHistoryHost: serverHistoryHost, bodyText: state.assistantBody) }
                .tabItem { Label(ShellTab.assistant.title(state.language), systemImage: "bubble.left.and.bubble.right") }
                .tag(ShellTab.assistant)
            TripShell(state: state, host: tripContainerHost)
            .tabItem { Label(ShellTab.trips.title(state.language), systemImage: "map") }
            .tag(ShellTab.trips)
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        Text(state.language.text("Coming soon", "尚未开放")).font(.title2)
                        Text(state.language.text("Translation tools are planned for a future version. No tools are connected.", "翻译工具计划在后续版本提供。目前未接入工具。"))
                    }.frame(maxWidth: .infinity, alignment: .leading).padding()
                }.navigationTitle(ShellTab.plugins.title(state.language))
            }
            .tabItem { Label(ShellTab.plugins.title(state.language), systemImage: "square.grid.2x2") }
            .tag(ShellTab.plugins)
            MemoryShell(state: state, accountHost: accountHost, memoryHost: memoryContainerHost)
                .tabItem { Label(ShellTab.memory.title(state.language), systemImage: "tray") }
                .tag(ShellTab.memory)
        }
        .environment(\.locale, Locale(identifier: state.language.rawValue))
        .tint(.primary)
        .onChange(of: scenePhase) { _, phase in
            if phase != .active {
                tripContainerHost.suspendForBackground()
                memoryContainerHost.suspendForBackground()
            }
        }
    }
}

struct ShellStatusView: View {
    let state: ShellPageState
    let language: ShellLanguage

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if state == .loading { ProgressView().accessibilityLabel(language.text("Loading", "正在读取")) }
            Text(message).fixedSize(horizontal: false, vertical: true)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private var message: String {
        switch state {
        case .notConnected: language.text("This service is not connected yet. No records have been loaded.", "此服务尚未接入，尚未读取记录。")
        case .empty: language.text("No records to show.", "暂无记录。")
        case .loading: language.text("Loading records…", "正在读取记录…")
        case .failed: language.text("Could not load records. Nothing is marked as saved.", "记录读取失败，未标记任何保存成功。")
        case .offline: language.text("You are offline. Current records cannot be verified.", "当前离线，无法核实最新记录。")
        case .unknown: language.text("The result is unknown. Do not repeat the action until the original result is checked.", "结果尚不明确，核对原操作结果前请勿重复操作。")
        }
    }
}
#endif
