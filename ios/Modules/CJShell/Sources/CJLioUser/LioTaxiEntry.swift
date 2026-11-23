#if os(iOS)
import SwiftUI

public struct LioTaxiEntry: Sendable {
    let service: LioTaxiService
    let recentStore: LioTaxiRecentPlaces
    let tripPlaces: [LioTaxiPlace]
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
