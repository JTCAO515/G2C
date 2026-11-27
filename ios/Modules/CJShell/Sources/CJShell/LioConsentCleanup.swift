import CJCleanupClient
import CJLioUser

/// Removes an account's consent choices (#1747) together with its other message files.
@MainActor public enum LioConsentCleanup {
    public static func erase(in capturedTripDirectory: DeviceCleanupDirectory) throws {
        let consent = try capturedTripDirectory.child(LioConsentStore.directoryName)
        try consent.removeOwnedFile(named: LioConsentStore.fileName)
        try consent.removeEmptyChild()
    }
}
