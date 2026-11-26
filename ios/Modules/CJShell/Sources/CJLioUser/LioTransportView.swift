#if os(iOS)
import SwiftUI

/// Intercity transport search (#1519): enter two cities and a date, compare trains, flights and buses,
/// then book outside the app. Behind `G2CTransportEnabled`, hidden by default.
struct LioTransportView: View {
    private enum Field: Hashable { case from, to }

    let language: LioLanguage
    let service: LioTransportService
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @Environment(\.lioTransportRelay) private var relay
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var fromText = ""
    @State private var toText = ""
    @State private var date = Date()
    @State private var problem: LioTransportQuery.Problem?
    @State private var pending: LioTransportQuery?
    @State private var result: LioTransportResult?
    @State private var failure: LioTransportRelayFailure?
    @State private var mode = LioTransportMode.rail
    @State private var driverHub: LioTransportHub?
    @FocusState private var focus: Field?

    /// `from` and `to` fill the two city fields when a route opens the page (#1724); nothing is searched until
    /// the traveller taps search.
    init(language: LioLanguage, service: LioTransportService, from: String = "", to: String = "",
         date: LioTripDay? = nil) {
        self.language = language
        self.service = service
        _fromText = State(initialValue: from)
        _toText = State(initialValue: to)
        // #1739: the next trip day from the travel profile, else today.
        if let date { _date = State(initialValue: date.start()) }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                form
                if let problem {
                    Text(problem.message(language))
                        .foregroundStyle(LioTheme.danger)
                        .accessibilityIdentifier("lio.transport.problem")
                }
                if pending != nil {
                    ProgressView(language.text("Comparing…", "正在比较…"))
                        .frame(maxWidth: .infinity)
                }
                if let failure {
                    Text(failure.message(language))
                        .accessibilityIdentifier("lio.transport.failed")
                }
                if let result, pending == nil {
                    results(result)
                }
                Text(LioTransportCopy.footer(result != nil && pending == nil ? mode : nil, language))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.transport.footer")
            }
            .padding(18)
        }
        .scrollDismissesKeyboard(.interactively)
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .tint(LioTheme.vermilion)
        .navigationTitle(language.text("Intercity Travel", "城际交通"))
        .navigationBarTitleDisplayMode(.inline)
        .environment(\.calendar, LioTransportQuery.calendar)
        .environment(\.timeZone, LioTransportQuery.calendar.timeZone)
        .sheet(item: $driverHub) { hub in
            LioDriverSign(language: language, nameZH: hub.nameZH, nameEN: hub.driverNameEN,
                          requestZH: hub.driverRequestZH, identifierPrefix: "lio.transport.driver")
        }
        .task(id: pending) {
            guard let pending else { return }
            do {
                let found = try await service.upgraded(with: relay).search(pending)
                guard !Task.isCancelled, self.pending == pending else { return }
                result = found
                mode = Self.preferredMode(found)
            } catch {
                guard !Task.isCancelled, self.pending == pending else { return }
                failure = (error as? LioTransportRelayFailure) ?? .unavailable
                // Keep the booking links, tips and stations on screen even when the search fails.
                result = .guideOnly(for: pending)
                mode = .rail
            }
            self.pending = nil
        }
    }

    // MARK: Form

    private var form: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            HStack(alignment: .center, spacing: LioTheme.Spacing.xs) {
                VStack(spacing: LioTheme.Spacing.xs) {
                    cityField(language.text("From", "出发"), text: $fromText, field: .from,
                              id: "lio.transport.from")
                    Rectangle().fill(LioTheme.hairline).frame(height: LioTheme.outlineWidth)
                    cityField(language.text("To", "到达"), text: $toText, field: .to, id: "lio.transport.to")
                }
                Button {
                    swap(&fromText, &toText)
                } label: {
                    Image(systemName: "arrow.up.arrow.down")
                        .font(.body.weight(.semibold))
                        .frame(width: 44, height: 44)
                        .background(LioTheme.surfaceSunken, in: Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(language.text("Swap cities", "交换出发和到达"))
                .accessibilityIdentifier("lio.transport.swap")
            }
            DatePicker(language.text("Date", "日期"), selection: $date,
                       in: LioTransportQuery.calendar.startOfDay(for: Date())...LioTransportQuery.lastBookableDay(),
                       displayedComponents: [.date])
                .frame(minHeight: 44)
                .accessibilityIdentifier("lio.transport.date")
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: LioTheme.Spacing.xs) {
                    ForEach(LioTransportCity.all) { city in
                        Button(city.name(in: language)) { pick(city) }
                            .buttonStyle(.plain)
                            .font(.subheadline)
                            .padding(.horizontal, LioTheme.Spacing.sm)
                            .frame(minHeight: 44)
                            .background(LioTheme.surfaceSunken, in: Capsule())
                            .accessibilityIdentifier("lio.transport.city.\(city.id)")
                    }
                }
            }
            Button(action: compare) {
                Text(language.text("Compare trains, flights and buses", "比较火车、飞机和大巴"))
                    .font(.headline)
                    .foregroundStyle(LioTheme.onVermilion)
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .background(LioTheme.vermilion, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
            }
            .buttonStyle(.plain)
            .disabled(pending != nil)
            .accessibilityIdentifier("lio.transport.compare")
        }
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func cityField(_ label: String, text: Binding<String>, field: Field, id: String) -> some View {
        let prompt = field == .from ? language.text("City, e.g. Shanghai", "城市，例如上海")
            : language.text("City, e.g. Beijing", "城市，例如北京")
        return HStack(spacing: LioTheme.Spacing.sm) {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(LioTheme.inkSecondary)
                .frame(minWidth: 40, alignment: .leading)
            TextField(prompt, text: text)
                .focused($focus, equals: field)
                .textInputAutocapitalization(.words)
                .autocorrectionDisabled()
                .submitLabel(field == .from ? .next : .search)
                .onSubmit { field == .from ? (focus = .to) : compare() }
                .frame(minHeight: 44)
                .accessibilityIdentifier(id)
        }
    }

    private func pick(_ city: LioTransportCity) {
        let name = city.name(in: language)
        if focus == .to || (focus == nil && !fromText.isEmpty && toText.isEmpty) {
            toText = name
        } else {
            fromText = name
            if toText.isEmpty { focus = .to }
        }
    }

    private func compare() {
        focus = nil
        failure = nil
        switch LioTransportQuery.make(from: fromText, to: toText, date: date) {
        case .success(let query):
            problem = nil
            result = nil
            pending = query
        case .failure(let reason):
            problem = reason
        }
    }

    private static func preferredMode(_ result: LioTransportResult) -> LioTransportMode {
        LioTransportMode.allCases.first { !result.result(for: $0).options.isEmpty } ?? .rail
    }

    // MARK: Results

    @ViewBuilder private func results(_ result: LioTransportResult) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            let (from, to, day) = (result.query.from, result.query.to, result.query.day)
            Text(language.text("\(from.nameEN) → \(to.nameEN) · \(day)", "\(from.nameZH) → \(to.nameZH) · \(day)"))
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
            if result.isSample {
                Label(language.text("Sample data for preview", "预览示例数据"), systemImage: "testtube.2")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.transport.sample")
            }
            let tabs = LioTransportModeTabs.stacks(at: dynamicTypeSize)
                ? AnyLayout(VStackLayout(spacing: LioTheme.Spacing.xs))
                : AnyLayout(HStackLayout(spacing: LioTheme.Spacing.xs))
            tabs {
                ForEach(LioTransportMode.allCases) { item in
                    modeTab(item, result.result(for: item))
                }
            }
            modeSection(mode, result: result)
        }
    }

    private func modeTab(_ item: LioTransportMode, _ modeResult: LioTransportModeResult) -> some View {
        let selected = item == mode
        return Button { mode = item } label: {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                Label(item.name(language), systemImage: item.symbol)
                    .font(.subheadline.weight(.semibold))
                Text(summary(modeResult))
                    .font(.caption)
                    .foregroundStyle(selected ? LioTheme.onVermilion : LioTheme.inkSecondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(selected ? LioTheme.onVermilion : LioTheme.ink)
            .frame(maxWidth: .infinity, minHeight: 56, alignment: .topLeading)
            .padding(LioTheme.Spacing.xs)
            .background(selected ? LioTheme.vermilion : LioTheme.surface,
                        in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(item.identifier)
    }

    private func summary(_ modeResult: LioTransportModeResult) -> String {
        switch modeResult {
        case .options(let options) where options.isEmpty:
            return language.text("None found", "没有班次")
        case .options:
            var parts: [String] = []
            if let fastest = modeResult.fastestMinutes { parts.append(LioTransportFormat.duration(fastest, language)) }
            if let lowest = modeResult.lowestPriceMinor { parts.append(LioTransportFormat.from(lowest, language)) }
            return parts.joined(separator: " · ")
        case .guideOnly:
            return language.text("How to book", "购票指引")
        case .unavailable:
            return language.text("Unavailable now", "暂时查不到")
        }
    }

    @ViewBuilder private func modeSection(_ mode: LioTransportMode, result: LioTransportResult) -> some View {
        let modeResult = result.result(for: mode)
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            switch modeResult {
            case .options(let options):
                if options.isEmpty {
                    Text(language.text("No direct services found for this day.", "这一天没有找到直达班次。"))
                }
                ForEach(options) { option in
                    NavigationLink {
                        LioTransportOptionDetail(language: language, option: option, query: result.query,
                                                 driverHub: $driverHub)
                    } label: {
                        LioTransportOptionCard(language: language, option: option)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.transport.option.\(option.number)")
                }
            case .guideOnly:
                Text(guideOnlyText(mode))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("lio.transport.guide-only")
            case .unavailable:
                Text(language.text("This can't be checked right now. You can still look it up and book below.",
                                   "暂时查不到，可以直接用下方链接查看和订票。"))
            }
            Text(mode.availabilityNote(language))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
            LioTransportBookingButtons(language: language, mode: mode, query: result.query)
            if LioTransportCopy.showsDisclosure(LioTransportLinks.booking(mode, query: result.query, language: language)) {
                Text(LioTransportCopy.disclosure(language))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.transport.disclosure")
            }
            LioTransportTips(language: language, mode: mode)
            LioTransportHubList(language: language, mode: mode, query: result.query, driverHub: $driverHub)
        }
    }

    private func guideOnlyText(_ mode: LioTransportMode) -> String {
        switch mode {
        case .rail:
            language.text("Check train times, seats and prices on 12306 or Trip.com, then book there with your passport.",
                          "在 12306 或 Trip.com 查车次、余票和票价，再用护照订票。")
        case .flight:
            language.text("Compare flights and prices on Trip.com, then book there with your passport.",
                          "在 Trip.com 比较航班和票价，再用护照订票。")
        case .bus:
            language.text("Bus times aren't online in English. Buy at the intercity bus station with your passport.",
                          "大巴班次没有英文线上渠道，请凭护照到城际客运站购票。")
        }
    }
}

// MARK: - Pieces

private struct LioTransportOptionCard: View {
    let language: LioLanguage
    let option: LioTransportOption

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            HStack(alignment: .firstTextBaseline) {
                Text(option.number).font(.headline)
                if let carrier = option.carrier(language) {
                    Text(carrier).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
                Spacer(minLength: LioTheme.Spacing.xs)
                if let lowest = option.lowestPriceMinor {
                    Text(LioTransportFormat.from(lowest, language)).font(.headline).foregroundStyle(LioTheme.vermilion)
                }
            }
            HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xs) {
                Text(option.departTime).font(LioTheme.display(.title3).weight(.semibold))
                Image(systemName: "arrow.right").font(.caption).foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityHidden(true)
                Text(LioTransportFormat.arrival(option, language))
                    .font(LioTheme.display(.title3).weight(.semibold))
                    .accessibilityLabel(LioTransportFormat.arrivalSpoken(option, language))
                Spacer(minLength: LioTheme.Spacing.xs)
                Text(LioTransportFormat.duration(option.durationMinutes, language))
                    .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
            }
            Text(option.departure.name(in: language) + " → " + option.arrival.name(in: language))
                .font(.subheadline)
                .fixedSize(horizontal: false, vertical: true)
            if language == .english {
                Text(option.departure.nameZH + " → " + option.arrival.nameZH)
                    .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

private struct LioTransportOptionDetail: View {
    let language: LioLanguage
    let option: LioTransportOption
    let query: LioTransportQuery
    @Binding var driverHub: LioTransportHub?
    @Environment(\.lioTaxiEntry) private var taxiEntry

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                    Text([option.number, option.carrier(language)].compactMap { $0 }.joined(separator: " · "))
                        .font(LioTheme.display(.title2).weight(.bold))
                        .accessibilityAddTraits(.isHeader)
                    stop(option.departTime, option.departure)
                    Label(LioTransportFormat.duration(option.durationMinutes, language), systemImage: "clock")
                        .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    stop(LioTransportFormat.arrival(option, language),
                         option.arrival)
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel(LioTransportFormat.arrivalSpoken(option, language)
                                            + language.text(", ", "，") + option.arrival.name(in: language))
                }
                .padding(LioTheme.Spacing.md)
                .frame(maxWidth: .infinity, alignment: .leading)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                if !option.fares.isEmpty {
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                        ForEach(option.fares, id: \.self) { fare in
                            HStack {
                                Text(fare.className(language))
                                Spacer()
                                Text(LioTransportFormat.price(fare.priceMinor)).font(.headline)
                            }
                            .frame(minHeight: 32)
                        }
                    }
                    .padding(LioTheme.Spacing.md)
                    .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                }
                Text(option.mode.availabilityNote(language))
                    .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                LioTransportBookingButtons(language: language, mode: option.mode, query: query)
                if LioTransportCopy.showsDisclosure(LioTransportLinks.booking(option.mode, query: query,
                                                                               language: language)) {
                    Text(LioTransportCopy.disclosure(language))
                        .font(.footnote)
                        .foregroundStyle(LioTheme.inkSecondary)
                        .accessibilityIdentifier("lio.transport.detail.disclosure")
                }
                LioTransportHubActions(language: language, hub: option.departure, driverHub: $driverHub)
                LioTransportTips(language: language, mode: option.mode)
                Text(LioTransportCopy.footer(option.mode, language))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.transport.detail.footer")
            }
            .padding(18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(option.number)
        .navigationBarTitleDisplayMode(.inline)
    }

    private func stop(_ time: String, _ hub: LioTransportHub) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.sm) {
            Text(time).font(LioTheme.display(.title3).weight(.semibold)).frame(minWidth: 64, alignment: .leading)
            VStack(alignment: .leading, spacing: 2) {
                Text(hub.name(in: language)).font(.body.weight(.semibold))
                if let secondary = hub.secondaryName(in: language) {
                    Text(secondary).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
            }
        }
    }
}

