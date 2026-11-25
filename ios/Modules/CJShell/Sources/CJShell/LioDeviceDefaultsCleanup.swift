import Foundation

/// Values a traveller set in Lio that live in the app's shared UserDefaults rather than an account folder:
/// the nationality chosen in Local Support and the arrival checklist progress. Deleting the account removes them
/// (JT 2026-11-25). Switching accounts without deleting one keeps them; per-account storage was not approved.
public enum LioDeviceDefaultsCleanup {
    /// Must match the `@AppStorage` keys in LioLocalSupportView, LioArrivalView and the arrival checklist.
    public static let keys = ["lio.local-support.nationality", "lio.arrival.progress.v1"]

    /// Only account deletion (`account_cleanup`) clears them; `session_invalid` and `offline_expired` cleanups keep them.
    public static func applies(to cleanupReason: String) -> Bool { cleanupReason == "account_cleanup" }

    public static func erase(in defaults: UserDefaults = .standard) {
        for key in keys { defaults.removeObject(forKey: key) }
    }

    /// Account cleanup confirms that nothing is left before it reports the step done.
    public static func requireAbsent(in defaults: UserDefaults = .standard) throws {
        guard keys.allSatisfy({ defaults.object(forKey: $0) == nil }) else { throw Failure.stillPresent }
    }

    public enum Failure: Error, Equatable { case stillPresent }
}
