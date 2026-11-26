#if os(iOS)
import SwiftUI
import UIKit

/// Tools → Roadbook (#1514): roadbooks kept on this phone plus ones that can be made from trips and routes.
struct LioRoadbookLibraryView: View {
    let language: LioLanguage
    let store: LioRoadbookStore?
    /// Roadbooks that can be made now (saved trips, Lio's plans, routes). Kept ones replace these by id.
    let candidates: [LioRoadbook]
    /// The account's saved trips (#1725): a popular route can be used as my trip from its page.
    var savedPlans: LioSavedPlansModel? = nil
    @State private var kept: [LioRoadbook] = []
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.lioRoadbookEnricher) private var injectedEnricher

    /// The host's relay, or the Debug stand-in for previews and screenshots.
    private var enricher: LioRoadbookEnricher? {
        #if DEBUG
        if LioRoadbookPreview.requested { return LioRoadbookPreview.enricher }
        #endif
        return injectedEnricher
    }

    /// Two cards per row like the Tools tab; one at accessibility text sizes.
    private var columns: [GridItem] {
        Array(repeating: GridItem(.flexible(), spacing: LioTheme.Spacing.sm, alignment: .top),
              count: typeSize.isAccessibilitySize ? 1 : 2)
    }

    private var books: [LioRoadbook] { LioRoadbook.library(kept: kept, candidates: candidates, language: language) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
                Text(language.text("Take your trip day by day, even offline. Export it as a PDF to print or share.",
                                   "按天带着走的旅行手册，离线也能看，可导出 PDF 打印或分享。"))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if books.isEmpty {
                    Text(language.text("No roadbooks yet. Ask Lio to plan a trip in Chat, then make a roadbook from it.",
                                       "还没有路书。先在聊天里让 Lio 规划行程，再生成路书。"))
                        .padding(LioTheme.Spacing.md)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                        .accessibilityIdentifier("lio.roadbook.empty")
                }
                LazyVGrid(columns: columns, spacing: LioTheme.Spacing.sm) {
                    ForEach(books) { book in
                        NavigationLink {
                            LioRoadbookView(roadbook: book, language: language, store: store, savedPlans: savedPlans,
                                            onChange: reload)
                                .environment(\.lioRoadbookEnricher, enricher)
                        } label: {
                            LioRoadbookCard(roadbook: book, language: language, kept: kept.contains { $0.id == book.id })
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("lio.roadbook.row.\(book.id)")
                    }
                }
            }
            .padding(.horizontal, LioTheme.Spacing.md)
            .padding(.vertical, 18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Roadbook", "路书"))
        .navigationBarTitleDisplayMode(.inline)
        .tint(LioTheme.vermilion)
        .onAppear(perform: reload)
    }

    private func reload() { kept = store?.load() ?? [] }
}

/// One roadbook as a card: city, the plan's title, days and dates, and whether it is kept on this phone.
private struct LioRoadbookCard: View {
    let roadbook: LioRoadbook
    let language: LioLanguage
    let kept: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            HStack(alignment: .center, spacing: LioTheme.Spacing.xs) {
                Image(systemName: "book.closed")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(LioTheme.vermilion)
                    .frame(width: 36, height: 36)
                    .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                    .accessibilityHidden(true)
                Text(roadbook.source.title(language))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .lineLimit(2)
            }
            Text(roadbook.coverTitle(language))
                .font(.headline)
                .lineLimit(2)
            Text(roadbook.itinerary.title)
                .font(.subheadline)
                .lineLimit(2)
            Text(roadbook.coverLine(language))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .lineLimit(2)
            if kept {
                Label(language.text("On this phone", "已离线保存"), systemImage: "checkmark.circle.fill")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(LioTheme.jade)
                    .lineLimit(2)
            }
            Spacer(minLength: 0)
        }
        .fixedSize(horizontal: false, vertical: true)
        .multilineTextAlignment(.leading)
        .frame(maxWidth: .infinity, minHeight: 132, alignment: .topLeading)
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityElement(children: .combine)
    }
}

