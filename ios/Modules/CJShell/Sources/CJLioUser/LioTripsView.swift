#if os(iOS)
import MapKit
import SwiftUI
import CJRunClient

struct LioItineraryCard: View {
    let itinerary: LioItinerary
    let language: LioLanguage
    let showTrips: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            RunReadableText(text: itinerary.description)
            RunReadableText(text: itinerary.title, style: .headline)
                .accessibilityAddTraits(.isHeader)
            ForEach(itinerary.days) { day in
                DisclosureGroup {
                    LioDayStops(day: day, language: language)
                        .padding(.vertical, 6)
                } label: {
                    Text(dayTitle(day, language))
                        .frame(minHeight: 44, alignment: .leading)
                }
                .accessibilityIdentifier("lio.trip.day.\(day.number)")
            }
            Button(action: showTrips) {
                RunReadableText(text: language.text("Saved to Trips · View", "已保存到行程 · 查看"))
                    .frame(minHeight: 44, alignment: .leading)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier("lio.trip.show")
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 20))
    }
}

struct LioTripsView: View {
    let itineraries: [LioItinerary]
    let language: LioLanguage
    let openChat: () -> Void
    @State private var mapDay: LioItinerary.Day?

    var body: some View {
        NavigationStack {
            Group {
                if itineraries.isEmpty {
                    ContentUnavailableView {
                        Label(language.text("No trips yet", "还没有行程"), systemImage: "suitcase")
                    } description: {
                        Text(language.text("Tell Lio where you’d like to go.", "告诉 Lio 你想去哪儿。"))
                    } actions: {
                        Button(language.text("Chat with Lio", "和 Lio 聊聊"), action: openChat)
                            .buttonStyle(.bordered)
                    }
                } else {
                    List {
                        ForEach(itineraries) { itinerary in
                            Section(itinerary.title) {
                                ForEach(itinerary.days) { day in
                                    VStack(alignment: .leading, spacing: 10) {
                                        Text(dayTitle(day, language))
                                            .font(.headline)
                                            .accessibilityAddTraits(.isHeader)
                                        LioDayStops(day: day, language: language)
                                        if day.stops.contains(where: { $0.point != nil }) {
                                            Button(language.text("Show on map", "在地图上看")) { mapDay = day }
                                                .frame(minHeight: 44, alignment: .leading)
                                                .accessibilityIdentifier("lio.trip.map.\(day.number)")
                                        }
                                    }
                                    .padding(.vertical, 8)
                                }
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle(language.text("Trips", "行程"))
            .sheet(item: $mapDay) { day in
                LioDayMap(day: day, language: language)
            }
        }
    }
}

private struct LioDayStops: View {
    let day: LioItinerary.Day
    let language: LioLanguage

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(day.stops) { stop in
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: stop.fixed ? "lock.fill" : "circle.fill")
                        .font(.caption)
                        .frame(width: 20, height: 20)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(stop.time).font(.footnote)
                        RunReadableText(text: stop.name)
                        if stop.fixed {
                            Text(language.text("Fixed plan", "固定安排")).font(.footnote)
                        }
                    }
                }
            }
        }
    }
}

private struct LioDayMap: View {
    let day: LioItinerary.Day
    let language: LioLanguage
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Map {
                ForEach(day.stops) { stop in
                    if let point = stop.point {
                        Marker(stop.name, coordinate: CLLocationCoordinate2D(latitude: point.latitude, longitude: point.longitude))
                    }
                }
            }
            .navigationTitle(dayTitle(day, language))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(language.text("Done", "完成")) { dismiss() }
                }
            }
        }
    }
}

private func dayTitle(_ day: LioItinerary.Day, _ language: LioLanguage) -> String {
    language.text("Day \(day.number)", "第 \(day.number) 天")
}
#endif
