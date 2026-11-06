import Foundation
import Darwin
import CJSession
import CJMessageKeys

public enum OfflineDeviceClock {
    /// Prepare once, before the controller starts. Subsequent timer/read calls
    /// inspect the original kernel object and clock only, without file writes.
    @MainActor public static func makeReader(directory: URL) throws -> @MainActor () -> OfflineClock? {
        guard let group = Bundle.main.object(forInfoDictionaryKey: "G2COfflineClockGroup") as? String else {
            return read // Preserve existing consumers until they explicitly provision the new capability.
        }
        let root = directory.appendingPathComponent("BootContinuity", isDirectory: true)
        var attributes: [FileAttributeKey: Any] = [.posixPermissions: 0o700]
        #if os(iOS)
        attributes[.protectionKey] = FileProtectionType.complete
        #endif
        if !FileManager.default.fileExists(atPath: root.path) {
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: attributes)
        }
        let store = try AtomicSnapshotStore(existingPrivateDirectory: root, name: "boot-continuity.v1")
        let authority = try OfflineBootContinuity.prepare(store: store, group: group)
        return {
            do {
                guard try authority.isCurrent() else { return nil }
                var value = timespec()
                guard clock_gettime(CLOCK_MONOTONIC, &value) == 0 else { return nil }
                return sample(boot: authority.boot, uptime: Double(value.tv_sec) + Double(value.tv_nsec) / 1_000_000_000)
            } catch { return nil } // Missing kernel authority is unavailable, never a legacy-clock fallback.
        }
    }
    /// A kernel boot-session UUID keeps a new boot from borrowing an old monotonic anchor.
    /// Missing authority fails closed, rather than substituting wall time or a random UUID.
    public static func read() -> OfflineClock? {
        var length = 0
        guard sysctlbyname("kern.bootsessionuuid", nil, &length, nil, 0) == 0, (1...128).contains(length) else { return nil }
        var bytes = [CChar](repeating: 0, count: length)
        guard sysctlbyname("kern.bootsessionuuid", &bytes, &length, nil, 0) == 0,
              let text = String(bytes: bytes.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, encoding: .utf8),
              let boot = UUID(uuidString: text) else { return nil }
        return sample(boot: boot, uptime: ProcessInfo.processInfo.systemUptime)
    }
    private static func sample(boot: UUID, uptime: Double) -> OfflineClock? {
        let wall = Date().timeIntervalSince1970
        guard wall.isFinite, wall > 0, wall < Double(Int64.max) else { return nil }
        guard uptime.isFinite, uptime >= 0 else { return nil }
        return OfflineClock(trustedWallSeconds: Int64(wall), boot: boot,
                            uptime: uptime)
    }
}

#if os(iOS)
extension OfflineTripController {
    /// Explicit host integration, with device-only protected Keychain metadata and
    /// the canonical dedicated key purpose. No default backend/account/credentials.
    public convenience init(environment: UUID, applicationIdentifier: String, directory: URL,
                            sdkMaterial: @escaping @MainActor () throws -> SessionMaterial?,
                            policy: OfflinePolicy?, clock: (@MainActor () -> OfflineClock?)? = nil) throws {
        if let policy {
            guard policy.maximumAge > 0, policy.maximumAge <= OfflinePolicy.acceptedTrip.maximumAge else {
                throw OfflineFailure.unavailable
            }
        }
        let scope = try KeychainSessionScope(namespace: SessionNamespace(environment: environment, slot: "M3.OfflineTrip.Anchor"),
                                            applicationIdentifier: applicationIdentifier)
        let persistence = KeychainSessionStore(scope: scope, protection: .whenUnlockedThisDeviceOnly)
        let clock = try clock ?? OfflineDeviceClock.makeReader(directory: directory)
        self.init(environment: environment, root: directory, anchors: persistence, sdkMaterial: sdkMaterial,
            makeKeys: { namespace in
                try ScopedMessageKeyProvider(namespace: namespace, applicationIdentifier: applicationIdentifier,
                                             protection: .whenUnlockedThisDeviceOnly)
            }, clock: clock, policy: policy)
    }
}
#endif
