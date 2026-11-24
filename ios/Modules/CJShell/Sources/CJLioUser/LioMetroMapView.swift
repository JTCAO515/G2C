#if os(iOS)
import SwiftUI
import UIKit

/// Interactive metro map (#1450 item 2): pinch to zoom, drag to move, tap a station for its lines,
/// then take a taxi there or get directions. Drawn from the bundled operator data, no map tiles.
struct LioMetroMapScreen: View {
    let language: LioLanguage
    let city: LioMetroCity
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @Environment(\.colorScheme) private var colorScheme
    @State private var map: LioMetroMap?
    @State private var failed = false
    @State private var sheet: Sheet?
    @State private var taxiDestination: TaxiTarget?

    /// Navigation needs a hashable value; a taxi place is identified by its name and coordinate.
    private struct TaxiTarget: Hashable {
        let place: LioTaxiPlace
        static func == (lhs: Self, rhs: Self) -> Bool { lhs.place.id == rhs.place.id }
        func hash(into hasher: inout Hasher) { hasher.combine(place.id) }
    }

    private enum Sheet: Identifiable {
        case stations
        case station(LioMetroMap.Station)

        var id: String {
            switch self {
            case .stations: "stations"
            case let .station(station): station.id
            }
        }
    }

    var body: some View {
        Group {
            if let map {
                LioMetroMapCanvas(map: map, language: language, selected: selectedStation) { station in
                    sheet = .station(station)
                }
                .safeAreaInset(edge: .bottom, spacing: 0) { sourceBar(map) }
            } else if failed {
                ContentUnavailableView(language.text("Map unavailable", "地图暂不可用"), systemImage: "map",
                                       description: Text(language.text("Use the operator's official map instead.",
                                                                        "请改用运营方官方线路图。")))
            } else {
                ProgressView()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(LioTheme.paper)
        .navigationTitle(city.name(in: language) + language.text(" Metro Map", "地铁线路图"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { sheet = .stations } label: {
                    Label(language.text("Find a station", "查找车站"), systemImage: "magnifyingglass")
                }
                .disabled(map == nil)
                .accessibilityIdentifier("lio.metro.map.find")
            }
        }
        .sheet(item: $sheet) { item in
            if let map {
                switch item {
                case .stations:
                    LioMetroStationList(map: map, language: language) { station in sheet = .station(station) }
                case let .station(station):
                    LioMetroStationSheet(map: map, station: station, language: language, taxiEntry: taxiEntry) { place in
                        sheet = nil
                        taxiDestination = TaxiTarget(place: place)
                    }
                    .presentationDetents([.medium, .large])
                }
            }
        }
        .navigationDestination(item: $taxiDestination) { target in
            if let taxiEntry {
                LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                            recentStore: taxiEntry.recentStore, destination: target.place)
            }
        }
        .task {
            guard map == nil else { return }
            do { map = try LioMetroMap.bundled(city) } catch { failed = true }
        }
    }

    private var selectedStation: LioMetroMap.Station? {
        if case let .station(station) = sheet { return station }
        return nil
    }

    private func sourceBar(_ map: LioMetroMap) -> some View {
        Link(destination: map.source.urls[0]) {
            Text(map.sourceLine(in: language))
                .font(.caption)
                .foregroundStyle(LioTheme.inkSecondary)
                .multilineTextAlignment(.leading)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, LioTheme.Spacing.md)
                .padding(.vertical, LioTheme.Spacing.xs)
                .contentShape(Rectangle())
        }
        .background(LioTheme.surface)
        .overlay(alignment: .top) { Rectangle().fill(LioTheme.hairline).frame(height: 1) }
        .accessibilityIdentifier("lio.metro.map.source")
    }
}

/// The schematic itself. Positions are in map units; the view keeps its own zoom and pan.
struct LioMetroMapCanvas: View {
    let map: LioMetroMap
    let language: LioLanguage
    let selected: LioMetroMap.Station?
    let onSelect: (LioMetroMap.Station) -> Void

