#if os(iOS)
import SwiftUI
import CJMessageClient

struct MessageRecoveryStatus: View {
    let host: AssistantMessageHost
    let language: ShellLanguage
    @State private var pendingResubmission: MessageResubmissionContext?
    var body: some View {
        let resubmission = host.captureResubmission()
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
                    .accessibilityIdentifier("assistant.queryOriginal")
                if let resubmission {
                    Button(language.text("Resubmit original", "原样重新提交")) {
                        if resubmission.requiresConfirmation { pendingResubmission = resubmission }
                        else { host.resubmitOriginal(resubmission, confirmed: false) }
                    }.accessibilityIdentifier("assistant.resubmit")
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
        .confirmationDialog(language.text("Submit the original message again?", "重新提交原消息？"),
            isPresented: Binding(get: { pendingResubmission != nil }, set: { if !$0 { pendingResubmission = nil } }),
            presenting: pendingResubmission) { context in
                Button(language.text("Submit saved original", "提交已保存的原消息")) {
                    host.resubmitOriginal(context, confirmed: true); pendingResubmission = nil
                }.accessibilityIdentifier("assistant.confirmResubmit")
                Button(language.text("Cancel", "取消"), role: .cancel) { pendingResubmission = nil }
            } message: { _ in
                Text(language.text("This submits the saved original message unchanged.", "将原样重新提交已保存的原消息。"))
            }
        .onChange(of: host.isConfigured) { _, configured in if !configured { pendingResubmission = nil } }
    }
    private var status: String {
        switch host.activity {
        case .preparing: return language.text("Checking the conversation…", "正在核对会话…")
        case .sending: return language.text("Sending the original message…", "正在发送原消息…")
        case .inputRejected: return language.text("This message cannot be prepared. Check its length and try again.", "此消息无法提交，请检查内容长度后重试。")
        case .querying: return language.text("Checking the original action only…", "仅查询原操作中…")
        case .unknown: return language.text("The result is unknown. Keep the original action; do not resend.", "结果未知，请保留原操作，不要重新发送。")
        case .storageBlocked: return language.text("Local recovery is blocked. No empty-history or send-success claim is available.", "本地恢复已阻断，不能认定历史为空或发送成功。")
        case .unavailable, .invalidated: return language.text("Message recovery is not connected. Sending is unavailable.", "消息恢复尚未接入，发送不可用。")
        case .ready: break
        }
        guard let record = host.visibleRecord else {
            if host.supportsSending {
                if host.selectedConversation == nil { return language.text("Choose a conversation from history.", "请从历史中选择会话。") }
                return host.canStartMessage ? language.text("Ready for a message.", "可以编辑并发送消息。")
                    : language.text("Conversation unavailable. Refresh history to continue.", "会话暂不可用，请重新读取历史。")
            }
            return language.text("No bound original action is available. Sending is unavailable.", "暂无绑定的原操作，发送不可用。")
        }
        switch record.phase {
        case .staged: return language.text("Staged locally only. Sending is unavailable.", "仅在本地暂存，发送不可用。")
        case .queryRequired: return language.text("Original result needs checking. Query only; do not resend.", "原结果待核对，只能查询，请勿重发。")
        case .notObserved:
            if host.canResubmit { return language.text("The original request can still be accepted. You may submit it unchanged.", "原请求仍可接收，可以原样重新提交。") }
            return language.text("No receipt was observed. This does not prove the message was unsent or safe to resend.", "未观察到回执。这不证明消息未发送，也不允许重新发送。")
        case .accepted: return language.text("The original action has a confirmed receipt. This is not an assistant reply.", "原操作已有确认回执。这不是助手回复。")
        case .notAccepted: return language.text("The original request will no longer be accepted. Refresh this conversation’s history before starting a new message.", "原请求不会再被接受。请先刷新此会话的历史，再决定是否发送新消息。")
        case .integrityError: return language.text("The original message does not match its receipt. Sending is stopped for this conversation.", "原消息与回执不一致，已停止此会话的发送。")
        case .resyncRequired: return language.text("The conversation state needs resynchronization. Sending is stopped.", "会话状态需要重新同步，已停止发送。")
        }
    }
}
#endif
