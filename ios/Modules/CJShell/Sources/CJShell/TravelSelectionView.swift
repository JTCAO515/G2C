#if os(iOS)
import SwiftUI
import CJMessageHTTP
import CJRunClient

/// A choice requires the canonical owned travel read. No view label, configured
/// ID or unavailable response is converted into an implicit `none` selection.
struct TravelSelectionView: View {
    let model: TravelSelectionModel
    let language: ShellLanguage
    var requiresTravel=false
    @State private var selectionFailed = false

    var body: some View {
        List {
            Section {
                RunReadableText(text:requiresTravel ? language.text("Choose an independent travel memory context. This request requires one; it is never inferred from a formal Trip.","请明确选择独立的旅行记忆上下文。此请求必须绑定，不会从正式行程推断。") : language.text("Choose a travel to use its temporary memory, or choose no travel to use long-term memory only.", "选择旅行以使用对应的临时记忆，或明确选择不绑定旅行，仅使用长期记忆。"))
                status
                if selectionFailed {
                    RunReadableText(text:language.text("The selection could not be verified. No message has been sent.", "无法核实本次选择，尚未发送消息。"))
                        .accessibilityIdentifier("travel.selection.error")
                }
                if !requiresTravel { Button {
                    do { try model.selectNone();selectionFailed = false }
                    catch { selectionFailed = true }
                } label: {
                    RunReadableText(text:language.text("No travel · long-term memory only", "不绑定旅行 · 仅长期记忆"))
                        .frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle())
                }.buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("travel.selection.none") }
            } header: { ShellSectionHeading(title:language.text("Memory context", "记忆上下文")) }
            Section {
                ForEach(model.ids,id:\.self) { id in
                    Button {
                        selectionFailed = false
                        Task { await model.selectTravel(id) }
                    } label: {
                        RunReadableText(text:language.text("Travel ", "旅行 ") + id)
                            .frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle())
                    }.buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("travel.selection." + id)
                }
            } header: { ShellSectionHeading(title:language.text("Travel choices", "可选旅行")) }
        }.navigationTitle(language.text("Travel context", "旅行上下文"))
    }

    @ViewBuilder private var status: some View {
        switch model.state {
        case .unselected:
            RunReadableText(text:language.text("Choose a context before sending.", "发送前请明确选择上下文。"))
                .accessibilityIdentifier("travel.selection.status")
        case .loading:
            ProgressView(language.text("Reading the selected travel…", "正在读取所选旅行…"))
                .accessibilityIdentifier("travel.selection.loading")
        case .none:
            RunReadableText(text:requiresTravel ? language.text("A verified travel context is required.","必须选择可核实的旅行上下文。") : language.text("Selected: no travel · long-term memory only", "已选择：不绑定旅行 · 仅长期记忆"))
                .accessibilityIdentifier("travel.selection.status")
        case .travel(let travel):
            RunReadableText(text:language.text("Selected travel: ", "已选旅行：") + travel.id + " · "
                + language.text("version ", "版本 ") + String(travel.version))
                .accessibilityIdentifier("travel.selection.status")
        case .unavailable:
            RunReadableText(text:requiresTravel ? language.text("Travel unavailable. Choose a current owned travel context; no message has been sent.","旅行上下文不可用，请重新选择当前有效的本人旅行；尚未发送消息。") : language.text("Travel unavailable. Choose a current travel or explicitly choose no travel; no message has been sent.", "旅行不可用。请重新选择有效旅行，或明确选择不绑定旅行；尚未发送消息。"))
                .accessibilityIdentifier("travel.selection.status")
        }
    }
}
#endif
