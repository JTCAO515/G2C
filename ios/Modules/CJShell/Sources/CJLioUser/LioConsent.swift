import Foundation
import Observation
import SwiftUI

/// #1747 (W4-3): the first-launch consent page and the AI processing choice, behind `G2CConsentEnabled`, off unless
/// the build says YES. Without it the app behaves as before: nothing is asked and nothing is withheld. The wording and
/// the rules are `docs/privacy/consent-screens.md`.
enum LioConsentFeature {
    static let infoKey = "G2CConsentEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-consent-preview")
        #else
        return false
        #endif
    }
}

/// The traveller's choices for one account, on this device only: one file in the account's message folder, removed
/// with the account's other files on account deletion. Nothing is uploaded (a server record is a separate ticket).
@MainActor public struct LioConsentStore {
    nonisolated public static let directoryName = "consent"
    nonisolated public static let fileName = "consent.json"

    nonisolated public static func storageDirectory(inMessageDirectory directory: URL) -> URL {
        directory.appendingPathComponent(directoryName, isDirectory: true)
    }

    let directory: URL
    private var file: URL { directory.appendingPathComponent(Self.fileName) }

    /// The folder belongs to one account, so the store needs no notion of the current session: a change is checked
    /// against the session that asks for it (`LioConsent`), not against whoever built the home screen.
    public init(directory: URL) {
        self.directory = directory
    }

    struct Record: Codable, Equatable {
        let version: Int
        /// When the traveller agreed to keep the account's data on the servers in Hong Kong.
        let storageAgreedAt: Date
        /// Whether content may be sent to Alibaba Cloud Model Studio, and when that last changed.
        let aiProcessing: Bool
        let aiChangedAt: Date
    }

    /// The saved choices, or nil. A damaged or newer file reads as no choice: the page is shown again.
    func load() throws -> Record? {
        let data: Data
        do {
            data = try Data(contentsOf: file)
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return nil
        }
        guard let record = try? JSONDecoder().decode(Record.self, from: data), record.version == 1 else { return nil }
        return record
    }

    func save(_ record: Record) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var storedDirectory = directory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try storedDirectory.setResourceValues(attributes)
        let data = try JSONEncoder().encode(record)
        #if os(iOS)
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file, options: .atomic)
        #endif
    }

    func clear() throws {
        do {
            try FileManager.default.removeItem(at: file)
        } catch let error as CocoaError where error.code == .fileNoSuchFile {
            return
        }
    }
}

/// The account's consent, read from its own folder once when the home screen is made. Until the traveller has agreed
/// to the data storage nothing is allowed; AI processing is a separate choice that can be changed at any time.
/// What is allowed does not depend on whether the app is paused or offline (the folder is this account's, and signing
/// out or switching accounts ends the home screen that holds this). A change is recorded before it takes effect, so a
/// choice that could not be saved never looks made, and it is only made for a session that is still current: that
/// check is passed in by the caller at the moment of the change, from the home screen's latest state.
@MainActor @Observable
final class LioConsent {
    @ObservationIgnored private let store: LioConsentStore?
    private var record: LioConsentStore.Record?
    private(set) var revision = 0

    /// `store` nil keeps the choices in memory for this session only (previews).
    init(store: LioConsentStore?) {
        self.store = store
        record = (try? store?.load()) ?? nil
    }

    /// The traveller has agreed to the data storage, so the app may be used.
    var storageAgreed: Bool { record != nil }
    /// Content may be sent to Alibaba Cloud Model Studio. False until the first page was answered.
    var aiProcessing: Bool { record?.aiProcessing == true }

    /// The first page: agree to the storage, and choose AI processing. False (nothing changes) when the session is no
    /// longer current or it can't be saved.
    @discardableResult
    func agree(aiProcessing: Bool, at date: Date = .now, isCurrent: @MainActor () -> Bool = { true }) -> Bool {
        guard isCurrent() else { return false }
        let new = LioConsentStore.Record(version: 1, storageAgreedAt: date, aiProcessing: aiProcessing, aiChangedAt: date)
        do { try store?.save(new) } catch { return false }
        record = new
        revision += 1
        return true
    }

    /// Turns AI processing on or off (Me → Privacy). False when the first page has not been answered or it can't be saved.
    @discardableResult
    func setAIProcessing(_ on: Bool, at date: Date = .now, isCurrent: @MainActor () -> Bool = { true }) -> Bool {
        guard isCurrent(), let record else { return false }
        let new = LioConsentStore.Record(version: 1, storageAgreedAt: record.storageAgreedAt, aiProcessing: on, aiChangedAt: date)
        do { try store?.save(new) } catch { return false }
        self.record = new
        revision += 1
        return true
    }
}

private struct LioConsentKey: EnvironmentKey {
    static let defaultValue: LioConsent? = nil
}

private struct LioConsentSessionKey: EnvironmentKey {
    static let defaultValue: @MainActor () -> Bool = { true }
}

extension EnvironmentValues {
    /// The account's consent (#1747); nil when the build does not ask for it, which means nothing is withheld.
    var lioConsent: LioConsent? {
        get { self[LioConsentKey.self] }
        set { self[LioConsentKey.self] = newValue }
    }

    /// Whether the signed-in session is still the current one, from the home screen's latest state (#1747).
    var lioConsentSessionIsCurrent: @MainActor () -> Bool {
        get { self[LioConsentSessionKey.self] }
        set { self[LioConsentSessionKey.self] = newValue }
    }
}

extension Optional where Wrapped == LioConsent {
    /// Whether content may go to the AI model: always when the build does not ask for consent.
    @MainActor var allowsAIProcessing: Bool { self?.aiProcessing ?? true }
}
