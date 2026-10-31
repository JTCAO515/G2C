#if os(iOS)
import SwiftUI
import CJRunClient

struct TripDiscussionChoiceView:View {
    let host:AssistantMessageHost
    let language:ShellLanguage
    let openTrips:()->Void
    var body:some View {
        let newChat=host.captureNewConversationIntent()
        VStack(alignment:.leading,spacing:12) {
            RunReadableText(text:language.text("Trip discussion selection","行程讨论选区"),style:.headline)
            choiceContent
            RunReadableText(text:language.text("This choice applies to your next discussion message.","此选择用于下一条讨论消息。"),style:.caption)
            RunReadableText(text:language.text("It is not a binding receipt or permission to change a Trip.","不是绑定回执，也不授予修改行程的权限。"),style:.caption)
            Button {
                if let newChat { host.performConversationIntent(newChat) }
            } label: {
                RunReadableText(text:language.text("Start a new discussion chat","开始新的讨论聊天"))
                    .frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle())
            }.buttonStyle(ShellReadableButtonStyle()).disabled(newChat==nil).accessibilityIdentifier("assistant.chat.new")
            if host.hasUnassignedDraft {
                RunReadableText(text:language.text("Select a conversation for the current draft, or clear it before starting another chat.","请先为当前草稿选择会话，或清空后再新建聊天。"),style:.caption)
            }
            conversationStatus
            if let refusal=host.discussionRefusal {
                RunReadableText(text:language.text("This discussion request was refused or is unavailable. Reconcile the original message result; acceptance may still be unknown. The App did not disable existing memory.","本次讨论请求被拒绝或不可用。请核对原消息结果，是否已接受仍可能未知。App未关闭已有记忆。")+"\nHTTP "+String(refusal.status)+" · "+refusal.code)
                    .accessibilityIdentifier("assistant.trip.refusal")
            }
            button("assistant.trip.open",language.text("Choose a formal Trip, day or item","选择正式行程、日期或条目"),action:openTrips)
            button("assistant.trip.none",language.text("Discuss without a Trip selection","明确不绑定行程进行讨论")) { _=host.selectUnboundDiscussion() }
            RunReadableText(text:language.text("Discussion only.","仅支持讨论。"),style:.caption)
            RunReadableText(text:language.text("This profile cannot upgrade an account that already has MEMORY configured.","此模式不能升级已有 MEMORY 配置的账号。"),style:.caption)
            RunReadableText(text:language.text("Memory is never silently disabled.","不会静默关闭记忆。"),style:.caption)
        }.accessibilityElement(children:.contain).accessibilityIdentifier("assistant.trip.context")
    }
    @ViewBuilder private var conversationStatus:some View {
        switch host.conversationState {
        case .idle:EmptyView()
        case .working:
            RunReadableText(text:language.text("Checking the original chat request…","正在核对原聊天请求…")).accessibilityIdentifier("assistant.chat.status")
        case .unknown:
            RunReadableText(text:language.text("Original chat result unknown.","原聊天结果未知。")).accessibilityIdentifier("assistant.chat.status")
            RunReadableText(text:language.text("Check its original ID in local recovery; do not create another one.","请在本地恢复中核对原ID，不要另建聊天。"),style:.caption)
        case .available:
            RunReadableText(text:language.text("Original chat is available.","原聊天已可读取。")).accessibilityIdentifier("assistant.chat.status")
        case .rejected(_,let status):
            RunReadableText(text:language.text("Chat request unavailable. Check the original ID.","聊天请求不可用，请核对原ID。")+" · HTTP "+String(status)).accessibilityIdentifier("assistant.chat.status")
        }
    }
    private func button(_ id:String,_ title:String,action:@escaping()->Void) -> some View {
        Button(action:action) { RunReadableText(text:title).frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle()) }
            .buttonStyle(ShellReadableButtonStyle()).disabled(host.isBusy).accessibilityIdentifier(id)
    }
    @ViewBuilder private var choiceContent:some View {
        switch host.tripDiscussionChoice {
        case .unselected:
            RunReadableText(text:language.text("Choose a Trip or explicitly discuss without one.","请选择行程或明确不绑定。"))
                .accessibilityIdentifier("assistant.trip.choice")
            RunReadableText(text:language.text("No latest Trip is selected automatically.","不会自动选择最近行程。"))
                .accessibilityIdentifier("assistant.trip.noAutomatic")
        case .none:
            RunReadableText(text:language.text("Explicitly no formal Trip selected.","已明确不绑定正式行程。"))
                .accessibilityIdentifier("assistant.trip.choice")
            RunReadableText(text:language.text("Ambiguous references require clarification.","模糊指代需先澄清。"))
                .accessibilityIdentifier("assistant.trip.clarification")
        case .unavailable:
            RunReadableText(text:language.text("The original selection is unavailable.","原选择已不可用。"))
                .accessibilityIdentifier("assistant.trip.choice")
            RunReadableText(text:language.text("Read and choose it again; no replacement is inferred.","请重新读取并选择；不会推断替代行程。"))
        case .trip(let title,let choice):
            RunSelectableText(text:title).accessibilityIdentifier("assistant.trip.choice")
            RunSelectableText(text:choice.id).accessibilityIdentifier("assistant.trip.id")
            RunReadableText(text:language.text("Read version ","读取版本 ")+String(choice.expectedVersion)).accessibilityIdentifier("assistant.trip.version")
            if let day=choice.day {
                RunReadableText(text:language.text("Day: ","日期：")+day.date+" · "+day.timezone).accessibilityIdentifier("assistant.trip.day")
            }
            if let item=choice.itemID {
                RunSelectableText(text:language.text("Item: ","条目：")+item).accessibilityIdentifier("assistant.trip.item")
            }
        }
    }
}
#endif
