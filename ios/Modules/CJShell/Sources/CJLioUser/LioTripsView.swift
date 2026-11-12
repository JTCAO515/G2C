#if os(iOS)
import MapKit
import SwiftUI
import CJMessageHTTP
import CJRunClient
import CJTripClient

struct LioItineraryCard<Actions: View>: View {
    let itinerary: LioItinerary
    let language: LioLanguage
    let showTrips: () -> Void
    @ViewBuilder let actions: () -> Actions

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let introduction = itinerary.planningIntroduction(language) { RunReadableText(text: introduction) }
            Text(itinerary.title)
                .font(LioTheme.display(.headline))
                .foregroundStyle(LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
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
            actions()
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

struct LioTripRoute: Hashable {
    let tripID: Data
    let visit: UUID?

    init(id: String, visit: UUID? = nil) {
        tripID = Data(id.utf8)
        self.visit = visit
    }
}

struct LioTripsView: View {
    let itineraries: [LioItinerary]
    let language: LioLanguage
    let library: LioTripLibrary?
    let tripPlan: LioTripPlan?
    let currentPlan: LioItinerary?
    let canUndo: Bool
    let recordedMap: (@MainActor (StructuredTripDocument) -> AnyView)?
    @Binding var path: [LioTripRoute]
    let openChat: () -> Void
    @State private var saved: [StructuredTripSummary]?
    @State private var listUnavailable = false
    @State private var listAttempt = 0
    @Environment(\.colorScheme) private var colorScheme

    private var shownItineraries: [LioItinerary] {
        guard let currentPlan else { return itineraries }
        return [currentPlan] + itineraries.filter { $0.id != currentPlan.id }
    }

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if library != nil {
                    if listUnavailable {
                        ContentUnavailableView {
                            Label(language.text("Trips unavailable", "暂时无法显示行程"), systemImage: "suitcase")
                        } actions: {
                            Button(language.text("Try again", "再试一次")) { listAttempt += 1 }
                        }
                    } else if let saved {
                        if saved.isEmpty {
                            emptyTrips
                        } else {
                            tripList {
                                ForEach(saved, id: \.tripID) { trip in
                                    NavigationLink(value: LioTripRoute(id: trip.tripID)) {
                                        LioTripListCard(title: trip.title, itinerary: nil, language: language)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    } else {
                        ProgressView()
                    }
                } else if shownItineraries.isEmpty {
                    emptyTrips
                } else {
                    tripList {
                        ForEach(shownItineraries) { itinerary in
                            NavigationLink(value: LioTripRoute(id: itinerary.id)) {
                                LioTripListCard(title: itinerary.title, itinerary: itinerary, language: language)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .lioPage()
            .navigationTitle(language.text("Trips", "行程"))
            .toolbarBackground(LioTheme.paper, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(colorScheme, for: .navigationBar)
            .navigationDestination(for: LioTripRoute.self) { route in
                if let library {
                    LioTripDetail(tripID: String(decoding: route.tripID, as: UTF8.self), library: library,
                                  language: language, recordedMap: recordedMap)
                        .id(route)
                } else if let itinerary = shownItineraries.first(where: { $0.id == String(decoding: route.tripID, as: UTF8.self) }) {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            Text(itinerary.title)
                                .font(LioTheme.display(.title))
                                .foregroundStyle(LioTheme.ink)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityAddTraits(.isHeader)
                            LioTripTimeline(itinerary: itinerary, language: language)
                        }
                        .padding(16)
                    }
                        .lioPage()
                        .navigationTitle("")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbarBackground(LioTheme.paper, for: .navigationBar)
                        .toolbarBackground(.visible, for: .navigationBar)
                }
            }
            .toolbar {
                if let tripPlan {
                    ToolbarItem(placement: .topBarTrailing) {
                        NavigationLink(language.text("Previous plans", "此前的安排")) {
                            LioTripHistoryView(plan: tripPlan, language: language, canUndo: canUndo)
                        }
                        .accessibilityIdentifier("lio.trip.history")
                    }
                }
            }
            .task(id: listAttempt) {
                guard let library else { return }
                listUnavailable = false
                saved = nil
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

    private func tripList<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        ScrollView {
            VStack(spacing: 16, content: content)
                .padding(16)
        }
        .accessibilityIdentifier("lio.trip.list")
    }

    private var emptyTrips: some View {
        VStack(spacing: 16) {
            LioPortrait(size: 80)
            Text(language.text("No trips yet", "还没有行程"))
                .font(LioTheme.display(.title2))
                .accessibilityAddTraits(.isHeader)
            Text(language.text("Tell Lio where you’d like to go.", "告诉 Lio 你想去哪儿。"))
                .foregroundStyle(LioTheme.inkSecondary)
            Button(language.text("Chat with Lio", "和 Lio 聊聊"), action: openChat)
                .buttonStyle(.borderedProminent)
                .frame(minHeight: 44)
        }
        .multilineTextAlignment(.center)
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct LioTripDetail: View {
    let tripID: String
    let library: LioTripLibrary
    let language: LioLanguage
    let recordedMap: (@MainActor (StructuredTripDocument) -> AnyView)?
    @State private var record: StructuredTripRecord?
    @State private var unavailable = false
    @State private var attempt = 0

    var body: some View {
        Group {
            if let record {
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        Text(record.document.title)
                            .font(LioTheme.display(.title))
                            .foregroundStyle(LioTheme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityAddTraits(.isHeader)
                        LioSavedTripTimeline(record: record, language: language)
                        if let recordedMap { recordedMap(record.document) }
                    }
                    .padding(16)
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
        .lioPage()
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .task(id: attempt) {
            record = nil
            unavailable = false
            do {
                let value = try await library.detail(tripID)
                try Task.checkCancellation()
                record = value
                unavailable = value == nil
            } catch is CancellationError {
                return
            } catch {
                guard !Task.isCancelled else { return }
                unavailable = true
            }
        }
    }
}

private struct LioSavedTripTimeline: View {
    let record: StructuredTripRecord
    let language: LioLanguage
    private let places: Result<[TripPlaceProjection], any Error>

    init(record: StructuredTripRecord, language: LioLanguage) {
        self.record = record
        self.language = language
        places = Result { try TripPlaceProjection.read(from: record.document) }
    }

    var body: some View {
        switch places {
        case .success(let places):
            LioTripTimeline(itinerary: LioItinerary(record, places: places), language: language)
        case .failure:
            Text(language.text("Map unavailable", "暂时无法显示地图"))
            LioTripTimeline(itinerary: LioItinerary(record), language: language)
        }
    }
}

struct LioTripDays: View {
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
                        .foregroundStyle(stop.fixed == true ? LioTheme.jade : LioTheme.inkSecondary)
                        .frame(width: 20, height: 20)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        let ending = [stop.endDate, stop.endTime].compactMap { $0 }.joined(separator: " ")
                        Group {
                            if let start = stop.time, !ending.isEmpty {
                                Text("\(start)–\(ending)")
                            } else if let start = stop.time {
                                Text(start)
                            } else if !ending.isEmpty {
                                Text(language.text("Until \(ending)", "至 \(ending)"))
                            }
                        }
                        .font(.footnote)
                        .foregroundStyle(LioTheme.inkSecondary)
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

func dayTitle(_ day: LioItinerary.Day, _ language: LioLanguage) -> String {
    if let date = day.date { return date }
    if day.datePending { return language.text("Date to be decided", "日期待定") }
    return language.text("Day \(day.number)", "第 \(day.number) 天")
}
#endif
