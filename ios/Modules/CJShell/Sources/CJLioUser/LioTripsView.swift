#if os(iOS)
import MapKit
import SwiftUI
import CJRunClient
import CJTripClient

struct LioItineraryCard: View {
    let itinerary: LioItinerary
    let language: LioLanguage
    let showTrips: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let description = itinerary.description { RunReadableText(text: description) }
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
    let library: LioTripLibrary?
    let openChat: () -> Void
    @State private var mapDay: LioItinerary.Day?
    @State private var saved: [StructuredTripSummary]?
    @State private var listUnavailable = false
    @State private var listAttempt = 0

    var body: some View {
        NavigationStack {
            Group {
                if itineraries.isEmpty && library != nil && saved == nil {
                    if listUnavailable {
                        ContentUnavailableView {
                            Label(language.text("Trips unavailable", "暂时无法显示行程"), systemImage: "suitcase")
                        } actions: {
                            Button(language.text("Try again", "再试一次")) { listAttempt += 1 }
                        }
                    } else {
                        ProgressView()
                    }
                } else if itineraries.isEmpty && (saved?.isEmpty ?? true) {
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
                                LioTripDays(itinerary: itinerary, language: language) { mapDay = $0 }
                            }
                        }
                        if listUnavailable {
                            Button(language.text("Couldn’t show all trips. Try again.", "暂时无法显示全部行程，点此再试。")) {
                                listAttempt += 1
                            }
                        }
                        if let library, let saved {
                            let visible = Set(itineraries.map(\.id))
                            ForEach(saved.filter { !visible.contains($0.tripID) }, id: \.tripID) { trip in
                                NavigationLink(trip.title) {
                                    LioTripDetail(summary: trip, library: library, language: language)
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
            .task(id: listAttempt) {
                guard let library else { return }
                listUnavailable = false
                do {
                    let summaries = try await library.list()
                    try Task.checkCancellation()
                    saved = summaries
                } catch is CancellationError {
                    return
                } catch {
                    listUnavailable = true
                }
            }
        }
    }
}

private struct LioTripDetail: View {
    let summary: StructuredTripSummary
    let library: LioTripLibrary
    let language: LioLanguage
    @State private var itinerary: LioItinerary?
    @State private var unavailable = false
    @State private var attempt = 0
    @State private var mapDay: LioItinerary.Day?

    var body: some View {
        Group {
            if let itinerary {
                List {
                    LioTripDays(itinerary: itinerary, language: language) { mapDay = $0 }
                }
            } else if unavailable {
                ContentUnavailableView {
                    Label(language.text("Trip unavailable", "暂时无法显示这趟行程"), systemImage: "suitcase")
                } actions: {
                    Button(language.text("Try again", "再试一次")) { attempt += 1 }
                }
            } else {
                ProgressView()
            }
        }
        .navigationTitle(summary.title)
        .sheet(item: $mapDay) { day in
            LioDayMap(day: day, language: language)
        }
        .task(id: attempt) {
            unavailable = false
            do {
                let record = try await library.detail(summary.tripID)
                try Task.checkCancellation()
                itinerary = record.map(LioItinerary.init)
                unavailable = itinerary == nil
            } catch is CancellationError {
                return
            } catch {
                unavailable = true
            }
        }
    }
}

private struct LioTripDays: View {
    let itinerary: LioItinerary
    let language: LioLanguage
    let showMap: (LioItinerary.Day) -> Void

    var body: some View {
        ForEach(itinerary.days) { day in
            VStack(alignment: .leading, spacing: 10) {
                Text(dayTitle(day, language))
                    .font(.headline)
                    .accessibilityAddTraits(.isHeader)
                LioDayStops(day: day, language: language)
                if day.stops.contains(where: { $0.point != nil }) {
                    Button(language.text("Show on map", "在地图上看")) { showMap(day) }
                        .frame(minHeight: 44, alignment: .leading)
                        .accessibilityIdentifier("lio.trip.map.\(day.number)")
                }
            }
            .padding(.vertical, 8)
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
                    Image(systemName: stop.fixed == true ? "lock.fill" : "circle.fill")
                        .font(.caption)
                        .frame(width: 20, height: 20)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        let ending = [stop.endDate, stop.endTime].compactMap { $0 }.joined(separator: " ")
                        if let start = stop.time, !ending.isEmpty {
                            Text("\(start)–\(ending)").font(.footnote)
                        } else if let start = stop.time {
                            Text(start).font(.footnote)
                        } else if !ending.isEmpty {
                            Text(language.text("Until \(ending)", "至 \(ending)")).font(.footnote)
                        }
                        RunReadableText(text: stop.name)
                        if stop.fixed == true {
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
    if let date = day.date { return date }
    if day.datePending { return language.text("Date to be decided", "日期待定") }
    return language.text("Day \(day.number)", "第 \(day.number) 天")
}
#endif
