#if os(iOS)
import SwiftUI
import CJTripClient
import CJRunClient

/// Map markers are available only with an accepted structured record. A
/// conversation candidate or sample day card never provisions coordinates.
struct DemoV2TripsView: View {
    let language: ShellLanguage
    let days: [DemoV2Day]
    var acceptedDocument: StructuredTripDocument? = nil
    let onPlan: () -> Void
    let onEdit: (() -> Void)?
    let onAsk: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if days.isEmpty && acceptedDocument == nil {
                ShellCardHeading(title: language.text("No saved trips yet", "还没有已采用的行程"), symbol: "map")
                action(language.text("Plan a trip", "去规划行程"), symbol: "bubble.left", perform: onPlan)
            } else {
                if let document = acceptedDocument {
                    ShellCardHeading(title: document.title, symbol: "map")
                    TripPlaceMapView(document: document, language: language)
                        .id(document.contentSHA256)
                }
                ForEach(days) { DemoV2DayCard(day: $0, language: language) }
                if let onEdit {
                    action(language.text("Edit itinerary", "直接编辑"), symbol: "pencil", perform: onEdit)
                }
                action(language.text("Edit with Assistant", "问助手修改"), symbol: "bubble.left", perform: onAsk)
            }
        }
        .shellCard()
    }

    private func action(_ title: String, symbol: String, perform: @escaping () -> Void) -> some View {
        Button(action: perform) { ShellActionLabel(title: title, symbol: symbol) }
            .buttonStyle(ShellActionButtonStyle())
    }
}
#endif
