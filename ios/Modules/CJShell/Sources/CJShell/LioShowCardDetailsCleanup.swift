import CJCleanupClient
import CJLioUser

/// Removes the details an account typed on the show cards (#1572) together with its other message files.
@MainActor public enum LioShowCardDetailsCleanup {
    public static func erase(in capturedTripDirectory: DeviceCleanupDirectory) throws {
        let details = try capturedTripDirectory.child(LioShowCardDetailsStore.directoryName)
        try details.removeOwnedFile(named: LioShowCardDetailsStore.fileName)
        try details.removeEmptyChild()
    }
}
