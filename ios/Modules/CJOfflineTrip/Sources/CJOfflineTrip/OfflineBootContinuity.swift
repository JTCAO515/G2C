import Foundation
import CryptoKit
import Darwin

/// Kernel-object boundary, injectable only inside this module's tests.
protocol OfflineBootSemaphore {
    func exists(_ name: String) throws -> Bool
    func createExclusive(_ name: String) throws
    func removeCreated(_ name: String) throws
}

struct POSIXOfflineBootSemaphore: OfflineBootSemaphore {
    func exists(_ name: String) throws -> Bool {
        let value = sem_open(name, 0)
        guard value != SEM_FAILED else {
            if errno == ENOENT { return false }
            throw OfflineFailure.unavailable
        }
        guard sem_close(value) == 0 else { throw OfflineFailure.unavailable }
        return true
    }
    func createExclusive(_ name: String) throws {
        let value = sem_open(name, O_CREAT | O_EXCL, mode_t(0o600), UInt32(0))
        guard value != SEM_FAILED else { throw OfflineFailure.unavailable }
        guard sem_close(value) == 0 else { throw OfflineFailure.unavailable }
    }
    func removeCreated(_ name: String) throws {
        guard sem_unlink(name) == 0 else { throw OfflineFailure.unavailable }
    }
}

/// The App-private marker is not a clock or an authorization grant. It only
/// names the original kernel object. Never recreate a missing old object's name.
/// Apple DTS: https://developer.apple.com/forums/thread/110044?answerId=754364022
@MainActor struct OfflineBootContinuity {
    private struct Marker: Codable { let version: Int; let boot: UUID }
    struct Authority {
        let boot: UUID
        let name: String
        let kernel: any OfflineBootSemaphore
        func isCurrent() throws -> Bool { try kernel.exists(name) }
    }
    static func prepare(store: AtomicSnapshotStore, group: String,
                        kernel: any OfflineBootSemaphore = POSIXOfflineBootSemaphore()) throws -> Authority {
        // Darwin's 31-byte name buffer includes its NUL terminator. A 31-byte
        // string fails sem_open with ENAMETOOLONG; the maximum payload is 30.
        guard group.hasPrefix("group."), group.utf8.count + 1 + 12 <= 30,
              group.utf8.allSatisfy({ (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 46 }) else {
            throw OfflineFailure.unavailable
        }
        func authority(_ marker: Marker) -> Authority {
            let suffix = Data(SHA256.hash(data: Data(marker.boot.uuidString.utf8)))
                .base64EncodedString().replacingOccurrences(of: "+", with: "-")
                .replacingOccurrences(of: "/", with: "_").prefix(12)
            return Authority(boot: marker.boot, name: group + "/" + suffix, kernel: kernel)
        }
        if let bytes = try store.read() {
            guard bytes.count <= 128 else { throw OfflineFailure.corrupt }
            var strict = StrictSnapshotJSON(bytes: Array(bytes)); try strict.check()
            let fields = try JSONSerialization.jsonObject(with: bytes) as? [String: Any]
            guard fields.map({ Set($0.keys) }) == ["version", "boot"] else { throw OfflineFailure.corrupt }
            let marker = try JSONDecoder().decode(Marker.self, from: bytes)
            guard marker.version == 1 else { throw OfflineFailure.corrupt }
            let original = authority(marker)
            if try original.isCurrent() { return original }
        }
        let marker = Marker(version: 1, boot: UUID()), fresh = authority(marker)
        try kernel.createExclusive(fresh.name)
        do { try store.write(SnapshotCodec.encoder().encode(marker)) }
        catch {
            // Only this new object is ours to remove. No reader/anchor has been
            // given its domain; even an uncertain file commit cannot borrow it.
            try kernel.removeCreated(fresh.name)
            throw error
        }
        return fresh
    }
}
