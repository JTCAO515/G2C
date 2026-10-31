#if os(iOS)
import SwiftUI
import CJMessageHTTP
import CJRunClient

struct ScopedMessageChoiceView:View {
    let host:AssistantMessageHost
    let language:ShellLanguage
    let openTrips:()->Void
    let openNeeds:()->Void
    @State private var selectionFailed=false
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            RunReadableText(text:language.text("Original Trip and scoped request","原行程与局部请求"),style:.headline)
            if let display=host.scopedPresentation {
                let discussion=host.captureScopedIntent(.none,for:display)
                let proposed=host.captureScopedIntent(.proposeScopedEdit,for:display)
                let needs=host.captureScopedNeedsChoice(for:display)
                let newChat=host.captureNewConversationIntent(for:display)
                if let trip=display.trip,let title=display.title {
                    RunSelectableText(text:title).accessibilityIdentifier("assistant.edit.trip.title")
                    RunSelectableText(text:trip.id).accessibilityLabel(language.text("Trip identifier","行程标识"))
                        .accessibilityValue(trip.id).accessibilityIdentifier("assistant.edit.trip.id")
                    RunReadableText(text:language.text("Read version ","读取版本 ")+String(trip.expectedVersion)).accessibilityIdentifier("assistant.edit.trip.version")
                    if let day=trip.day {
                        RunReadableText(text:day.date+" · "+day.timezone).accessibilityIdentifier("assistant.edit.trip.day")
                    }
                    if !trip.itemIDs.isEmpty {
                        RunReadableText(text:language.text("Original item: ","原条目：")+trip.itemIDs.joined(separator:", ")).accessibilityIdentifier("assistant.edit.trip.item")
                    }
                } else {
                    RunReadableText(text:language.text("Choose a formal Trip, date or item. No latest Trip is selected automatically.","请明确选择正式行程、日期或条目，不会默认选择最近行程。")).accessibilityIdentifier("assistant.edit.trip.missing")
                }
                command("assistant.edit.intent.discuss",language.text("Discussion only","仅讨论"),value:discussion)
                command("assistant.edit.intent.propose",language.text("Request a scoped candidate","请求局部候选"),value:proposed)
                RunReadableText(text:display.intent == .proposeScopedEdit ? language.text("Selected: request a scoped candidate","已选择：请求局部候选") : language.text("Selected: discussion only","已选择：仅讨论"))
                    .accessibilityIdentifier("assistant.edit.intent")
                if let chosen=display.needs {
                    RunReadableText(text:language.text("Chosen saved needs: ","已选已保存需求：")+chosen.id+" · "+String(chosen.expectedVersion)).accessibilityIdentifier("assistant.edit.needs")
                } else {
                    RunReadableText(text:language.text("For a candidate, explicitly choose a saved needs revision.","请求候选前，请明确选择已保存的需求版本。")).accessibilityIdentifier("assistant.edit.needs.missing")
                }
                button("assistant.edit.needs.open",language.text("Read saved journey needs","读取已保存旅行需求"),disabled:host.isBusy,action:openNeeds)
                let label=needs?.needsSelection.map { language.text("Use read needs ","使用已读需求 ")+$0.id+" · "+String($0.expectedVersion) }
                command("assistant.edit.needs.choose",label ?? language.text("Read current saved needs first","请先读取当前已保存需求"),value:needs)
                button("assistant.chat.new",language.text("Start a new chat for this Trip","新建此行程的聊天"),disabled:newChat==nil) {
                    if let newChat { host.performConversationIntent(newChat) }
                }
                if host.hasUnassignedDraft {
                    RunReadableText(text:language.text("Select a conversation for this draft, or clear it before starting another chat.","请先为当前草稿选择会话，或清空后再新建聊天。"))
                }
            } else {
                RunReadableText(text:language.text("Original selection unavailable. Read and choose the current original again.","原选择不可用，请重新读取并选择当前原记录。")).accessibilityIdentifier("assistant.edit.unavailable")
            }
            conversationStatus
            if let refusal=host.discussionRefusal {
                RunReadableText(text:(refusal.definiteFailure ? language.text("The original request was explicitly rejected. Its original bytes and refusal are retained. Read the current conversation again before a new request.","原请求已明确拒绝，原字节和拒绝证据保留。请重新读取当前会话后再发起新请求。") : language.text("Original outcome unknown or unavailable. Reconcile that original request; do not send another one as a retry.","原请求结果未知或不可用。请核对原请求，不要另发请求冒充重试。"))+"\nHTTP "+String(refusal.status)+" · "+refusal.code).accessibilityIdentifier("assistant.edit.refusal")
            }
            button("assistant.edit.trip.open",language.text("Choose a formal Trip, date or item","选择正式行程、日期或条目"),disabled:host.isBusy,action:openTrips)
            RunReadableText(text:language.text("Choose an independent travel memory context explicitly. A different Trip clears the earlier memory-context and needs choices.","请明确选择独立的旅行记忆上下文。更换行程后会清空先前的记忆上下文和需求选择。"),style:.caption)
            RunReadableText(text:language.text("A candidate requires a selected date or item. Generation does not automatically accept changes, replace a formal Trip or rewrite long-term memory.","候选请求必须选定日期或条目。生成不会自动接受修改、替换正式行程或重写长期记忆。"),style:.caption)
            if selectionFailed { RunReadableText(text:language.text("The displayed choice changed. Read and choose it again.","所显示的选择已变化，请重新读取并选择。")) }
        }.accessibilityElement(children:.contain).accessibilityIdentifier("assistant.edit.context")
    }
    private func command(_ id:String,_ title:String,value:ScopedMessageChoiceCommand?) -> some View {
        button(id,title,disabled:value==nil) {
            guard let value else { return }
            selectionFailed = !host.performScopedChoice(value)
        }
    }
    private func button(_ id:String,_ title:String,disabled:Bool,action:@escaping()->Void) -> some View {
        Button(action:action) { RunReadableText(text:title).frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle()) }
            .buttonStyle(ShellReadableButtonStyle()).disabled(disabled).accessibilityIdentifier(id)
    }
    @ViewBuilder private var conversationStatus:some View {
        switch host.conversationState {
        case .idle:EmptyView()
        case .working:RunReadableText(text:language.text("Checking the original chat request…","正在核对原聊天请求…")).accessibilityIdentifier("assistant.chat.status")
        case .available:RunReadableText(text:language.text("Original chat is available.","原聊天已可读取。")).accessibilityIdentifier("assistant.chat.status")
        case .unknown:RunReadableText(text:language.text("Original chat result unknown. Check its original ID in local recovery.","原聊天结果未知，请在本地恢复中核对原ID。")).accessibilityIdentifier("assistant.chat.status")
        case .rejected(_,let status):RunReadableText(text:language.text("Original chat request unavailable.","原聊天请求不可用。")+" · HTTP "+String(status)).accessibilityIdentifier("assistant.chat.status")
        }
    }
}
#endif
