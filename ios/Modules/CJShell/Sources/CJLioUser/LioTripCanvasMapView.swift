import SwiftUI

/// #1996 / #1995: the "Map" page of the trip canvas. It draws the canvas through the replaceable map layer
/// (`LioTripMapLayer`; MapKit by default) and shows the name of the point that was tapped. The bubble card of a
/// place is another lane's work (#1992); until it is wired a tap highlights the point and names it.
struct LioTripCanvasMapView<Layer: LioTripMapLayer>: View {
    let canvas: LioTripCanvas
    let language: LioLanguage
    let layer: Layer
    @State private var selected: String?

    private var input: LioTripMapInput { LioTripMapInput(canvas: canvas, language: language) }

    /// The name of the point with `id` in `canvas`, or nil when there is no such point (or no selection).
    static func name(ofPoint id: String?, in canvas: LioTripCanvas, language: LioLanguage) -> String? {
        guard let id else { return nil }
        return canvas.segments.flatMap(\.days).flatMap(\.points).first { $0.id == id }?.name(language)
    }

    private var selectedName: String? { Self.name(ofPoint: selected, in: canvas, language: language) }

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            LioTripMapView(input: input, language: language, selectedPointID: selected, layer: layer) { selected = $0 }
            if let selectedName {
                Text(selectedName)
                    .font(.headline).foregroundStyle(LioTheme.ink)
                    .accessibilityIdentifier("lio.trip-canvas.map-selected")
            }
        }
    }
}

#if os(iOS)
extension LioTripCanvasMapView where Layer == LioMapKitTripLayer {
    init(canvas: LioTripCanvas, language: LioLanguage) {
        self.init(canvas: canvas, language: language, layer: LioMapKitTripLayer())
    }
}
#endif
