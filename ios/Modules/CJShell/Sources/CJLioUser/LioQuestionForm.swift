import CJRunClient
import SwiftUI

/// Selection only edits the draft. The parent sends one ordinary message on submission.
struct LioQuestionForm: View {
    @Binding var draft: LioQuestionDraft
    let language: LioLanguage
    let canSend: Bool
    let onSend: (String) -> Void
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
            ForEach(draft.questions) { question in
                VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                    Text(question.question)
                        .font(.headline)
                        .foregroundStyle(LioTheme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                    if typeSize.isAccessibilitySize {
                        VStack(spacing: LioTheme.Spacing.xs) {
                            options(in: question)
                        }
                    } else {
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())],
                                  alignment: .leading, spacing: LioTheme.Spacing.xs) {
                            options(in: question)
                        }
                    }
                }
                .accessibilityElement(children: .contain)
            }
            Button {
                onSend(draft.jointReply)
            } label: {
                Text(language.text("Done, continue", "好了，继续"))
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.vertical, LioTheme.Spacing.sm)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .padding(.horizontal, LioTheme.Spacing.sm)
            }
            .buttonStyle(LioQuestionSubmitStyle())
            .disabled(!canSend || draft.jointReply.isEmpty)
            .accessibilityIdentifier("lio.questions.continue")
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("lio.questions.\(draft.messageID)")
    }

    private func options(in question: LioQuestionGroup) -> some View {
        ForEach(question.options) { option in
            optionButton(option, in: question)
        }
    }

    private func optionButton(_ option: LioQuestionOption, in question: LioQuestionGroup) -> some View {
        let selected = draft.isSelected(option, in: question)
        return Button {
            draft.toggle(option, in: question)
        } label: {
            HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xs) {
                RunReadableText(text: option.displayText)
                    .id(typeSize)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(selected ? LioTheme.vermilion : LioTheme.inkSecondary)
                    .accessibilityHidden(true)
            }
            .foregroundStyle(LioTheme.ink)
            .padding(LioTheme.Spacing.sm)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(selected ? LioTheme.surfaceSunken : LioTheme.surface,
                        in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
            .overlay {
                RoundedRectangle(cornerRadius: LioTheme.Radius.small)
                    .stroke(selected ? LioTheme.vermilion : LioTheme.hairline,
                            lineWidth: LioTheme.outlineWidth)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
        }
        .buttonStyle(.plain)
        .disabled(!canSend)
        .accessibilityLabel(option.displayText)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("lio.questions.\(draft.messageID).\(option.id)")
    }
}

/// Keep the label readable without changing native disabled interaction.
private struct LioQuestionSubmitStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(isEnabled ? LioTheme.onVermilion : LioTheme.inkSecondary)
            .background(isEnabled ? LioTheme.vermilion : LioTheme.surfaceSunken, in: Capsule())
            .opacity(configuration.isPressed && isEnabled ? 0.85 : 1)
    }
}
