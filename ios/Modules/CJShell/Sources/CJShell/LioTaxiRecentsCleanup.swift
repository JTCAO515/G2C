import CJCleanupClient
import CJLioUser

@MainActor public enum LioTaxiRecentsCleanup {
    public static func erase(in capturedTripDirectory: DeviceCleanupDirectory) throws {
        let recents = try capturedTripDirectory.child(LioTaxiRecentPlaces.directoryName)
        try recents.removeOwnedFile(named: LioTaxiRecentPlaces.fileName)
        try recents.removeEmptyChild()
    }
}