private struct LioTransportBookingButtons: View {
    let language: LioLanguage
    let mode: LioTransportMode
    let query: LioTransportQuery
    @Environment(\.openURL) private var openURL

    var body: some View {
        let links = LioTransportLinks.booking(mode, query: query, language: language)
        if !links.isEmpty {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                ForEach(Array(links.enumerated()), id: \.offset) { index, link in
                    Button { openURL(link.url) } label: {
                        HStack {
                            Text(language.text("Book on \(link.provider.label(language))",
                                               "去 \(link.provider.label(language)) 订票"))
                                .font(.headline)
                            Spacer()
                            Image(systemName: "arrow.up.right.square").accessibilityHidden(true)
                        }
                        .foregroundStyle(index == 0 ? LioTheme.onVermilion : LioTheme.ink)
                        .padding(.horizontal, LioTheme.Spacing.md)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(index == 0 ? LioTheme.vermilion : LioTheme.surface,
                                    in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.transport.book.\(mode.rawValue).\(index)")
                }
            }
        }
    }
}

/// Stations (trains, buses) or airports (flights) in both cities, each with "show the driver" and, when the
/// hub has a coordinate and the taxi tool is enabled, "taxi there".
private struct LioTransportHubList: View {
    let language: LioLanguage
    let mode: LioTransportMode
    let query: LioTransportQuery
    @Binding var driverHub: LioTransportHub?

