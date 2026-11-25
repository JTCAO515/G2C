import CJCleanupClient
import CJLioUser

/// Removes the plans an account saved on this device (#1453) together with its other message files.
@MainActor public enum LioSavedPlansCleanup {
    public static func erase(in capturedTripDirectory: DeviceCleanupDirectory) throws {
        let plans = try capturedTripDirectory.child(LioSavedPlans.directoryName)
        try plans.removeOwnedFile(named: LioSavedPlans.fileName)
        try plans.removeEmptyChild()
    }
}
