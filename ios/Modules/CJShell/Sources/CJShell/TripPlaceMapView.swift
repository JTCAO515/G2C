#if os(iOS)
import SwiftUI
import MapKit
import CJTripClient
import CJRunClient

struct TripPlaceMapView: View {
    let document: StructuredTripDocument
    let language: ShellLanguage
    @State private var expanded = false
    @State private var failed = false
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            switch projection {
            case .failure:
                RunReadableText(text: language.text("Place sources unavailable. The text itinerary remains readable.", "地点来源不可读取，文字行程仍可阅读。"))
            case .success(let places):
                if places.isEmpty {
                    RunReadableText(text: language.text("No recorded places; no map markers.", "没有地点来源记录，不补地图标记。")).accessibilityIdentifier("trip.map.empty")
                } else {
                    ForEach(places) { place in
                        VStack(alignment: .leading, spacing: 6) {
                            RunSelectableText(text: place.nameZH).accessibilityIdentifier("trip.map.name." + place.id)
                            RunSelectableText(text: place.provider + " · " + place.providerID).accessibilityIdentifier("trip.map.identity." + place.id)
                            RunSelectableText(text: place.addressZH.value ?? language.text("Address UNKNOWN", "地址 UNKNOWN")).accessibilityIdentifier("trip.map.address." + place.id)
                            if language == .english {
                                RunSelectableText(text: place.officialNameEN.value ?? "Official English name UNKNOWN")
                                RunSelectableText(text: place.officialAddressEN.value ?? "Official English address UNKNOWN")
                            }
                            RunSelectableText(text: (place.rawCoordinate ?? "UNKNOWN") + " · " + (place.crs ?? "UNKNOWN"))
                                .accessibilityIdentifier("trip.map.coordinate." + place.id)
                            RunReadableText(text: place.evidenceLevel + " · pending · " + (place.markerCoordinate == nil ? language.text("Location needs verification; no marker", "位置待核实，不画点") : language.text("Recorded coordinates; physical alignment unverified", "来源坐标，实际点位对齐未核实")))
                                .accessibilityIdentifier("trip.map.status." + place.id)
                        }
                    }
                    if places.contains(where: { $0.markerCoordinate != nil }) {
                        Button { expanded.toggle() } label: {
                            RunReadableText(text: expanded ? language.text("Hide map", "收起地图") : language.text("Show Apple map", "显示 Apple 地图"))
                                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
                        }.buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("trip.map.show")
                        RunReadableText(text: language.text("Viewing the map sends its region to Apple. Your location is not requested. Text remains available if map tiles fail.", "查看地图会向 Apple 发送查看区域，不申请你的位置。地图瓦片失败时仍可阅读文字。"), style: .caption)
                        if expanded {
                            RecordedPlaceMap(places: places, language: language, failed: { failed = true })
                                .frame(height: 320).accessibilityIdentifier("trip.map.canvas")
                        }
                        if failed {
                            RunReadableText(text: language.text("Map unavailable. Use the recorded names and addresses above.", "地图暂不可用，请使用上方来源名称和地址。"))
                                .accessibilityIdentifier("trip.map.unavailable")
                        }
                    }
                }
            }
        }.accessibilityIdentifier("trip.map.sources")
    }
    private var projection: Result<[TripPlaceProjection], any Error> {
        Result { try TripPlaceProjection.read(from: document) }
    }
}

private final class RecordedPlaceAnnotation: NSObject, MKAnnotation {
    let place: TripPlaceProjection
    let coordinate: CLLocationCoordinate2D
    var title: String? { place.nameZH }
    var subtitle: String? { place.providerID + " · " + place.rawCoordinate! }
    init(place: TripPlaceProjection, coordinate: PlaceCoordinateV1) {
        self.place = place
        // Representation for MapKit only; source strings remain verbatim. No CRS conversion.
        self.coordinate = .init(latitude: NSDecimalNumber(decimal: coordinate.latitude.value).doubleValue,
                                longitude: NSDecimalNumber(decimal: coordinate.longitude.value).doubleValue)
    }
}

private struct RecordedPlaceMap: UIViewRepresentable {
    let places: [TripPlaceProjection]
    let language: ShellLanguage
    let failed: () -> Void
    func makeCoordinator() -> Coordinator { Coordinator(failed: failed) }
    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.showsUserLocation = false
        map.userTrackingMode = .none
        map.pointOfInterestFilter = .excludingAll
        map.delegate = context.coordinator
        return map
    }
    func updateUIView(_ map: MKMapView, context: Context) {
        let signature = places.map { $0.id + ":" + $0.snapshotSHA256 }.joined(separator: "|") + language.rawValue
        guard context.coordinator.signature != signature else { return }
        context.coordinator.signature = signature
        map.removeAnnotations(map.annotations)
        let annotations = places.compactMap { place in place.markerCoordinate.map { RecordedPlaceAnnotation(place: place, coordinate: $0) } }
        map.addAnnotations(annotations)
        map.showAnnotations(annotations, animated: false)
    }
    static func dismantleUIView(_ map: MKMapView, coordinator: Coordinator) {
        map.delegate = nil
        map.removeAnnotations(map.annotations)
    }
    final class Coordinator: NSObject, MKMapViewDelegate {
        var signature: String?
        let failed: () -> Void
        init(failed: @escaping () -> Void) { self.failed = failed }
        func mapViewDidFailLoadingMap(_ mapView: MKMapView, withError error: any Error) { failed() }
        func mapView(_ mapView: MKMapView, viewFor annotation: any MKAnnotation) -> MKAnnotationView? {
            guard let recorded = annotation as? RecordedPlaceAnnotation else { return nil }
            let view = MKMarkerAnnotationView(annotation: recorded, reuseIdentifier: nil)
            view.canShowCallout = true
            view.isAccessibilityElement = true
            view.accessibilityIdentifier = "trip.map.marker." + recorded.place.id
            view.accessibilityLabel = recorded.place.nameZH + " · " + recorded.place.providerID + " · " + recorded.place.rawCoordinate! + " · GCJ-02"
            view.accessibilityValue = String(recorded.coordinate.longitude) + "," + String(recorded.coordinate.latitude)
            return view
        }
    }
}
#endif
