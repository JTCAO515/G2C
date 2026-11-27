import Foundation
import Observation
import SwiftUI

/// #1748 (W4-4): the in-app choice to use location, asked before the system permission. Behind
/// `G2CLocationConsentEnabled`, off unless the build says YES; it is turned on only after the server stops keeping
/// coordinates with the account (#1833). Without it the app behaves as before.
enum LioLocationConsentFeature {
    static let infoKey = "G2CLocationConsentEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-location-consent-preview")
        #else
        return false
        #endif
    }
}

/// The traveller's choice for one account, on this device only: one file in the account's message folder, removed
/// with the account's other files on account deletion. Nothing is uploaded.
@MainActor public struct LioLocationConsentStore {
    nonisolated public static let directoryName = "location-consent"
    nonisolated public static let fileName = "location-consent.json"

    nonisolated public static func storageDirectory(inMessageDirectory directory: URL) -> URL {
        directory.appendingPathComponent(directoryName, isDirectory: true)
    }

    let directory: URL
    private let isCurrent: @MainActor () -> Bool
    private var file: URL { directory.appendingPathComponent(Self.fileName) }

    public init(directory: URL, isCurrent: @escaping @MainActor () -> Bool) {
        self.directory = directory
        self.isCurrent = isCurrent
    }

    private struct Archive: Codable {
        let version: Int
        let allowedAt: Date
    }

    /// When the traveller allowed location, or nil. A damaged or newer file reads as not allowed.
    func load() throws -> Date? {
        guard isCurrent() else { throw CancellationError() }
        let data: Data
        do {
            data = try Data(contentsOf: file)
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return nil
        }
        guard let archive = try? JSONDecoder().decode(Archive.self, from: data), archive.version == 1 else { return nil }
        return archive.allowedAt
    }

    func allow(at date: Date) throws {
        guard isCurrent() else { throw CancellationError() }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var storedDirectory = directory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try storedDirectory.setResourceValues(attributes)
        let data = try JSONEncoder().encode(Archive(version: 1, allowedAt: date))
        #if os(iOS)
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file, options: .atomic)
        #endif
    }

    func clear() throws {
        guard isCurrent() else { throw CancellationError() }
        do {
            try FileManager.default.removeItem(at: file)
        } catch let error as CocoaError where error.code == .fileNoSuchFile {
            return
        }
    }
}

/// Why a location read did not happen (#1748).
enum LioLocationConsentFailure: Error, Equatable {
    /// The traveller has not allowed location in the app yet (or turned it off); ask before reading.
    case consentNeeded
    /// The choice changed, or the account did, while a read was under way; its result is dropped.
    case withdrawn
}

/// The current account's choice (#1748). Reads check it before asking the system and again when a result arrives,
/// so turning it off, signing out or switching accounts drops a result that comes back late.
@MainActor @Observable
final class LioLocationConsent {
    @ObservationIgnored private var store: LioLocationConsentStore?
    @ObservationIgnored private var isCurrent: @MainActor () -> Bool
    private var allowedAt: Date?
    /// Bumped by every change, so a read can tell that the choice changed while it waited.
    private(set) var revision = 0

    /// `store` nil keeps the choice in memory for this session only.
    init(store: LioLocationConsentStore?, isCurrent: @escaping @MainActor () -> Bool) {
        self.store = store
        self.isCurrent = isCurrent
        allowedAt = (try? store?.load()) ?? nil
    }

    /// Points the choice at the session the home screen has now. Coming back from the background builds a new session
    /// for the same account without rebuilding the home screen, so the check given at creation would stay false for
    /// good and the choice would read as "not allowed" until the app was restarted. Called with every render of the home
    /// screen; changes nothing the screen observes.
    func rebind(isCurrent newCheck: @escaping @MainActor () -> Bool) {
        isCurrent = newCheck
        if let directory = store?.directory { store = LioLocationConsentStore(directory: directory, isCurrent: newCheck) }
    }

    var allowed: Bool { allowedAt != nil && isCurrent() }

    /// Records the choice; false (and nothing changes) when the account is no longer current or the file can't be written.
    @discardableResult
    func allow(at date: Date = .now) -> Bool {
        guard isCurrent() else { return false }
        do { try store?.allow(at: date) } catch { return false }
        allowedAt = date
        revision += 1
        return true
    }

    /// Turns location off. Reads stop at once, even if the file can't be removed now.
    func withdraw() {
        allowedAt = nil
        revision += 1
        try? store?.clear()
    }

    /// Call before reading: throws unless the traveller allowed location for the current account. Returns a token
    /// for `admit`.
    func requireAllowed() throws -> Int {
        guard allowed else { throw LioLocationConsentFailure.consentNeeded }
        return revision
    }

    /// Call when a read returns: the value only if nothing changed since `requireAllowed` gave `token`.
    func admit<Value>(_ value: Value, token: Int) throws -> Value {
        guard allowed, revision == token else { throw LioLocationConsentFailure.withdrawn }
        return value
    }

    /// `read` behind the choice: it runs only when location is allowed, and its result is dropped if the choice or
    /// the account changed meanwhile.
    func gate<Value: Sendable>(_ read: @escaping @MainActor @Sendable () async throws -> Value)
        -> @MainActor @Sendable () async throws -> Value {
        { [self] in
            let token = try requireAllowed()
            let value = try await read()
            return try admit(value, token: token)
        }
    }
}

private struct LioLocationConsentKey: EnvironmentKey {
    static let defaultValue: LioLocationConsent? = nil
}

extension EnvironmentValues {
    /// The in-app location choice (#1748); nil when the build does not ask for it.
    var lioLocationConsent: LioLocationConsent? {
        get { self[LioLocationConsentKey.self] }
        set { self[LioLocationConsentKey.self] = newValue }
    }
}
