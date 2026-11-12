#if os(iOS)
import CJMessageHTTP
import CJRunClient
import Foundation
import SwiftUI

enum LioMemoryFeedbackKind: Equatable {
    case remembered, changed, saveUnavailable, readUnavailable

    var replacesPrompt: Bool { self == .remembered || self == .changed }

    func text(_ language: LioLanguage) -> String {
        switch self {
        case .remembered: language.text("Remembered", "已记住")
        case .changed: language.text("That suggestion changed.", "这条建议已有变化。")
        case .saveUnavailable: language.text("Couldn’t save your choice right now.", "暂时无法保存你的选择。")
        case .readUnavailable: language.text("Couldn’t show your saved choice.", "暂时无法显示你的选择。")
        }
    }
}

struct LioMemoryFeedback: Identifiable {
    let tag: LioMemoryWire.Tag
    let turnID: Data
    let kind: LioMemoryFeedbackKind
    var id: LioMemoryWire.Tag { tag }
}

struct LioMemoryConfirmation: View {
    let text: String
    let language: LioLanguage
    let disabled: Bool
    let waiting: Bool
    let notice: String?
    let remember: () -> Void
    let dismiss: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var prompt: String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let preference = trimmed.last.map { ".。!?！？".contains($0) } == true ? String(trimmed.dropLast()) : trimmed
        return language.text("Remember: \(preference)?", "记住：\(preference)？")
    }

    var body: some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: LioTheme.Spacing.xs))
            : AnyLayout(HStackLayout(alignment: .center, spacing: LioTheme.Spacing.xs))
        let buttonLayout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: LioTheme.Spacing.xs))
            : AnyLayout(HStackLayout(spacing: LioTheme.Spacing.xs))
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            layout {
                HStack(alignment: .top, spacing: LioTheme.Spacing.xs) {
                    Image(systemName: "bookmark")
                        .foregroundStyle(LioTheme.gold)
                        .accessibilityHidden(true)
                    RunReadableText(text: prompt)
                }
                buttonLayout {
                    Button(action: remember) {
                        Text(language.text("Remember", "记住"))
                            .foregroundStyle(disabled ? LioTheme.inkSecondary : LioTheme.vermilion)
                            .frame(minWidth: 44, minHeight: 44)
                            .padding(.horizontal, LioTheme.Spacing.xs)
                            .overlay {
                                RoundedRectangle(cornerRadius: LioTheme.Radius.small)
                                    .stroke(disabled ? LioTheme.hairline : LioTheme.vermilion,
                                            lineWidth: LioTheme.outlineWidth)
                                    .accessibilityHidden(true)
                            }
                    }
                    .accessibilityIdentifier("lio.memory.remember")
                    Button(action: dismiss) {
                        Text(language.text("Dismiss", "不用"))
                            .foregroundStyle(LioTheme.inkSecondary)
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Rectangle())
                    }
                    .accessibilityIdentifier("lio.memory.dismiss")
                }
                .buttonStyle(.plain)
                .font(.subheadline.weight(.semibold))
                .fixedSize(horizontal: !dynamicTypeSize.isAccessibilitySize, vertical: false)
                .disabled(disabled)
            }
            if waiting {
                HStack(spacing: LioTheme.Spacing.xs) {
                    ProgressView().controlSize(.small)
                    Text(language.text("Waiting to save your choice…", "正在等待保存你的选择…"))
                        .accessibilityIdentifier("lio.memory.waiting")
                }
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
            }
            if let notice {
                Text(notice).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
        }
        .padding(LioTheme.Spacing.sm)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.small))
    }
}

struct LioMemoryFeedbackView: View {
    let feedback: LioMemoryFeedback
    let language: LioLanguage
    let expire: () -> Void

    var body: some View {
        Label(feedback.kind.text(language),
              systemImage: feedback.kind == .remembered ? "checkmark.circle.fill" : "info.circle")
            .font(.subheadline.weight(.medium))
            .foregroundStyle(feedback.kind == .remembered ? LioTheme.jade : LioTheme.inkSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .padding(LioTheme.Spacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.small))
            .task(id: feedback.kind) {
                guard feedback.kind == .remembered else { return }
                do { try await Task.sleep(for: .seconds(2)) }
                catch { return }
                expire()
            }
    }
}
#endif
