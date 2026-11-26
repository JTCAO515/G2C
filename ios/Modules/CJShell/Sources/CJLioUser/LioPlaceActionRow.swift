#if os(iOS)
import SwiftUI
import UIKit

/// The buttons under a trip place (#1740), from `LioPlaceActions`. Taxi and booking open their tools through the
/// router; the driver card is the shared show card; directions open a maps app. Identifiers are
/// `<prefix>.taxi.<stop id>`, `<prefix>.driver.<stop id>`, `<prefix>.navigate.<stop id>` and `<prefix>.book.<stop id>`;
/// the driver card's are `<prefix>.driver.card.*`.
struct LioPlaceActionRow: View {
    let stop: LioRichItinerary.Stop
    let language: LioLanguage
    var identifierPrefix: String
    /// Called after a tool opened, for example to close the sheet this row is in.
    var openedTool: (@MainActor () -> Void)?
    @Environment(LioRouter.self) private var router: LioRouter?
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @State private var showingDriver = false
    @State private var mapsUnavailable = false

    private var actions: LioPlaceActions {
        var context = LioToolContext(language: language)
        context.taxiEntry = taxiEntry
        let visible = Set(LioToolCatalog.visible(context.availability()))
        let routable = router?.toolsShown == true
        return LioPlaceActions(stop: stop) { routable && visible.contains($0) }
    }

    var body: some View {
        let actions = actions
        if !actions.actions.isEmpty {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: LioTheme.Spacing.xs) { buttons(actions) }
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) { buttons(actions) }
            }
            .buttonStyle(LioSecondaryButtonStyle(fullWidth: false))
            .fullScreenCover(isPresented: $showingDriver) {
                if let card = actions.driver {
                    LioShowCardSheet(language: language, content: card, title: language.text("Show the driver", "给司机看"),
                                     identifierPrefix: "\(identifierPrefix).driver.card")
                }
            }
            .alert(language.text("Maps couldn’t open this place.", "地图无法打开这个地点。"), isPresented: $mapsUnavailable) {
                Button(language.text("OK", "好"), role: .cancel) {}
            }
        }
    }

    @ViewBuilder private func buttons(_ actions: LioPlaceActions) -> some View {
        if let route = actions.taxi {
            Button { open(route) } label: { Label(language.text("Taxi", "打车"), systemImage: "car.fill") }
                .accessibilityIdentifier("\(identifierPrefix).taxi.\(stop.id)")
        }
        if actions.driver != nil {
            Button { showingDriver = true } label: {
                Label(language.text("Show driver", "给司机看"), systemImage: "person.text.rectangle")
            }
            .accessibilityIdentifier("\(identifierPrefix).driver.\(stop.id)")
        }
        if let navigation = actions.navigation {
            Button { navigate(navigation) } label: {
                Label(language.text("Directions", "导航"), systemImage: "arrow.triangle.turn.up.right.diamond")
            }
            .accessibilityIdentifier("\(identifierPrefix).navigate.\(stop.id)")
        }
        if let route = actions.booking {
            Button { open(route) } label: { Label(language.text("Book", "预约"), systemImage: "ticket") }
                .accessibilityIdentifier("\(identifierPrefix).book.\(stop.id)")
        }
    }

    private func open(_ route: LioRoute) {
        if router?.open(route) == true { openedTool?() }
    }

    private func navigate(_ navigation: LioPlaceActions.Navigation) {
        let urls = navigation.urls
        Task { @MainActor in
            for url in urls { if await UIApplication.shared.open(url) { return } }
            mapsUnavailable = true
        }
    }
}
#endif