/// One roadbook: cover, a day at a time split into morning / afternoon / evening, where to stay and the essentials.
struct LioRoadbookView: View {
    let roadbook: LioRoadbook
    let language: LioLanguage
    let store: LioRoadbookStore?
    /// Saved trips (#1725); a template's page offers "Use as my trip" when they can be written.
    var savedPlans: LioSavedPlansModel? = nil
    var onChange: () -> Void = {}
    @Environment(LioRouter.self) private var router: LioRouter?
    @State private var selectedDay: Int?
    @State private var kept = false
    @State private var notice: String?
    @State private var exporting = false
    @State private var shared: SharedFile?
    @State private var taxiPlace: LioTaxiPlace?
    @State private var driverPlace: LioRichItinerary.Place?
    @State private var filled: [String: LioRoadbookDetail] = [:]
    @State private var filling = false
    @State private var expanded: Set<String> = []
    /// Owns the fill-in task: it is cancelled only when this roadbook screen goes away for good, not when
    /// another screen (Local Support, the driver card) covers it, so a request in flight is never thrown away.
    /// It starts as nil and is made in `fill()`: the view value the task captures then only holds nil,
    /// so the task never keeps its own owner alive (#1631 review).
    @State private var filler: LioRoadbookFillTask?
    @Environment(\.lioTaxiEntry) private var taxiEntry
    #if os(iOS)
    @Environment(\.lioRoadbookEnricher) private var enricher
    #endif
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// The roadbook as shown: places filled in during this visit on top of the ones it already had.
    private var book: LioRoadbook { roadbook.with(details: filled) }

    private struct SharedFile: Identifiable { let url: URL; var id: URL { url } }

