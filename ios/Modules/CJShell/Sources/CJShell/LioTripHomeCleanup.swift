import CJCleanupClient
import CJLioUser

/// Removes the trip home's profile and ticks for an account together with its other message files.
@MainActor public enum LioTripHomeCleanup {
    public static func erase(in capturedTripDirectory: DeviceCleanupDirectory) throws {
        let tripHome = try capturedTripDirectory.child(LioTripHomeStore.directoryName)
        try tripHome.removeOwnedFile(named: LioTripHomeStore.fileName)
        try tripHome.removeEmptyChild()
    }
}
