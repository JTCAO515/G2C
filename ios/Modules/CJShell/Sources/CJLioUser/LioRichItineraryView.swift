#if os(iOS)
import SwiftUI
import CJRunClient

struct LioRichItineraryView: View {
    let itinerary: LioRichItinerary
    let language: LioLanguage
    @State private var selectedDay: Int?
    @State private var selection: LioRichItinerary.Stop?
    @State private var showingMap = false
    @State private var mapUnavailable = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var day: LioRichItinerary.Day? { itinerary.days.first { $0.number == selectedDay } ?? itinerary.days.first }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text(itinerary.title).font(LioTheme.display(.largeTitle)).accessibilityAddTraits(.isHeader)
                if itinerary.undated {
                    Text(language.text("Start date not set", "出发日期待定")).foregroundStyle(LioTheme.inkSecondary)
                }
                dayPicker
                if let day {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(day.theme).font(LioTheme.display(.title2)).accessibilityAddTraits(.isHeader)
                        Text(day.area).foregroundStyle(LioTheme.inkSecondary)
                    }
                    if !day.mapNumbers.isEmpty { map(day) }
                    if day.stops.isEmpty {
                        Text(language.text("No activities planned for this day yet.", "这一天还没有安排。"))
                    }
                    VStack(spacing: 12) {
                        ForEach(Array(day.stops.enumerated()), id: \.element.id) { index, stop in
                            stopCard(stop, number: index + 1)
                            if let leg = day.leg(after: index) {
                                Label(leg.description(language), systemImage: leg.symbol)
                                    .font(.subheadline)
                                    .foregroundStyle(LioTheme.inkSecondary)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.leading, 20)
                                    .accessibilityIdentifier("lio.rich.leg.\(index + 1)")
                            }
                        }
                    }
                }
                lodging
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(16)
        }
        .foregroundStyle(LioTheme.ink)
        .lioPage()
        .tint(LioTheme.vermilion)
        .sheet(item: $selection) { stop in LioRichStopDetail(stop: stop, language: language) }
    }

    private var dayPicker: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 8) {
                ForEach(itinerary.days) { day in
                    Button {
                        withAnimation(LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion)) {
                            selectedDay = day.number
                            showingMap = false
                            mapUnavailable = false
                        }
                    } label: {
                        Text(day.date ?? language.text("Day \(day.number)", "第 \(day.number) 天"))
                            .font(.subheadline.weight(.semibold))
                            .padding(.horizontal, 16).frame(minHeight: 44)
                            .background(self.day?.id == day.id ? LioTheme.surfaceSunken : LioTheme.surface, in: Capsule())
                            .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(self.day?.id == day.id ? [.isSelected] : [])
                    .accessibilityIdentifier("lio.rich.day.\(day.number)")
                }
            }
            .padding(.vertical, 2)
        }
        .scrollIndicators(.hidden)
    }

    private func stopCard(_ stop: LioRichItinerary.Stop, number: Int) -> some View {
        Button { selection = stop } label: {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top, spacing: 12) {
                    Text("\(number)").font(.headline).foregroundStyle(LioTheme.onVermilion)
                        .frame(minWidth: 32, minHeight: 32).background(LioTheme.vermilion, in: Circle())
                    VStack(alignment: .leading, spacing: 6) {
                        Label(stop.kind.title(language), systemImage: stop.kind.symbol).font(.subheadline)
                        if let time = stop.time { Text(time).font(.subheadline).foregroundStyle(LioTheme.inkSecondary) }
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                Text(stop.place.displayName(language)).font(.headline)
                if language == .english { Text(stop.place.nameZH).font(.subheadline).foregroundStyle(LioTheme.inkSecondary) }
                Text(stop.text).font(.body)
                if stop.fixed == true {
                    Label(language.text("Fixed plan", "固定安排"), systemImage: "lock.fill").font(.subheadline)
                }
                if !stop.place.matched {
                    Text(language.text("Suggested place", "地点建议")).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .padding(16)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("lio.rich.stop.\(stop.id)")
    }

    @ViewBuilder private func map(_ day: LioRichItinerary.Day) -> some View {
        if showingMap {
            LioRouteMap(day: day.mapDay, focusedStop: nil, failed: { mapUnavailable = true }, loaded: { mapUnavailable = false })
                .frame(height: 220)
                .clipShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                .accessibilityLabel(language.text("Trip map", "行程地图"))
                .accessibilityAddTraits(.isImage)
                .accessibilityIdentifier("lio.rich.map")
            if mapUnavailable { Text(language.text("Map unavailable", "暂时无法显示地图")).foregroundStyle(LioTheme.inkSecondary) }
        } else {
            Button { showingMap = true } label: {
                Label(language.text("Show map", "查看地图"), systemImage: "map")
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityIdentifier("lio.rich.show-map")
        }
        Text(language.text("Viewing the map sends its area to Apple.", "查看地图时，Apple 会收到地图显示区域。"))
            .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
        Link(destination: URL(string: "https://www.apple.com/legal/internet-services/maps/")!) {
            RunReadableText(text: language.text("Apple Maps legal information", "Apple 地图法律信息"), style: .caption)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
        }
    }

    private var lodging: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label(language.text("Places to stay", "住宿建议"), systemImage: "bed.double")
                .font(LioTheme.display(.title2)).accessibilityAddTraits(.isHeader)
            Text(itinerary.lodgingArea).foregroundStyle(LioTheme.inkSecondary)
            ForEach(itinerary.hotels) { hotel in
                VStack(alignment: .leading, spacing: 8) {
                    Text(hotel.place.displayName(language)).font(.headline)
                    if language == .english { Text(hotel.place.nameZH).font(.subheadline) }
                    if !hotel.place.matched { Text(language.text("Suggested place", "地点建议")).font(.subheadline) }
                    if let note = hotel.note { Text(note) }
                }
                .frame(maxWidth: .infinity, alignment: .leading).padding(16)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            }
        }
    }
}

private struct LioRichStopDetail: View {
    let stop: LioRichItinerary.Stop
    let language: LioLanguage
    @State private var showingDriver = false
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Button(language.text("Done", "完成")) { dismiss() }
                    .frame(minHeight: 44).contentShape(Rectangle()).accessibilityIdentifier("lio.rich.detail.done")
                Label(stop.kind.title(language), systemImage: stop.kind.symbol).font(.subheadline)
                Text(stop.place.displayName(language)).font(LioTheme.display(.title)).accessibilityAddTraits(.isHeader)
                if language == .english { Text(stop.place.nameZH).font(.title3) }
                if let time = stop.time { Text(time).foregroundStyle(LioTheme.inkSecondary) }
                if stop.fixed == true { Label(language.text("Fixed plan", "固定安排"), systemImage: "lock.fill") }
                Text(stop.text)
                if let address = stop.place.driverAddress { Text(address).textSelection(.enabled) }
                else { Text(language.text("Address not available yet.", "暂无地址。")).foregroundStyle(LioTheme.inkSecondary) }
                if let note = stop.note { Text(note) }
                if let tip = stop.tip { Label(tip, systemImage: "lightbulb").fixedSize(horizontal: false, vertical: true) }
                Button { showingDriver = true } label: {
                    Label(language.text("Show driver", "给司机看"), systemImage: "taxi")
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
                }
                .disabled(stop.place.driverAddress == nil)
                .accessibilityIdentifier("lio.rich.driver")
            }.padding(20)
        }
        .foregroundStyle(LioTheme.ink).lioPage().tint(LioTheme.vermilion)
        .sheet(isPresented: $showingDriver) { LioDriverCard(place: stop.place, language: language) }
    }
}

private struct LioDriverCard: View {
    let place: LioRichItinerary.Place
    let language: LioLanguage
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                Button(language.text("Done", "完成")) { dismiss() }
                    .frame(minHeight: 44).contentShape(Rectangle()).accessibilityIdentifier("lio.rich.driver.done")
                Text(language.text("Please take me here", "请送我到这里"))
                    .font(.headline).foregroundStyle(LioTheme.inkSecondary)
                Text(place.nameZH).font(.largeTitle.weight(.bold)).accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("lio.rich.driver.name")
                if let address = place.driverAddress {
                    Text(address).font(.title2).accessibilityIdentifier("lio.rich.driver.address")
                }
            }
            .textSelection(.enabled).fixedSize(horizontal: false, vertical: true).padding(24)
        }.foregroundStyle(LioTheme.ink).lioPage()
    }
}
#endif
