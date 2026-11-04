#if os(iOS) && DEBUG && G2C_AMAP_LOCAL && canImport(MAMapKit) && !targetEnvironment(simulator)
import SwiftUI
import MAMapKit
import AMapFoundationKit
import CJTripClient
import CJRunClient

/// Compiled only by the explicitly prepared local iPhone development configuration.
/// The ordinary App, CI and Release builds have no SDK dependency.
struct AMapRecordedPlaceMap: UIViewRepresentable {
    let places: [TripPlaceProjection]
    let language: ShellLanguage
    let failed: () -> Void
    let loaded: () -> Void

    private static let key: String? = {
        guard let url = Bundle.main.url(forResource: "AMapLocalKey", withExtension: "plist") else { return nil }
        do {
            let data = try Data(contentsOf: url)
            return LocalAMapConfiguration.key(data:data,bundleID:Bundle.main.bundleIdentifier)
        } catch {
            // Local configuration is unavailable; the parent explicitly names
            // the MapKit fallback. Never expose file contents or SDK errors.
            return nil
        }
    }()
    static var isConfigured: Bool { key != nil }

    func makeCoordinator() -> Coordinator { Coordinator(failed: failed, loaded: loaded) }
    func makeUIView(context: Context) -> AMapRecordedCanvas {
        // This representable is inserted only after the visible explicit consent.
        MAMapView.updatePrivacyShow(.didShow, privacyInfo: .didContain)
        MAMapView.updatePrivacyAgree(.didAgree)
        AMapServices.shared().apiKey = Self.key!
        AMapServices.shared().enableHTTPS = true
        AMapServices.shared().analysisAgree = false
        AMapServices.shared().regionLanguageType = language == .english ? .en : .zhHans
        let map = AMapRecordedCanvas(frame: .zero)
        map.delegate = context.coordinator
        map.showsUserLocation = false
        map.isShowsIndoorMap = false
        map.showsCompass = false
        map.isRotateEnabled = false
        map.isRotateCameraEnabled = false
        map.accessibilityIdentifier = "trip.map.amap"
        context.coordinator.mapCreated()
        return map
    }
    func updateUIView(_ map: AMapRecordedCanvas, context: Context) {
        let signature = places.map { $0.id + ":" + $0.snapshotSHA256 }.joined(separator: "|") + language.rawValue
        guard context.coordinator.signature != signature else { return }
        context.coordinator.signature = signature
        AMapServices.shared().regionLanguageType = language == .english ? .en : .zhHans
        map.removeAnnotations(map.annotations)
        let annotations = places.compactMap { place in place.markerCoordinate.map { Annotation(place: place, coordinate: $0) } }
        map.addAnnotations(annotations)
        map.recordedAnnotations = annotations
        map.fitRecordedPlaces = true
        map.setNeedsLayout()
    }
    static func dismantleUIView(_ map: AMapRecordedCanvas, coordinator: Coordinator) {
        map.delegate = nil
        coordinator.retire()
        map.removeAnnotations(map.annotations)
    }

    final class Annotation: NSObject, MAAnnotation {
        let place: TripPlaceProjection
        let coordinate: CLLocationCoordinate2D
        var title: String? { place.nameZH }
        var subtitle: String? { place.providerID }
        init(place: TripPlaceProjection, coordinate: PlaceCoordinateV1) {
            self.place = place
            // Projection already admits only original GCJ-02. No conversion.
            self.coordinate = .init(latitude: NSDecimalNumber(decimal: coordinate.latitude.value).doubleValue,
                                    longitude: NSDecimalNumber(decimal: coordinate.longitude.value).doubleValue)
        }
    }
    @MainActor final class Coordinator: NSObject, @preconcurrency MAMapViewDelegate {
        var signature: String?
        private static var creations = 0
        private var creation = 0
        private var active = true
        let failed: () -> Void
        let loaded: () -> Void
        init(failed: @escaping () -> Void, loaded: @escaping () -> Void) { self.failed = failed; self.loaded = loaded }
        func mapCreated() { Self.creations += 1; creation = Self.creations }
        func retire() { active = false }
        func mapViewDidFinishLoadingMap(_ mapView: MAMapView!) {
            guard active else { return }
            mapView.accessibilityValue = "loaded|map-creations:" + String(creation)
            loaded()
        }
        func mapViewDidFailLoadingMap(_ mapView: MAMapView!, withError error: (any Error)!) {
            guard active else { return }
            // SDK errors may include credentials; never log or surface them.
            failed()
        }
        func mapView(_ mapView: MAMapView!, viewFor annotation: (any MAAnnotation)!) -> MAAnnotationView! {
            guard let annotation = annotation as? Annotation else { return nil }
            let view = MAPinAnnotationView(annotation: annotation, reuseIdentifier: "source")!
            view.canShowCallout = true
            view.isAccessibilityElement = true
            view.accessibilityTraits.insert(.button)
            view.accessibilityIdentifier = "trip.map.marker." + annotation.place.id
            view.accessibilityLabel = annotation.place.nameZH
            view.accessibilityValue = [annotation.place.providerID, annotation.place.rawCoordinate!, "GCJ-02",
                String(annotation.coordinate.longitude) + "," + String(annotation.coordinate.latitude)].joined(separator: "|")
            return view
        }
    }
}

/// Fit only after SwiftUI has supplied a real viewport. The SDK owns projection
/// and rendering; source records and raw GCJ-02 declarations are never changed.
final class AMapRecordedCanvas: MAMapView {
    var recordedAnnotations: [AMapRecordedPlaceMap.Annotation] = []
    var fitRecordedPlaces = false
    override func layoutSubviews() {
        super.layoutSubviews()
        guard fitRecordedPlaces, bounds.width > 0, bounds.height > 0 else { return }
        fitRecordedPlaces = false
        showAnnotations(recordedAnnotations, edgePadding: UIEdgeInsets(top:45,left:45,bottom:45,right:45), animated:false)
        zoomLevel = min(zoomLevel, 15)
    }
}
#endif
