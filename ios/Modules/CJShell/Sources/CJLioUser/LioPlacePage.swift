#if os(iOS)
import SwiftUI
import UIKit

/// The place page (#1992, 58.1 D-4): one page for every place, opened from a bubble card's "See more", a point on
/// the trip canvas, a point on the map or a metro station. Callers pass a `placeID`; everything else is read
/// here, so no caller draws its own version.
///
/// It shows a photo slot (a placeholder: no picture is shown until its licence is on record), the Chinese and
/// English names, an intro, opening and booking notes, how to get there, nearby places to eat and five buttons:
/// add to trip, taxi, show the driver, directions and booking. The tool buttons reuse the trip's actions
/// (`LioPlaceActions`, #1740): taxi and booking open their tools through `LioRouter` (taxi with the destination
/// the tool reads, booking with the sight), the driver card is the shared show card, directions open AMap or
/// Apple Maps. A button appears only when it can work for that place; there are no greyed-out buttons.
///
/// Add to trip is a callback: the page does not talk to the server. Without a callback the button is not shown.
/// Identifiers start with `lio.place.`; the driver card's are `lio.place.driver.card.*`.
struct LioPlacePage: View {
    let placeID: String
    let language: LioLanguage
    var repository: LioPlaceRepository = .bundled
    /// Called with the place when the traveller taps "Add to trip".
    var onAddToTrip: (@MainActor (LioPlace) -> Void)?
    /// Called with a place id when the traveller taps a nearby place; the host decides how to show it.
    var onOpenPlace: (@MainActor (String) -> Void)?
    /// Called after a tool opened (the page has already asked to be dismissed).
    var openedTool: (@MainActor () -> Void)?

