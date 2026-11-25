#if os(iOS)
import CJRunClient
import SwiftUI
import UIKit

/// The Tools tab (#1421): a two-column grid of tool cards. Hidden tools are not listed.
struct LioToolsView: View {
    let language: LioLanguage
    let history: LioTranslationHistory?
    let relay: LioRelayTranslationClient?
    let currencyRelay: LioCurrencyRelayClient?
    let enabled: Bool
    let sessionIsCurrent: @MainActor () -> Bool
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @Environment(\.lioNearbyService) private var nearbyService
    @Environment(\.lioHotelFinder) private var hotelFinder
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.lioRoadbookDirectory) private var roadbookDirectory
    @Environment(\.lioSavedPlans) private var savedPlans

    private var availability: LioToolCatalog.Availability {
        var available = LioToolCatalog.Availability()
        available.taxi = taxiEntry != nil
        available.currency = currencyRelay != nil
        available.nearby = nearbyService != nil
        available.hotels = hotelSearch != nil
        available.roadbook = LioRoadbookFeature.enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: "G2CRoadbookEnabled"))
        available.transport = LioTransportService.fromBuild() != nil
        available.arrival = LioArrivalFeature.enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: LioArrivalFeature.infoKey))
        #if DEBUG
        available.hotels = available.hotels || ProcessInfo.processInfo.arguments.contains("--lio-hotels-preview")
        if LioRoadbookPreview.requested { available.roadbook = true }
        if LioArrivalPreview.requested { available.arrival = true }
        #endif
        return available
    }

    /// Hotel search (#1510) only when the build enables it (`G2CHotelEnabled`, off by default), or with the
    /// Debug preview fixture (`--lio-hotel-search-preview`).
    private var hotelSearch: LioHotelFinder? {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--lio-hotel-search-preview") { return .preview }
        #endif
        return hotelFinder
    }

    private var columns: [GridItem] {
        let count = typeSize.isAccessibilitySize ? 1 : 2
        return Array(repeating: GridItem(.flexible(), spacing: LioTheme.Spacing.sm, alignment: .top), count: count)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                    Text(LioToolCatalog.title(language))
                        .font(LioTheme.display(.largeTitle).bold())
                        .foregroundStyle(LioTheme.ink)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityAddTraits(.isHeader)
                    LazyVGrid(columns: columns, spacing: LioTheme.Spacing.sm) {
                        ForEach(LioToolCatalog.visible(availability), id: \.self) { tool in
                            NavigationLink {
                                destination(tool)
                                    .toolbar(.visible, for: .navigationBar)
                            } label: {
                                LioToolCard(tool: tool, language: language)
                            }
                            .buttonStyle(LioToolCardStyle())
                            .accessibilityElement(children: .ignore)
                            .accessibilityLabel(tool.accessibilityLabel(language))
                            .accessibilityAddTraits(.isButton)
                            .accessibilityIdentifier(tool.identifier)
                        }
                    }
                }
                .padding(.horizontal, LioTheme.Spacing.md)
                .padding(.vertical, 18)
            }
            .background(LioTheme.paper)
            .navigationTitle(LioToolCatalog.title(language))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(.hidden, for: .navigationBar)
        }
        .tint(LioTheme.vermilion)
    }

    /// Offline copies live in the signed-in account's folder (#1553) and stop when the session changes.
    private var roadbookStore: LioRoadbookStore? {
        #if DEBUG
        if LioRoadbookPreview.requested { return try? LioRoadbookStore.preview() }
        #endif
        guard let roadbookDirectory else { return nil }
        return LioRoadbookStore(directory: roadbookDirectory, isCurrent: sessionIsCurrent)
    }

    /// Roadbooks that can be made now: the account's saved plans (#1547), plus Debug previews.
    private var roadbookCandidates: [LioRoadbook] {
        var books = (savedPlans?.plans ?? []).map { LioRoadbook(savedPlan: $0) }
        #if DEBUG
        if LioRoadbookPreview.requested { books += LioRoadbookPreview.library(language) }
        #endif
        return books
    }

    @ViewBuilder private func destination(_ tool: LioTool) -> some View {
        switch tool {
        case .arrival:
            LioArrivalView(language: language, hotels: arrivalTrip?.hotels ?? [], arrival: arrivalTrip?.arrival)
        case .localSupport:
            LioLocalSupportView(language: language, directory: try? LocalSupportDirectory.bundled())
        case .taxi:
            if let taxiEntry {
                LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                            recentStore: taxiEntry.recentStore)
            }
        case .currency:
            if let currencyRelay {
                LioCurrencyView(language: language, load: currencyRelay.load)
            }
        case .metro:
            LioMetroGuideView(language: language)
        case .payment:
            LioPaymentGuideView(language: language)
        case .translation:
            LioTextTranslationView(language: language, history: history, enabled: enabled, isCurrent: {
                UIApplication.shared.applicationState != .background && sessionIsCurrent()
            }, relay: relay)
        case .phrases:
            LioPhraseCardsView(language: language)
        case .nearby:
            if let nearbyService {
                LioNearbyView(language: language, service: nearbyService)
            }
        case .transport:
            if let service = LioTransportService.fromBuild() {
                LioTransportView(language: language, service: service)
            }
        case .roadbook:
            LioRoadbookLibraryView(language: language, store: roadbookStore, candidates: roadbookCandidates)
        case .hotels:
            if let hotelSearch {
                LioHotelOffersView(language: language, finder: hotelSearch)
            } else {
                hotelLinks
            }
        }
    }

    /// Arrival mode uses the stays and first day of the next saved dated plan (or the first saved plan).
    private var arrivalTrip: (hotels: [LioRichItinerary.Hotel], arrival: Date?)? {
        #if DEBUG
        if LioArrivalPreview.requested { return (LioArrivalPreview.hotels, nil) }
        #endif
        let plans = savedPlans?.plans ?? []
        let today = LioArrivalDay(date: .now)
        let upcoming = plans.first { plan in plan.startDate.flatMap(LioArrivalDay.init).map { $0 >= today } ?? false }
        guard let plan = upcoming ?? plans.first else { return nil }
        return (plan.itinerary.hotels, plan.startDate.flatMap(LioArrivalDay.init)?.date)
    }

    @ViewBuilder private var hotelLinks: some View {
        #if DEBUG
        let partial = ProcessInfo.processInfo.arguments.contains("--lio-hotels-preview-partial")
        LioHotelsView(language: language, service: .preview(unapplied: partial ? [.guests] : []),
                      suggestedArea: LioHotelService.previewArea)
        #else
        EmptyView()
        #endif
    }
}

/// One tool card: tinted icon, name and a one-sentence summary on a `surface` card.
struct LioToolCard: View {
    let tool: LioTool
    let language: LioLanguage

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Image(systemName: tool.symbol)
                .font(.title3.weight(.semibold))
                .foregroundStyle(LioTheme.vermilion)
                .frame(width: 36, height: 36)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                .accessibilityHidden(true)
            Text(tool.name(language))
                .font(.headline)
                .foregroundStyle(LioTheme.ink)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            Text(tool.summary(language))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .multilineTextAlignment(.leading)
        .frame(maxWidth: .infinity, minHeight: 108, alignment: .topLeading)
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

private struct LioToolCardStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(LioTheme.Motion.animation(LioTheme.Motion.micro, reduceMotion: reduceMotion),
                       value: configuration.isPressed)
    }
}
#endif
