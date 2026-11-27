#if os(iOS)
import SwiftUI
import UIKit

/// 大交通 (#2007): the old Intercity Travel page grown into three parts: compare cities (as before), look up a
/// flight by number or send a train number to 12306, and read about airports and stations.
enum LioBigTransportTab: String, CaseIterable, Identifiable, Sendable {
    case compare, lookup, hubs

    var id: String { rawValue }

    func name(_ language: LioLanguage) -> String {
        switch self {
        case .compare: language.text("Compare", "城际对比")
        case .lookup: language.text("Flight / Train", "航班车次")
        case .hubs: language.text("Airports & Stations", "机场车站")
        }
    }
}

struct LioBigTransportView: View {
    let language: LioLanguage
    let service: LioTransportService
    let from: String
    let to: String
    let date: LioTripDay?
    let flight: String?
    let train: String?
    @State private var tab: LioBigTransportTab
    @State private var pack = LioHubPack.bundled()
    @State private var focusedHub: String?

    /// `tab` is `compare`, `lookup` or `hubs` (a route parameter); `flight` and `train` fill the lookup box.
    init(language: LioLanguage, service: LioTransportService, from: String = "", to: String = "",
         date: LioTripDay? = nil, tab: String? = nil, flight: String? = nil, train: String? = nil) {
        self.language = language
        self.service = service
        self.from = from
        self.to = to
        self.date = date
        self.flight = flight
        self.train = train
        _tab = State(initialValue: LioBigTransportTab(rawValue: tab ?? "")
            ?? (flight != nil || train != nil ? .lookup : .compare))
    }

    private var hubsVisible: Bool {
        pack.isVisible(isDebug: LioTransportHubsBuild.isDebug, draftFlagOn: LioHubPack.draftFlagOn())
    }

    private var tabs: [LioBigTransportTab] {
        LioBigTransportTab.allCases.filter { $0 != .hubs || hubsVisible }
    }

