import SwiftUI
#if canImport(Textual)
import Textual
#endif

public struct ProbeView: View {
    @Environment(\.dynamicTypeSize) private var systemType
    @State private var streamMetrics: String?
    @State private var draft = ""
    @State private var shown = 1
    @State private var partial = ""
    @State private var streaming = false
    @State private var following = true
    @State private var useTextual = true
    @State private var largeType = false
    @State private var notice: String?
    @FocusState private var inputFocused: Bool

    public init() {
        // Deterministic local probe modes; no product runtime configuration.
        let args = ProcessInfo.processInfo.arguments
        _largeType = State(initialValue: args.contains("--large-type"))
        _streaming = State(initialValue: args.contains("--stream"))
        _useTextual = State(initialValue: !args.contains("--plain"))
    }

    public var body: some View {
        TabView {
            assistant.tabItem { Label("助手 Assistant", systemImage: "bubble.left") }
            Text("行程 Trips · 样例无正式数据 No product data").tabItem { Label("行程 Trips", systemImage: "map") }
            Text("插件尚未开放 Plugins are not available").tabItem { Label("插件 Plugins", systemImage: "puzzlepiece") }
            Text("记忆 Memory · 账号登录未运行 Auth UNRUN").tabItem { Label("记忆 Memory", systemImage: "brain") }
        }
        .dynamicTypeSize(largeType ? .accessibility3 : systemType)
        .task {
            if ProcessInfo.processInfo.arguments.contains("--keyboard") {
                do { try await Task.sleep(for: .milliseconds(300)) }
                catch { return }
                inputFocused = true
            }
        }
        .environment(\.openURL, OpenURLAction { _ in
            notice = "链接未打开 · No external link opened"
            return .handled
        })
        .alert("本地样例 Local probe", isPresented: Binding(get: { notice != nil }, set: { if !$0 { notice = nil } })) {
            Button("好 OK") { notice = nil }
        } message: { Text(notice ?? "") }
    }

