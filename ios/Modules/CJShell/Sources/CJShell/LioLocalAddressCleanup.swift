import CJCleanupClient
import CJLioUser

@MainActor public enum LioLocalAddressCleanup {
    public static func erase(in capturedMessageDirectory: DeviceCleanupDirectory) throws {
        let directory = try capturedMessageDirectory.child(LioLocalAddressRelayClient.pendingDirectoryName)
        try directory.removeOwnedFile(named: LioLocalAddressRelayClient.pendingFileName)
        try directory.removeEmptyChild()
    }
}
