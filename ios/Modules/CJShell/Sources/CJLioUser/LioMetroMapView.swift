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

    @State private var viewport = LioMetroViewport()
    /// Live gestures. They reset by themselves when a gesture ends or the system cancels it.
    @GestureState private var pinch: Pinch?
    @GestureState private var dragOffset: CGSize = .zero
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var colorScheme

    private var palette: LioMetroPalette { colorScheme == .dark ? .dark : .light }

    private struct Pinch: Equatable {
        let magnification: CGFloat
        let anchor: UnitPoint
    }
    /// How far from a station's dot, in points, a tap still selects it.
    static let tapReach: CGFloat = 22

    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            let shown = viewport.showing(magnification: pinch?.magnification,
                                         anchor: anchorPoint(pinch?.anchor ?? .center, size: size), drag: dragOffset)
                .clamped(content: Self.content(map: map, size: size), view: size)
            let layout = Layout(map: map, size: size, zoom: shown.zoom, pan: shown.pan)
            ZStack {
                LioMetroPaperBackground(palette: palette)
                Canvas { context, _ in draw(in: &context, layout: layout) }
            }
                .contentShape(Rectangle())
                .gesture(magnify(size: size).simultaneously(with: drag(size: size)))
                .onTapGesture { location in
                    let point = layout.mapPoint(location)
                    if let station = map.station(nearX: point.x, y: point.y, radius: Self.tapReach / layout.scale) {
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

    /// The map's size in points at zoom 1, fitted to the view.
    static func content(map: LioMetroMap, size: CGSize) -> CGSize {
        let fit = Layout(map: map, size: size, zoom: 1, pan: .zero).scale
        return CGSize(width: map.width * fit, height: map.height * fit)
    }

    private func anchorPoint(_ anchor: UnitPoint, size: CGSize) -> CGPoint {
        CGPoint(x: anchor.x * size.width - size.width / 2, y: anchor.y * size.height - size.height / 2)
    }

    /// Commit a viewport; clamp it only when no other gesture is still live, so the picture never jumps.
    private func commit(_ next: LioMetroViewport, size: CGSize, otherGestureLive: Bool) {
        viewport = otherGestureLive ? next : next.clamped(content: Self.content(map: map, size: size), view: size)
    }

    private func magnify(size: CGSize) -> some Gesture {
        MagnifyGesture()
            .updating($pinch) { value, state, _ in
                state = Pinch(magnification: value.magnification, anchor: value.startAnchor)
            }
            .onEnded { value in
                commit(viewport.endingPinch(by: value.magnification, about: anchorPoint(value.startAnchor, size: size),
                                            liveDrag: dragOffset),
                       size: size, otherGestureLive: dragOffset != .zero)
            }
    }

    private func drag(size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 4)
            .updating($dragOffset) { value, state, _ in state = value.translation }
            .onEnded { value in
                commit(viewport.dragged(by: value.translation), size: size, otherGestureLive: pinch != nil)
            }
    }

    private func zoomControls(size: CGSize) -> some View {
        VStack(spacing: 0) {
            zoomButton("arrow.down.right.and.arrow.up.left", label: language.text("Whole map", "全图"), id: "lio.metro.map.fit") {
                showWholeMap()
            }
            .disabled(viewport == LioMetroViewport())
            Divider().frame(width: 28)
            zoomButton("plus.magnifyingglass", label: language.text("Zoom in", "放大"), id: "lio.metro.map.zoom-in") {
                setZoom(viewport.zoom * 2, size: size)
            }
            Divider().frame(width: 28)
            zoomButton("minus.magnifyingglass", label: language.text("Zoom out", "缩小"), id: "lio.metro.map.zoom-out") {
                setZoom(viewport.zoom / 2, size: size)
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

    private func showWholeMap() {
        if reduceMotion { viewport = LioMetroViewport() } else { withAnimation(LioTheme.Motion.change) { viewport = LioMetroViewport() } }
    }

    private func setZoom(_ value: CGFloat, size: CGSize) {
        // Zoom about the view's centre, like a pinch there.
        let next = viewport.pinched(by: value / viewport.zoom, about: .zero)
            .clamped(content: Self.content(map: map, size: size), view: size)
        if reduceMotion { viewport = next } else { withAnimation(LioTheme.Motion.change) { viewport = next } }
    }

    // MARK: Drawing

    private func draw(in context: inout GraphicsContext, layout: Layout) {
        let gap = 36 * layout.scale // on-screen distance between typical neighbours
        // Thin and small for the whole map, growing as the traveller zooms in.
        let lineWidth = min(7, max(1.4, gap * 0.11))
        let visible = CGRect(origin: .zero, size: layout.size).insetBy(dx: -40, dy: -40)
        let colors = palette

        // Water first, so lines and stations sit on top of it.
        let waterWidth = max(8, gap * 0.7)
        for water in map.water {
            var path = Path()
            path.addLines(water.points.map { layout.viewPoint(x: $0.x, y: $0.y) })
            context.stroke(path, with: .color(colors.water),
                           style: StrokeStyle(lineWidth: waterWidth, lineCap: .round, lineJoin: .round))
            context.stroke(path, with: .color(colors.waterCurrent),
                           style: StrokeStyle(lineWidth: max(1, waterWidth * 0.1), lineCap: .round, lineJoin: .round,
                                              dash: [2, 6]))
        }

        for line in map.lines {
            var path = Path()
            for (from, to) in line.edges {
                guard let a = map.station(from), let b = map.station(to) else { continue }
                path.move(to: layout.viewPoint(x: a.x, y: a.y))
                path.addLine(to: layout.viewPoint(x: b.x, y: b.y))
            }
            context.stroke(path, with: .color(Self.color(line)),
                           style: StrokeStyle(lineWidth: lineWidth, lineCap: .round, lineJoin: .round))
        }

        var labels: [(LioMetroMap.Station, CGPoint, CGFloat)] = []
        for station in map.stations {
            let point = layout.viewPoint(x: station.x, y: station.y)
            guard visible.contains(point) else { continue }
            let radius: CGFloat
            if station.isInterchange {
                // Interchanges: a light dot with a fine warm-grey ring.
                radius = lineWidth * 0.95 + 0.8
                let dot = Path(ellipseIn: CGRect(x: point.x - radius, y: point.y - radius, width: radius * 2, height: radius * 2))
                context.fill(dot, with: .color(colors.interchangeFill))
                context.stroke(dot, with: .color(colors.interchangeRing), lineWidth: max(0.8, lineWidth * 0.32))
            } else {
                // Other stations take their line's colour, so the map is not black and white.
                radius = lineWidth * 0.55
                let dot = Path(ellipseIn: CGRect(x: point.x - radius, y: point.y - radius, width: radius * 2, height: radius * 2))
                context.fill(dot, with: .color(colors.stationFill))
                let line = station.lines.first.flatMap(map.line)
                context.stroke(dot, with: .color(line.map(Self.color) ?? colors.label), lineWidth: max(0.8, lineWidth * 0.45))
            }
            if station.id == selected?.id {
                let ring = Path(ellipseIn: CGRect(x: point.x - radius - 4, y: point.y - radius - 4,
                                                  width: radius * 2 + 8, height: radius * 2 + 8))
                context.stroke(ring, with: .color(LioTheme.vermilion), lineWidth: 3)
            }
            labels.append((station, point, radius))
        }

        // Names: the whole map shows only the biggest interchanges; more appear as there is room.
        func rank(_ station: LioMetroMap.Station) -> Int {
            station.id == selected?.id ? 0 : station.lines.count >= 3 ? 1 : station.isInterchange ? 2 : 3
        }
        let limit = gap >= 40 ? 3 : gap >= 26 ? 2 : 1
        let fontSize = min(13, max(9, gap * 0.24))
        var taken: [CGRect] = []
        for (station, point, radius) in labels.filter({ rank($0.0) <= limit }).sorted(by: { rank($0.0) < rank($1.0) }) {
            let text = context.resolve(Text(station.name(in: language))
                .font(.system(size: fontSize, weight: station.isInterchange ? .semibold : .regular))
                .foregroundStyle(colors.label))
            let measured = text.measure(in: CGSize(width: 240, height: 60))
            let frame = CGRect(x: point.x + radius + 3, y: point.y - measured.height / 2,
                               width: measured.width, height: measured.height)
            guard !taken.contains(where: { $0.intersects(frame) }) else { continue }
            taken.append(frame)
            context.fill(Path(frame.insetBy(dx: -2, dy: 0)), with: .color(colors.background.opacity(0.85)))
            context.draw(text, in: frame)
        }

        // River names last, on the water itself, at the first stretch (from the middle out) where
        // they cover no station name.
        guard gap >= 18 else { return }
        for water in map.water where water.points.count >= 2 {
            let name = context.resolve(Text(water.name(in: language))
                .font(.system(size: min(14, max(10, gap * 0.28)), weight: .medium).italic())
                .foregroundStyle(colors.waterLabel))
            let size = name.measure(in: CGSize(width: 240, height: 60))
            let stretches = Array(zip(water.points, water.points.dropFirst()))
            let middle = stretches.count / 2
            let order = stretches.indices.sorted { abs($0 - middle) < abs($1 - middle) }
            for index in order {
                let (a, b) = stretches[index]
                let centre = layout.viewPoint(x: (a.x + b.x) / 2, y: (a.y + b.y) / 2)
                let frame = CGRect(x: centre.x - size.width / 2, y: centre.y - size.height / 2,
                                   width: size.width, height: size.height)
                guard CGRect(origin: .zero, size: layout.size).contains(frame),
                      !taken.contains(where: { $0.intersects(frame) }) else { continue }
                context.draw(name, in: frame)
                break
            }
        }
    }

    private static func color(_ line: LioMetroMap.Line) -> Color {
        let rgb = line.rgb
        return Color(red: rgb.red, green: rgb.green, blue: rgb.blue)
    }
}

/// The map's own colours (#1450 look, "warm paper"): a soft paper background with schematic water,
/// line-coloured stations and warm-grey names, with a matching dark set.
struct LioMetroPalette {
    let background: Color
    let grain: Color
    let vignette: Color
    let water: Color
    let waterCurrent: Color
    let waterLabel: Color
    let label: Color
    let interchangeFill: Color
    let interchangeRing: Color
    let stationFill: Color

    private static func hex(_ value: Int, _ alpha: Double = 1) -> Color {
        Color(red: Double((value >> 16) & 0xFF) / 255, green: Double((value >> 8) & 0xFF) / 255,
              blue: Double(value & 0xFF) / 255).opacity(alpha)
    }

    static let light = LioMetroPalette(
        background: hex(0xF3EEE4), grain: hex(0x6B5A3E, 0.07), vignette: hex(0x6B5A3E, 0.14),
        water: hex(0xC9DDE6), waterCurrent: hex(0xA9C6D3, 0.8), waterLabel: hex(0x6F96A8),
        label: hex(0x3B3732), interchangeFill: hex(0xFFFFFF), interchangeRing: hex(0x5B544B), stationFill: hex(0xFFFFFF))

    static let dark = LioMetroPalette(
        background: hex(0x1F1D1A), grain: hex(0xF3EEE4, 0.05), vignette: hex(0x000000, 0.35),
        water: hex(0x263840), waterCurrent: hex(0x3A5562, 0.9), waterLabel: hex(0x7FA6B8),
        label: hex(0xEAE4D9), interchangeFill: hex(0xF1ECE3), interchangeRing: hex(0x1F1D1A), stationFill: hex(0x1F1D1A))
}

/// Paper behind the map: a flat colour, a fine fixed grain and a soft vignette. It does not move
/// with the map, so it is drawn once per size rather than on every gesture frame.
private struct LioMetroPaperBackground: View {
    let palette: LioMetroPalette

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                palette.background
                Canvas { context, size in
                    var seed: UInt64 = 0x9E3779B97F4A7C15
                    func next() -> Double {
                        seed = seed &* 6364136223846793005 &+ 1442695040888963407
                        return Double(seed >> 11) / Double(1 << 53)
                    }
                    let count = Int(size.width * size.height / 90)
                    for _ in 0..<count {
                        let side = 0.6 + next() * 0.9
                        context.fill(Path(CGRect(x: next() * size.width, y: next() * size.height, width: side, height: side)),
                                     with: .color(palette.grain))
                    }
                }
                RadialGradient(colors: [.clear, palette.vignette], center: .center,
                               startRadius: min(proxy.size.width, proxy.size.height) * 0.45,
                               endRadius: max(proxy.size.width, proxy.size.height) * 0.75)
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
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
