#if os(iOS)
import CJRunClient
import SwiftUI

/// The chat card for a planned trip: title, day and stop counts, and a button that opens the day-by-day page.
struct LioPlanCard: View {
    let plan: LioPlanSummary
    let language: LioLanguage
    let open: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Label(language.text("Trip plan", "行程方案"), systemImage: "map")
                .font(.caption.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary)
            Text(plan.title).font(LioTheme.display(.headline)).foregroundStyle(LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader)
            Text(language.text("\(plan.days.count) days · \(plan.stopCount) stops", "\(plan.days.count) 天 · \(plan.stopCount) 个地点"))
                .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
            Button(action: open) {
                Label(language.text("View day by day", "按天查看"), systemImage: "list.bullet.below.rectangle")
            }
            .buttonStyle(LioPrimaryButtonStyle())
            .accessibilityIdentifier("lio.plan.open")
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("lio.plan.card")
    }
}

/// The day-by-day page in its own navigation stack, closed with Done.
struct LioPlanSheet: View {
    let plan: LioPlanSummary
    let language: LioLanguage
    let actions: LioItineraryTimelineView.Actions
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            LioItineraryTimelineView(itinerary: plan.itinerary, language: language, startDate: plan.startDate, actions: actions)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button { dismiss() } label: {
                            RunReadableText(text: language.text("Done", "完成"), color: LioTheme.vermilion).fixedSize()
                                .frame(minHeight: 44)
                        }
                        .accessibilityLabel(language.text("Done", "完成"))
                        .accessibilityIdentifier("lio.plan.done")
                    }
                }
        }
        .tint(LioTheme.vermilion)
    }
}
#endif
