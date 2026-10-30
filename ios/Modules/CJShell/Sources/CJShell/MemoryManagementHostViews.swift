#if os(iOS)
import SwiftUI
import CJMemoryClient
import CJRunClient

/// Compose the accepted client's UI without creating selections or granting permissions.
struct MemoryManagementHostControls: View {
    let host: MemoryContainerHost
    let language: ShellLanguage
    var body: some View {
        if let presentation = host.managementPresentation, let selection = presentation.selection {
            MemoryManagementControls(client: presentation.client, selection: selection, binding: presentation.binding, language: language == .english ? .english : .chinese)
        } else {
            Text(language.text("Read the current memory detail before requesting an action.", "请先读取当前记忆详情，再请求管理操作。"))
        }
    }
}

struct MemoryManagementHostRecovery: View {
    let host: MemoryContainerHost
    let language: ShellLanguage
    var body: some View {
        let action = host.captureAction()
        VStack(alignment: .leading, spacing: 10) {
            RunReadableText(text: language.text("Previous memory actions", "此前的记忆操作"))
            RunReadableText(text: language.text("Recover by querying the stored original action only. A receipt does not establish current eligibility or permit resending.", "恢复时仅查询已保存的原操作。历史回执不代表当前资格，也不允许重新发送。"), style: .caption)
            MemoryActionButton(title: language.text("Read original memory actions", "读取原记忆操作"), enabled: action != nil) {
                host.loadManagementPending(context: action)
            }.accessibilityIdentifier("memory.manage.loadOriginals")
            switch host.managementPending {
            case .unconfigured:
                Text(language.text("Original memory actions have not been loaded.", "尚未读取原记忆操作。"))
            case .loading: ProgressView()
            case .failed:
                Text(language.text("Original actions could not be read. Recovery is unavailable.", "无法读取原操作，暂不能恢复查询。"))
            case .loaded(let records):
                if records.isEmpty { Text(language.text("No original memory actions found.", "未发现原记忆操作。")) }
                if let presentation = host.managementPresentation {
                    ForEach(records, id: \.originalUTF8) { record in
                        MemoryManagementRecoveryView(client: presentation.client, pending: record, binding: presentation.binding, language: language == .english ? .english : .chinese)
                    }
                }
            }
        }
    }
}
#endif
