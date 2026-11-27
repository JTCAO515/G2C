import CJCleanupClient
import CJLioUser

/// Removes the trip home's profile and ticks, the trip canvas (#1995) and the one-time autosave notice's record (#1994),
/// all in the same folder, for an account together with its other message files.
@MainActor public enum LioTripHomeCleanup {
    public static func erase(in capturedTripDirectory: DeviceCleanupDirectory) throws {
        let tripHome = try capturedTripDirectory.child(LioTripHomeStore.directoryName)
        try tripHome.removeOwnedFile(named: LioTripHomeStore.fileName)
        try tripHome.removeOwnedFile(named: LioTripCanvasStore.fileName)
        try tripHome.removeOwnedFile(named: LioAutosaveNoticeStore.fileName)
        try tripHome.removeEmptyChild()
    }
}
