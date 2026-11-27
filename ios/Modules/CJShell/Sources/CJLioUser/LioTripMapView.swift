import SwiftUI

/// #1996: the map behind the trip map. The page (`LioTripMapView`) depends only on this: a layer draws the
/// background map, the numbered points, the day lines and their labels, tells the page which point was tapped, and
/// shows every point at first. `LioMapKitTripLayer` is the default; a test double or another map can stand in.
///
/// A layer draws only what `LioTripMapScene` holds: coordinates are GCJ-02 and are not converted here (see
/// LioTripMapModel.swift). Colours come from `LioTripMapPalette.color(slot:)`. The layer starts with `scene.fit`
/// in view and moves to the new `fit` when the scene changes.
@MainActor protocol LioTripMapLayer {
    associatedtype Content: View

    /// The map for `scene`. `selectedID` is the caller's point id to highlight (nil for none); `select` is called
    /// with the tapped point's id and nothing else.
    @ViewBuilder func content(scene: LioTripMapScene, selectedID: String?,
                              select: @escaping @MainActor (String) -> Void) -> Content
}

/// The trip map page: the day legend, the map from the layer, and the points that have no position.
/// A tap on a point calls `onSelect(pointID)`; the bubble card is the caller's.
struct LioTripMapView<Layer: LioTripMapLayer>: View {
    static var defaultMapHeight: CGFloat { 340 }

    let scene: LioTripMapScene
    let language: LioLanguage
    let selectedPointID: String?
    let layer: Layer
    let mapHeight: CGFloat
    let onSelect: @MainActor (String) -> Void

    init(input: LioTripMapInput, language: LioLanguage, selectedPointID: String? = nil, layer: Layer,
         mapHeight: CGFloat = Self.defaultMapHeight, onSelect: @escaping @MainActor (String) -> Void) {
        scene = LioTripMapScene(input, language: language)
        self.language = language
        self.selectedPointID = selectedPointID
        self.layer = layer
        self.mapHeight = mapHeight
        self.onSelect = onSelect
    }

    /// The layer's map as the page gives it to it.
    var mapContent: Layer.Content {
        layer.content(scene: scene, selectedID: selectedPointID, select: onSelect)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
            if scene.isEmpty {
                emptyState
            } else {
                legend
                mapContent
                    .frame(height: mapHeight)
                    .clipShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                    .overlay {
                        RoundedRectangle(cornerRadius: LioTheme.Radius.card)
                            .stroke(LioTheme.hairline, lineWidth: LioTheme.outlineWidth)
                            .allowsHitTesting(false)
                    }
                    .accessibilityIdentifier("lio.tripmap.map")
            }
            if !scene.unplaced.isEmpty { unplacedList }
        }
    }

    private var legend: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: LioTheme.Spacing.xs) {
                ForEach(scene.legend) { entry in
                    HStack(spacing: 6) {
                        Circle().fill(LioTripMapPalette.color(slot: entry.colorSlot)).frame(width: 10, height: 10)
                        Text(language.text("Day \(entry.dayNumber)", "第 \(entry.dayNumber) 天"))
                            .font(.subheadline).foregroundStyle(LioTheme.ink)
                    }
                    .padding(.horizontal, LioTheme.Spacing.sm).padding(.vertical, 6)
                    .lioCard(Capsule())
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier("lio.tripmap.legend.\(entry.dayNumber)")
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: LioTheme.Spacing.xs) {
            Image(systemName: "map").font(.title).foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
            Text(scene.hasNoPoints
                 ? language.text("No places to show yet", "还没有可以显示的地点")
                 : language.text("None of these places has a location yet", "这些地点暂时都没有位置"))
                .font(.headline).foregroundStyle(LioTheme.ink).multilineTextAlignment(.center)
            Text(scene.hasNoPoints
                 ? language.text("Places you add to the trip will appear on the map.", "加入行程的地点会显示在地图上。")
                 : language.text("They are listed below, so you can still find them.", "它们列在下面，仍然可以查看。"))
                .font(.subheadline).foregroundStyle(LioTheme.inkSecondary).multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(LioTheme.Spacing.lg)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lio.tripmap.empty")
    }

    private var unplacedList: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text(language.text("Places without a location", "没有位置的点"))
                .font(.headline).foregroundStyle(LioTheme.ink)
                .accessibilityAddTraits(.isHeader)
            ForEach(scene.unplaced) { item in
                HStack(spacing: LioTheme.Spacing.xs) {
                    Circle().fill(LioTripMapPalette.color(slot: item.colorSlot)).frame(width: 8, height: 8)
                        .accessibilityHidden(true)
                    Text(language.text("Day \(item.dayNumber) · \(item.number). \(item.name)",
                                       "第 \(item.dayNumber) 天 · \(item.number). \(item.name)"))
                        .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("lio.tripmap.unplaced.\(item.pointID)")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityIdentifier("lio.tripmap.unplaced")
    }
}
