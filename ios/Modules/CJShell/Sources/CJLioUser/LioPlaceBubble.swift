import Foundation

/// Words of the place bubble card (#1991). The first group is `codex-inbox/G4/ui-copy.json` (`place.more.button`); the
/// rest is not in that file yet, so its wording is a placeholder for the copy review (`isPlaceholder`). Swapping a
/// string changes only this file.
enum LioPlaceBubbleCopy: String, CaseIterable, Sendable {
    // In ui-copy.json.
    case more = "place.more.button"
    case saveFailed = "common.save_failed.message"

    // Placeholders: not in ui-copy.json.
    case placeKind = "place.mention.kind"
    case mentionHint = "place.mention.hint"
    case added = "place.bubble.added"
    case alreadyAdded = "place.bubble.already_added"
    case close = "place.bubble.close"

    var isPlaceholder: Bool {
        switch self {
        case .more, .saveFailed: false
        default: true
        }
    }

    private var words: (en: String, zh: String) {
        switch self {
        case .more: ("See more", "更多")
        case .saveFailed: ("Couldn’t save your changes.", "未能保存。")
        case .placeKind: ("place", "地点")
        case .mentionHint: ("Opens a card for this place", "打开这个地点的卡片")
        case .added: ("Added to your trip", "已加入行程")
        case .alreadyAdded: ("Already in your trip", "已在行程里")
        case .close: ("Close", "关闭")
        }
    }

    func text(_ language: LioLanguage) -> String { language == .chinese ? words.zh : words.en }

    /// What VoiceOver says for a place word: its name, then "place" (「故宫博物院，地点」).
    static func spoken(_ name: String, _ language: LioLanguage) -> String {
        name + language.text(", ", "，") + LioPlaceBubbleCopy.placeKind.text(language)
    }
}

extension LioPlacePresentation {
    /// The one line about opening and booking on a bubble card: the booking and closing days when the library has
    /// them, else the first line of the opening hours; nil when it has neither.
    var bubbleHint: String? { statusLine ?? hours.first }
}

#if os(iOS)
import SwiftUI
import UIKit

/// The small card a tapped place word opens in place (#1991, 58.1 D-3): a small picture slot, the Chinese and English
/// names, one line about the place, an opening or booking hint, up to five buttons (add to trip, taxi, show the
/// driver, directions, booking: the place page's own, from `LioPlaceActions`) and "See more" for the place page. A
/// button appears only when it can work for that place; there are no greyed-out buttons. Identifiers are
/// `lio.place.bubble.name|name.other|intro|hint` and `lio.place.bubble.add|taxi|driver|navigate|book|more` (none on
/// the card itself: an identifier on a container would replace its children's).
struct LioPlaceBubbleCard: View {
    let place: LioPlace
    let language: LioLanguage
    let actions: LioPlaceActions
    /// The place comes from the unreviewed development pack (Debug builds only): the card says so, as the place page does.
    var developmentData = false
    /// Whether "Add to trip" can work here; `addResult` is what the last tap did.
    let canAdd: Bool
    let addResult: LioPlaceTripAdd?
    var add: () -> Void = {}
    var open: (LioRoute) -> Void = { _ in }
    var showDriver: () -> Void = {}
    var navigate: (LioPlaceActions.Navigation) -> Void = { _ in }
    var more: () -> Void = {}
    @ScaledMetric(relativeTo: .body) private var pictureSize = 56.0

