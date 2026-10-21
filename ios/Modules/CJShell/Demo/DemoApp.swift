import SwiftUI

// Compiled together with module sources by scripts/build-demo.sh, not a product target.
@main struct CJShellDemo: App {
    @State private var state = ShellState()
    private let arguments = ProcessInfo.processInfo.arguments

    var body: some Scene {
        WindowGroup {
            if arguments.contains("--gallery") {
                Gallery()
            } else {
                ShellView(state: state)
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
                        .padding(8)
                    ShellView(state: sample)
                }.dynamicTypeSize(largeText ? .accessibility3 : .large)
            }
        }
    }

    private static let longBody = "SYNTHETIC / 合成展示；不是旅行建议。\n\n" +
        (1...40).map { "\($0). Native text selection and scrolling. 中英混排正文，用于检查悬浮控件、安全区、键盘与长文滚动。" }.joined(separator: "\n\n")
}
