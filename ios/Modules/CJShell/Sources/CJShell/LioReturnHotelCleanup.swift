import CJCleanupClient
import CJLioUser

/// Removes the stay hotel an account saved for Back to Hotel (#1573) together with its other message files.
@MainActor public enum LioReturnHotelCleanup {
    public static func erase(in capturedTripDirectory: DeviceCleanupDirectory) throws {
        let hotel = try capturedTripDirectory.child(LioReturnHotelStore.directoryName)
        try hotel.removeOwnedFile(named: LioReturnHotelStore.fileName)
        try hotel.removeEmptyChild()
    }
}
