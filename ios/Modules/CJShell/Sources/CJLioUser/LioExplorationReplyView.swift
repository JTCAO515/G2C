#if os(iOS)
import CJRunClient
import SwiftUI

/// Local presentation preparation. The parent reconciles the complete snapshot and draft together.
struct LioExplorationReplyView: View {
    let presentation: LioExplorationPresentation
    @Binding var questions: LioQuestionDraft
    let language: LioLanguage
    let canSend: Bool
    let onSend: (String) -> Void
    @State private var editing: LioExplorationPresentation.ProfileEntry?
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            HStack(spacing: LioTheme.Spacing.xs) {
                LioPortrait(size: 22)
                Text("Lio").font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.ink)
            }
            .accessibilityHidden(true)
            if !presentation.profile.isEmpty { profile }
            ForEach(presentation.segments.indices, id: \.self) { index in
                bubble(presentation.segments[index].text, identifier: "lio.segment.\(index)")
            }
            if let answer = presentation.plainAnswer(questionCount: questions.questions.count) {
                bubble(answer, identifier: "lio.answer")
            }
            if !questions.questions.isEmpty {
                LioQuestionForm(draft: $questions, language: language, canSend: canSend, onSend: onSend)
            }
            ForEach(presentation.notices) { notice in
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                    Label(language.text("Lio noticed", "Lio 注意到"),
                          systemImage: notice.severity == .warning ? "exclamationmark.circle" : "bell")
                        .font(.headline)
                        .foregroundStyle(LioTheme.ink)
                        .accessibilityAddTraits(.isHeader)
                    replyText(notice.text)
                    if let url = notice.source.url {
                        Link(destination: url) {
                            Label(language.text("Source", "来源"), systemImage: "link")
                                .fixedSize(horizontal: false, vertical: true)
                                .frame(minHeight: 44, alignment: .leading)
                        }
                        .foregroundStyle(LioTheme.vermilion)
                        .accessibilityIdentifier("lio.notice.source.\(notice.id)")
                    }
                }
                .padding(LioTheme.Spacing.md)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("lio.notice.\(notice.id)")
            }
            ForEach(presentation.exits) { exit in
                Button { onSend(exit.sendText) } label: {
                    Label(exit.displayText, systemImage: "arrow.right")
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .padding(.horizontal, LioTheme.Spacing.sm)
                        .padding(.vertical, LioTheme.Spacing.xxs)
                }
                .buttonStyle(.bordered)
                .tint(LioTheme.vermilion)
                .disabled(!canSend)
                .accessibilityIdentifier("lio.exit.\(exit.id)")
            }
        }
        .sheet(item: $editing) { entry in
            LioProfileChangeSheet(entry: entry, language: language, canSend: canSend, onSend: onSend)
        }
    }

    @ViewBuilder private var profile: some View {
        if typeSize.isAccessibilitySize {
            VStack(spacing: LioTheme.Spacing.xs) { profileEntries }
        } else {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())],
                      alignment: .leading, spacing: LioTheme.Spacing.xs) { profileEntries }
        }
    }

    private var profileEntries: some View {
        ForEach(presentation.profile) { entry in
            Button { editing = entry } label: {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                    HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xs) {
                        RunReadableText(text: entry.displayText)
                            .id(typeSize)
                            .fixedSize(horizontal: false, vertical: true)
                        Image(systemName: "pencil").foregroundStyle(LioTheme.inkSecondary)
                            .accessibilityHidden(true)
                    }
                    if let annotation = entry.annotation(language) {
                        Text(annotation).font(.caption).foregroundStyle(LioTheme.inkSecondary)
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .padding(.horizontal, LioTheme.Spacing.sm)
                .padding(.vertical, LioTheme.Spacing.xs)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
            .accessibilityIdentifier("lio.profile.\(entry.id)")
        }
    }

    private func bubble(_ text: String, identifier: String) -> some View {
        replyText(text)
            .accessibilityIdentifier(identifier)
            .padding(.horizontal, 14)
            .padding(.vertical, LioTheme.Spacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(UnevenRoundedRectangle(topLeadingRadius: LioTheme.Radius.tail,
                                            bottomLeadingRadius: LioTheme.Radius.card,
                                            bottomTrailingRadius: LioTheme.Radius.card,
                                            topTrailingRadius: LioTheme.Radius.card))
    }

    @ViewBuilder private func replyText(_ text: String) -> some View {
        if let rendered = LioReplyMarkdown.render(text) {
            let blocks = LioReplyTextBlock.make(from: rendered)
            VStack(alignment: .leading, spacing: 0) {
                ForEach(blocks.indices, id: \.self) { index in
                    Text(blocks[index].text).textSelection(.enabled)
                        .font(blocks[index].font ?? .body)
                        .foregroundStyle(LioTheme.ink)
                        .lineSpacing(4)
                        .id(typeSize)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(blocks[index].font == nil ? [] : .isHeader)
                        .padding(.top, CGFloat(max(0, blocks[index].leadingSeparator.count - 1)) * LioTheme.Spacing.sm)
                }
            }
            .accessibilityElement(children: .contain)
        } else {
            Text(language.text("This reply can’t be shown right now.", "这条回答暂时无法显示。"))
                .foregroundStyle(LioTheme.inkSecondary)
        }
    }
}

private struct LioProfileChangeSheet: View {
    let entry: LioExplorationPresentation.ProfileEntry
    let language: LioLanguage
    let canSend: Bool
    let onSend: (String) -> Void
    @State private var text: String
    @FocusState private var typing: Bool
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize

    init(entry: LioExplorationPresentation.ProfileEntry, language: LioLanguage,
         canSend: Bool, onSend: @escaping (String) -> Void) {
        self.entry = entry
        self.language = language
        self.canSend = canSend
        self.onSend = onSend
        _text = State(initialValue: entry.displayText)
    }

    private var sendEnabled: Bool {
        canSend && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            let controls = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: LioTheme.Spacing.xs))
                : AnyLayout(HStackLayout(spacing: LioTheme.Spacing.sm))
            controls {
                Button { dismiss() } label: {
                    Text(language.text("Cancel", "取消"))
                        .font(.body)
                        .foregroundStyle(LioTheme.vermilion)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                if !typeSize.isAccessibilitySize { Spacer() }
                Button(action: send) {
                    Text(language.text("Send", "发送"))
                        .font(.headline)
                        .foregroundStyle(LioTheme.vermilion)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!sendEnabled)
                .accessibilityIdentifier("lio.profile.edit.send")
            }
            .tint(LioTheme.vermilion)
            .padding(.horizontal, LioTheme.Spacing.md)
            .padding(.top, LioTheme.Spacing.sm)
            Form {
                Section {
                    TextField(language.text("Tell Lio what to change", "告诉 Lio 怎样调整"), text: $text, axis: .vertical)
                        .focused($typing)
                        .accessibilityIdentifier("lio.profile.edit.text")
                        .submitLabel(.send)
                        .onSubmit(send)
                } header: {
                    Text(language.text("Adjust this preference", "调整这项偏好"))
                        .foregroundStyle(LioTheme.inkSecondary)
                }
                .lioRow()
            }
            .lioPage()
            .tint(LioTheme.vermilion)
        }
        .background(LioTheme.paper)
        .task { typing = true }
    }

    private func send() {
        guard sendEnabled else { return }
        onSend(text)
        dismiss()
    }
}
#endif
