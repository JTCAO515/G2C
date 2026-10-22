#if os(iOS)
import SwiftUI
import CJMemoryClient

struct MemoryShell: View {
    @Bindable var state: ShellState
    let accountHost: AccountHost
    let memoryHost: MemoryContainerHost
    private var language: ShellLanguage { state.language }

    var body: some View {
        NavigationStack(path: $state.memoryPath) {
            List {
                Section(language.text("Your memories", "你的记忆")) {
                    MemoryContainerGroups(host: memoryHost, state: state)
                    NavigationLink(language.text("Add memory", "新增记忆"), value: MemoryRoute.manualMemory)
                }
                Section(language.text("Me", "我的")) {
                    NavigationLink(language.text("Account", "账号"), value: MemoryRoute.account)
                    NavigationLink(language.text("Language", "语言"), value: MemoryRoute.language)
                }
                Section(language.text("Information", "说明")) {
                    NavigationLink(language.text("Help", "帮助"), value: MemoryRoute.help)
                    NavigationLink(language.text("Privacy", "隐私"), value: MemoryRoute.privacy)
                    NavigationLink(language.text("Support", "支持"), value: MemoryRoute.support)
                }
            }
            .navigationTitle(ShellTab.memory.title(language))
            .navigationDestination(for: MemoryRoute.self) { route in destination(route) }
        }
    }

    @ViewBuilder private func destination(_ route: MemoryRoute) -> some View {
        switch route {
        case .language:
            Form {
                Picker(language.text("Language", "语言"), selection: Binding(get: { state.language }, set: state.selectLanguage)) {
                    Text("English").tag(ShellLanguage.english)
                    Text("简体中文").tag(ShellLanguage.chinese)
                }.pickerStyle(.inline)
                if state.invalidStoredLanguage {
                    Text(language.text("The saved language is unsupported. English is shown until you select a language.", "已保存的语言暂不支持。选择语言前将显示英文。"))
                }
                Text(language.text("Saved on this device. Switching language keeps your current navigation and unsent draft.", "保存在此设备。切换语言会保留当前导航和未发送草稿。"))
            }.navigationTitle(language.text("Language", "语言"))
        case .group(let group):
            List {
                ShellStatusView(state: state.memoryState, language: language)
                Text(language.text("Memory details, sources, dates and editing controls will appear when the memory service is connected. No changes can be saved here yet.", "记忆服务接入后提供详情、来源、时间和编辑操作。目前无法在此保存更改。"))
            }.navigationTitle(group.title(language))
        case .memoryItems:
            MemoryContainerItems(host: memoryHost, state: state)
        case .memoryDetail:
            MemoryContainerDetail(host: memoryHost, language: language)
        case .manualMemory:
            MemoryContainerManual(host: memoryHost, language: language)
        case .account:
            AccountView(host: accountHost, shell: state)
        case .help:
            information(language.text("Help", "帮助"), language.text("Use the four tabs to open Assistant, Trips, Plugins and Memory. Account and language settings are in Memory. Memory can show available groups, records and their sources when connected. New memory saving is not available yet. Translation tools are planned for a later version.", "通过四个标签进入助手、行程、插件和记忆。账号和语言设置位于记忆内。接入后可在记忆中查看分组、条目及来源，目前暂不支持保存新记忆。翻译工具计划在后续版本提供。"))
        case .privacy:
            information(language.text("Privacy", "隐私"), language.text("Your language preference is saved on this device. When connected, Memory reads records and queries previous save results. Private memory views are cleared when the account changes or the app leaves the foreground. This does not delete stored records. Retention and deletion terms are not available here yet. This is a description of the current interface, not a complete product privacy policy.", "语言偏好保存在此设备。接入后，记忆页面可以读取条目并查询此前的保存结果。账号变化或应用离开前台时会清空私密记忆页面，但不会删除已存储的记录。此处尚未提供数据保留与删除条款。这是当前界面的说明，不是完整产品隐私政策。"))
        case .support:
            information(language.text("Support", "支持"), language.text("A support contact has not been confirmed. This screen cannot send support requests. Help describes the currently available features.", "支持联系方式尚未确认，此页面无法发送支持请求。帮助页面说明当前可用功能。"))
        }
    }

    private func information(_ title: String, _ body: String) -> some View {
        ScrollView { Text(body).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading).padding() }
            .navigationTitle(title)
    }
}

#Preview("English — not connected") {
    ShellView(state: ShellState())
}
#endif