    @State private var zoom: CGFloat = 1
    @State private var pan: CGSize = .zero
    @State private var lastMagnification: CGFloat?
    @State private var lastTranslation: CGSize?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    static let maximumZoom: CGFloat = 12

    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            let layout = Layout(map: map, size: size, zoom: zoom, pan: pan)
            Canvas { context, _ in draw(in: &context, layout: layout) }
                .contentShape(Rectangle())
                .gesture(magnify(size: size).simultaneously(with: drag(size: size)))
                .onTapGesture { location in
                    let point = layout.mapPoint(location)
                    if let station = map.station(nearX: point.x, y: point.y, radius: 22 / layout.scale) {
                        onSelect(station)
                    }
                }
                .overlay(alignment: .topTrailing) { zoomControls(size: size) }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(language.text(
                    "\(map.city.name(in: language)) metro map, \(map.lines.count) lines. Use Find a station to choose a station.",
                    "\(map.city.name(in: language))地铁线路图，共 \(map.lines.count) 条线路。可用“查找车站”选择车站。"))
                .accessibilityIdentifier("lio.metro.map.canvas")
        }
        .clipped()
    }

    // MARK: Geometry

    struct Layout {
        let map: LioMetroMap
        let size: CGSize
        let zoom: CGFloat
        let pan: CGSize

        /// Points per map unit.
        var scale: CGFloat {
            let fit = min(size.width / map.width, size.height / map.height)
            return (fit.isFinite && fit > 0 ? fit : 1) * zoom
        }

        func viewPoint(x: Double, y: Double) -> CGPoint {
            CGPoint(x: size.width / 2 + (x - map.width / 2) * scale + pan.width,
                    y: size.height / 2 + (y - map.height / 2) * scale + pan.height)
        }

        func mapPoint(_ point: CGPoint) -> (x: Double, y: Double) {
            ((point.x - size.width / 2 - pan.width) / scale + map.width / 2,
             (point.y - size.height / 2 - pan.height) / scale + map.height / 2)
        }
    }

    /// Keep at least part of the map on screen whatever the pan.
    static func clamped(pan: CGSize, zoom: CGFloat, map: LioMetroMap, size: CGSize) -> CGSize {
        let layout = Layout(map: map, size: size, zoom: zoom, pan: .zero)
        let limitX = max(0, (map.width * layout.scale - size.width) / 2) + size.width * 0.25
        let limitY = max(0, (map.height * layout.scale - size.height) / 2) + size.height * 0.25
        return CGSize(width: min(max(pan.width, -limitX), limitX), height: min(max(pan.height, -limitY), limitY))
    }

    // Both gestures apply only the change since their previous update, so pinching and dragging
    // together compose instead of overwriting each other, and lifting one finger never jumps.
    private func magnify(size: CGSize) -> some Gesture {
        MagnifyGesture()
            .onChanged { value in
                let step = value.magnification / (lastMagnification ?? 1)
                lastMagnification = value.magnification
                let newZoom = min(max(zoom * step, 1), Self.maximumZoom)
                // Zoom about the pinch point so the station under the fingers stays put.
                let anchor = CGPoint(x: value.startAnchor.x * size.width - size.width / 2,
                                     y: value.startAnchor.y * size.height - size.height / 2)
                let ratio = newZoom / zoom
                zoom = newZoom
                pan = Self.clamped(pan: CGSize(width: anchor.x - (anchor.x - pan.width) * ratio,
                                               height: anchor.y - (anchor.y - pan.height) * ratio),
                                   zoom: newZoom, map: map, size: size)
            }
            .onEnded { _ in lastMagnification = nil }
    }

    private func drag(size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 4)
            .onChanged { value in
                let previous = lastTranslation ?? .zero
                lastTranslation = value.translation
                pan = Self.clamped(pan: CGSize(width: pan.width + value.translation.width - previous.width,
                                               height: pan.height + value.translation.height - previous.height),
                                   zoom: zoom, map: map, size: size)
            }
            .onEnded { _ in lastTranslation = nil }
    }

    private func zoomControls(size: CGSize) -> some View {
        VStack(spacing: 0) {
            zoomButton("plus.magnifyingglass", label: language.text("Zoom in", "放大"), id: "lio.metro.map.zoom-in") {
                setZoom(zoom * 2, size: size)
            }
            Divider().frame(width: 28)
            zoomButton("minus.magnifyingglass", label: language.text("Zoom out", "缩小"), id: "lio.metro.map.zoom-out") {
                setZoom(zoom / 2, size: size)
            }
        }
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
        .overlay { RoundedRectangle(cornerRadius: LioTheme.Radius.small).stroke(LioTheme.hairline) }
        .padding(LioTheme.Spacing.sm)
    }

    private func zoomButton(_ symbol: String, label: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.body.weight(.semibold))
                .foregroundStyle(LioTheme.ink)
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .accessibilityLabel(label)
        .accessibilityIdentifier(id)
    }

    private func setZoom(_ value: CGFloat, size: CGSize) {
        let newZoom = min(max(value, 1), Self.maximumZoom)
        let ratio = newZoom / zoom
        let update = {
            zoom = newZoom
            pan = Self.clamped(pan: CGSize(width: pan.width * ratio, height: pan.height * ratio),
                               zoom: newZoom, map: map, size: size)
        }
        if reduceMotion { update() } else { withAnimation(LioTheme.Motion.change, update) }
    }

    // MARK: Drawing

    private func draw(in context: inout GraphicsContext, layout: Layout) {
        let gap = 36 * layout.scale // on-screen distance between typical neighbours
        let lineWidth = min(8, max(2.5, gap * 0.12))
        let visible = CGRect(origin: .zero, size: layout.size).insetBy(dx: -40, dy: -40)

        for line in map.lines {
            var path = Path()
            for (from, to) in line.edges {
                guard let a = map.station(from), let b = map.station(to) else { continue }
                path.move(to: layout.viewPoint(x: a.x, y: a.y))
                path.addLine(to: layout.viewPoint(x: b.x, y: b.y))
            }
            let rgb = line.rgb
            context.stroke(path, with: .color(Color(red: rgb.red, green: rgb.green, blue: rgb.blue)),
                           style: StrokeStyle(lineWidth: lineWidth, lineCap: .round, lineJoin: .round))
        }

        var labels: [(LioMetroMap.Station, CGPoint, CGFloat)] = []
        for station in map.stations {
            let point = layout.viewPoint(x: station.x, y: station.y)
            guard visible.contains(point) else { continue }
            let radius = station.isInterchange ? lineWidth * 1.1 + 1.5 : lineWidth * 0.75
            let dot = Path(ellipseIn: CGRect(x: point.x - radius, y: point.y - radius, width: radius * 2, height: radius * 2))
            context.fill(dot, with: .color(LioTheme.surface))
            context.stroke(dot, with: .color(LioTheme.ink), lineWidth: station.isInterchange ? 1.5 : 1)
            if station.id == selected?.id {
                let ring = Path(ellipseIn: CGRect(x: point.x - radius - 4, y: point.y - radius - 4,
                                                  width: radius * 2 + 8, height: radius * 2 + 8))
                context.stroke(ring, with: .color(LioTheme.vermilion), lineWidth: 3)
            }
            labels.append((station, point, radius))
        }

        // Interchanges are named first; other names appear once there is room for them.
        guard gap >= 22 else { return }
        let fontSize = min(13, max(9, gap * 0.24))
        var taken: [CGRect] = []
        let ordered = labels.filter { gap >= 40 || $0.0.isInterchange || $0.0.id == selected?.id }
            .sorted { ($0.0.id == selected?.id ? 0 : $0.0.isInterchange ? 1 : 2) < ($1.0.id == selected?.id ? 0 : $1.0.isInterchange ? 1 : 2) }
        for (station, point, radius) in ordered {
            let text = context.resolve(Text(station.name(in: language))
                .font(.system(size: fontSize, weight: station.isInterchange ? .semibold : .regular))
                .foregroundStyle(LioTheme.ink))
            let measured = text.measure(in: CGSize(width: 240, height: 60))
            let frame = CGRect(x: point.x + radius + 3, y: point.y - measured.height / 2,
                               width: measured.width, height: measured.height)
            guard !taken.contains(where: { $0.intersects(frame) }) else { continue }
            taken.append(frame)
            context.fill(Path(roundedRect: frame.insetBy(dx: -2, dy: 0), cornerRadius: 3),
                         with: .color(LioTheme.paper.opacity(0.8)))
            context.draw(text, in: frame)
        }
    }
}

