import CJMessageHTTP
import Foundation
#if os(iOS)
import SwiftUI
#endif

/// #2001 (M-3, App): the one line under an answer that says which remembered preferences it was based on, behind
/// `G2CMemoryNoteEnabled` (off unless the build says YES). Off, the App never reads `rich.memory.used` and nothing on
/// screen changes. It also needs `LIO-answer-rich.1` (`G2CAnswerRichEnabled`): the field is part of it. The server's
/// own switches decide which accounts get it; the note is shown only when the server sent it.
enum LioMemoryNoteFeature {
    static let infoKey = "G2CMemoryNoteEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-memory-note-preview")
        #else
        return false
        #endif
    }
}

/// What the line says: up to three current titles and how many remembered preferences were used in all. The titles are
/// the server's (re-checked there at every read against the memory that is still in use); the remembered text itself
/// never comes with them. A title the App's display rules refuse is left out, and with none left there is no line.
struct LioMemoryUsedNote: Equatable, Sendable {
    let titles: [String]
    let total: Int

    init?(_ used: LioTimelineWire.MemoryUsed?) {
        guard let used else { return nil }
        let shown = used.items.map(\.title).filter { LioPublicDisplay.permitsText($0) }
        guard !shown.isEmpty else { return nil }
        titles = shown
        total = max(used.total, shown.count)
    }
}

/// The wording. The one-preference line is `ui-copy.json` (G4, `memory.applied.description`); the line for several is a
/// placeholder in the same voice, to be confirmed by the coordinator.
enum LioMemoryNoteCopy {
    static func line(_ note: LioMemoryUsedNote, _ l: LioLanguage) -> String {
        if note.total == 1, let title = note.titles.first {
            return l.text("Based on your saved preference: \(title)", "按你记住的「\(title)」")
        }
        let more = note.total > note.titles.count
        let joined = note.titles.joined(separator: l.text(", ", "、"))
        return l.text("Based on your \(note.total) saved preferences: \(joined)\(more ? " and more" : "")",
                      "按你记住的 \(note.total) 条偏好：\(joined)\(more ? "等" : "")")
    }

    static func hint(_ l: LioLanguage) -> String { l.text("Opens My memory", "打开「我的记忆」") }
}

#if os(iOS)
/// One footnote line under the answer. With a memory page to open it is a button (44 pt high) that opens "My memory",
/// where the preference can be changed, paused or deleted; without one it is plain text.
struct LioMemoryNoteLine: View {
    let note: LioMemoryUsedNote
    let language: LioLanguage
    /// Nil where the host has no memory page.
    let open: (() -> Void)?

    var body: some View {
        if let open {
            Button(action: open) { label(showsChevron: true) }
                .buttonStyle(.plain)
                .accessibilityHint(LioMemoryNoteCopy.hint(language))
                .accessibilityIdentifier("lio.memory.note")
        } else {
            label(showsChevron: false).accessibilityIdentifier("lio.memory.note")
        }
    }

    private func label(showsChevron: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xxs) {
            Image(systemName: "bookmark").font(.footnote).foregroundStyle(LioTheme.gold).accessibilityHidden(true)
            Text(LioMemoryNoteCopy.line(note, language))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
            if showsChevron {
                Image(systemName: "chevron.forward").font(.caption2.weight(.semibold))
                    .foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .contentShape(Rectangle())
    }
}
#endif
