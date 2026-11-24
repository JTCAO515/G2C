#if os(iOS)
import SwiftUI

/// Interactive metro map (#1454): drawn natively from `LioMetroMap`, pinch to zoom, drag to pan,
/// tap a station for its lines and transfers, then take a taxi or get directions there.
struct LioMetroMapView: View {
    let map: LioMetroMap
    let language: LioLanguage
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @State private var scale: CGFloat = 1
    @State private var committedScale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var committedOffset: CGSize = .zero
    @State private var selected: LioMetroMap.Station?

    private static let minScale: CGFloat = 1
    private static let maxScale: CGFloat = 5

    var body: some View {
        GeometryReader { proxy in
            let side = min(proxy.size.width, proxy.size.height) - 32
            let origin = CGPoint(x: (proxy.size.width - side) / 2, y: (proxy.size.height - side) / 2)
            Canvas { context, _ in
                draw(in: &context, side: side, origin: origin)
            }
            .contentShape(Rectangle())
            .gesture(SpatialTapGesture().onEnded { tap in
                let point = mapPoint(tap.location, side: side, origin: origin)
                selected = map.station(near: point.x, point.y, radius: 22 / (side * scale))
            })
            .simultaneousGesture(MagnifyGesture()
                .onChanged { value in scale = clamp(committedScale * value.magnification) }
                .onEnded { _ in committedScale = scale })
            .simultaneousGesture(DragGesture(minimumDistance: 4)
                .onChanged { value in
                    offset = CGSize(width: committedOffset.width + value.translation.width,
                                    height: committedOffset.height + value.translation.height)
                }
                .onEnded { _ in committedOffset = offset })
            .accessibilityElement(children: .contain)
            .accessibilityLabel(language.text("Metro map", "地铁图"))
        }
        .background(LioTheme.surface)
        .clipped()
        .overlay(alignment: .bottomLeading) { attribution }
        .overlay(alignment: .topTrailing) { zoomControls }
        .sheet(item: $selected) { station in
            NavigationStack { stationSheet(station) }
                .presentationDetents([.medium, .large])
        }
    }

    // MARK: Drawing

    private func position(_ station: LioMetroMap.Station, side: CGFloat, origin: CGPoint) -> CGPoint {
        CGPoint(x: origin.x + offset.width + (station.x - 0.5) * side * scale + side / 2,
                y: origin.y + offset.height + (station.y - 0.5) * side * scale + side / 2)
    }

    private func mapPoint(_ location: CGPoint, side: CGFloat, origin: CGPoint) -> (x: Double, y: Double) {
        ((location.x - origin.x - offset.width - side / 2) / (side * scale) + 0.5,
         (location.y - origin.y - offset.height - side / 2) / (side * scale) + 0.5)
    }