    var body: some View {
        VStack(spacing: 0) {
            Picker(language.text("Section", "分区"), selection: $tab) {
                ForEach(tabs) { item in Text(item.name(language)).tag(item) }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, LioTheme.Spacing.md)
            .padding(.vertical, LioTheme.Spacing.xs)
            .accessibilityIdentifier("lio.bigtransport.tabs")
            switch hubsVisible || tab != .hubs ? tab : .compare {
            case .compare:
                LioTransportView(language: language, service: service, from: from, to: to, date: date)
            case .lookup:
                LioTransportLookupView(language: language, flight: flight, train: train, pack: hubsVisible ? pack : nil) { code in
                    focusedHub = code
                    tab = .hubs
                }
            case .hubs:
                LioTransportHubsView(language: language, pack: pack, focus: focusedHub)
            }
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Transport", "大交通"))
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Flight and train lookup

struct LioTransportLookupView: View {
    private enum Kind: Hashable { case flight, train }

    let language: LioLanguage
    let pack: LioHubPack?
    let openAirport: (String) -> Void
    @Environment(\.lioTransportRelay) private var relay
    @State private var kind: Kind
    @State private var flightText: String
    @State private var trainText: String
    @State private var date = Date()
    @State private var flightProblem: LioFlightQuery.Problem?
    @State private var trainProblem: LioTrainLookup.Problem?
    @State private var pending: LioFlightQuery?
    @State private var result: LioFlightLookupResult?
    @State private var failure: LioTransportRelayFailure?
    @State private var trainNumber: String?
    @State private var copied = false

    init(language: LioLanguage, flight: String?, train: String?, pack: LioHubPack?,
         openAirport: @escaping (String) -> Void) {
        self.language = language
        self.pack = pack
        self.openAirport = openAirport
        _kind = State(initialValue: train != nil && flight == nil ? .train : .flight)
        _flightText = State(initialValue: flight ?? "")
        _trainText = State(initialValue: train ?? "")
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                Picker(language.text("Look up", "查找"), selection: $kind) {
                    Text(language.text("Flight number", "航班号")).tag(Kind.flight)
                    Text(language.text("Train number", "车次")).tag(Kind.train)
                }
                .pickerStyle(.segmented)
                .accessibilityIdentifier("lio.bigtransport.kind")
                switch kind {
                case .flight: flightForm
                case .train: trainForm
                }
            }
            .padding(18)
        }
        .scrollDismissesKeyboard(.interactively)
        .foregroundStyle(LioTheme.ink)
        .tint(LioTheme.vermilion)
        .environment(\.calendar, LioTransportQuery.calendar)
        .environment(\.timeZone, LioTransportQuery.calendar.timeZone)
        .task(id: pending) {
            guard let pending, let relay else { return }
            do {
                let found = try await relay.flightStatus(pending)
                guard !Task.isCancelled, self.pending == pending else { return }
                result = found
            } catch {
                guard !Task.isCancelled, self.pending == pending else { return }
                failure = (error as? LioTransportRelayFailure) ?? .lookupUnavailable
            }
            self.pending = nil
        }
    }

    // MARK: Flight

    private var flightForm: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                HStack(spacing: LioTheme.Spacing.sm) {
                    Text(language.text("Flight", "航班"))
                        .font(.subheadline)
                        .foregroundStyle(LioTheme.inkSecondary)
                        .frame(minWidth: 40, alignment: .leading)
                    TextField(language.text("e.g. MU5102", "例如 MU5102"), text: $flightText)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .submitLabel(.search)
                        .onSubmit(searchFlight)
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("lio.bigtransport.flight")
                }
                DatePicker(language.text("Date", "日期"), selection: $date,
                           in: yesterday...LioTransportQuery.lastBookableDay(), displayedComponents: [.date])
                    .frame(minHeight: 44)
                    .accessibilityIdentifier("lio.bigtransport.flightdate")
                Button(action: searchFlight) {
                    Text(language.text("Look up flight", "查航班"))
                        .font(.headline)
                        .foregroundStyle(LioTheme.onVermilion)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(LioTheme.vermilion, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                }
                .buttonStyle(.plain)
                .disabled(pending != nil)
                .accessibilityIdentifier("lio.bigtransport.flightsearch")
            }
            .padding(LioTheme.Spacing.md)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            if relay == nil {
                Text(language.text("Flight lookup isn't available in this build yet.", "这个版本暂时不能查航班。"))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.bigtransport.norelay")
            }
            if let flightProblem {
                Text(flightProblem.message(language))
                    .foregroundStyle(LioTheme.danger)
                    .accessibilityIdentifier("lio.bigtransport.flightproblem")
            }
            if pending != nil {
                ProgressView(language.text("Looking up…", "正在查找…")).frame(maxWidth: .infinity)
            }
            if let failure {
                Text(failure.message(language)).accessibilityIdentifier("lio.bigtransport.flightfailed")
            }
            if let result, pending == nil { flightResults(result) }
            Text(language.text("Times and status come from VariFlight and can change; check the airline or airport notice before you leave.",
                               "时间和状态来自飞常准，可能变动；出发前请以航空公司和机场通知为准。"))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
        }
    }

    private var yesterday: Date {
        let calendar = LioTransportQuery.calendar
        return calendar.date(byAdding: .day, value: -1, to: calendar.startOfDay(for: Date())) ?? Date()
    }

    private func searchFlight() {
        failure = nil
        switch LioFlightQuery.make(number: flightText, date: date) {
        case .success(let query):
            flightProblem = nil
            result = nil
            pending = query
        case .failure(let problem):
            flightProblem = problem
        }
    }

    @ViewBuilder private func flightResults(_ result: LioFlightLookupResult) -> some View {
        if result.flights.isEmpty {
            let (number, day) = (result.query.number, result.query.day)
            Text(language.text("No flight \(number) found on \(day). Check the number and date.",
                               "\(day) 没有查到航班 \(number)。请核对航班号和日期。"))
                .accessibilityIdentifier("lio.bigtransport.flightempty")
        } else {
            ForEach(result.flights) { flight in flightCard(flight, day: result.query.day) }
            if result.more {
                Text(language.text("More flights match; showing the first ones.", "还有更多匹配的航班，这里只显示前面的。"))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
            }
        }
    }

    private func flightCard(_ flight: LioFlightStatus, day: String) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            HStack(alignment: .firstTextBaseline) {
                Text(flight.flightNumber).font(.title3.weight(.semibold))
                if let airline = flight.airline(language) { Text(airline).foregroundStyle(LioTheme.inkSecondary) }
                Spacer()
                if let status = flight.status {
                    Text(status)
                        .font(.subheadline.weight(.semibold))
                        .padding(.horizontal, LioTheme.Spacing.xs)
                        .padding(.vertical, LioTheme.Spacing.xxs)
                        .background(LioTheme.surfaceSunken, in: Capsule())
                }
            }
            .accessibilityElement(children: .combine)
            leg(language.text("From", "出发"), code: flight.departure, isDeparture: true, flight: flight,
                planned: flight.plannedDeparture, actual: flight.actualDeparture, terminal: flight.departureTerminal, day: day)
            leg(language.text("To", "到达"), code: flight.arrival, isDeparture: false, flight: flight,
                planned: flight.plannedArrival, actual: flight.actualArrival, terminal: flight.arrivalTerminal, day: day)
            if flight.gate != nil || flight.checkInCounter != nil || flight.baggageCarousel != nil {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                    if let gate = flight.gate { fact(language.text("Gate", "登机口"), gate) }
                    if let counter = flight.checkInCounter { fact(language.text("Check-in", "值机柜台"), counter) }
                    if let carousel = flight.baggageCarousel { fact(language.text("Baggage", "行李转盘"), carousel) }
                }
            }
            if flight.codeshare == true {
                Text(language.text("This is a codeshare number; the flight is operated by another airline.",
                                   "这是共享航班号，实际由其他航司执飞。"))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
            }
        }
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityIdentifier("lio.bigtransport.flightcard")
    }

    private func leg(_ label: String, code: String?, isDeparture: Bool, flight: LioFlightStatus, planned: String?,
                     actual: String?, terminal: String?, day: String) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xs) {
                Text(label).font(.subheadline).foregroundStyle(LioTheme.inkSecondary).frame(minWidth: 40, alignment: .leading)
                Text([code, flight.airportName(departure: isDeparture, language)]
                    .compactMap { $0 }.reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
                    .joined(separator: " · "))
                    .font(.body.weight(.semibold))
            }
            if let planned { fact(language.text("Scheduled", "计划"), LioFlightTimeText.display(planned, queriedDay: day)) }
            if let actual { fact(language.text("Actual", "实际"), LioFlightTimeText.display(actual, queriedDay: day)) }
            if let terminal { fact(language.text("Terminal", "航站楼"), terminal) }
            if let code, pack?.airport(code: code) != nil {
                Button(language.text("Airport info", "机场信息")) { openAirport(code) }
                    .font(.subheadline)
                    .frame(minHeight: 44, alignment: .leading)
                    .accessibilityIdentifier("lio.bigtransport.airportinfo.\(code)")
            }
        }
    }

    private func fact(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xs) {
            Text(label).font(.subheadline).foregroundStyle(LioTheme.inkSecondary).frame(minWidth: 72, alignment: .leading)
            Text(value).font(.subheadline)
        }
    }

    // MARK: Train

    private var trainForm: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                HStack(spacing: LioTheme.Spacing.sm) {
                    Text(language.text("Train", "车次"))
                        .font(.subheadline)
                        .foregroundStyle(LioTheme.inkSecondary)
                        .frame(minWidth: 40, alignment: .leading)
                    TextField(language.text("e.g. G1", "例如 G1"), text: $trainText)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .submitLabel(.go)
                        .onSubmit(checkTrain)
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("lio.bigtransport.train")
                }
                Button(action: checkTrain) {
                    Text(language.text("Check on 12306", "去 12306 查车次"))
                        .font(.headline)
                        .foregroundStyle(LioTheme.onVermilion)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(LioTheme.vermilion, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.bigtransport.trainsearch")
            }
            .padding(LioTheme.Spacing.md)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            if let trainProblem {
                Text(trainProblem.message(language))
                    .foregroundStyle(LioTheme.danger)
                    .accessibilityIdentifier("lio.bigtransport.trainproblem")
            }
            if let number = trainNumber { trainHandOff(number) }
            Text(LioTrainLookup.reason(language))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.bigtransport.trainreason")
        }
    }

    private func checkTrain() {
        switch LioTrainLookup.check(trainText) {
        case .success(let number):
            trainProblem = nil
            copied = false
            trainNumber = number
        case .failure(let problem):
            trainNumber = nil
            trainProblem = problem
        }
    }

    private func trainHandOff(_ number: String) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            Text(number).font(.title2.weight(.semibold)).accessibilityIdentifier("lio.bigtransport.trainnumber")
            Text(language.text("12306 asks for the train number and the date itself. Copy the number, then open the page.",
                               "12306 页面会让你自己输入车次和日期。先复制车次号，再打开页面。"))
                .font(.subheadline)
            Button {
                UIPasteboard.general.string = number
                copied = true
            } label: {
                Label(copied ? language.text("Copied", "已复制") : language.text("Copy train number", "复制车次号"),
                      systemImage: copied ? "checkmark" : "doc.on.doc")
                    .frame(minHeight: 44)
            }
            .accessibilityIdentifier("lio.bigtransport.traincopy")
            Link(destination: LioTrainLookup.byNumberURL) {
                Label(language.text("Open 12306 train lookup", "打开 12306 查车次"), systemImage: "arrow.up.right.square")
                    .frame(minHeight: 44)
            }
            .accessibilityIdentifier("lio.bigtransport.trainlink")
            Link(destination: LioTrainLookup.englishURL) {
                Label(language.text("12306 in English", "12306 英文入口"), systemImage: "globe")
                    .frame(minHeight: 44)
            }
            .accessibilityIdentifier("lio.bigtransport.trainlinken")
        }
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