    @Environment(LioRouter.self) private var router: LioRouter?
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @Environment(\.dismiss) private var dismiss
    @ScaledMetric(relativeTo: .body) private var imageHeight = 168.0
    @State private var showingDriver = false
    @State private var mapsUnavailable = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
                if let place = repository.place(id: placeID) {
                    content(LioPlacePresentation(place, language: language,
                                                 developmentData: repository.isDevelopmentData(place)), place)
                } else {
                    notFound
                }
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(LioTheme.paper)
        .foregroundStyle(LioTheme.ink)
        .tint(LioTheme.vermilion)
    }

    // MARK: Content

    @ViewBuilder private func content(_ page: LioPlacePresentation, _ place: LioPlace) -> some View {
        photoSlot(page)
        header(page)
        buttons(page, place)
        if let intro = page.intro { section(.about, lines: [intro], identifier: "intro") }
        openingAndBooking(page)
        directions(page)
        nearby(page)
        official(page)
    }

    /// No picture is shown without a licence record, and nothing is drawn in its place: a plain slot that says so.
    private func photoSlot(_ page: LioPlacePresentation) -> some View {
        ZStack {
            RoundedRectangle(cornerRadius: LioTheme.Radius.card).fill(LioTheme.surfaceSunken)
            VStack(spacing: LioTheme.Spacing.xs) {
                Image(systemName: page.symbol).font(.largeTitle).accessibilityHidden(true)
                Text(LioPlaceCopy.imagePlaceholder.text(language)).font(.footnote)
            }
            .foregroundStyle(LioTheme.inkSecondary)
        }
        .frame(maxWidth: .infinity, minHeight: imageHeight)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lio.place.image")
    }

    /// Places from the unreviewed development pack (Debug builds only) say so, in words VoiceOver reads out.
    @ViewBuilder private func developmentBadge(_ page: LioPlacePresentation) -> some View {
        if let label = page.developmentLabel, let note = page.developmentNote {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                Label(label, systemImage: "hammer.fill")
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, LioTheme.Spacing.sm).padding(.vertical, LioTheme.Spacing.xxs)
                    .background(Capsule().fill(LioTheme.surfaceSunken))
                    .overlay(Capsule().stroke(LioTheme.vermilion, lineWidth: 1))
                Text(note).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(note)
            .accessibilityIdentifier("lio.place.devdata")
        }
    }

    private func header(_ page: LioPlacePresentation) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            developmentBadge(page)
            Label(page.kindLabel, systemImage: page.symbol)
                .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.place.kind")
            Text(page.title)
                .font(LioTheme.display(.largeTitle))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("lio.place.name")
            if let subtitle = page.subtitle {
                Text(subtitle).font(.title3).foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("lio.place.name.other")
            }
            if let status = page.statusLine {
                Label(status, systemImage: "ticket").font(.callout)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("lio.place.status")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Buttons

    private func buttons(_ page: LioPlacePresentation, _ place: LioPlace) -> some View {
        let actions = page.actions { routable && visibleTools.contains($0) }
        return VStack(spacing: LioTheme.Spacing.sm) {
            if let onAddToTrip {
                Button { onAddToTrip(place) } label: {
                    Label(LioPlaceCopy.addToTrip.text(language), systemImage: "plus.circle.fill")
                }
                .buttonStyle(LioPrimaryButtonStyle())
                .accessibilityIdentifier("lio.place.add")
            }
            if !actions.actions.isEmpty {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: LioTheme.Spacing.sm)],
                          spacing: LioTheme.Spacing.sm) {
                    if let route = actions.taxi {
                        Button { open(route) } label: {
                            Label(LioPlaceCopy.taxi.text(language), systemImage: "car.fill")
                        }
                        .accessibilityIdentifier("lio.place.taxi")
                    }
                    if actions.driver != nil {
                        Button { showingDriver = true } label: {
                            Label(LioPlaceCopy.showDriver.text(language), systemImage: "person.text.rectangle")
                        }
                        .accessibilityIdentifier("lio.place.driver")
                    }
                    if let navigation = actions.navigation {
                        Button { navigate(navigation) } label: {
                            Label(LioPlaceCopy.navigate.text(language), systemImage: "arrow.triangle.turn.up.right.diamond")
                        }
                        .accessibilityIdentifier("lio.place.navigate")
                    }
                    if let route = actions.booking {
                        Button { open(route) } label: {
                            Label(LioPlaceCopy.book.text(language), systemImage: "ticket")
                        }
                        .accessibilityIdentifier("lio.place.book")
                    }
                }
                .buttonStyle(LioSecondaryButtonStyle())
            }
        }
        .fullScreenCover(isPresented: $showingDriver) {
            if let card = actions.driver {
                LioShowCardSheet(language: language, content: card,
                                 title: LioPlaceCopy.showDriver.text(language),
                                 identifierPrefix: "lio.place.driver.card")
            }
        }
        .alert(LioPlaceCopy.mapsUnavailable.text(language), isPresented: $mapsUnavailable) {
            Button(LioPlaceCopy.ok.text(language), role: .cancel) {}
        }
    }

    /// Tools this build shows; a tool's button needs the router too, because the router opens the tool.
    private var visibleTools: Set<LioTool> {
        var context = LioToolContext(language: language)
        context.taxiEntry = taxiEntry
        return Set(LioToolCatalog.visible(context.availability()))
    }

    private var routable: Bool { router?.toolsShown == true }

    private func open(_ route: LioRoute) {
        guard router?.open(route) == true else { return }
        dismiss()
        openedTool?()
    }

    private func navigate(_ navigation: LioPlaceActions.Navigation) {
        let urls = navigation.urls
        Task { @MainActor in
            for url in urls { if await UIApplication.shared.open(url) { return } }
            mapsUnavailable = true
        }
    }

    // MARK: Sections

    // These two return their sections without a container, so a place with none of them adds no empty gap.
    @ViewBuilder private func openingAndBooking(_ page: LioPlacePresentation) -> some View {
        if !page.hours.isEmpty {
            section(.hours, lines: page.hours, identifier: "hours",
                    footnote: page.hoursAreChineseOnly ? LioPlaceCopy.hoursInChinese.text(language) : nil)
        }
        if !page.tickets.isEmpty { section(.tickets, lines: page.tickets, identifier: "tickets") }
        if page.bookingChannel != nil || page.bookingURL != nil { bookingChannel(page) }
    }

    private func bookingChannel(_ page: LioPlacePresentation) -> some View {
        card(LioPlaceCopy.bookingMethod.text(language)) {
            if let channel = page.bookingChannel { Text(channel).fixedSize(horizontal: false, vertical: true) }
            if let url = page.bookingURL {
                linkRow(LioPlaceCopy.officialInfo.text(language), url: url, identifier: "lio.place.booking.link")
            }
        }
    }

    @ViewBuilder private func directions(_ page: LioPlacePresentation) -> some View {
        if !page.directions.isEmpty {
            section(.directions, lines: page.directions, identifier: "directions", selectable: true)
        }
        if !page.terminals.isEmpty { section(.terminalsLabel, lines: page.terminals, identifier: "terminals") }
        if !page.tips.isEmpty { section(.tipsLabel, lines: page.tips, identifier: "tips") }
    }

    @ViewBuilder private func nearby(_ page: LioPlacePresentation) -> some View {
        let neighbours = page.nearbyFood(in: repository)
        if !neighbours.isEmpty {
            card(LioPlaceCopy.nearbyFood.text(language)) {
                ForEach(neighbours, id: \.place.id) { neighbour in
                    nearbyRow(neighbour)
                }
            }
            .accessibilityIdentifier("lio.place.nearby")
        }
    }

    @ViewBuilder private func nearbyRow(_ neighbour: LioPlaceRepository.Neighbour) -> some View {
        let other = LioPlacePresentation(neighbour.place, language: language,
                                         developmentData: repository.isDevelopmentData(neighbour.place))
        let label = VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            HStack(alignment: .firstTextBaseline) {
                Text(other.title).font(.headline).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: LioTheme.Spacing.xs)
                Text(LioPlacePresentation.distanceText(neighbour.metres)).font(.subheadline)
                    .foregroundStyle(LioTheme.inkSecondary)
            }
            if let line = other.oneLiner {
                Text(line).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let dev = other.developmentLabel {
                Label(dev, systemImage: "hammer.fill").font(.caption.weight(.semibold))
                    .foregroundStyle(LioTheme.vermilion)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .contentShape(Rectangle())
        if let onOpenPlace {
            Button { onOpenPlace(neighbour.place.id) } label: { label }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.place.nearby.\(neighbour.place.id)")
        } else {
            label.accessibilityElement(children: .combine)
                .accessibilityIdentifier("lio.place.nearby.\(neighbour.place.id)")
        }
    }

    @ViewBuilder private func official(_ page: LioPlacePresentation) -> some View {
        if let url = page.officialURL {
            card(nil) {
                linkRow(LioPlaceCopy.officialInfo.text(language), url: url, identifier: "lio.place.official")
                if let checked = page.checkedText {
                    Text(checked).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                        .accessibilityIdentifier("lio.place.checked")
                }
            }
        } else if let checked = page.checkedText {
            Text(checked).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.place.checked")
        }
    }

    private var notFound: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            Image(systemName: "mappin.slash").font(.largeTitle).foregroundStyle(LioTheme.inkSecondary)
                .accessibilityHidden(true)
            Text(LioPlaceCopy.notFoundTitle.text(language)).font(LioTheme.display(.title2))
                .accessibilityAddTraits(.isHeader)
            Text(LioPlaceCopy.notFoundBody.text(language)).foregroundStyle(LioTheme.inkSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lio.place.not-found")
    }

    // MARK: Pieces

    @ViewBuilder private func section(_ key: LioPlaceCopy, lines: [String], identifier: String, selectable: Bool = false,
                                      footnote: String? = nil) -> some View {
        let body = card(key.text(language)) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                Text(line).fixedSize(horizontal: false, vertical: true)
            }
            if let footnote {
                Text(footnote).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
        }
        if selectable {
            // An address can be copied; each line stays its own element.
            body.textSelection(.enabled).accessibilityIdentifier("lio.place.\(identifier)")
        } else {
            body.accessibilityElement(children: .combine).accessibilityIdentifier("lio.place.\(identifier)")
        }
    }

    private func card<Content: View>(_ title: String?, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            if let title {
                Text(title).font(.headline).accessibilityAddTraits(.isHeader)
            }
            content()
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func linkRow(_ title: String, url: URL, identifier: String) -> some View {
        Link(destination: url) {
            Label(title, systemImage: "arrow.up.right.square")
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
        }
        .accessibilityIdentifier(identifier)
    }
}
#endif
