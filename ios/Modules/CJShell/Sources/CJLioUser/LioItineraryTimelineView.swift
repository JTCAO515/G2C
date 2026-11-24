#if os(iOS)
import MapKit
import SwiftUI

/// #1453 proposal: a planned trip as day tabs, a day map and a timeline of stops with travel legs between them.
/// It reads the existing `LioRichItinerary` view model; actions are shown for review and are not wired yet.
struct LioItineraryTimelineView: View {
    let itinerary: LioRichItinerary
    let language: LioLanguage
    @State private var selectedDay = 1

    private var day: LioRichItinerary.Day? { itinerary.days.first { $0.number == selectedDay } ?? itinerary.days.first }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                header
                dayPicker
                if let day {
                    dayHeader(day)
                    dayMap(day)
                    timeline(day)
                    dayActions
                }
                stayCard
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Trip plan", "行程方案"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text(itinerary.title).font(LioTheme.display(.title).weight(.bold))
            let stops = itinerary.days.reduce(0) { $0 + $1.stops.count }
            Text(language.text("\(itinerary.days.count) days · \(stops) stops · dates not set",
                               "\(itinerary.days.count) 天 · \(stops) 个地点 · 日期待定"))
                .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
            HStack(spacing: LioTheme.Spacing.xs) {
                Button { } label: { Label(language.text("Save to Trips", "保存到行程"), systemImage: "bookmark") }
                    .buttonStyle(LioPrimaryButtonStyle())
                Button { } label: { Label(language.text("Share", "分享"), systemImage: "square.and.arrow.up") }
                    .buttonStyle(LioSecondaryButtonStyle(fullWidth: false))
            }
        }
    }

    private var dayPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: LioTheme.Spacing.xs) {
                ForEach(itinerary.days) { item in
                    let selected = item.number == (day?.number ?? 0)
                    Button { selectedDay = item.number } label: {
                        VStack(spacing: 2) {
                            Text(language.text("Day \(item.number)", "第 \(item.number) 天")).font(.subheadline.weight(.semibold))
                            Text(item.area).font(.caption).lineLimit(1)
                        }
                        .foregroundStyle(selected ? LioTheme.onVermilion : LioTheme.ink)
                        .padding(.horizontal, 14).padding(.vertical, 8)
                        .background(selected ? LioTheme.vermilion : LioTheme.surface, in: Capsule())
                        .overlay { Capsule().stroke(selected ? .clear : LioTheme.hairline) }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func dayHeader(_ day: LioRichItinerary.Day) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(day.theme).font(.title3.weight(.semibold))
            Label(day.area, systemImage: "mappin.and.ellipse").font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
        }
    }

    private func dayMap(_ day: LioRichItinerary.Day) -> some View {
        let points = day.stops.enumerated().compactMap { index, stop in
            stop.place.mapPoint.map { (index + 1, stop.place.displayName(language), $0) }
        }
        return Map {
            ForEach(points, id: \.0) { number, name, point in
                Marker(name, monogram: Text("\(number)"),
                       coordinate: .init(latitude: point.latitude, longitude: point.longitude))
                    .tint(LioTheme.vermilion)
            }
        }
        .frame(height: 180)
        .clipShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .allowsHitTesting(false)
    }

    private func timeline(_ day: LioRichItinerary.Day) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(day.stops.enumerated()), id: \.element.id) { index, stop in
                stopRow(stop, number: index + 1, last: index == day.stops.count - 1)
                if let leg = day.leg(after: index) { legRow(leg) }
            }
        }
    }

    private func stopRow(_ stop: LioRichItinerary.Stop, number: Int, last: Bool) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(stop.time ?? "—").font(.subheadline.weight(.semibold)).monospacedDigit()
                .frame(width: 48, alignment: .trailing).padding(.top, 14)
            VStack(spacing: 0) {
                Text("\(number)").font(.caption.weight(.bold)).foregroundStyle(LioTheme.onVermilion)
                    .frame(width: 24, height: 24).background(LioTheme.vermilion, in: Circle()).padding(.top, 12)
                Rectangle().fill(LioTheme.hairline).frame(width: 2).frame(maxHeight: .infinity).opacity(last ? 0 : 1)
            }
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: stop.kind.symbol).foregroundStyle(LioTheme.vermilion).font(.footnote)
                    Text(stop.kind.title(language)).font(.caption.weight(.medium)).foregroundStyle(LioTheme.inkSecondary)
                    if let note = stop.note {
                        Text("· " + note).font(.caption).foregroundStyle(LioTheme.inkSecondary).lineLimit(1)
                    }
                }
                Text(stop.place.displayName(language)).font(.headline)
                if language == .english { Text(stop.place.nameZH).font(.subheadline).foregroundStyle(LioTheme.inkSecondary) }
                Text(stop.text).font(.subheadline).foregroundStyle(LioTheme.ink).fixedSize(horizontal: false, vertical: true)
                if let tip = stop.tip {
                    Label(tip, systemImage: "lightbulb").font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                }
                if stop.place.driverAddress != nil {
                    HStack(spacing: LioTheme.Spacing.xs) {
                        chip(language.text("Taxi", "打车"), "car.fill")
                        chip(language.text("Map", "导航"), "arrow.triangle.turn.up.right.diamond")
                        chip(language.text("Driver", "司机卡"), "character.bubble")
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .padding(.bottom, 4)
        }
    }

    private func legRow(_ leg: LioRichItinerary.Leg) -> some View {
        HStack(spacing: 10) {
            Spacer().frame(width: 48)
            Rectangle().fill(LioTheme.hairline).frame(width: 2, height: 34).padding(.horizontal, 11)
            Label(leg.description(language), systemImage: leg.symbol)
                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
        }
    }

    private func chip(_ title: String, _ symbol: String) -> some View {
        Label(title, systemImage: symbol)
            .font(.caption.weight(.semibold))
            .foregroundStyle(LioTheme.vermilion)
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background(LioTheme.vermilion.opacity(0.08), in: Capsule())
            .lineLimit(1)
    }

    private var dayActions: some View {
        HStack(spacing: LioTheme.Spacing.xs) {
            Button { } label: { Label(language.text("Change this day", "调整这一天"), systemImage: "slider.horizontal.3") }
            Button { } label: { Label(language.text("Ask Lio", "问 Lio"), systemImage: "bubble.left") }
        }
        .buttonStyle(LioSecondaryButtonStyle())
    }

    @ViewBuilder private var stayCard: some View {
        if !itinerary.hotels.isEmpty {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                Label(language.text("Where to stay", "住宿建议"), systemImage: "bed.double").font(.headline)
                Text(itinerary.lodgingArea).font(.subheadline)
                ForEach(itinerary.hotels) { hotel in
                    Text("· " + hotel.place.displayName(language) + (hotel.note.map { " — " + $0 } ?? ""))
                        .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        }
    }
}

