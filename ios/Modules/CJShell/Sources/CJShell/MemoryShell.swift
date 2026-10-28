#if os(iOS)
import SwiftUI
import CJMemoryClient

struct MemoryShell: View {
    @Bindable var state: ShellState
    let accountHost: AccountHost
    let memoryHost: MemoryContainerHost
    let feedbackHost: FeedbackContainerHost
    let developmentAccountHost: DevelopmentAccountHost?
    private var language: ShellLanguage { state.language }

    var body: some View {
        NavigationStack(path: $state.memoryPath) {
            List {
                Section {
                    MemoryContainerGroups(host: memoryHost, state: state)
                    route(language.text("Add memory", "新增记忆"), to: .manualMemory, identifier: "memory.add")
                } header: { ShellSectionHeading(title: language.text("Your memories", "你的记忆")) }
                Section {
                    VStack(alignment: .leading, spacing: 0) {
                        ShellSectionHeading(title: language.text("Me", "我的")).padding(.vertical, 8)
                        route(language.text("Account", "账号"), to: .account, identifier: "memory.account")
                        Divider()
                        route(language.text("Language", "语言"), to: .language, identifier: "memory.language")
                        ShellSectionHeading(title: language.text("Information", "说明")).padding(.top, 16).padding(.bottom, 8)
                        route(language.text("Help", "帮助"), to: .help, identifier: "memory.help")
                        Divider()
                        route(language.text("Privacy facts draft", "隐私事实草稿"), to: .privacy, identifier: "memory.privacy")
                        Divider()
                        route(language.text("Support", "支持"), to: .support, identifier: "memory.support")
                        Divider()
                        route(language.text("Feedback", "问题反馈"), to: .feedback(feedbackHost.captureEntry()), identifier: "memory.feedback")
                    }
                }
            }
            .navigationTitle(ShellTab.memory.title(language))
            .navigationDestination(for: MemoryRoute.self) { route in destination(route) }
        }
    }

    private func route(_ title: String, to destination: MemoryRoute, identifier: String) -> some View {
        Button { state.memoryPath.append(destination) } label: {
            HStack {
                Text(title).font(.body).foregroundStyle(Color(uiColor: .label))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(identifier + ".label")
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.caption.weight(.semibold))
                    .foregroundStyle(Color(uiColor: .label)).accessibilityHidden(true)
            }.frame(minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier(identifier)
    }

    @ViewBuilder private func destination(_ route: MemoryRoute) -> some View {
        switch route {
        case .language:
            Form {
                Picker(selection: Binding(get: { state.language }, set: { state.selectLanguage($0) })) {
                    Text("English").tag(ShellLanguage.english)
                    Text("简体中文").tag(ShellLanguage.chinese)
                } label: { ShellSectionHeading(title: language.text("Language", "语言")) }
                .pickerStyle(.inline)
                if state.invalidStoredLanguage {
                    Text(language.text("The saved language is unsupported. English is shown until you select a language.", "已保存的语言暂不支持。选择语言前将显示英文。"))
                }
                Text(language.text("Saved on this device. Switching language keeps your current navigation and unsent draft.", "保存在此设备。\n切换语言会保留当前导航和未发送草稿。"))
                    .font(.body.leading(.loose)).fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 4)
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
            if let developmentAccountHost {
                DevelopmentAccountView(host: developmentAccountHost, language: language)
            } else {
                AccountView(host: accountHost, shell: state)
            }
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
