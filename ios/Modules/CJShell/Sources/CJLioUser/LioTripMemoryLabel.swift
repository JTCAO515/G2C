import CJMessageHTTP
import Foundation

/// #2010 (M-5): `G2CTripMemoryLabelEnabled` in the build's Info.plist; off unless it says YES. Off, nothing is stored with
/// a saved plan, the canvas shows no label and nothing opens "My memory" from it. Reading `rich.memory.used` from the
/// server needs no switch of its own (the data is passive); the label also needs the trip canvas switch.
enum LioTripMemoryLabelFeature {
    static let infoKey = "G2CTripMemoryLabelEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool { enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) }
}

/// What the canvas label says (#2010): one label for the whole plan, "Based on your preferences", and under it the
/// memories the answer was based on, at most 3, plus how many more were used. It is made from the plan as it was
/// saved, so the titles are the ones the answer showed; what a tap opens is decided when it is tapped (see
/// `LioMemoryOpening`), because the traveller may have stopped or deleted the memory since.
struct LioTripMemoryLabel: Equatable {
    struct Entry: Equatable, Identifiable {
        let itemID: String
        let title: String
        var id: String { itemID }
    }

    let entries: [Entry]
    /// How many memories the answer used in all; at least `entries.count`.
    let total: Int

    /// The label for a canvas, or nil: no plan, a plan with no memories, or either switch off.
    static func make(for plan: LioPlanSummary?, labelEnabled: Bool, canvasEnabled: Bool) -> Self? {
        guard labelEnabled, canvasEnabled, let used = plan?.memoryUsed, !used.items.isEmpty else { return nil }
        return Self(entries: used.items.prefix(3).map { Entry(itemID: $0.itemID, title: $0.title) },
                    total: max(used.total, used.items.count))
    }

    /// Memories used beyond the ones listed.
    var more: Int { max(0, total - entries.count) }

    func title(_ language: LioLanguage) -> String { language.text("Based on your preferences", "按你的偏好") }

    /// The line above the list.
    func intro(_ language: LioLanguage) -> String {
        language.text("Based on what you asked me to remember:", "根据你让我记住的内容：")
    }

    /// "and 2 more" after the listed titles; nil when all of them are listed.
    func moreText(_ language: LioLanguage) -> String? {
        more == 0 ? nil : language.text("and \(more) more", "等 \(total) 条")
    }

    func accessibilityValue(expanded: Bool, _ language: LioLanguage) -> String {
        expanded ? language.text("Expanded", "已展开") : language.text("Collapsed", "已收起")
    }
}

/// Where a tap on one remembered item goes (#2010). The memory page is opened in every case; the item's own page only
/// when it is still in the list, so a memory stopped or deleted since the plan was saved (or an id this phone has not
/// loaded) lands on the list and shows no error.
public enum LioMemoryOpening: Equatable, Sendable {
    case list
    case item(String)

    /// `loaded` is the ids the memory page has read; nil while it has not read any yet.
    public static func target(itemID: String?, loaded: [String]?) -> Self {
        guard let itemID, LioTimelineWire.validMemoryItemID(itemID), let loaded, loaded.contains(itemID) else { return .list }
        return .item(itemID)
    }
}

#if os(iOS)
import SwiftUI

private struct LioOpenMemoryItemKey: EnvironmentKey {
    static let defaultValue: String? = nil
}

public extension EnvironmentValues {
    /// Set on the memory page when it is opened from a plan's label (#2010): the item to show, if it is still saved.
    var lioOpenMemoryItem: String? {
        get { self[LioOpenMemoryItemKey.self] }
        set { self[LioOpenMemoryItemKey.self] = newValue }
    }
}

/// The label at the top of the trip canvas: one tag for the whole plan, opened to list the memories it was based on.
/// Each listed memory opens "My memory" at that item. Without a router (previews) the rows are plain text.
struct LioTripMemoryLabelView: View {
    let label: LioTripMemoryLabel
    let language: LioLanguage
    var open: ((String) -> Void)?
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Button { expanded.toggle() } label: {
                HStack(spacing: LioTheme.Spacing.xxs) {
                    Image(systemName: "bookmark").foregroundStyle(LioTheme.gold).accessibilityHidden(true)
                    Text(label.title(language)).font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.ink)
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.caption.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
                }
                .padding(.horizontal, LioTheme.Spacing.sm)
                .frame(minHeight: 44)
                .background(LioTheme.surfaceSunken, in: Capsule())
                .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(label.title(language))
            .accessibilityValue(label.accessibilityValue(expanded: expanded, language))
            .accessibilityIdentifier("lio.trip-canvas.memory-label")
            if expanded { list }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var list: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            Text(label.intro(language)).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(label.entries) { entry in
                if let open {
                    Button { open(entry.itemID) } label: {
                        HStack(spacing: LioTheme.Spacing.xs) {
                            Text(entry.title).font(.subheadline).foregroundStyle(LioTheme.ink)
                                .multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: LioTheme.Spacing.xxs)
                            Image(systemName: "chevron.forward").font(.footnote.weight(.semibold))
                                .foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
                        }
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint(language.text("Opens this memory", "打开这条记忆"))
                    .accessibilityIdentifier("lio.trip-canvas.memory-label.item.\(entry.itemID)")
                } else {
                    Text(entry.title).font(.subheadline).foregroundStyle(LioTheme.ink)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .accessibilityIdentifier("lio.trip-canvas.memory-label.item.\(entry.itemID)")
                }
            }
            if let more = label.moreText(language) {
                Text(more).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.trip-canvas.memory-label.more")
            }
        }
        .padding(LioTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.small))
        .accessibilityIdentifier("lio.trip-canvas.memory-label.list")
    }
}
#endif

extension LioTimelineWire.MemoryUsed {
    /// The wire's rules (`LIO-answer-rich.1`, `memory.used`) applied to values that were stored: one to three items, a
    /// total of 1...99 that is at least the number listed, no item twice. A single bad item is dropped on its own; nothing
    /// left, or a list that breaks a rule as a whole, means none. Used when a saved plan is read back, so a file edited by
    /// hand (or written by a newer app) cannot put a longer list or a bad id on the screen.
    static func validated(_ listed: [Item?], total: Int) -> LioTimelineWire.MemoryUsed? {
        guard (1...3).contains(listed.count), (1...99).contains(total), total >= listed.count else { return nil }
        let ids = listed.compactMap { $0?.itemID }
        guard Set(ids).count == ids.count else { return nil }
        let items = listed.compactMap { item -> Item? in
            guard let item, LioTimelineWire.validMemoryItemID(item.itemID), LioTimelineWire.validMemoryTitle(item.title) else { return nil }
            return item
        }
        return items.isEmpty ? nil : LioTimelineWire.MemoryUsed(items: items, total: total)
    }
}
