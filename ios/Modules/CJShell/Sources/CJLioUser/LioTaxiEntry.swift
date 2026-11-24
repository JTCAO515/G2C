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
            try await relay.search(query)
        }, currentPickup: {
            try relay.requireCurrentSession()
            return try await LioTaxiPickupLocation().pickup()
        }, estimate: { route in
            try await relay.estimate(route)
        }, rideLink: { route in
            try await relay.rideLink(route)
        }, openRideLink: { url in
            try relay.requireCurrentSession()
            // v.didi.cn is not a universal link for this path; it redirects to DiDi's OneTravel app link with
            // pickup and destination (#1451, checked by S). Open it normally only when DiDi is installed.
            guard let didi = URL(string: "OneTravel://"), UIApplication.shared.canOpenURL(didi) else { return false }
            return await UIApplication.shared.open(url)
        }, openAppStore: {
            UIApplication.shared.open(URL(string: "https://apps.apple.com/app/id554499054")!)
        })
        let recent = LioTaxiRecentPlaces(directory: recentDirectory, isCurrent: { relay.permitsLocalAccess })
        return Self(service: service, recentStore: recent, tripPlaces: tripPlaces)
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