// MARK: - Airports and stations

struct LioTransportHubsView: View {
    let language: LioLanguage
    let pack: LioHubPack
    let focus: String?
    @State private var city: String
    @State private var expanded: Set<String>
    @State private var driver: LioHubPlace?

    init(language: LioLanguage, pack: LioHubPack, focus: String?) {
        self.language = language
        self.pack = pack
        self.focus = focus
        let focused = focus.flatMap { pack.airport(code: $0) }
        _city = State(initialValue: focused?.city ?? pack.cities.first ?? "beijing")
        _expanded = State(initialValue: focused.map { [$0.id] } ?? [])
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                    if pack.status == .draft {
                        Label(language.text("Draft data for testing, not reviewed yet: check each entry", "草稿数据，仅供测试，尚未审核，每条都待核"),
                              systemImage: "testtube.2")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(LioTheme.inkSecondary)
                            .accessibilityIdentifier("lio.bigtransport.hubsdraft")
                    }
                    cityChips
                    section(language.text("Airports", "机场"), .airport)
                    section(language.text("Railway stations", "火车站"), .rail)
                    Text(language.text("Check the airport or station notice for the latest; each entry shows the day it was checked.",
                                       "最新情况以机场、车站公告为准；每条都标明了核对日期。"))
                        .font(.footnote)
                        .foregroundStyle(LioTheme.inkSecondary)
                }
                .padding(18)
            }
            .onAppear {
                if let id = focus.flatMap({ pack.airport(code: $0)?.id }) {
                    proxy.scrollTo(id, anchor: .top)
                }
            }
        }
        .foregroundStyle(LioTheme.ink)
        .tint(LioTheme.vermilion)
        .sheet(item: $driver) { hub in
            LioDriverSign(language: language, nameZH: hub.nameZh, nameEN: hub.driverNameEN,
                          requestZH: hub.driverRequestZH, identifierPrefix: "lio.bigtransport.driver")
        }
    }

    private func cityName(_ id: String) -> String {
        LioTransportCity.all.first { $0.id == id }?.name(in: language) ?? id
    }

    private var cityChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: LioTheme.Spacing.xs) {
                ForEach(pack.cities, id: \.self) { id in
                    Button(cityName(id)) { city = id }
                        .buttonStyle(.plain)
                        .font(.subheadline)
                        .foregroundStyle(id == city ? LioTheme.onVermilion : LioTheme.ink)
                        .padding(.horizontal, LioTheme.Spacing.sm)
                        .frame(minHeight: 44)
                        .background(id == city ? LioTheme.vermilion : LioTheme.surfaceSunken, in: Capsule())
                        .accessibilityAddTraits(id == city ? .isSelected : [])
                        .accessibilityIdentifier("lio.bigtransport.hubcity.\(id)")
                }
            }
        }
    }

    @ViewBuilder private func section(_ title: String, _ kind: LioHubPlace.Kind) -> some View {
        let hubs = pack.hubs(in: city, kind: kind)
        if !hubs.isEmpty {
            Text(title).font(.headline).accessibilityAddTraits(.isHeader)
            ForEach(hubs) { hub in hubRow(hub).id(hub.id) }
        }
    }

    private func hubRow(_ hub: LioHubPlace) -> some View {
        let open = Binding(get: { expanded.contains(hub.id) },
                           set: { if $0 { expanded.insert(hub.id) } else { expanded.remove(hub.id) } })
        return DisclosureGroup(isExpanded: open) {
            hubDetail(hub).padding(.top, LioTheme.Spacing.xs)
        } label: {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                Text([hub.name(language), hub.code].compactMap { $0 }.joined(separator: " · "))
                    .font(.body.weight(.semibold))
                if let other = hub.secondaryName(language) {
                    Text(other).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
                if pack.status == .draft {
                    Text(language.text("Unverified", "待核"))
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, LioTheme.Spacing.xs)
                        .background(LioTheme.surfaceSunken, in: Capsule())
                        .accessibilityIdentifier("lio.bigtransport.hubdraftbadge.\(hub.id)")
                }
            }
            .frame(minHeight: 44, alignment: .leading)
        }
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityIdentifier("lio.bigtransport.hub.\(hub.id)")
    }

    private func hubDetail(_ hub: LioHubPlace) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            if let terminals = hub.terminals, !terminals.isEmpty {
                block(language.text("Terminals", "航站楼"),
                      terminals.map { [$0.name, hub.terminalNote($0, language)].compactMap { $0 }.joined(separator: ": ") })
            }
            let toCity = hub.toCity(language)
            if !toCity.isEmpty {
                block(hub.hubType == .airport ? language.text("Getting to the city", "去市区")
                      : language.text("Getting around from here", "从这里出发"), toCity)
            }
            let tips = hub.tips(language)
            if !tips.isEmpty { block(language.text("Tips for visitors", "给外国游客的提示"), tips) }
            Button {
                driver = hub
            } label: {
                Label(language.text("Show the driver", "给司机看"), systemImage: "person.text.rectangle")
                    .frame(minHeight: 44)
            }
            .accessibilityIdentifier("lio.bigtransport.hubdriver.\(hub.id)")
            if let url = hub.officialURL {
                Link(destination: url) {
                    Label(language.text("Official page", "官方页面"), systemImage: "arrow.up.right.square")
                        .frame(minHeight: 44)
                }
            }
            if let checked = hub.checkedOn {
                Text(language.text("Checked \(checked)", "核对于 \(checked)"))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
            }
        }
    }

    private func block(_ title: String, _ lines: [String]) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            Text(title).font(.subheadline.weight(.semibold))
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in Text(line).font(.subheadline) }
        }
    }
}

extension LioHubPlace: Hashable {
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
#endif
