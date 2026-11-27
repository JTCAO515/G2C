#if os(iOS)
import MapKit
import SwiftUI

/// #1996: the default `LioTripMapLayer`. Apple MapKit is only the background: the markers, lines and labels are
/// ours, drawn from the scene.
///
/// Coordinates are given to MapKit as they are (GCJ-02). Apple Maps' base map in mainland China is GCJ-02, so
/// no conversion is applied here or anywhere else (see LioTripMapModel.swift); the six-city real-device check
/// confirms it. Points of interest are off, so only our numbers mark places. Nothing here searches, routes or
/// calls a map service of ours: finding nearby places and taxis stay on AMap.
struct LioMapKitTripLayer: LioTripMapLayer {
    func content(scene: LioTripMapScene, selectedID: String?,
                 select: @escaping @MainActor (String) -> Void) -> some View {
        LioMapKitTripMap(scene: scene, selectedID: selectedID, select: select)
    }
}

extension LioTripMapView where Layer == LioMapKitTripLayer {
    /// The trip map on MapKit.
    init(input: LioTripMapInput, language: LioLanguage, selectedPointID: String? = nil,
         mapHeight: CGFloat = Self.defaultMapHeight, onSelect: @escaping @MainActor (String) -> Void) {
        self.init(input: input, language: language, selectedPointID: selectedPointID, layer: LioMapKitTripLayer(),
                  mapHeight: mapHeight, onSelect: onSelect)
    }
}

private extension LioTripMapCoordinate {
    var location: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: latitude, longitude: longitude) }
}

private struct LioMapKitTripMap: View {
    let scene: LioTripMapScene
    let selectedID: String?
    let select: @MainActor (String) -> Void
    @State private var position: MapCameraPosition

    init(scene: LioTripMapScene, selectedID: String?, select: @escaping @MainActor (String) -> Void) {
        self.scene = scene
        self.selectedID = selectedID
        self.select = select
        _position = State(initialValue: Self.camera(for: scene))
    }

    private static func camera(for scene: LioTripMapScene) -> MapCameraPosition {
        guard let fit = scene.fit else { return .automatic }
        return .region(MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: fit.centerLatitude, longitude: fit.centerLongitude),
            span: MKCoordinateSpan(latitudeDelta: fit.latitudeSpan, longitudeDelta: fit.longitudeSpan)))
    }

    var body: some View {
        Map(position: $position) {
            ForEach(scene.lines) { line in
                // A page-coloured casing under the day colour keeps the line readable on any base map.
                MapPolyline(coordinates: [line.from.location, line.to.location])
                    .stroke(LioTheme.surface, style: StrokeStyle(lineWidth: 7, lineCap: .round))
                MapPolyline(coordinates: [line.from.location, line.to.location])
                    .stroke(LioTripMapPalette.color(slot: line.colorSlot), style: StrokeStyle(lineWidth: 4, lineCap: .round))
            }
            ForEach(scene.lines.filter { $0.label != nil }) { line in
                Annotation("", coordinate: line.midpoint.location, anchor: .center) {
                    segmentLabel(line)
                }
                .annotationTitles(.hidden)
            }
            ForEach(scene.pins) { pin in
                Annotation(pin.name, coordinate: pin.coordinate.location, anchor: .center) {
                    marker(pin)
                }
                .annotationTitles(.hidden)
            }
        }
        .mapStyle(.standard(elevation: .flat, pointsOfInterest: .excludingAll))
        .mapControls { MapCompass(); MapScaleView() }
        .onChange(of: scene.fit) { _, _ in position = Self.camera(for: scene) }
    }

    private func marker(_ pin: LioTripMapScene.Pin) -> some View {
        let selected = pin.id == selectedID
        return Button { select(pin.id) } label: {
            Text("\(pin.number)")
                .font(.caption.weight(.bold)).minimumScaleFactor(0.7).lineLimit(1)
                .foregroundStyle(LioTheme.onVermilion)
                .frame(minWidth: 28, minHeight: 28)
                .background(LioTripMapPalette.color(slot: pin.colorSlot), in: Circle())
                .overlay(Circle().stroke(selected ? LioTheme.ink : LioTheme.surface, lineWidth: selected ? 3 : 2))
                .scaleEffect(selected ? 1.25 : 1)
                .frame(minWidth: 44, minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(pin.accessibilityLabel)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("lio.tripmap.pin.\(pin.id)")
    }

    private func segmentLabel(_ line: LioTripMapScene.Line) -> some View {
        Text(line.label ?? "")
            .font(.caption2.weight(.medium)).foregroundStyle(LioTheme.ink)
            .padding(.horizontal, 6).padding(.vertical, 3)
            .background(LioTheme.surface, in: Capsule())
            .overlay(Capsule().stroke(LioTripMapPalette.color(slot: line.colorSlot), lineWidth: 1.5))
            .allowsHitTesting(false)
            .accessibilityIdentifier("lio.tripmap.segment.\(line.key)")
    }
}
#endif
