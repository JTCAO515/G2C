import CJCleanupClient
import CJLioUser

/// Removes an account's in-app location choice (#1748) together with its other message files.
@MainActor public enum LioLocationConsentCleanup {
    public static func erase(in capturedTripDirectory: DeviceCleanupDirectory) throws {
        let consent = try capturedTripDirectory.child(LioLocationConsentStore.directoryName)
        try consent.removeOwnedFile(named: LioLocationConsentStore.fileName)
        try consent.removeEmptyChild()
    }
}