extension LioItineraryTimelineView {
    static var previewRequested: Bool {
        #if DEBUG
        ProcessInfo.processInfo.arguments.contains("--lio-itinerary-preview")
        #else
        false
        #endif
    }

    /// Proposal fixture: well-known Beijing sights with approximate public coordinates, for screenshots only.
    static func beijingPreview(_ language: LioLanguage) -> LioRichItinerary {
        #if DEBUG
        func t(_ en: String, _ zh: String) -> String { language.text(en, zh) }
        func place(_ zh: String, _ en: String, _ lat: Double, _ lng: Double) -> LioRichItinerary.Place {
            .init(nameZH: zh, nameEN: en, address: zh, matched: true, point: .init(latitude: lat, longitude: lng))
        }
        let a = LioRichItinerary.Stop(id: "d1a", kind: .sight, text: t("Watch the flag-raising area and walk the square.", "看升旗区域，走一走广场。"),
                                      time: "08:30", place: place("天安门广场", "Tian'anmen Square", 39.9055, 116.3976),
                                      note: t("1 hr", "约 1 小时"), tip: t("Bring your passport for the security check.", "安检需要护照。"))
        let b = LioRichItinerary.Stop(id: "d1b", kind: .sight, text: t("Halls, courtyards and the imperial garden, south to north.", "由南向北看大殿、院落和御花园。"),
                                      time: "09:45", place: place("故宫博物院", "Palace Museum", 39.9163, 116.3972),
                                      note: t("3 hrs", "约 3 小时"), tip: t("Book tickets 7 days ahead; closed Mondays.", "提前 7 天预约，周一闭馆。"))
        let c = LioRichItinerary.Stop(id: "d1c", kind: .meal, text: t("Roast duck lunch near Wangfujing.", "在王府井附近吃烤鸭。"),
                                      time: "13:15", place: place("四季民福烤鸭店（故宫店）", "Siji Minfu Roast Duck", 39.9135, 116.4035),
                                      note: t("1 hr", "约 1 小时"), tip: nil)
        let d = LioRichItinerary.Stop(id: "d1d", kind: .sight, text: t("Climb for the view over the Forbidden City.", "登高俯瞰故宫全景。"),
                                      time: "15:00", place: place("景山公园", "Jingshan Park", 39.9255, 116.3966),
                                      note: t("1 hr", "约 1 小时"), tip: t("Best light before sunset.", "日落前光线最好。"))
        let day1 = LioRichItinerary.Day(number: 1, date: nil, theme: t("Imperial centre", "皇城中轴"), area: t("Dongcheng", "东城区"),
                                        stops: [a, b, c, d], legs: [
                                            .init(fromID: a.id, toID: b.id, estimate: .init(mode: .walking, seconds: 900, metres: 1100)),
                                            .init(fromID: b.id, toID: c.id, estimate: .init(mode: .walking, seconds: 1080, metres: 1300)),
                                            .init(fromID: c.id, toID: d.id, estimate: .init(mode: .taxi, seconds: 600, metres: 2600)),
                                        ])
        let e = LioRichItinerary.Stop(id: "d2a", kind: .sight, text: t("Walk the restored Mutianyu section; cable car up.", "游览慕田峪长城，可坐缆车上山。"),
                                      time: "08:00", place: place("慕田峪长城", "Mutianyu Great Wall", 40.4319, 116.5704),
                                      note: t("4 hrs", "约 4 小时"), tip: t("About 90 minutes by car from the city.", "从市区开车约 90 分钟。"))
        let f = LioRichItinerary.Stop(id: "d2b", kind: .meal, text: t("Late lunch back in town.", "回城吃晚一点的午饭。"),
                                      time: "14:30", place: place("簋街", "Guijie Food Street", 39.9407, 116.4268),
                                      note: t("1 hr", "约 1 小时"), tip: nil)
        let day2 = LioRichItinerary.Day(number: 2, date: nil, theme: t("Great Wall day", "长城一日"), area: t("Huairou", "怀柔区"),
                                        stops: [e, f], legs: [.init(fromID: e.id, toID: f.id,
                                                                    estimate: .init(mode: .taxi, seconds: 5400, metres: 72000))])
        let g = LioRichItinerary.Stop(id: "d3a", kind: .sight, text: t("Morning tai chi and the Hall of Prayer.", "看晨练和祈年殿。"),
                                      time: "08:30", place: place("天坛公园", "Temple of Heaven", 39.8822, 116.4066),
                                      note: t("2 hrs", "约 2 小时"), tip: nil)
        let h = LioRichItinerary.Stop(id: "d3b", kind: .sight, text: t("Hutong lanes and Houhai lake.", "逛胡同和后海。"),
                                      time: "11:30", place: place("南锣鼓巷", "Nanluoguxiang", 39.9370, 116.4033),
                                      note: t("2 hrs", "约 2 小时"), tip: nil)
        let day3 = LioRichItinerary.Day(number: 3, date: nil, theme: t("Temples and hutongs", "天坛与胡同"), area: t("Dongcheng", "东城区"),
                                        stops: [g, h], legs: [.init(fromID: g.id, toID: h.id,
                                                                    estimate: .init(mode: .transit, seconds: 1800, metres: 7000))])
        return .init(title: t("Three free days in Beijing", "北京三天自由行"), undated: true, days: [day1, day2, day3],
                     lodgingArea: t("Stay around Wangfujing or Dongsi for easy metro access.", "住王府井或东四一带，地铁方便。"),
                     hotels: [.init(id: "h1", place: place("王府井一带", "Wangfujing area", 39.914, 116.410),
                                    note: t("Walk to the Palace Museum", "步行可到故宫"))])
        #else
        // Release builds never show the proposal preview.
        return .init(title: "", undated: true, days: [], lodgingArea: "", hotels: [])
        #endif
    }
}
#endif
