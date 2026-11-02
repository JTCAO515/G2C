import Foundation
import Darwin
import CJSession
import CJMessageKeys

public enum OfflineDeviceClock {
    /// A kernel boot-session UUID keeps a new boot from borrowing an old monotonic anchor.
    /// Missing authority fails closed, rather than substituting wall time or a random UUID.
    public static func read() -> OfflineClock? {
        var length = 0
        guard sysctlbyname("kern.bootsessionuuid", nil, &length, nil, 0) == 0, (1...128).contains(length) else { return nil }
        var bytes = [CChar](repeating: 0, count: length)
        guard sysctlbyname("kern.bootsessionuuid", &bytes, &length, nil, 0) == 0,
              let text = String(bytes: bytes.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, encoding: .utf8),
              let boot = UUID(uuidString: text) else { return nil }
        let wall = Date().timeIntervalSince1970
        guard wall.isFinite, wall > 0, wall < Double(Int64.max) else { return nil }
        return OfflineClock(trustedWallSeconds: Int64(wall), boot: boot,
                            uptime: ProcessInfo.processInfo.systemUptime)
    }
}

#if os(iOS)
extension OfflineTripController {
    /// Explicit host integration, with device-only protected Keychain metadata and
    /// the canonical dedicated key purpose. No default backend/account/credentials.
    public convenience init(environment: UUID, applicationIdentifier: String, directory: URL,
                            sdkMaterial: @escaping @MainActor () throws -> SessionMaterial?,
                            policy: OfflinePolicy?, clock: @escaping @MainActor () -> OfflineClock? = OfflineDeviceClock.read) throws {
        if let policy {
            guard policy.maximumAge > 0, policy.maximumAge <= OfflinePolicy.acceptedTrip.maximumAge else {
                throw OfflineFailure.unavailable
            }
        }
        let scope = try KeychainSessionScope(namespace: SessionNamespace(environment: environment, slot: "M3.OfflineTrip.Anchor"),
                                            applicationIdentifier: applicationIdentifier)
        let persistence = KeychainSessionStore(scope: scope, protection: .whenUnlockedThisDeviceOnly)
        self.init(environment: environment, root: directory, anchors: persistence, sdkMaterial: sdkMaterial,
            makeKeys: { namespace in
                try ScopedMessageKeyProvider(namespace: namespace, applicationIdentifier: applicationIdentifier,
                                             protection: .whenUnlockedThisDeviceOnly)
            }, clock: clock, policy: policy)
    }
}
#endif
