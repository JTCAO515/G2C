#if os(iOS)
import SwiftUI
import UIKit

public struct LioTaxiEntry: Sendable {
    let service: LioTaxiService
    let recentStore: LioTaxiRecentPlaces
    let tripPlaces: [LioTaxiPlace]
    @MainActor static func internalBeta(relay: LioTaxiRelayClient, recentDirectory: URL,
                                        tripPlaces: [LioTaxiPlace]) -> Self {
        let service = LioTaxiService(search: { query in
            tripPlaces.filter {
                $0.nameZH.localizedStandardContains(query) || $0.nameEN.localizedStandardContains(query)
                    || $0.addressZH?.localizedStandardContains(query) == true
            }
        }, currentPickup: {
            try await LioTaxiPickupLocation().pickup()
        }, estimate: { route in
            try await relay.estimate(route)
        }, rideLink: { route in
            try await relay.rideLink(route)
        }, openRideLink: { url in
            await UIApplication.shared.open(url, options: [.universalLinksOnly: true])
        }, openAppStore: {
            UIApplication.shared.open(URL(string: "https://apps.apple.com/app/id554499054")!)
        })
        return Self(service: service, recentStore: LioTaxiRecentPlaces(directory: recentDirectory),
                    tripPlaces: tripPlaces)
    }

}

private struct LioTaxiEntryKey: EnvironmentKey {
    static let defaultValue: LioTaxiEntry? = nil
}

extension EnvironmentValues {
    var lioTaxiEntry: LioTaxiEntry? {
        get { self[LioTaxiEntryKey.self] }
        set { self[LioTaxiEntryKey.self] = newValue }
    }
}

#if DEBUG
extension LioTaxiEntry {
    @MainActor static var previewFromArguments: LioTaxiEntry? {
        guard let service = LioTaxiService.previewFromArguments else { return nil }
        return LioTaxiEntry(service: service, recentStore: LioTaxiService.previewRecents,
                            tripPlaces: LioTaxiService.previewDestinations)
    }
}
#endif
#endif