    var body: some View {
        let page = LioPlacePresentation(place, language: language, developmentData: developmentData)
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            HStack(alignment: .top, spacing: LioTheme.Spacing.sm) {
                picture(page)
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                    Text(page.title)
                        .font(.headline)
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("lio.place.bubble.name")
                    if let subtitle = page.subtitle {
                        Text(subtitle).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                            .accessibilityIdentifier("lio.place.bubble.name.other")
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            if let label = page.developmentLabel, let note = page.developmentNote {
                Label(label, systemImage: "hammer.fill").font(.caption.weight(.semibold)).foregroundStyle(LioTheme.vermilion)
                    .accessibilityLabel(note)
                    .accessibilityIdentifier("lio.place.bubble.dev")
            }
            if let line = page.oneLiner {
                Text(line).font(.subheadline).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("lio.place.bubble.intro")
            }
            if let hint = page.bubbleHint {
                Label(hint, systemImage: "ticket").font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("lio.place.bubble.hint")
            }
            buttons
            Button(action: more) {
                HStack {
                    Text(LioPlaceBubbleCopy.more.text(language))
                    Spacer(minLength: LioTheme.Spacing.xs)
                    Image(systemName: "chevron.right").accessibilityHidden(true)
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(LioTheme.vermilion)
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.place.bubble.more")
        }
        .foregroundStyle(LioTheme.ink)
        .tint(LioTheme.vermilion)
        .padding(LioTheme.Spacing.md)
        .frame(width: 320, alignment: .leading)
    }

    /// No picture is shown without a licence record (as on the place page): a plain slot with the place's symbol.
    private func picture(_ page: LioPlacePresentation) -> some View {
        ZStack {
            RoundedRectangle(cornerRadius: LioTheme.Radius.small).fill(LioTheme.surfaceSunken)
            Image(systemName: page.symbol).font(.title3).foregroundStyle(LioTheme.inkSecondary)
        }
        .frame(width: pictureSize, height: pictureSize)
        .accessibilityHidden(true)
    }

    @ViewBuilder private var buttons: some View {
        if canAdd || !actions.actions.isEmpty {
            VStack(spacing: LioTheme.Spacing.xs) {
                if canAdd { addButton }
                if !actions.actions.isEmpty {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 128), spacing: LioTheme.Spacing.xs)],
                              spacing: LioTheme.Spacing.xs) {
                        if let route = actions.taxi {
                            Button { open(route) } label: {
                                Label(LioPlaceCopy.taxi.text(language), systemImage: "car.fill")
                            }
                            .accessibilityIdentifier("lio.place.bubble.taxi")
                        }
                        if actions.driver != nil {
                            Button(action: showDriver) {
                                Label(LioPlaceCopy.showDriver.text(language), systemImage: "person.text.rectangle")
                            }
                            .accessibilityIdentifier("lio.place.bubble.driver")
                        }
                        if let navigation = actions.navigation {
                            Button { navigate(navigation) } label: {
                                Label(LioPlaceCopy.navigate.text(language), systemImage: "arrow.triangle.turn.up.right.diamond")
                            }
                            .accessibilityIdentifier("lio.place.bubble.navigate")
                        }
                        if let route = actions.booking {
                            Button { open(route) } label: {
                                Label(LioPlaceCopy.book.text(language), systemImage: "ticket")
                            }
                            .accessibilityIdentifier("lio.place.bubble.book")
                        }
                    }
                    .buttonStyle(LioPlaceBubbleButtonStyle())
                }
            }
        }
    }

    @ViewBuilder private var addButton: some View {
        let done = addResult == .added || addResult == .alreadyThere
        Button(action: add) {
            Label(addTitle, systemImage: done ? "checkmark.circle.fill" : "plus.circle.fill")
        }
        .buttonStyle(LioPrimaryButtonStyle())
        .disabled(done)
        .accessibilityIdentifier("lio.place.bubble.add")
        if addResult == .failed {
            Text(LioPlaceBubbleCopy.saveFailed.text(language)).font(.footnote).foregroundStyle(LioTheme.danger)
                .accessibilityIdentifier("lio.place.bubble.add.failed")
        }
    }

    private var addTitle: String {
        switch addResult {
        case .added: LioPlaceBubbleCopy.added.text(language)
        case .alreadyThere: LioPlaceBubbleCopy.alreadyAdded.text(language)
        case .failed, nil: LioPlaceCopy.addToTrip.text(language)
        }
    }
}

/// The card's small buttons: the secondary look with less padding and a smaller type, so a label such as "Get directions"
/// wraps between words (never inside one) in the card's width, and at least 44 pt high.
struct LioPlaceBubbleButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .multilineTextAlignment(.center)
            .foregroundStyle(isEnabled ? LioTheme.ink : LioTheme.inkSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, LioTheme.Spacing.xs)
            .padding(.vertical, LioTheme.Spacing.xs)
            .frame(maxWidth: .infinity, minHeight: 44)
            .background(configuration.isPressed ? LioTheme.surfaceSunken : LioTheme.surface,
                        in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
            .overlay {
                RoundedRectangle(cornerRadius: LioTheme.Radius.small)
                    .stroke(LioTheme.hairline, lineWidth: LioTheme.outlineWidth)
                    .allowsHitTesting(false)
            }
            .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.small))
    }
}

/// Wraps one answer bubble whose text has place words (#1991). A tap on a word opens `LioPlaceBubbleCard` in a popover
/// in place (`.presentationCompactAdaptation(.popover)` keeps the bubble form on iPhone), pointing at the tapped spot;
/// "See more" opens the place page. A place the App's library does not have was never made a word, so no empty card
/// can open. VoiceOver reads the text as it is and lists each place as an action named "<name>, place".
///
/// With no spans it adds nothing: no gesture, no link handling.
struct LioPlaceMentionHost<Content: View>: View {
    let spans: [LioPlaceSpan]
    let language: LioLanguage
    var repository: LioPlaceRepository = .bundled
    /// Puts a place on the traveller's trip; nil hides "Add to trip".
    var addToTrip: (@MainActor @Sendable (LioPlace) -> LioPlaceTripAdd)?
    private let content: Content

    init(spans: [LioPlaceSpan], language: LioLanguage, repository: LioPlaceRepository = .bundled,
         addToTrip: (@MainActor @Sendable (LioPlace) -> LioPlaceTripAdd)? = nil, @ViewBuilder content: () -> Content) {
        self.spans = spans
        self.language = language
        self.repository = repository
        self.addToTrip = addToTrip
        self.content = content()
    }

