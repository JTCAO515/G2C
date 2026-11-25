import CJCleanupClient
import CJLioUser
import Foundation

/// Removes an account's roadbook copies together with its other message files. Only digest-named JSON files are
/// removed; any other entry keeps the folder, so cleanup reports it incomplete instead of deleting unknown data.
@MainActor public enum LioRoadbookCleanup {
    public static func erase(in capturedTripDirectory: DeviceCleanupDirectory) throws {
        let roadbooks = try capturedTripDirectory.child(LioAccountFolders.roadbookDirectoryName)
        if let url = try roadbooks.existingURLForTrustedHost() {
            for name in try FileManager.default.contentsOfDirectory(atPath: url.path)
                where LioAccountFolders.isRoadbookFileName(name) {
                try roadbooks.removeOwnedFile(named: name)
            }
        }
        try roadbooks.removeEmptyChild()
    }
}
