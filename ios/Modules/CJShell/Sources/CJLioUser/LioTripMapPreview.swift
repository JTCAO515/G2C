#if os(iOS)
import SwiftUI

/// #1996 screenshots only: `--lio-trip-map-preview [full|unplaced|none]` (Debug builds, with `--lio-preview`)
/// shows the Trips tab as the trip map on sample data. `full` is the three-day Beijing sample with one place that has no
/// position; `unplaced` is the same trip with no positions at all (the empty state with the list below);
/// `none` is a trip with no stops. Nothing is read or written; always false outside Debug builds.
enum LioTripMapPreview {
    static var requested: Bool {
        #if DEBUG
        ProcessInfo.processInfo.arguments.contains("--lio-trip-map-preview")
        #else
        false
        #endif
    }

    @MainActor static func page(language: LioLanguage) -> AnyView {
        #if DEBUG
        AnyView(LioTripMapPreviewPage(language: language, variant: variant))
        #else
        AnyView(EmptyView())
        #endif
    }

    enum Variant: String { case full, unplaced, none }

    static var variant: Variant {
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: "--lio-trip-map-preview"), index + 1 < arguments.count else { return .full }
        return Variant(rawValue: arguments[index + 1]) ?? .full
    }
}

#if DEBUG
private struct LioTripMapPreviewPage: View {
    let language: LioLanguage
    let variant: LioTripMapPreview.Variant
    @State private var selected: String?

    private var input: LioTripMapInput {
        let full = LioTripMapInput(itinerary: LioRoadbookPreview.beijing(language).itinerary, language: language)
        switch variant {
        case .full: return full
        case .none: return LioTripMapInput(days: [])
        case .unplaced:
            return LioTripMapInput(days: full.days.map { day in
                .init(number: day.number, colorSlot: day.colorSlot,
                      points: day.points.map { .init(id: $0.id, name: $0.name, latitude: nil, longitude: nil, number: $0.number) },
                      segments: day.segments)
            })
        }
    }

    private var selectedName: String? {
        input.days.flatMap(\.points).first { $0.id == selected }?.name
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                Text(language.text("Trip map", "行程地图")).font(LioTheme.display(.title2)).foregroundStyle(LioTheme.ink)
                LioTripMapView(input: input, language: language, selectedPointID: selected) { selected = $0 }
                // The bubble card is another line's work; the preview only shows that the tap arrives.
                if let selectedName {
                    Text(language.text("Selected: \(selectedName)", "已选中：\(selectedName)"))
                        .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                        .accessibilityIdentifier("lio.tripmap.preview.selected")
                }
            }
            .padding(LioTheme.Spacing.md)
        }
        .background(LioTheme.paper)
    }
}
#endif
#endif