/// One station: its names, lines and interchanges, and how to get there.
struct LioMetroStationSheet: View {
    let map: LioMetroMap
    let station: LioMetroMap.Station
    let language: LioLanguage
    let taxiEntry: LioTaxiEntry?
    let onTaxi: (LioTaxiPlace) -> Void
    @State private var searching = false
    @State private var notice: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(station.nameZH)
                            .font(LioTheme.display(.title).weight(.bold))
                            .textSelection(.enabled)
                            .accessibilityIdentifier("lio.metro.station.name-zh")
                        Text(station.nameEN)
                            .font(.title3)
                            .foregroundStyle(LioTheme.inkSecondary)
                            .accessibilityIdentifier("lio.metro.station.name-en")
                    }
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                        Text(language.text("Lines", "所属线路")).font(.headline).accessibilityAddTraits(.isHeader)
                        FlowChips(lines: map.lines(at: station), language: language)
                        if station.isInterchange {
                            Text(interchangeText)
                                .font(.subheadline)
                                .foregroundStyle(LioTheme.inkSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("lio.metro.station.interchange")
                        }
                    }
                    if taxiEntry != nil {
                        Button(action: taxi) {
                            action(language.text("Taxi to this station", "打车去这站"), symbol: "car.fill", prominent: true)
                                .overlay(alignment: .trailing) {
                                    if searching { ProgressView().tint(LioTheme.onVermilion).padding(.trailing, 16) }
                                }
                        }
                        .buttonStyle(.plain)
                        .disabled(searching)
                        .accessibilityIdentifier("lio.metro.station.taxi")
                    }
                    Button(action: directions) {
                        action(language.text("Directions in AMap", "用高德地图导航"),
                               symbol: "arrow.triangle.turn.up.right.diamond.fill")
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.metro.station.directions")
                    if let notice {
                        Text(notice).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                            .accessibilityIdentifier("lio.metro.station.notice")
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(18)
            }
            .background(LioTheme.paper)
            .foregroundStyle(LioTheme.ink)
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var interchangeText: String {
        let names = map.lines(at: station).map { $0.name(in: language) }
        return language.text("Interchange: change here between \(names.joined(separator: ", ")).",
                             "换乘站：可在此换乘\(names.joined(separator: "、"))。")
    }

    private func action(_ title: String, symbol: String, prominent: Bool = false) -> some View {
        Label(title, systemImage: symbol)
            .font(.headline)
            .foregroundStyle(prominent ? LioTheme.onVermilion : LioTheme.ink)
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(prominent ? LioTheme.vermilion : LioTheme.surface,
                        in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .overlay {
                if !prominent {
                    RoundedRectangle(cornerRadius: LioTheme.Radius.card).stroke(LioTheme.hairline).allowsHitTesting(false)
                }
            }
    }

    /// Finds "<station>地铁站" with the app's own place search, then opens the usual taxi page.
    private func taxi() {
        guard let taxiEntry else { return }
        let query = LioTaxiSearchQuery(text: map.searchName(for: station), city: map.city.taxiCity, near: nil)
        searching = true
        notice = nil
        Task { @MainActor in
            defer { searching = false }
            do {
                let places = try await taxiEntry.service.search(query)
                if let place = LioMetroStationAction.bestPlace(places, for: station) {
                    onTaxi(place)
                } else {
                    notice = LioTaxiSearchNotice.noMatches(for: query, language: language)
                }
            } catch {
                notice = LioTaxiSearchNotice.failure(error, language: language)
            }
        }
    }

    /// AMap searches by name (no coordinates are bundled); Apple Maps is the fallback.
    private func directions() {
        let urls = LioMetroStationAction.directionURLs(cityZH: map.city.name(in: .chinese), name: map.searchName(for: station))
        Task { @MainActor in
            for url in urls where await UIApplication.shared.open(url) { return }
            notice = language.text("Install AMap or Apple Maps to get directions.", "请安装高德地图或苹果地图后再导航。")
        }
    }
}

/// Line names as coloured chips, wrapping onto new rows.
private struct FlowChips: View {
    let lines: [LioMetroMap.Line]
    let language: LioLanguage

    var body: some View {
        LioMetroFlowLayout(spacing: 8) {
            ForEach(lines) { line in
                let rgb = line.rgb
                let color = Color(red: rgb.red, green: rgb.green, blue: rgb.blue)
                let light = 0.299 * rgb.red + 0.587 * rgb.green + 0.114 * rgb.blue > 0.6
                Text(line.name(in: language))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(light ? Color.black : Color.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(color, in: Capsule())
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lio.metro.station.lines")
    }
}

private struct LioMetroFlowLayout: Layout {
    let spacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let width = rows.map { $0.width }.max() ?? 0
        let height = rows.map(\.height).reduce(0, +) + spacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for index in row.items {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private func arrange(width: CGFloat, subviews: Subviews) -> [(items: [Int], width: CGFloat, height: CGFloat)] {
        var rows: [(items: [Int], width: CGFloat, height: CGFloat)] = []
        var current: (items: [Int], width: CGFloat, height: CGFloat) = ([], 0, 0)
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let needed = current.items.isEmpty ? size.width : current.width + spacing + size.width
            if needed > width, !current.items.isEmpty {
                rows.append(current)
                current = ([index], size.width, size.height)
            } else {
                current = (current.items + [index], needed, max(current.height, size.height))
            }
        }
        if !current.items.isEmpty { rows.append(current) }
        return rows
    }
}

/// Every station, searchable in English or Chinese; interchanges first.
struct LioMetroStationList: View {
    let map: LioMetroMap
    let language: LioLanguage
    let onSelect: (LioMetroMap.Station) -> Void
    @State private var query = ""
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(map.stations(matching: query)) { station in
                Button { onSelect(station) } label: {
                    HStack(spacing: 10) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(station.name(in: language)).font(.body).foregroundStyle(LioTheme.ink)
                            Text(language == .english ? station.nameZH : station.nameEN)
                                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                        }
                        Spacer(minLength: 8)
                        HStack(spacing: 3) {
                            ForEach(map.lines(at: station)) { line in
                                let rgb = line.rgb
                                Circle().fill(Color(red: rgb.red, green: rgb.green, blue: rgb.blue)).frame(width: 10, height: 10)
                            }
                        }
                        .accessibilityHidden(true)
                    }
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(station.name(in: language) + language.text(", ", "，")
                                    + map.lines(at: station).map { $0.name(in: language) }.joined(separator: language.text(", ", "、")))
            }
            .listStyle(.plain)
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always),
                        prompt: language.text("Station name in English or Chinese", "输入中文或英文站名"))
            .navigationTitle(language.text("Find a station", "查找车站"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.text("Close", "关闭")) { dismiss() }
                }
            }
        }
    }
}
#endif