    private var day: LioRichItinerary.Day? {
        book.itinerary.days.first { $0.number == selectedDay } ?? book.itinerary.days.first
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
                cover
                if let notice {
                    Text(notice).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                        .accessibilityIdentifier("lio.roadbook.notice")
                }
                if book.itinerary.days.count > 1 { dayPicker }
                if let day { dayPage(day) }
                lodging
                essentials
                Text(LioRoadbook.officialNotice(language)).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
            .padding(.horizontal, LioTheme.Spacing.md)
            .padding(.vertical, 18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(book.coverTitle(language))
        .navigationBarTitleDisplayMode(.inline)
        .tint(LioTheme.vermilion)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { export() } label: {
                    Label(language.text("Export PDF", "导出 PDF"), systemImage: "square.and.arrow.up")
                }
                .disabled(exporting)
                .accessibilityIdentifier("lio.roadbook.export")
            }
        }
        .onAppear { kept = store?.contains(book.id) ?? false }
        // The exported PDF may hold a saved trip: it leaves the phone only through the share sheet
        // and is removed as soon as sharing ends or the roadbook closes.
        .sheet(item: $shared, onDismiss: LioRoadbookPDF.removeExports) { file in
            LioRoadbookShareSheet(items: [file.url]).ignoresSafeArea()
        }
        .onDisappear(perform: LioRoadbookPDF.removeExports)
        .sheet(item: $taxiPlace) { place in
            if let taxiEntry {
                NavigationStack {
                    LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                                recentStore: taxiEntry.recentStore, destination: place)
                }
            }
        }
        .fullScreenCover(item: Binding(get: { driverPlace.map(DriverPlace.init) }, set: { driverPlace = $0?.place })) { item in
            // The app's shared driver sign (#1550): large Chinese name and checked address, screen kept awake.
            LioDriverSign(language: language, nameZH: item.place.nameZH, nameEN: item.place.nameEN,
                          addressZH: LioRoadbook.driverAddress(item.place), requestZH: "请送我到这里",
                          identifierPrefix: "lio.roadbook.driver")
        }
    }

    private struct DriverPlace: Identifiable {
        let place: LioRichItinerary.Place
        var id: String { place.nameZH + (place.address ?? "") }
    }

    // MARK: cover

    private var cover: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text(language.text("Travel roadbook", "自由行路书"))
                .font(.footnote.weight(.semibold)).foregroundStyle(LioTheme.vermilion)
            Text(book.coverTitle(language))
                .font(LioTheme.display(.largeTitle).weight(.bold))
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("lio.roadbook.cover.title")
            if book.city != nil { Text(book.itinerary.title).font(.headline) }
            Text(book.coverLine(language)).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.roadbook.cover.line")
            HStack(spacing: LioTheme.Spacing.xs) {
                if kept {
                    Label(language.text("On this phone", "已离线保存"), systemImage: "checkmark.circle.fill")
                        .font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.jade)
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("lio.roadbook.kept")
                } else if store != nil {
                    Button { keep() } label: {
                        Label(language.text("Keep offline", "离线保存"), systemImage: "arrow.down.circle")
                    }
                    .buttonStyle(LioSecondaryButtonStyle(fullWidth: false))
                    .accessibilityIdentifier("lio.roadbook.keep")
                }
                Button { export() } label: {
                    Label(language.text("PDF", "导出 PDF"), systemImage: "doc.richtext")
                }
                .buttonStyle(LioSecondaryButtonStyle(fullWidth: false))
                .disabled(exporting)
                .accessibilityIdentifier("lio.roadbook.pdf")
            }
            .padding(.top, LioTheme.Spacing.xs)
            useAsTrip
            #if os(iOS)
            if enricher != nil, !book.placesToFillIn().isEmpty {
                Button { fill() } label: {
                    Label(filling ? language.text("Filling in…", "正在补充…")
                                  : language.text("Add place details", "补充景点信息"), systemImage: "sparkles")
                }
                .buttonStyle(LioSecondaryButtonStyle(fullWidth: false))
                .disabled(filling)
                .accessibilityIdentifier("lio.roadbook.fill")
                Text(language.text("Sends only place names and the city.", "只发送地点名和城市。"))
                    .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
            #endif
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private var dayPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: LioTheme.Spacing.xs) {
                ForEach(book.itinerary.days) { item in
                    let selected = item.number == day?.number
                    Button {
                        withAnimation(LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion)) {
                            selectedDay = item.number
                        }
                    } label: {
                        VStack(spacing: 2) {
                            Text(language.text("Day \(item.number)", "第 \(item.number) 天")).font(.subheadline.weight(.semibold))
                            if !item.area.isEmpty { Text(item.area).font(.caption).lineLimit(1) }
                        }
                        .foregroundStyle(selected ? LioTheme.onVermilion : LioTheme.ink)
                        .padding(.horizontal, LioTheme.Spacing.md)
                        .frame(minHeight: 48)
                        .background(selected ? LioTheme.vermilion : LioTheme.surface, in: Capsule())
                        .overlay { Capsule().stroke(LioTheme.hairline, lineWidth: selected ? 0 : LioTheme.outlineWidth) }
                        .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(selected ? [.isSelected] : [])
                    .accessibilityIdentifier("lio.roadbook.day.\(item.number)")
                }
            }
            .padding(.vertical, 2)
        }
    }

    // MARK: a day

    private func dayPage(_ day: LioRichItinerary.Day) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                Text(book.dayTitle(day, language)).font(LioTheme.display(.title2).weight(.bold))
                    .accessibilityAddTraits(.isHeader)
                let summary = [day.theme, day.area].filter { !$0.isEmpty }.joined(separator: " · ")
                if !summary.isEmpty { Text(summary).foregroundStyle(LioTheme.inkSecondary) }
            }
            let segments = LioRoadbook.segments(day)
            if segments.isEmpty {
                Text(language.text("No activities planned for this day yet.", "这一天还没有安排。"))
                    .foregroundStyle(LioTheme.inkSecondary)
            }
            ForEach(segments) { segment in
                VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                    Label(segment.period.title(language), systemImage: segment.period.symbol)
                        .font(.headline).foregroundStyle(LioTheme.vermilion)
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("lio.roadbook.period.\(segment.period)")
                    ForEach(segment.entries) { entry in
                        stopCard(entry)
                        if let leg = entry.legAfter {
                            Label(leg.description(language), systemImage: leg.symbol)
                                .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(.leading, LioTheme.Spacing.md)
                                .accessibilityIdentifier("lio.roadbook.leg.\(entry.number)")
                        }
                    }
                }
            }
        }
    }

    private func stopCard(_ entry: LioRoadbookEntry) -> some View {
        let stop = entry.stop
        let address = LioRoadbook.driverAddress(stop.place)
        return VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            HStack(alignment: .top, spacing: LioTheme.Spacing.sm) {
                Text("\(entry.number)").font(.subheadline.weight(.bold)).foregroundStyle(LioTheme.onVermilion)
                    .frame(minWidth: 28, minHeight: 28).background(LioTheme.vermilion, in: Circle())
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(stop.place.displayName(language)).font(.headline)
                    if language == .english, stop.place.nameEN != stop.place.nameZH {
                        Text(stop.place.nameZH).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    }
                    let meta = [stop.kind.title(language), stop.time, stop.note].compactMap { $0 }.filter { !$0.isEmpty }
                    Text(meta.joined(separator: " · ")).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                }
            }
            if !stop.text.isEmpty { Text(stop.text) }
            if let address {
                Label(address, systemImage: "mappin").font(.subheadline).textSelection(.enabled)
            } else {
                Text(language.text("Suggested place — check the address before you go.", "地点建议，出发前请再确认地址。"))
                    .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
            if let tip = stop.tip, !tip.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Label(tip, systemImage: "exclamationmark.circle").font(.subheadline)
                    Text(language.text("Check official sources", "以官方为准")).font(.caption).foregroundStyle(LioTheme.inkSecondary)
                }
                .padding(LioTheme.Spacing.xs)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
            }
            if let detail = book.details[stop.id] {
                detailSection(detail, stopID: stop.id)
            }
            // #1740: taxi, driver card, directions and booking through the shared row and the tool router.
            LioPlaceActionRow(stop: stop, language: language, identifierPrefix: "lio.roadbook")
        }
        .fixedSize(horizontal: false, vertical: true)
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityIdentifier("lio.roadbook.stop.\(stop.id)")
    }

    // MARK: place details (ROADBOOK.1)

    private func detailSection(_ detail: LioRoadbookDetail, stopID: String) -> some View {
        DisclosureGroup(isExpanded: Binding(get: { expanded.contains(stopID) },
                                            set: { if $0 { expanded.insert(stopID) } else { expanded.remove(stopID) } })) {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                ForEach(LioRoadbookDetail.Field.allCases, id: \.self) { field in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(field.title(language)).font(.footnote.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary)
                        Text(detail.field(field, language)).font(.subheadline)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
                if !detail.metro.isEmpty {
                    Label(detail.metro.map { $0.text(language) }.joined(separator: language.text("; ", "；")),
                          systemImage: "tram").font(.subheadline)
                }
                ForEach(detail.restaurants) { restaurant in
                    HStack(alignment: .top, spacing: LioTheme.Spacing.xs) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(restaurant.nameZH).font(.subheadline.weight(.semibold))
                            Text(restaurant.addressZH).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                        }
                        Spacer(minLength: 0)
                        if taxiEntry != nil {
                            Button { taxiPlace = restaurant.taxiPlace } label: {
                                Image(systemName: "car.fill").frame(width: 44, height: 44)
                            }
                            .accessibilityLabel(language.text("Taxi to \(restaurant.nameZH)", "打车去\(restaurant.nameZH)"))
                        }
                        Button { driverPlace = restaurant.place } label: {
                            Image(systemName: "person.text.rectangle").frame(width: 44, height: 44)
                        }
                        .accessibilityLabel(language.text("Show the driver", "给司机看"))
                    }
                }
                Text(LioRoadbook.officialNotice(language)).font(.caption).foregroundStyle(LioTheme.inkSecondary)
            }
            .padding(.top, LioTheme.Spacing.xs)
        } label: {
            Label(language.text("Place details", "景点详情"), systemImage: "text.book.closed").font(.subheadline.weight(.semibold))
        }
        .accessibilityIdentifier("lio.roadbook.detail.\(stopID)")
    }

    // MARK: back matter

    @ViewBuilder private var lodging: some View {
        let itinerary = book.itinerary
        if !itinerary.lodgingArea.isEmpty || !itinerary.hotels.isEmpty {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                Label(language.text("Where to stay", "住宿区域"), systemImage: "bed.double")
                    .font(.headline).accessibilityAddTraits(.isHeader)
                if !itinerary.lodgingArea.isEmpty { Text(itinerary.lodgingArea) }
                ForEach(itinerary.hotels) { hotel in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(hotel.place.displayName(language)).font(.subheadline.weight(.semibold))
                        if let note = LioRoadbook.visibleNote(hotel.note) { Text(note).font(.footnote).foregroundStyle(LioTheme.inkSecondary) }
                    }
                }
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        }
    }

    private var essentials: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            ForEach(LioRoadbookEssentials.sections(language)) { section in
                DisclosureGroup {
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                        ForEach(section.items) { item in essentialItem(item) }
                        if section.id == "emergency" {
                            NavigationLink {
                                LioLocalSupportView(language: language, directory: try? LocalSupportDirectory.bundled())
                            } label: {
                                Label(language.text("Open Local Support", "打开本地协助"), systemImage: "lifepreserver")
                                    .frame(minHeight: 44)
                            }
                            .accessibilityIdentifier("lio.roadbook.local-support")
                        }
                    }
                    .padding(.top, LioTheme.Spacing.xs)
                } label: {
                    Label(section.title, systemImage: section.symbol).font(.headline).foregroundStyle(LioTheme.ink)
                }
                .padding(LioTheme.Spacing.md)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                .accessibilityIdentifier("lio.roadbook.essentials.\(section.id)")
            }
        }
    }

    @ViewBuilder private func essentialItem(_ item: LioRoadbookEssentialItem) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            if let phone = item.phone, let url = URL(string: "tel:" + phone) {
                Link(destination: url) {
                    Label("\(item.title)  \(phone)", systemImage: "phone.fill").font(.subheadline.weight(.semibold))
                        .frame(minHeight: 44, alignment: .leading)
                }
            } else {
                Text(item.title).font(.subheadline.weight(.semibold))
            }
            if language == .english, let chinese = item.chinese, chinese != item.title {
                Text(chinese).font(.title3)
            }
            if let detail = item.detail { Text(detail).font(.footnote).foregroundStyle(LioTheme.inkSecondary) }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: actions

    /// #1725: a popular route becomes the traveller's trip (its checked places, on this phone only).
    @ViewBuilder private var useAsTrip: some View {
        if roadbook.source == .template, let savedPlans, savedPlans.writable {
            if savedPlans.isSavedTemplate(roadbook) {
                HStack(spacing: LioTheme.Spacing.xs) {
                    Label(language.text("Saved as my trip", "已用作我的行程"), systemImage: "checkmark.circle.fill")
                        .font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.jade)
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("lio.roadbook.template-saved")
                    if let router {
                        Button(language.text("Open Trips", "查看行程")) { router.tab = .trips }
                            .buttonStyle(LioSecondaryButtonStyle(fullWidth: false))
                            .accessibilityIdentifier("lio.roadbook.template-open-trips")
                    }
                }
            } else {
                Button { useTemplate(savedPlans) } label: {
                    Label(language.text("Use as my trip", "用作我的行程"), systemImage: "calendar.badge.plus")
                }
                .buttonStyle(LioSecondaryButtonStyle(fullWidth: false))
                .accessibilityIdentifier("lio.roadbook.use-template")
            }
        }
    }

    private func useTemplate(_ savedPlans: LioSavedPlansModel) {
        if savedPlans.saveTemplate(roadbook) != nil {
            notice = nil
        } else {
            notice = language.text("Couldn’t save this route as your trip. Try again.", "暂时无法用作我的行程，请重试。")
        }
    }

    private func keep() {
        guard let store else { return }
        do {
            try store.save(book.kept())
            kept = true
            notice = nil
            onChange()
        } catch {
            notice = language.text("Couldn’t keep this roadbook on your phone. Try again.", "暂时无法离线保存，请重试。")
        }
    }

    #if os(iOS)
    /// Asks the relay for every place not filled in yet, at most eight per request, and keeps the answers.
    private func fill() {
        guard let enricher, !filling else { return }
        filling = true
        notice = nil
        let batches = LioRoadbookWire.batches(book.placesToFillIn())
        let holder = LioRoadbookFillTask()
        filler = holder
        // The task gets only these bindings and values, never `self`: through its @State storage `self`
        // reaches the holder, which would keep the task alive after the screen closes (#1631 review).
        let state = LioRoadbookFillState(filled: $filled, notice: $notice, filling: $filling, kept: $kept)
        let (roadbook, store, language) = (roadbook, store, language)
        holder.task = Task {
            await Self.fill(batches, enricher: enricher, roadbook: roadbook, store: store, language: language,
                            state: state)
        }
    }

    private static func fill(_ batches: [[LioRoadbookPlaceQuery]], enricher: LioRoadbookEnricher,
                             roadbook: LioRoadbook, store: LioRoadbookStore?, language: LioLanguage,
                             state: LioRoadbookFillState) async {
        defer { state.filling.wrappedValue = false }
        var limited = false, missing = false, notice: String?
        for batch in batches {
            guard !Task.isCancelled else { break }
            do {
                let result = try await enricher.enrich(batch)
                for (id, status) in result {
                    switch status {
                    case .ready(let detail): state.filled.wrappedValue[id] = detail
                    case .limited: limited = true
                    case .unavailable: missing = true
                    }
                }
            } catch let failure as LioRoadbookFailure {
                notice = failure.message(language)
                break
            } catch is CancellationError {
                break  // the screen closed or the session changed: nothing to tell
            } catch {
                notice = LioRoadbookFailure.unavailable.message(language)
                break
            }
            if limited { break }
        }
        if notice == nil, limited { notice = LioRoadbookFailure.limited.message(language) }
        else if notice == nil, missing {
            notice = language.text("Some places couldn’t be filled in.", "部分地点暂时无法补充。")
        }
        if let notice { state.notice.wrappedValue = notice }
        if state.kept.wrappedValue, let store {
            // Keep the time the copy was first kept, not the route's own date.
            let book = roadbook.with(details: state.filled.wrappedValue)
            let keptAt = store.load().first { $0.id == book.id }?.createdAt ?? .now
            do {
                try store.save(book.kept(at: keptAt))
            } catch {
                // Same notice as a failed first keep: the copy on the phone still lacks these places.
                state.notice.wrappedValue = language.text("Couldn’t keep this roadbook on your phone. Try again.",
                                                          "暂时无法离线保存，请重试。")
            }
        }
    }
    #endif

    private func export() {
        guard !exporting else { return }
        exporting = true
        let roadbook = book, language = language
        let folder = LioRoadbookPDF.exportDirectory
        Task {
            defer { exporting = false }
            do {
                let url = try await Task.detached(priority: .userInitiated) {
                    try LioRoadbookPDF.write(roadbook, language: language, to: folder)
                }.value
                shared = SharedFile(url: url)
            } catch {
                notice = language.text("Couldn’t make the PDF. Try again.", "暂时无法生成 PDF，请重试。")
            }
        }
    }
}

/// The system share sheet for the exported PDF (Save to Files, Print, AirDrop, Mail…).
struct LioRoadbookShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}

#if DEBUG
#Preview("Roadbook library") {
    NavigationStack {
        LioRoadbookLibraryView(language: .chinese, store: nil, candidates: LioRoadbookPreview.library(.chinese))
    }
}

#Preview("Roadbook") {
    NavigationStack {
        LioRoadbookView(roadbook: LioRoadbookPreview.beijing(.english), language: .english, store: nil)
    }
}
#endif
#endif
