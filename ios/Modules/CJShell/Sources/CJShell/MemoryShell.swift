#if os(iOS)
import SwiftUI
import CJMemoryClient

struct MemoryShell: View {
    @Bindable var state: ShellState
    let accountHost: AccountHost
    let memoryHost: MemoryContainerHost
    let feedbackHost: FeedbackContainerHost
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
                    NavigationLink(language.text("Privacy facts draft", "隐私事实草稿"), value: MemoryRoute.privacy)
                    NavigationLink(language.text("Support", "支持"), value: MemoryRoute.support)
                    NavigationLink(language.text("Feedback", "问题反馈"), value: MemoryRoute.feedback(feedbackHost.captureEntry()))
                }
                LaunchInformationSection(language: language)
            }
            .navigationTitle(ShellTab.memory.title(language))
            .navigationDestination(for: MemoryRoute.self) { route in destination(route) }
        }
    }

    @ViewBuilder private func destination(_ route: MemoryRoute) -> some View {
        switch route {
        case .language:
            Form {
                Picker(language.text("Language", "语言"), selection: Binding(get: { state.language }, set: { state.selectLanguage($0) })) {
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
        case .feedback(let entry):
            FeedbackContainerView(host: feedbackHost, entry: entry, language: language)
        case .account:
            AccountView(host: accountHost, shell: state)
        case .help:
            HelpView(language: language)
        case .privacy:
            PrivacyFactsDraftView(language: language)
        case .support:
            SupportInformationView(language: language)
        }
    }

}

#Preview("English — not connected") {
    ShellView(state: ShellState())
}
#endif
