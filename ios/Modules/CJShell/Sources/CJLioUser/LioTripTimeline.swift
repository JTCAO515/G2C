#if os(iOS)
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
                let focusedName = day.stops.first { $0.id == focusedStop }?.name
                if day.stops.contains(where: { $0.point != nil }) {
                    VStack(alignment: .leading, spacing: 8) {
                        LioRouteMap(day: day, focusedStop: focusedStop,
                                    failed: { mapUnavailable = true }, loaded: { mapUnavailable = false })
                            .frame(height: 220)
                            .clipShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                            .accessibilityIdentifier("lio.trip.route-map")
                            .accessibilityLabel(language.text("Trip map", "行程地图"))
                            .accessibilityValue(focusedName ?? "")
                            .accessibilityAddTraits(.isImage)
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
                let ending = stop.endingText(language)
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

#endif