    var body: some View {
        if mode != .bus {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                Text(mode == .flight ? language.text("Airports", "机场") : language.text("Main stations", "主要火车站"))
                    .font(.headline)
                    .accessibilityAddTraits(.isHeader)
                Text(language.text("Show a driver the Chinese name, or take a taxi there.", "可以把中文站名给司机看，或直接打车过去。"))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                ForEach([query.from, query.to]) { city in
                    VStack(alignment: .leading, spacing: 0) {
                        Text(city.name(in: language))
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(LioTheme.inkSecondary)
                            .padding(.bottom, LioTheme.Spacing.xxs)
                        let hubs = mode == .flight ? city.airports : city.stations
                        ForEach(Array(hubs.enumerated()), id: \.element) { index, hub in
                            if index > 0 { Rectangle().fill(LioTheme.hairline).frame(height: LioTheme.outlineWidth) }
                            LioTransportHubRow(language: language, hub: hub, driverHub: $driverHub)
                        }
                    }
                    .padding(LioTheme.Spacing.md)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                }
            }
        }
    }
}

/// One station or airport: names on the left, "show the driver" and (with a coordinate) "taxi there" on the right.
private struct LioTransportHubRow: View {
    let language: LioLanguage
    let hub: LioTransportHub
    @Binding var driverHub: LioTransportHub?
    @Environment(\.lioTaxiEntry) private var taxiEntry

