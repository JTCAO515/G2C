#if os(iOS)
import CJRunClient
import SwiftUI

/// Local presentation preparation. The parent reconciles the complete snapshot and draft together.
struct LioExplorationReplyView: View {
    let presentation: LioExplorationPresentation
    @Binding var questions: LioQuestionDraft
    let language: LioLanguage
    let canSend: Bool
    var editProfile: ((LioExplorationPresentation.ProfileEntry) -> Void)? = nil
    let onSend: (String) -> Void
    @State private var exitsConsumed = false
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
                    HStack(spacing: LioTheme.Spacing.xs) {
                        Image(systemName: notice.severity == .warning ? "exclamationmark.circle" : "bell")
                            .font(.headline).foregroundStyle(LioTheme.ink).accessibilityHidden(true)
                        RunReadableText(text: language.text("Lio noticed", "Lio 注意到"), style: .headline, color: LioTheme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                        .accessibilityAddTraits(.isHeader)
                    replyText(notice.text)
                    if let url = notice.source.url {
                        Link(destination: url) {
                            HStack(spacing: LioTheme.Spacing.xs) {
                                Image(systemName: "link").font(.body).foregroundStyle(LioTheme.vermilion)
                                    .accessibilityHidden(true)
                                RunReadableText(text: language.text("Source", "来源"), color: LioTheme.vermilion)

                            }
                                .fixedSize(horizontal: false, vertical: true)
                                .frame(minHeight: 44, alignment: .leading)
                        }
                        .foregroundStyle(LioTheme.vermilion)
                        .accessibilityLabel(language.text("Source", "来源"))
                        .accessibilityIdentifier("lio.notice.source.\(notice.id)")
                    }
                }
                .padding(LioTheme.Spacing.md)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("lio.notice.\(notice.id)")
            }
            if !exitsConsumed && !presentation.exits.isEmpty {
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) { exitButtons }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: LioTheme.Spacing.xs) { exitButtons }
                        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) { exitButtons }
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
        .font(.body)
        .sheet(item: $editing) { entry in
            LioProfileChangeSheet(entry: entry, language: language, canSend: canSend, onSend: onSend)
        }
    }

    private var exitShape: AnyShape {
        if typeSize.isAccessibilitySize {
            AnyShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        } else {
            AnyShape(Capsule())
        }
    }

    private var exitButtons: some View {
        ForEach(presentation.exits) { exit in
            Button {
                onSend(exit.sendText)
                exitsConsumed = true
            } label: {
                HStack(spacing: LioTheme.Spacing.xs) {
                    Image(systemName: "arrow.right").font(.body).accessibilityHidden(true)
                    RunReadableText(text: exit.displayText, color: canSend ? LioTheme.ink : LioTheme.inkSecondary)
                }
                .foregroundStyle(canSend ? LioTheme.ink : LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: typeSize.isAccessibilitySize ? .infinity : nil, minHeight: 44, alignment: .leading)
                .padding(.horizontal, LioTheme.Spacing.sm)
                .padding(.vertical, LioTheme.Spacing.xxs)
                .background(LioTheme.surface, in: exitShape)
                .overlay {
                    exitShape.stroke(LioTheme.hairline, lineWidth: 1)
                        .allowsHitTesting(false).accessibilityHidden(true)
                }
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
            .accessibilityLabel(exit.displayText)
            .accessibilityIdentifier("lio.exit.\(exit.id)")
        }
    }

    private var profile: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: typeSize.isAccessibilitySize ? 1 : 2),
                  alignment: .leading, spacing: LioTheme.Spacing.xs) { profileEntries }
    }

    private var profileEntries: some View {
        ForEach(presentation.profile) { entry in
            Button {
                if let editProfile { editProfile(entry) }
                else { editing = entry }
            } label: {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                    HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xs) {
                        RunReadableText(text: entry.displayText)

                            .fixedSize(horizontal: false, vertical: true)
                        Image(systemName: "pencil").foregroundStyle(LioTheme.inkSecondary)
                            .accessibilityHidden(true)
                    }
                    if let annotation = entry.annotation(language) {
                        RunReadableText(text: annotation, style: .caption, color: LioTheme.inkSecondary)

                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .padding(.horizontal, LioTheme.Spacing.sm)
                .padding(.vertical, LioTheme.Spacing.xs)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
            .accessibilityLabel(entry.displayText)
            .accessibilityValue(entry.annotation(language) ?? "")
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

struct LioProfileChangeSheet: View {
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