    private struct Selection: Identifiable {
        let id = UUID()
        let placeID: String
        let point: CGPoint?
    }

    private struct PageItem: Identifiable { let id: String }

    @Environment(LioRouter.self) private var router: LioRouter?
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @State private var selection: Selection?
    @State private var lastTap: CGPoint?
    @State private var addResult: LioPlaceTripAdd?
    @State private var driverCard: LioShowCardContent?
    @State private var showingDriver = false
    @State private var page: PageItem?
    @State private var mapsUnavailable = false

    var body: some View {
        content
            .environment(\.openURL, OpenURLAction { url in
                guard !spans.isEmpty else { return .systemAction }
                if let id = LioPlaceLinkMarker.placeID(in: url) {
                    choose(id)
                    return .handled
                }
                // Any other link in the `g2c-place` family is not ours: it does nothing.
                return LioPlaceLinkMarker.isPlaceLink(url) ? .handled : .systemAction
            })
            .simultaneousGesture(SpatialTapGesture().onEnded { lastTap = $0.location },
                                 including: spans.isEmpty ? .none : .all)
            .accessibilityActions {
                ForEach(spans, id: \.placeID) { span in
                    if let place = repository.place(id: span.placeID) {
                        Button(LioPlaceBubbleCopy.spoken(place.name(language), language)) { choose(span.placeID) }
                    }
                }
            }
            .popover(item: $selection, attachmentAnchor: anchor, arrowEdge: .top) { selection in
                if let place = repository.place(id: selection.placeID) { bubble(place) }
            }
            .fullScreenCover(isPresented: $showingDriver) {
                if let card = driverCard {
                    LioShowCardSheet(language: language, content: card, title: LioPlaceCopy.showDriver.text(language),
                                     identifierPrefix: "lio.place.bubble.driver.card")
                }
            }
            .sheet(item: $page) { item in placePage(item.id) }
            .alert(LioPlaceCopy.mapsUnavailable.text(language), isPresented: $mapsUnavailable) {
                Button(LioPlaceCopy.ok.text(language), role: .cancel) {}
            }
    }

    private var anchor: PopoverAttachmentAnchor {
        guard let point = selection?.point else { return .rect(.bounds) }
        return .rect(.rect(CGRect(x: point.x - 1, y: point.y - 1, width: 2, height: 2)))
    }

    /// Opens the card of a place the library has; anything else does nothing. The tap's position is recorded by a
    /// gesture that runs beside the link, so the card waits one turn for it.
    private func choose(_ id: String) {
        guard repository.place(id: id) != nil else { return }
        Task { @MainActor in
            await Task.yield()
            addResult = nil
            selection = Selection(placeID: id, point: lastTap)
        }
    }

    private func bubble(_ place: LioPlace) -> some View {
        let actions = placeActions(place)
        let card = LioPlaceBubbleCard(
            place: place, language: language, actions: actions, developmentData: repository.isDevelopmentData(place),
            canAdd: addToTrip != nil, addResult: addResult,
            add: { addResult = addToTrip?(place) ?? .failed },
            open: { route in if router?.open(route) == true { selection = nil } },
            showDriver: {
                driverCard = actions.driver
                dismissThen { showingDriver = true }
            },
            navigate: { navigation in
                dismissThen { openMaps(navigation) }
            },
            more: { dismissThen { page = PageItem(id: place.id) } })
        return ViewThatFits(in: .vertical) {
            card
            ScrollView { card }
        }
        .presentationCompactAdaptation(.popover)
    }

    private func placeActions(_ place: LioPlace) -> LioPlaceActions {
        var context = LioToolContext(language: language)
        context.taxiEntry = taxiEntry
        let visible = Set(LioToolCatalog.visible(context.availability()))
        let routable = router?.toolsShown == true
        return LioPlacePresentation(place, language: language, developmentData: repository.isDevelopmentData(place))
            .actions { routable && visible.contains($0) }
    }

    /// Closes the card, then does `work` once it is gone (a cover or sheet cannot open while the popover is closing).
    private func dismissThen(_ work: @escaping @MainActor () -> Void) {
        selection = nil
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(400))
            work()
        }
    }

    private func openMaps(_ navigation: LioPlaceActions.Navigation) {
        let urls = navigation.urls
        Task { @MainActor in
            for url in urls { if await UIApplication.shared.open(url) { return } }
            mapsUnavailable = true
        }
    }

    private func placePage(_ id: String) -> some View {
        NavigationStack {
            LioPlacePage(placeID: id, language: language, repository: repository,
                         onAddToTrip: addToTrip.map { add -> @MainActor (LioPlace) -> Void in { place in _ = add(place) } },
                         onOpenPlace: { other in page = PageItem(id: other) })
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button(LioPlaceBubbleCopy.close.text(language)) { page = nil }
                            .accessibilityIdentifier("lio.place.bubble.page.close")
                    }
                }
        }
    }
}
#endif
