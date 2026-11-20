#if os(iOS)
import SwiftUI

struct LioLocalSupportDraftEditor: View {
    let language: LioLanguage
    @State private var draft: LocalSupportDraft

    init(language: LioLanguage, storage: LocalSupportDraftStorage) {
        self.language = language
        _draft = State(initialValue: LocalSupportDraft(storage: storage))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(language.text("Need other help? Write it down", "需要其他帮助？写下来"))
                .font(.title2.bold())
                .accessibilityAddTraits(.isHeader)
            TextField(language.text("Describe what's happening, where you are and what you need",
                                    "描述你的情况、所在位置和需要的帮助"),
                      text: Binding(get: { draft.text }, set: { draft.edit($0) }), axis: .vertical)
                .lineLimit(4...10)
                .padding(12)
                .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                .disabled(!draft.canEdit)
                .accessibilityIdentifier("lio.support.draft")
            if let issue = draft.problem {
                Text(message(issue))
                    .font(.subheadline)
                    .foregroundStyle(LioTheme.ink)
                    .accessibilityIdentifier("lio.support.draft-message")
            }
            ViewThatFits(in: .horizontal) {
                HStack { controls }
                VStack(alignment: .leading) { controls }
            }
            Text(language.text("Sending is coming soon", "发送功能即将开放"))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
        }
        .task { draft.load() }
    }

    @ViewBuilder private var controls: some View {
        Button(language.text("Send", "发送")) {}
            .frame(minHeight: 44)
            .disabled(true)
            .accessibilityIdentifier("lio.support.send")
        Button(language.text("Clear", "清空"), action: draft.clear)
            .frame(minHeight: 44)
            .disabled(!draft.canEdit || draft.text.isEmpty)
            .accessibilityIdentifier("lio.support.draft-clear")
    }

    private func message(_ issue: LocalSupportDraft.Problem) -> String {
        switch issue {
        case .tooLong: language.text("Use up to 1,000 characters.", "最多可输入 1000 字。")
        case .cannotLoad: language.text("This device couldn’t show the draft.", "此设备暂无法显示草稿。")
        case .cannotSave: language.text("This device couldn’t save the draft.", "此设备暂无法保存草稿。")
        case .cannotClear: language.text("This device couldn’t clear the draft.", "此设备暂无法清空草稿。")
        }
    }
}
#endif
