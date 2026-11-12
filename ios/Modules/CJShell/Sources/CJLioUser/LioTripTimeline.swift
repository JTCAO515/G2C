#if os(iOS)
import MapKit
import SwiftUI

struct LioTripListCard: View {
    let title: String
    let itinerary: LioItinerary?
    let language: LioLanguage

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 10) {
                Text(title)
                    .font(LioTheme.display(.title3))
                    .foregroundStyle(LioTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let itinerary {
                    if let first = itinerary.days.first?.date, let last = itinerary.days.last?.date {
                        Text(first == last ? first : "\(first) – \(last)")
                            .font(.subheadline)
                    }
                    let days = itinerary.days.count
                    let stops = itinerary.days.reduce(0) { $0 + $1.stops.count }
                    Text(language.text("\(days) days · \(stops) stops", "\(days) 天 · \(stops) 项安排"))
                        .font(.subheadline)
                }
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .accessibilityHidden(true)
        }
        .foregroundStyle(LioTheme.inkSecondary)
        .padding(20)
        .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

struct LioTripTimeline: View {
    let itinerary: LioItinerary
    let language: LioLanguage
    @State private var selectedDay: Int?
    @State private var focusedStop: String?
    @State private var mapUnavailable = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var day: LioItinerary.Day? {
        itinerary.days.first { $0.number == selectedDay } ?? itinerary.days.first
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            if let day {
                if day.stops.contains(where: { $0.point != nil }) {
                    VStack(alignment: .leading, spacing: 8) {
                        LioRouteMap(day: day, focusedStop: focusedStop,
                                    failed: { mapUnavailable = true }, loaded: { mapUnavailable = false })
                            .frame(height: 220)
                            .clipShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                            .accessibilityIdentifier("lio.trip.route-map")
                            .accessibilityValue(focusedStop ?? "")
                        if mapUnavailable {
                            Text(language.text("Map unavailable", "暂时无法显示地图"))
                                .accessibilityIdentifier("lio.trip.route-map.unavailable")
                                .foregroundStyle(LioTheme.inkSecondary)
                        }
                        Text(language.text("Viewing the map sends its area to Apple.", "查看地图时，Apple 会收到地图显示区域。"))
                            .font(.footnote)
                            .foregroundStyle(LioTheme.inkSecondary)
                        Link(destination: URL(string: "https://www.apple.com/legal/internet-services/maps/")!) {
                            Text(language.text("Apple Maps legal information", "Apple 地图法律信息"))
                                .font(.footnote)
                                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                                .contentShape(Rectangle())
                        }
                    }
                }
                ScrollView(.horizontal) {
                    HStack(spacing: 8) {
                        ForEach(itinerary.days) { choice in
                            Button {
                                selectedDay = choice.number
                                focusedStop = nil
                                mapUnavailable = false
                            } label: {
                                Text(dayTitle(choice, language))
                                    .font(.subheadline.weight(.semibold))
                                    .padding(.horizontal, 16)
                                    .frame(minHeight: 44)
                                    .background(day.number == choice.number ? LioTheme.surfaceSunken : LioTheme.surface,
                                                in: Capsule())
                                    .overlay { Capsule().stroke(LioTheme.hairline, lineWidth: 1) }
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(LioTheme.ink)
                            .accessibilityAddTraits(day.number == choice.number ? [.isSelected] : [])
                            .accessibilityIdentifier("lio.trip.select-day.\(choice.number)")
                        }
                    }
                    .padding(.vertical, 2)
                }
                .scrollIndicators(.hidden)
                Text(dayTitle(day, language))
                    .font(LioTheme.display(.title2))
                    .accessibilityAddTraits(.isHeader)
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(day.stops.enumerated()), id: \.element.id) { index, stop in
                        timelineStop(stop, number: index + 1, last: index == day.stops.count - 1)
                    }
                }
            }
        }
        .foregroundStyle(LioTheme.ink)
        .animation(LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion), value: selectedDay)
    }

    private func timelineStop(_ stop: LioItinerary.Stop, number: Int, last: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 0) {
                Text("\(number)")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(LioTheme.onVermilion)
                    .frame(width: 28, height: 28)
                    .background(LioTheme.vermilion, in: Circle())
                if !last { Rectangle().fill(LioTheme.hairline).frame(width: 1).frame(maxHeight: .infinity) }
            }
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 6) {
                let ending = [stop.endDate, stop.endTime].compactMap { $0 }.joined(separator: " ")
                if let start = stop.time {
                    Text(ending.isEmpty ? start : "\(start)–\(ending)")
                        .font(.subheadline)
                        .foregroundStyle(LioTheme.inkSecondary)
                } else if !ending.isEmpty {
                    Text(language.text("Until \(ending)", "至 \(ending)"))
                        .font(.subheadline)
                        .foregroundStyle(LioTheme.inkSecondary)
                }
                if stop.point != nil {
                    Button { focusedStop = stop.id } label: {
                        Text(stop.name)
                            .font(.body.weight(.medium))
                            .multilineTextAlignment(.leading)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.trip.focus.\(stop.id)")
                } else {
                    Text(stop.name).font(.body.weight(.medium))
                }
                if stop.fixed == true {
                    Label(language.text("Fixed plan", "固定安排"), systemImage: "lock.fill")
                        .font(.subheadline)
                        .foregroundStyle(LioTheme.jade)
                }
            }
            .padding(.bottom, last ? 0 : 24)
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

private struct LioRouteMap: UIViewRepresentable {
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
private final class LioRouteCanvas: UIView {
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
                marker.isAccessibilityElement = true
                marker.accessibilityLabel = stop.stop.name
                marker.accessibilityIdentifier = "lio.trip.marker.\(stop.stop.id)"
                self.addSubview(marker)
                self.markers.append(marker)
            }
            self.loaded?()
        }
    }
}
#endif
