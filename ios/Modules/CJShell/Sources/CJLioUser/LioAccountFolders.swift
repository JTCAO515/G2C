import Foundation
import SwiftUI

/// Folders inside the signed-in account's message directory that Lio features keep on this device.
/// Account cleanup removes them with the account's other message files.
public enum LioAccountFolders {
    /// Roadbook offline copies (`LioRoadbookStore`): one JSON file per roadbook, named by a SHA-256 hex digest.
    public static let roadbookDirectoryName = LioRoadbookStore.directoryName

    public static func roadbooks(inMessageDirectory directory: URL) -> URL {
        LioRoadbookStore.storageDirectory(inMessageDirectory: directory)
    }

    /// The only file names a roadbook folder may hold; anything else keeps cleanup incomplete.
    public static func isRoadbookFileName(_ name: String) -> Bool {
        // Bytes, not characters: a hex letter followed by a combining mark must not pass.
        let bytes = Array(name.utf8)
        guard bytes.count == 69, bytes.suffix(5).elementsEqual(".json".utf8) else { return false }
        return bytes.prefix(64).allSatisfy { (0x30...0x39).contains($0) || (0x61...0x66).contains($0) }
    }
}

private struct LioRoadbookDirectoryKey: EnvironmentKey { static let defaultValue: URL? = nil }
private struct LioSavedPlansKey: EnvironmentKey { static let defaultValue: LioSavedPlansModel? = nil }

extension EnvironmentValues {
    /// The account's roadbook folder for the Tools tab; nil when no account folder is available.
    var lioRoadbookDirectory: URL? {
        get { self[LioRoadbookDirectoryKey.self] }
        set { self[LioRoadbookDirectoryKey.self] = newValue }
    }
    /// Plans saved from the chat (#1453) for the current account; nil when saving is unavailable.
    var lioSavedPlans: LioSavedPlansModel? {
        get { self[LioSavedPlansKey.self] }
        set { self[LioSavedPlansKey.self] = newValue }
    }
}
