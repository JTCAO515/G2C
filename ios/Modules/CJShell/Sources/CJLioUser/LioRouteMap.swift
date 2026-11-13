#if os(iOS)
import MapKit
import SwiftUI

struct LioRouteMap: UIViewRepresentable {
    let day: LioItinerary.Day
    let focusedStop: String?
    let failed: () -> Void
    let loaded: () -> Void
    @Environment(\.colorScheme) private var colorScheme

    func makeUIView(context: Context) -> LioRouteCanvas { LioRouteCanvas() }
    func updateUIView(_ map: LioRouteCanvas, context: Context) {
        map.configure(day: day, focusedStop: focusedStop, style: colorScheme == .dark ? .dark : .light,
                      failed: failed, loaded: loaded)
    }
    static func dismantleUIView(_ map: LioRouteCanvas, coordinator: ()) { map.retire() }
}

/// MapKit renders the map; numbered labels represent the known stops.
/// Like the existing recorded map, the image is kept only for this view's lifetime.
final class LioRouteCanvas: UIView {
    private let image = UIImageView()
    private var day: LioItinerary.Day?
    private var focusedStop: String?
    private var style = UIUserInterfaceStyle.unspecified
    private var request: MKMapSnapshotter?
    private var markers: [UILabel] = []
    private var failed: (() -> Void)?
    private var loaded: (() -> Void)?
    private var size = CGSize.zero

    override init(frame: CGRect) {
        super.init(frame: frame)
        clipsToBounds = true
        image.isAccessibilityElement = false
        addSubview(image)
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is unavailable") }

    func configure(day: LioItinerary.Day, focusedStop: String?, style: UIUserInterfaceStyle,
                   failed: @escaping () -> Void, loaded: @escaping () -> Void) {
        if self.day != day || self.focusedStop != focusedStop || self.style != style {
            retire()
            self.day = day
            self.focusedStop = focusedStop
            self.style = style
            size = .zero
            setNeedsLayout()
        }
        self.failed = failed
        self.loaded = loaded
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        image.frame = bounds
        guard bounds.width > 0, bounds.height > 0, size != bounds.size else { return }
        size = bounds.size
        load()
    }

    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {
        super.traitCollectionDidChange(previousTraitCollection)
        if previousTraitCollection?.preferredContentSizeCategory != traitCollection.preferredContentSizeCategory {
            size = .zero
            setNeedsLayout()
        }
    }

    func retire() {
        request?.cancel()
        request = nil
        image.image = nil
        markers.forEach { $0.removeFromSuperview() }
        markers = []
        failed = nil
        loaded = nil
    }

    private func load() {
        request?.cancel()
        image.image = nil
        markers.forEach { $0.removeFromSuperview() }
        markers = []
        guard let day else { return }
        let stops = day.stops.enumerated().compactMap { index, stop in
            stop.point.map { (number: index + 1, stop: stop, coordinate: CLLocationCoordinate2D(latitude: $0.latitude, longitude: $0.longitude)) }
        }
        let options = MKMapSnapshotter.Options()
        options.size = bounds.size
        options.traitCollection = UITraitCollection(userInterfaceStyle: style)
        options.pointOfInterestFilter = .excludingAll
        if let focused = stops.first(where: { $0.stop.id == focusedStop }) {
            options.region = MKCoordinateRegion(center: focused.coordinate, span: .init(latitudeDelta: 0.015, longitudeDelta: 0.015))
        } else {
            var rect = MKMapRect.null
            for stop in stops {
                let point = MKMapPoint(stop.coordinate)
                rect = rect.union(MKMapRect(x: point.x - 4000, y: point.y - 4000, width: 8000, height: 8000))
            }
            options.mapRect = rect.insetBy(dx: -rect.width * 0.25, dy: -rect.height * 0.25)
        }
        let operation = MKMapSnapshotter(options: options)
        request = operation
        #if DEBUG && targetEnvironment(simulator)
        if ProcessInfo.processInfo.environment["G2C_ACCEPTANCE_MAP_LOADING"] == "synthetic-delegate-failure" {
            Task { @MainActor [weak self, weak operation] in
                guard let self, let operation, self.request === operation else { return }
                self.failed?()
            }
            return
        }
        #endif
        operation.start { [weak self, weak operation] snapshot, error in
            guard let self, let operation, self.request === operation else { return }
            guard let snapshot, error == nil else { self.failed?(); return }
            self.image.image = snapshot.image
            for stop in stops {
                let point = snapshot.point(for: stop.coordinate)
                let font = UIFont.preferredFont(forTextStyle: .footnote)
                let number = "\(stop.number)"
                let textWidth = (number as NSString).size(withAttributes: [.font: font]).width
                let diameter = max(44, ceil(max(font.lineHeight, textWidth) + 16))
                guard self.bounds.insetBy(dx: diameter / 2, dy: diameter / 2).contains(point) else { continue }
                let marker = UILabel()
                marker.text = number
                marker.font = font
                marker.adjustsFontForContentSizeCategory = true
                marker.textAlignment = .center
                marker.textColor = UIColor(LioTheme.onVermilion)
                marker.backgroundColor = UIColor(LioTheme.vermilion)
                marker.layer.cornerRadius = diameter / 2
                marker.clipsToBounds = true
                marker.frame = CGRect(x: point.x - diameter / 2, y: point.y - diameter / 2, width: diameter, height: diameter)
                // The timeline provides the full, actionable place names;
                // these repeated counters only orient the visual map.
                marker.isAccessibilityElement = false
                marker.accessibilityIdentifier = "lio.trip.marker.\(stop.stop.id)"
                self.addSubview(marker)
                self.markers.append(marker)
            }
            self.loaded?()
        }
    }
}
#endif