    var body: some View {
        HStack(alignment: .center, spacing: LioTheme.Spacing.xs) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xs) {
                    Text(hub.name(in: language)).font(.body.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    if let code = hub.code { Text(code).font(.subheadline).foregroundStyle(LioTheme.inkSecondary) }
                }
                if let secondary = hub.secondaryName(in: language) {
                    Text(secondary).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
            }
            Spacer(minLength: LioTheme.Spacing.xs)
            Button { driverHub = hub } label: { icon("character.bubble") }
                .buttonStyle(.plain)
                .accessibilityLabel(language.text("Show the driver: \(hub.nameEN)", "给司机看：\(hub.nameZH)"))
                .accessibilityIdentifier("lio.transport.driver.\(hub.id)")
            if let taxiEntry, let place = hub.taxiPlace {
                NavigationLink {
                    LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                                recentStore: taxiEntry.recentStore, destination: place)
                } label: { icon("car.fill") }
                .buttonStyle(.plain)
                .accessibilityLabel(language.text("Taxi to \(hub.nameEN)", "打车去\(hub.nameZH)"))
                .accessibilityIdentifier("lio.transport.taxi.\(hub.id)")
            }
        }
        .padding(.vertical, LioTheme.Spacing.xs)
    }

    private func icon(_ symbol: String) -> some View {
        Image(systemName: symbol)
            .font(.body.weight(.semibold))
            .foregroundStyle(LioTheme.vermilion)
            .frame(width: 44, height: 44)
            .background(LioTheme.surfaceSunken, in: Circle())
    }
}