    private func draw(in context: inout GraphicsContext, side: CGFloat, origin: CGPoint) {
        let lineWidth = max(3, 4 * sqrt(scale))
        for line in map.lines {
            var path = Path()
            let points = line.stations.compactMap(map.station).map { position($0, side: side, origin: origin) }
            guard let first = points.first else { continue }
            path.move(to: first)
            points.dropFirst().forEach { path.addLine(to: $0) }
            context.stroke(path, with: .color(Color(hex: line.color)),
                           style: StrokeStyle(lineWidth: lineWidth, lineCap: .round, lineJoin: .round))
        }
        let showLabels = scale >= 1.6 || map.stations.count <= 30
        for station in map.stations {
            let center = position(station, side: side, origin: origin)
            let radius = station.isInterchange ? lineWidth * 1.3 : lineWidth * 0.85
            let dot = Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2))
            context.fill(dot, with: .color(.white))
            context.stroke(dot, with: .color(station.isInterchange ? LioTheme.ink : lineColor(station)),
                           lineWidth: station.isInterchange ? 2 : 1.5)
            if showLabels {
                let text = Text(language == .chinese ? station.nameZH : station.nameEN)
                    .font(.system(size: 11, weight: station.isInterchange ? .semibold : .regular))
                    .foregroundColor(LioTheme.ink)
                // Labels sit just above-right of the dot on a paper halo so lines underneath stay readable.
                let resolved = context.resolve(text)
                let size = resolved.measure(in: CGSize(width: 240, height: 40))
                let anchor = CGPoint(x: center.x + radius + 2, y: center.y - radius - 1)
                let halo = CGRect(x: anchor.x - 2, y: anchor.y - size.height, width: size.width + 4, height: size.height)
                context.fill(Path(roundedRect: halo, cornerRadius: 3), with: .color(LioTheme.surface.opacity(0.85)))
                context.draw(resolved, at: anchor, anchor: .bottomLeading)
            }
        }
    }

    private func lineColor(_ station: LioMetroMap.Station) -> Color {
        station.lines.first.flatMap(map.line).map { Color(hex: $0.color) } ?? LioTheme.ink
    }

    private func clamp(_ value: CGFloat) -> CGFloat { min(Self.maxScale, max(Self.minScale, value)) }

    // MARK: Chrome

    private var zoomControls: some View {
        VStack(spacing: 0) {
            Button { zoom(by: 1.5) } label: { Image(systemName: "plus").frame(width: 44, height: 44) }
                .accessibilityLabel(language.text("Zoom in", "放大"))
            Divider().frame(width: 28)
            Button { zoom(by: 1 / 1.5) } label: { Image(systemName: "minus").frame(width: 44, height: 44) }
                .accessibilityLabel(language.text("Zoom out", "缩小"))
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay { RoundedRectangle(cornerRadius: 12).stroke(LioTheme.hairline) }
        .padding(12)
    }

    private func zoom(by factor: CGFloat) {
        withAnimation(.easeOut(duration: 0.2)) {
            scale = clamp(scale * factor)
            committedScale = scale
            if scale == Self.minScale { offset = .zero; committedOffset = .zero }
        }
    }

    private var attribution: some View {
        Link(destination: map.source.url) {
            Text("\(map.source.name) · \(map.source.license)")
                .font(.caption2)
                .foregroundStyle(LioTheme.inkSecondary)
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(LioTheme.surface.opacity(0.9), in: Capsule())
        }
        .padding(12)
    }

    // MARK: Station

    private func stationSheet(_ station: LioMetroMap.Station) -> some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    Text(language == .chinese ? station.nameZH : station.nameEN).font(LioTheme.display(.title2).weight(.bold))
                    Text(language == .chinese ? station.nameEN : station.nameZH).foregroundStyle(LioTheme.inkSecondary)
                    if station.isInterchange {
                        Text(language.text("Interchange", "换乘站")).font(.caption.weight(.semibold))
                            .foregroundStyle(LioTheme.onVermilion)
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(LioTheme.vermilion, in: Capsule())
                    }
                }
                .padding(.vertical, 4)
            }
            .lioRow()
            Section(language.text("Lines", "线路")) {
                ForEach(map.lines(at: station)) { line in
                    HStack(spacing: 10) {
                        RoundedRectangle(cornerRadius: 3).fill(Color(hex: line.color)).frame(width: 18, height: 6)
                        Text(language == .chinese ? line.nameZH : line.nameEN)
                        Spacer(minLength: 8)
                        Text(terminals(line)).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                    }
                    .frame(minHeight: 36)
                }
            }
            .lioRow()
            Section {
                if let taxiEntry {
                    NavigationLink {
                        LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                                    recentStore: taxiEntry.recentStore, destination: taxiPlace(station))
                    } label: {
                        Label(language.text("Taxi to this station", "打车到这个站"), systemImage: "car.fill")
                    }
                }
                Link(destination: directionsURL(station)) {
                    Label(language.text("Directions in Apple Maps", "用苹果地图导航"),
                          systemImage: "arrow.triangle.turn.up.right.diamond")
                }
            }
            .lioRow()
        }
        .lioPage()
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button(language.text("Done", "完成")) { selected = nil }
            }
        }
    }

    private func terminals(_ line: LioMetroMap.Line) -> String {
        let ends = [line.stations.first, line.stations.last].compactMap { $0.flatMap(map.station) }
        guard ends.count == 2, ends[0].id != ends[1].id else { return language.text("Loop", "环线") }
        return ends.map { language == .chinese ? $0.nameZH : $0.nameEN }.joined(separator: " — ")
    }

    private func taxiPlace(_ station: LioMetroMap.Station) -> LioTaxiPlace {
        LioTaxiPlace(nameZH: station.nameZH + "地铁站", nameEN: station.nameEN + " Station", addressZH: nil,
                     coordinate: .init(latitude: station.latitude, longitude: station.longitude,
                                       referenceSystem: station.referenceSystem))
    }

    private func directionsURL(_ station: LioMetroMap.Station) -> URL {
        var parts = URLComponents(string: "https://maps.apple.com/")!
        parts.queryItems = [.init(name: "daddr", value: "\(station.latitude),\(station.longitude)"),
                            .init(name: "q", value: station.nameZH + "地铁站")]
        return parts.url!
    }
}

private extension Color {
    /// "#RRGGBB", already validated by `LioMetroMapWire`.
    init(hex: String) {
        let value = Int(hex.dropFirst(), radix: 16) ?? 0
        self.init(red: Double((value >> 16) & 0xFF) / 255, green: Double((value >> 8) & 0xFF) / 255,
                  blue: Double(value & 0xFF) / 255)
    }
}
#endif
