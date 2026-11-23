#if os(iOS)
import MapKit
import SwiftUI
import UIKit
import CJMessageHTTP
import CJRunClient
import CJTripClient

struct LioItineraryCard<Actions: View>: View {
    let itinerary: LioItinerary
    let language: LioLanguage
    var celebrate = false
    let showTrips: () -> Void
    @ViewBuilder let actions: () -> Actions
    @State private var savedAppeared = false
    @State private var selectedDay: Int?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    private var day: LioItinerary.Day? {
        itinerary.days.first { $0.number == selectedDay } ?? itinerary.days.first
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let introduction = itinerary.planningIntroduction(language) { RunReadableText(text: introduction, color: LioTheme.ink) }
            VStack(alignment: .leading, spacing: 12) {
                Label(language.text("Itinerary", "行程"), systemImage: "map")
                    .font(.caption.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary)
                Text(itinerary.title)
                    .font(LioTheme.display(.headline))
                    .foregroundStyle(LioTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                LioTripCalendarLabel(calendar: itinerary.calendar, language: language)
                Text(language.text("\(itinerary.days.count) days · \(itinerary.days.reduce(0) { $0 + $1.stops.count }) stops",
                                   "\(itinerary.days.count) 天 · \(itinerary.days.reduce(0) { $0 + $1.stops.count }) 项安排"))
                    .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 8) { dayChips }
                } else {
                    ScrollView(.horizontal) {
                        HStack(spacing: 8) { dayChips }.padding(.vertical, 2)
                    }
                    .scrollIndicators(.hidden)
                }
                if let day {
                    if day.stops.isEmpty {
                        Text(language.text("No plans for this day yet.", "这一天还没有安排。"))
                            .foregroundStyle(LioTheme.inkSecondary)
                            .accessibilityIdentifier("lio.trip.day.empty")
                    } else {
                        LioDayStops(day: day, language: language, maximumStops: 4)
                        if day.stops.count > 4 {
                            Text(language.text("\(day.stops.count - 4) more stops", "还有 \(day.stops.count - 4) 项安排"))
                                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                                .accessibilityIdentifier("lio.trip.more-stops")
                        }
                    }
                }
                Button(action: showTrips) {
                    HStack {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(LioTheme.jade)
                            .symbolEffect(.bounce, options: .nonRepeating, value: savedAppeared)
                            .accessibilityHidden(true)
                        RunReadableText(text: language.text("Saved to Trips · View", "已保存到行程 · 查看"))
                            .frame(minHeight: 44, alignment: .leading)
                    }
                }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("lio.trip.show")
                actions()
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        }
        .onAppear { if celebrate && !reduceMotion { savedAppeared = true } }
    }

    private var dayChips: some View {
        ForEach(itinerary.days) { choice in
            Button { selectedDay = choice.number } label: {
                Text(dayTitle(choice, language, calendar: itinerary.calendar))
                    .font(.subheadline.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16)
                    .frame(minHeight: 44, alignment: .leading)
                    .background(day?.number == choice.number ? LioTheme.surfaceSunken : LioTheme.surface,
                                in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                    .overlay { RoundedRectangle(cornerRadius: LioTheme.Radius.small).stroke(LioTheme.hairline, lineWidth: 1) }
            }
            .buttonStyle(.plain).foregroundStyle(LioTheme.ink)
            .accessibilityAddTraits(day?.number == choice.number ? [.isSelected] : [])
            .accessibilityIdentifier("lio.trip.day.\(choice.number)")
        }
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

private extension View {
    @ViewBuilder
    func lioTripZoomSource(_ id: Data, in namespace: Namespace.ID, reduceMotion: Bool) -> some View {
        if #available(iOS 18, *), !reduceMotion {
            matchedTransitionSource(id: id, in: namespace)
        } else {
            self
        }
    }

    @ViewBuilder
    func lioTripZoomDestination(_ route: LioTripRoute, in namespace: Namespace.ID, reduceMotion: Bool) -> some View {
        // A visit from Chat switches tabs, so its card is outside this navigation stack.
        if #available(iOS 18, *), !reduceMotion, route.visit == nil {
            navigationTransition(.zoom(sourceID: route.tripID, in: namespace))
        } else {
            self
        }
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
    let sessionRevision: UUID?
    let zoomNamespace: Namespace.ID
    @Binding var path: [LioTripRoute]
    let openChat: () -> Void
    @State private var saved: [LioTripLibrary.Entry]?
    @State private var listUnavailable = false
    @State private var listAttempt = 0
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private struct ListRead: Equatable {
        let attempt: Int
        let session: UUID?
    }
    private struct DetailRead: Hashable {
        let route: LioTripRoute
        let session: UUID?
    }

    private var shownItineraries: [LioItinerary] {
        guard let currentPlan else { return itineraries }
        return [currentPlan] + itineraries.filter { $0.id != currentPlan.id }
    }

    var body: some View {
        NavigationStack(path: $path) {
            VStack(alignment: .leading, spacing: 0) {
                Text(language.text("Trips", "行程"))
                    .font(LioTheme.display(.largeTitle))
                    .foregroundStyle(LioTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 8)
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
                                    let route = LioTripRoute(id: trip.tripID)
                                    NavigationLink(value: route) {
                                        LioTripListCard(title: trip.title, itinerary: nil, language: language,
                                                       calendar: trip.calendar, dayCount: trip.dayCount)
                                            .lioTripZoomSource(route.tripID, in: zoomNamespace, reduceMotion: reduceMotion)
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
                            let route = LioTripRoute(id: itinerary.id)
                            NavigationLink(value: route) {
                                LioTripListCard(title: itinerary.title, itinerary: itinerary, language: language)
                                    .lioTripZoomSource(route.tripID, in: zoomNamespace, reduceMotion: reduceMotion)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .lioPage()
            .navigationTitle(language.text("Trips", "行程"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(LioTheme.paper, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(colorScheme, for: .navigationBar)
            .navigationDestination(for: LioTripRoute.self) { route in
                if let library {
                    LioTripDetail(tripID: String(decoding: route.tripID, as: UTF8.self), library: library,
                                  language: language, recordedMap: recordedMap)
                        .id(DetailRead(route: route, session: sessionRevision))
                        .lioTripZoomDestination(route, in: zoomNamespace, reduceMotion: reduceMotion)
                } else if let itinerary = shownItineraries.first(where: { $0.id == String(decoding: route.tripID, as: UTF8.self) }) {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            Text(itinerary.title)
                                .font(LioTheme.display(.title).weight(.semibold))
                                .foregroundColor(LioTheme.ink)
                                .background(LioTheme.paper)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityAddTraits(.isHeader)
                            LioTripTimeline(itinerary: itinerary, language: language)
                        }
                        .padding(16)
                    }
                        .lioPage()
                        .navigationTitle("")
                        .navigationBarTitleDisplayMode(.inline)
                        .lioTripZoomDestination(route, in: zoomNamespace, reduceMotion: reduceMotion)
                        .toolbarBackground(LioTheme.paper, for: .navigationBar)
                        .toolbarBackground(.visible, for: .navigationBar)
                }
            }
            .toolbar {
                // The full-size D5 title is in the page; navigation keeps its actions and back label.
                ToolbarItem(placement: .principal) { Color.clear.frame(width: 1, height: 1).accessibilityHidden(true) }
                if let tripPlan {
                    ToolbarItem(placement: .topBarTrailing) {
                        NavigationLink(language.text("Previous plans", "此前的安排")) {
                            LioTripHistoryView(plan: tripPlan, language: language, canUndo: canUndo)
                        }
                        .accessibilityIdentifier("lio.trip.history")
                    }
                }
            }
            .task(id: ListRead(attempt: listAttempt, session: sessionRevision)) {
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
                    guard !Task.isCancelled else { return }
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
        .clipped()
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
                .fixedSize(horizontal: false, vertical: true)
                .padding(.vertical, 2)
            Button(action: openChat) {
                Text(language.text("Chat with Lio", "和 Lio 聊聊"))
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.vertical, 2)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .foregroundStyle(LioTheme.onVermilion)
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
    @Environment(\.self) private var environment
    @State private var record: LioTripLibrary.Record?
    @State private var unavailable = false
    @State private var attempt = 0

    var body: some View {
        Group {
            if let record {
                SavedTripViewport {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 24) {
                            RunReadableText(text: record.title, style: .displayTitle,
                                            color: Color(LioTheme.ink.resolve(in: environment)))
                                .background(LioTheme.paper)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityAddTraits(.isHeader)
                            switch record {
                            case .legacy(let value):
                                LioSavedTripTimeline(record: value, language: language)
                                if let recordedMap { recordedMap(value.document) }
                            case .calendar(let value):
                                LioCalendarSavedTripTimeline(record: value, language: language)
                                if case .legacy(let document) = value.content, let recordedMap { recordedMap(document) }
                            }
                        }
                        .padding(16)
                    }
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

@MainActor private struct SavedTripViewport<Content: View>: UIViewControllerRepresentable {
    let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }
    func makeUIViewController(context: Context) -> SavedTripViewportController<Content> {
        SavedTripViewportController(content: content)
    }
    func updateUIViewController(_ controller: SavedTripViewportController<Content>, context: Context) {
        controller.updateContent(content)
    }
}

@MainActor private final class SavedTripViewportController<Content: View>: UIViewController {
    private let hosting: UIHostingController<Content>
    init(content: Content) {
        hosting = UIHostingController(rootView: content)
        super.init(nibName: nil, bundle: nil)
        hosting.safeAreaRegions = []
    }
    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .clear
        addChild(hosting)
        hosting.view.backgroundColor = .clear
        hosting.view.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(hosting.view)
        NSLayoutConstraint.activate([
            hosting.view.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            hosting.view.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
            hosting.view.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor),
            hosting.view.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor)
        ])
        hosting.didMove(toParent: self)
    }
    func updateContent(_ content: Content) { hosting.rootView = content }
}

private struct LioCalendarSavedTripTimeline: View {
    let record: CalendarStructuredTripRecord
    let language: LioLanguage
    private let places: Result<[TripPlaceProjection], any Error>

    init(record: CalendarStructuredTripRecord, language: LioLanguage) {
        self.record = record
        self.language = language
        places = Result {
            switch record.content {
            case .legacy(let document): try TripPlaceProjection.read(from: document)
            case .calendar(let document): try TripPlaceProjection.read(from: document)
            }
        }
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
        LioTripCalendarLabel(calendar: itinerary.calendar, language: language)
        ForEach(itinerary.days) { day in
            VStack(alignment: .leading, spacing: 10) {
                Text(dayTitle(day, language, calendar: itinerary.calendar))
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
    var maximumStops: Int? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(maximumStops.map { Array(day.stops.prefix($0)) } ?? day.stops) { stop in
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: stop.fixed == true ? "lock.fill" : "circle.fill")
                        .font(.caption)
                        .foregroundStyle(stop.fixed == true ? LioTheme.jade : LioTheme.inkSecondary)
                        .frame(width: 20, height: 20)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        let ending = stop.endingText(language)
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
                        RunReadableText(text: stop.name, color: LioTheme.ink)
                        if stop.fixed == true {
                            Text(language.text("Fixed plan", "固定安排")).font(.footnote)
                        }
                    }
                }
            }
        }
    }
}

func dayTitle(_ day: LioItinerary.Day, _ language: LioLanguage, calendar: LioItinerary.CalendarState? = nil) -> String {
    day.title(language, calendar: calendar)
}
#endif
