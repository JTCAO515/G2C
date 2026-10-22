import SwiftUI
import CJShell
import CJAuth
import CJSession
import CJMessageClient

// Compiled together with module sources by scripts/build-demo.sh, not a product target.
@main struct CJShellDemo: App {
    @State private var state: ShellState
    private let accountHost: AccountHost?
    private let messageHost: AssistantMessageHost?
    private let messageDemoFailed: Bool
    private let arguments = ProcessInfo.processInfo.arguments

    init() {
        let shell = ShellState()
        self._state = State(initialValue: shell)
        let args = ProcessInfo.processInfo.arguments
        if args.contains("--message-demo") {
            do {
                self.messageHost = try makeMessageDemo(shell, args: args)
                self.messageDemoFailed = false
            } catch {
                self.messageHost = nil
                self.messageDemoFailed = true
            }
        } else { self.messageHost = nil; self.messageDemoFailed = false }
        if args.contains("--session-demo") {
            shell.selectedTab = .memory
            shell.memoryPath = [.account]
            let store = DemoSessionStore(failClear: args.contains("--clear-fails"))
            let lifecycle = SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly)
            self.accountHost = AccountHost(shell: shell, session: lifecycle, verifyRestored: { _, _ in
                args.contains("--restore-unknown") ? .networkUnknown : .needsServerVerification
            }) { _, _ in UnconfiguredSDKAdapter() }
        } else { self.accountHost = nil }
    }

    var body: some Scene {
        WindowGroup {
            if arguments.contains("--gallery") {
                Gallery()
            } else {
                VStack(spacing: 0) {
                    if arguments.contains("--session-demo") {
                        Text("SYNTHETIC SESSION / 合成内存存储；无 Keychain 或真实账号")
                            .font(.caption).padding(8)
                    }
                    if messageDemoFailed { Text("Synthetic message setup failed / 合成消息准备失败") }
                    ShellView(state: state, accountHost: accountHost, messageHost: messageHost)
                }
            }
        }
    }
}

private struct Gallery: View {
    @State private var phase = ShellPageState.notConnected
    @State private var language = ShellLanguage.english
    @State private var tab = ShellTab.assistant
    @State private var largeText = false
    @State private var longText = false
    @State private var sample: ShellState?

    var body: some View {
        NavigationStack {
            Form {
                Text("SYNTHETIC UI SAMPLES / 合成界面样例 — no service or saved records.")
                Picker("Language / 语言", selection: $language) {
                    Text("English").tag(ShellLanguage.english)
                    Text("简体中文").tag(ShellLanguage.chinese)
                }
                Picker("Tab / 标签", selection: $tab) {
                    ForEach(ShellTab.allCases, id: \.self) { Text($0.title(language)).tag($0) }
                }
                Picker("Presentation state / 展示状态", selection: $phase) {
                    ForEach(ShellPageState.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                }
                Toggle("Accessibility text / 无障碍大字体", isOn: $largeText)
                Toggle("Long native body / 原生长正文", isOn: $longText)
                Button("Open sample / 打开样例") {
                    // Isolated suite; never reads production language preference.
                    guard let defaults = UserDefaults(suiteName: "cj006.demo.gallery") else { return }
                    let state = ShellState(preferences: defaults)
                    state.selectLanguage(language)
                    state.selectedTab = tab
                    state.apply(ShellPresentation(assistantBody: longText ? Self.longBody : nil,
                                                  assistant: phase, trips: phase, memory: phase),
                                for: state.generation)
                    sample = state
                }
            }.navigationTitle("CJ006 samples")
        }
        .fullScreenCover(isPresented: Binding(get: { sample != nil }, set: { if !$0 { sample = nil } })) {
            if let sample {
                VStack(spacing: 0) {
                    Button("Close synthetic sample / 关闭合成样例") { self.sample = nil }
                        .font(.caption).dynamicTypeSize(.large).padding(8)
                    ShellView(state: sample)
                }.dynamicTypeSize(largeText ? .accessibility3 : .large)
            }
        }
    }

    private static let longBody = "SYNTHETIC / 合成展示；不是旅行建议。\n\n" +
        (1...40).map { "\($0). Native text selection and scrolling. 中英混排正文，用于检查悬浮控件、安全区、键盘与长文滚动。" }.joined(separator: "\n\n")
}

// Demo-only memory implementation. Never constructs KeychainSessionStore or calls Security APIs.
@MainActor private final class DemoSessionStore: SessionPersistence {
    private var cleared = false
    private let failClear: Bool
    init(failClear: Bool) { self.failClear = failClear }
    func load() throws -> SessionMaterial? {
        if cleared { throw SessionFailure.restorationBlocked }
        return try SessionMaterial(trustedSDKBytes: Data([1, 2, 3]))
    }
    func save(_ material: SessionMaterial) throws { throw SessionFailure.storageUnavailable }
    func clearAndBlock() throws {
        if failClear { throw SessionFailure.storageUnavailable }
        cleared = true
    }
}

@MainActor private final class DemoMessageStore: SecureMessageStorage {
    private var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}

@MainActor private func makeMessageDemo(_ shell: ShellState, args: [String]) throws -> AssistantMessageHost {
    let recovery = MessageRecovery(storage: DemoMessageStore())
    let scope = try StorageScope(environment: "synthetic-ui", account: "synthetic-account")
    let lease = try recovery.activate(scope)
    let id = "synthetic-original-1"
    try recovery.saveDraft(Data("Synthetic draft / 合成草稿".utf8), conversationID: "synthetic-conversation", lease: lease)
    try recovery.stage(messageID: id, originalUTF8: Data("Synthetic original bytes, not a wire request".utf8), lease: lease)
    if !args.contains("--message-staged") {
        let original = try recovery.beginSubmission(messageID: id, lease: lease)
        try recovery.observeUnknown(original.operation) // only a memory transition; no transport
    }
    let host = AssistantMessageHost(shell: shell)
    let bound = host.bind(AssistantMessageBinding(recovery: recovery, scope: scope, lease: lease,
        generation: shell.generation,
        synthetic: true, isCurrent: { true }, invalidateResources: {}, queryOriginal: { id, lease in
            let operation = try recovery.beginQuery(messageID: id, lease: lease)
            if args.contains("--message-unknown") {
                try recovery.observeUnknown(operation)
                throw RecoveryError.persistenceUnknown
            } else if args.contains("--message-receipt") {
                guard let record = try recovery.action(messageID: id, lease: lease) else { throw RecoveryError.invalidInput }
                try recovery.observeReceipt(operation, messageID: id, inputSHA256: record.inputSHA256,
                    receipt: Data("synthetic receipt, not service output".utf8))
            } else { try recovery.observeNotObserved(operation) }
        }))
    guard bound else { throw RecoveryError.inactive }
    return host
}
