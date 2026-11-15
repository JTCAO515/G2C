#if os(iOS)
import SwiftUI
import UIKit
import CJRunClient

/// Shared by the invitation consent and the existing signed-in menu.
public struct LioDemoNoticePage<Actions: View>: View {
    private let language: LioLanguage
    private let actions: Actions
    @Environment(\.colorScheme) private var colorScheme
    public init(language: LioLanguage, @ViewBuilder actions: () -> Actions) {
        self.language = language
        self.actions = actions()
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                LioPortrait(size: 58)
                RunReadableText(text: language.text("Use fictional trip details", "请使用虚构旅行信息"),
                                style: .displayHeadline, color: LioTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                // Interim internal-demo wording until #225 is decided; consent is unchanged.
                RunReadableText(text: language.text(
                    "This is an internal demo. Please use fictional trip details and leave out personal information.",
                    "这是内部演示。请使用虚构的旅行信息，别填写个人信息。"), color: LioTheme.ink)
                    .accessibilityIdentifier("demo.invite.consent")
                actions
                Divider().accessibilityHidden(true)
                LioBuildUpdatesSection(language: language)
                Divider().accessibilityHidden(true)
                LioProblemNotesSection(language: language, notes: .shared)
            }
            .frame(maxWidth: 480, alignment: .leading)
            .padding(24)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .background(LioTheme.paper)
        .accessibilityIdentifier("lio.information.scroll")
        .navigationTitle(language.text("Internal demo consent", "内部演示同意"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .principal) {
                RunReadableText(text: language.text("Internal demo consent", "内部演示同意"), style: .headline, color: LioTheme.ink)
                    .fixedSize()
                    .accessibilityAddTraits(.isHeader)
            }
        }
    }
}

/// On-device problem notes, shown for screenshots or copying; nothing is uploaded.
struct LioProblemNotesSection: View {
    let language: LioLanguage
    let notes: LioDiagnosticLog
    @State private var copied = false

    var body: some View {
        let text = notes.text(language)
        VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
            RunReadableText(text: language.text("Problem notes", "问题记录"), style: .displayTitle2, color: LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("lio.problems.heading")
            RunReadableText(text: language.text(
                "Kept only on this device, up to \(LioDiagnosticLog.limit) notes. No message text or sign-in details.",
                "只保存在本机，最多 \(LioDiagnosticLog.limit) 条，不含消息内容或登录信息。"), color: LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.problems.privacy")
            RunSelectableText(text: text, color: LioTheme.ink)
                .accessibilityIdentifier("lio.problems.list")
            if !notes.entries.isEmpty {
                Button {
                    UIPasteboard.general.string = text
                    copied = true
                } label: {
                    Text(copied ? language.text("Copied", "已复制") : language.text("Copy notes", "复制记录"))
                        .frame(minHeight: 44)
                }
                .accessibilityIdentifier("lio.problems.copy")
            }
        }
    }
}

private struct LioBuildUpdatesSection: View {
    let language: LioLanguage
    private let installedBuild = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
            RunReadableText(text: language.text("Build updates", "本版更新"), style: .displayTitle2, color: LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("lio.updates.heading")
            if let installedBuild {
                RunReadableText(text: language.text("Current build: \(installedBuild)", "当前构建：\(installedBuild)"),
                                style: .headline, color: LioTheme.ink)
                    .accessibilityIdentifier("lio.updates.current-build")
                switch LioBuildUpdates.bundled {
                case .success(let book):
                    if let number = Int(installedBuild), let current = book.releases.first(where: { $0.build == number }) {
                        release(current)
                        if let previous = book.releases.first(where: { $0.build == current.previousBuild }) {
                            Divider().accessibilityHidden(true)
                            RunReadableText(text: language.text("Previous build: \(previous.build)", "上一构建：\(previous.build)"),
                                            style: .headline, color: LioTheme.ink)
                                .accessibilityAddTraits(.isHeader)
                                .accessibilityIdentifier("lio.updates.previous")
                            release(previous)
                        }
                    } else { unavailable }
                case .failure: unavailable
                }
            } else {
                unavailable
            }
        }
    }

    private var unavailable: some View {
        RunReadableText(text: language.text("Update information isn’t available for this build.", "本构建暂无更新说明。"),
                        color: LioTheme.inkSecondary)
            .accessibilityIdentifier("lio.updates.unavailable")
    }

    private struct ReleaseRow: Identifiable {
        let id: String
        let text: String
        let isHeading: Bool
    }

    private func release(_ release: LioBuildUpdates.Release) -> some View {
        let rows = release.sections.flatMap { section in
            let prefix = "lio.updates.\(release.build).\(section.id.rawValue)"
            return [ReleaseRow(id: prefix, text: section.title.value(language), isHeading: true)]
                + section.items.values(language).enumerated().map { index, text in
                    ReleaseRow(id: "\(prefix).\(index)", text: "• " + text, isHeading: false)
                }
        }
        return VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            ForEach(rows) { row in
                Group {
                    if row.isHeading {
                        RunReadableText(text: row.text, style: .headline, color: LioTheme.ink)
                            .accessibilityAddTraits(.isHeader)
                    } else {
                        RunSelectableText(text: row.text, color: LioTheme.ink)
                    }
                }
                .accessibilityIdentifier(row.id)
                .padding(.top, row.isHeading ? LioTheme.Spacing.md : 0)
            }
        }
    }
}
#endif