/// The departure stop of one service, with labelled actions (used on the detail page).
private struct LioTransportHubActions: View {
    let language: LioLanguage
    let hub: LioTransportHub
    @Binding var driverHub: LioTransportHub?
    @Environment(\.lioTaxiEntry) private var taxiEntry

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text(language.text("Getting to \(hub.nameEN)", "去\(hub.nameZH)"))
                .font(.headline)
            HStack(spacing: LioTheme.Spacing.xs) {
                Button { driverHub = hub } label: {
                    action(language.text("Show the driver", "给司机看"), symbol: "character.bubble")
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.transport.detail.driver")
                if let taxiEntry, let place = hub.taxiPlace {
                    NavigationLink {
                        LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                                    recentStore: taxiEntry.recentStore, destination: place)
                    } label: {
                        action(language.text("Taxi there", "打车去"), symbol: "car.fill")
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.transport.detail.taxi")
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func action(_ title: String, symbol: String) -> some View {
        Label(title, systemImage: symbol)
            .font(.subheadline.weight(.semibold))
            .padding(.horizontal, LioTheme.Spacing.sm)
            .frame(minHeight: 44)
            .background(LioTheme.surfaceSunken, in: Capsule())
    }
}

private struct LioTransportTips: View {
    let language: LioLanguage
    let mode: LioTransportMode
    @State private var expanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                ForEach(LioTransportGuide.tips(for: mode)) { tip in
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                        Text(tip.title(language)).font(.subheadline.weight(.semibold))
                        Text(tip.body(language)).font(.subheadline).fixedSize(horizontal: false, vertical: true)
                    }
                }
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                    Text(language.text("Sources (checked \(LioTransportGuide.checkedOn))",
                                       "来源（核对于 \(LioTransportGuide.checkedOn)）"))
                        .font(.footnote.weight(.semibold))
                    ForEach(LioTransportGuide.sources(for: mode), id: \.url) { source in
                        Link(source.name, destination: source.url).font(.footnote)
                    }
                }
                .foregroundStyle(LioTheme.inkSecondary)
            }
            .padding(.top, LioTheme.Spacing.xs)
        } label: {
            Text(language.text("Tips for foreign visitors", "外国人购票要点"))
                .font(.headline)
                .foregroundStyle(LioTheme.ink)
        }
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityIdentifier("lio.transport.tips")
    }
}

extension LioTransportHub: Identifiable {
    var id: String { kind.rawValue + nameZH }
}
#endif