    private var assistant: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 22) {
                    Text("CJ-004 · 合成渲染样例 Synthetic rendering probe")
                        .font(.caption).foregroundStyle(.secondary)
                    VStack(alignment: .leading) {
                        #if canImport(Textual)
                        Toggle("Textual", isOn: $useTextual)
                        #else
                        Text("原生纯文本 Native plain text").font(.caption)
                        #endif
                        Toggle("大字 Large", isOn: $largeType)
                    }
                    Button(streaming ? "停止 Stop" : "增量文本 Stream fixture") {
                        if !streaming { partial = "" }
                        streaming.toggle()
                    }
                    ForEach(0..<shown, id: \.self) { index in
                        VStack(alignment: .leading, spacing: 8) {
                            Text("样例段落 Fixture \(index + 1)").font(.caption).foregroundStyle(.secondary)
                            #if canImport(Textual)
                            if useTextual {
                                StructuredText(markdown: index == 0 ? Self.sample : partial)
                                    .textual.textSelection(.enabled)
                                    .textual.imageAttachmentLoader(BlockedAttachments())
                                    .textual.emojiAttachmentLoader(BlockedAttachments())
                            } else {
                                Text(index == 0 ? Self.sample : partial).textSelection(.enabled)
                            }
                            #else
                            Text(index == 0 ? Self.sample : partial).textSelection(.enabled)
                            #endif
                            if index == 1, let streamMetrics {
                                Text(streamMetrics).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .id(index)
                    }
                    Color.clear.frame(height: 1).id("end")
                }
                .padding(.horizontal, 18)
                .padding(.top, largeType ? 120 : 72)
                .padding(.bottom, 12)
            }
            .clipped() // Keep scrolling content out of the system status-bar safe area.
            .scrollDismissesKeyboard(.interactively)
            .simultaneousGesture(DragGesture().onChanged { _ in following = false })
            .overlay(alignment: .top) { floatingControls }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                VStack(spacing: 8) {
                    if streaming { Button("停止 Stop") { streaming = false } }
                    if !following {
                        Button("回到底部 Follow latest") {
                            following = true
                            proxy.scrollTo("end", anchor: .bottom)
                        }
                    }
                    composer
                }
                .padding(10)
                .background(.regularMaterial)
            }
            .onChange(of: partial) { _, _ in
                if following { proxy.scrollTo("end", anchor: .bottom) }
            }
            .task(id: streaming) {
                guard streaming else { return }
                shown = 2
                streamMetrics = nil
                let started = ContinuousClock.now
                var updates = 0
                defer { streamMetrics = "Local insertion: \(partial.count) characters / \(updates) updates / \(started.duration(to: .now)). Not frame latency." }
                let characters = Array(String(repeating: Self.sample + "\n\n", count: 6))
                var cursor = 0
                while cursor < characters.count {
                    do { try await Task.sleep(for: .milliseconds(100)) }
                    catch { return }
                    guard !Task.isCancelled else { return }
                    let end = min(cursor + 80, characters.count)
                    partial += String(characters[cursor..<end])
                    cursor = end
                    updates += 1
                }
                streaming = false
            }
        }
    }

    private var floatingControls: some View {
        HStack(alignment: .top) {
            Button { notice = "历史入口占位 History placeholder" } label: {
                VStack(spacing: 4) {
                    Capsule().frame(width: 18, height: 2)
                    Capsule().frame(width: 18, height: 2)
                }.frame(minWidth: 44, minHeight: 44)
            }.accessibilityLabel("历史 History")
                .background(.thinMaterial, in: Capsule())
            Spacer(minLength: 8)
            Button { notice = "角色入口占位 Character placeholder" } label: {
                Label("Muse", systemImage: "person.crop.circle").padding(12)
            }.background(.thinMaterial, in: Capsule())
            Spacer(minLength: 8)
            Button { notice = "礼物尚未开放 Gifts unavailable" } label: {
                Image(systemName: "gift").frame(minWidth: 44, minHeight: 44)
            }.accessibilityLabel("礼物 Gifts")
                .background(.thinMaterial, in: Capsule())
        }
        .padding(.horizontal, 12).padding(.top, 6)
        // Only individual controls hit-test; no full-width overlay background.
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 8) {
            Button { notice = "附件尚未开放 Attachments unavailable" } label: {
                Image(systemName: "plus").frame(minWidth: 44, minHeight: 44)
            }.accessibilityLabel("添加 Add")
            TextField("开始聊天 Start chatting", text: $draft, axis: .vertical)
                .lineLimit(1...4).focused($inputFocused)
                .accessibilityIdentifier("composer")
            Button {
                if draft.isEmpty { notice = "语音尚未开放 Voice unavailable" }
                else { notice = "仅本地样例，未发送 Local only; nothing sent"; inputFocused = false }
            } label: {
                Image(systemName: draft.isEmpty ? "mic" : "arrow.up")
                    .frame(minWidth: 44, minHeight: 44)
            }.accessibilityLabel(draft.isEmpty ? "语音 Voice" : "发送 Send")
        }
        .padding(4).background(.background, in: RoundedRectangle(cornerRadius: 24))
    }

    private static let sample = """
    ## English with 中文地点
    This is a **synthetic layout fixture**, not travel advice. 北京、上海 and 广州 are mixed into a long English paragraph to test wrapping and selection. 这是一段用于排版与选择的中文测试文本，并不提供时间、价格或行程承诺。

    - First list item includes 中文与 English.
    - Second item wraps across multiple lines to exercise large text and narrow widths. 中英文同等呈现。

    1. Select a sentence / 选择一句文字。
    2. Tap [inert example link](https://example.invalid); the app intercepts it and never opens a browser.

    ![blocked remote image](https://example.invalid/tracker.png)

    <script>alert("never executed")</script>

    > Long responses must remain readable beneath the floating controls. 长回答必须能滚动到无遮挡区域。
    """
}
