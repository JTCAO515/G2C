#if os(iOS)
import SwiftUI
import CJMessageClient

struct MessageRecoveryStatus: View {
    let host: AssistantMessageHost
    let language: ShellLanguage
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if host.isSynthetic {
                Text(language.text("Synthetic local state — not a service reply", "合成本地状态——不是服务回复")).font(.caption)
            }
            Text(status).accessibilityIdentifier("assistant.recoveryStatus")
            if host.isConfigured {
                Button(language.text("Save draft locally", "保存本地草稿")) { host.saveDraft() }
                    .disabled(!host.canSaveDraft)
                if host.draftStored {
                    Text(language.text("Draft stored locally; this does not establish delivery status.", "草稿已交给配置的本地存储，不能据此判断投递状态。"))
                }
                Button(language.text("Check original action", "查询原操作")) { host.queryOriginal() }
                    .disabled(!host.canQuery)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    private var status: String {
        switch host.activity {
        case .querying: return language.text("Checking the original action only…", "仅查询原操作中…")
        case .unknown: return language.text("The result is unknown. Keep the original action; do not resend.", "结果未知，请保留原操作，不要重新发送。")
        case .storageBlocked: return language.text("Local recovery is blocked. No empty-history or send-success claim is available.", "本地恢复已阻断，不能认定历史为空或发送成功。")
        case .unavailable, .invalidated: return language.text("Message recovery is not connected. Sending is unavailable.", "消息恢复尚未接入，发送不可用。")
        case .ready: break
        }
        guard let record = host.visibleRecord else {
            return language.text("No bound original action is available. Sending is unavailable.", "暂无绑定的原操作，发送不可用。")
        }
        switch record.phase {
        case .staged: return language.text("Staged locally only. Sending is unavailable.", "仅在本地暂存，发送不可用。")
        case .queryRequired: return language.text("Original result needs checking. Query only; do not resend.", "原结果待核对，只能查询，请勿重发。")
        case .notObserved: return language.text("No receipt was observed. This does not prove the message was unsent or safe to resend.", "未观察到回执。这不证明消息未发送，也不允许重新发送。")
        case .accepted: return language.text("The original action has a confirmed receipt. This is not an assistant reply.", "原操作已有确认回执。这不是助手回复。")
        }
    }
}
#endif
