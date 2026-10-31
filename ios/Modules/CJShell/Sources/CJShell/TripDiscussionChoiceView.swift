#if os(iOS)
import SwiftUI
import CJRunClient

struct TripDiscussionChoiceView:View {
    let host:AssistantMessageHost
    let language:ShellLanguage
    let openTrips:()->Void
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            RunReadableText(text:language.text("Trip discussion selection","行程讨论选区"),style:.headline)
            RunReadableText(text:choiceLabel).accessibilityIdentifier("assistant.trip.choice")
            RunReadableText(text:language.text("This choice applies to your next discussion message. It is not a binding receipt or permission to change a Trip.","此选择用于下一条讨论消息；不是绑定回执，也不授予修改行程的权限。"),style:.caption)
            if let refusal=host.discussionRefusal {
                RunReadableText(text:language.text("This discussion was refused. No new binding was established; existing memory was not changed.","本次讨论被拒绝，未建立新绑定，已有记忆未被更改。")+"\nHTTP "+String(refusal.status)+" · "+refusal.code)
                    .accessibilityIdentifier("assistant.trip.refusal")
            }
            button("assistant.trip.open",language.text("Choose a formal Trip, day or item","选择正式行程、日期或条目"),action:openTrips)
            button("assistant.trip.none",language.text("Discuss without a Trip selection","明确不绑定行程进行讨论")) { _=host.selectUnboundDiscussion() }
            RunReadableText(text:language.text("Discussion only. This profile cannot upgrade an account that already has MEMORY configured; memory is never silently disabled.","仅支持讨论。此模式不能升级已有 MEMORY 配置的账号，也不会静默关闭记忆。"),style:.caption)
        }.accessibilityElement(children:.contain).accessibilityIdentifier("assistant.trip.context")
    }
    private func button(_ id:String,_ title:String,action:@escaping()->Void) -> some View {
        Button(action:action) { RunReadableText(text:title).frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle()) }
            .buttonStyle(ShellReadableButtonStyle()).disabled(host.isBusy).accessibilityIdentifier(id)
    }
    private var choiceLabel:String {
        switch host.tripDiscussionChoice {
        case .unselected:language.text("Choose a Trip or explicitly discuss without one. No latest Trip is selected automatically.","请选择行程或明确不绑定；不会自动选择最近行程。")
        case .none:language.text("Explicitly no formal Trip selected. Ambiguous references require clarification.","已明确不绑定正式行程；模糊指代需先澄清。")
        case .unavailable:language.text("The original selection is unavailable. Read and choose it again; no replacement is inferred.","原选择已不可用，请重新读取并选择；不会推断替代行程。")
        case .trip(let title,let choice):
            ([title,choice.id,language.text("Read version ","读取版本 ")+String(choice.expectedVersion)]
             + (choice.day.map { [language.text("Day: ","日期：")+$0.date+" · "+$0.timezone] } ?? [])
             + (choice.itemID.map { [language.text("Item: ","条目：")+$0] } ?? [])) .joined(separator:"\n")
        }
    }
}
#endif
