import CJMessageHTTP
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
        /// #1999: whether Lio may offer to remember preferences. Absent until the traveller has been asked once. It lives
        /// in this file, the account's one consent file, so it is kept and erased with the other choices.
        var memory: Memory? = nil

        struct Memory: Codable, Equatable {
            let state: LioMemoryConsentWire.State
            let changedAt: Date
            /// The `request_id` of the write that carries this choice to the server; a retry sends the same one.
            let requestID: String
            let textVersion: String
            /// The server has answered this choice. Until then the choice is only on this device.
            let synced: Bool
        }
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
        let new = LioConsentStore.Record(version: 1, storageAgreedAt: record.storageAgreedAt, aiProcessing: on, aiChangedAt: date,
                                         memory: record.memory)
        do { try store?.save(new) } catch { return false }
        self.record = new
        revision += 1
        return true
    }

    // MARK: memory (#1999)

    /// The traveller's choice about memory suggestions on this device. `undecided` until they have been asked once.
    var memoryChoice: LioMemoryChoice {
        switch record?.memory?.state {
        case .granted?: .granted
        case .withdrawn?: .withdrawn
        case nil: .undecided
        }
    }

    /// The choice the server has not answered yet, to be written with exactly these values; nil when it has.
    var memoryUnsynced: LioMemoryConsentWire.Request? {
        guard let memory = record?.memory, !memory.synced else { return nil }
        return LioMemoryConsentWire.Request(state: memory.state, textVersion: memory.textVersion, requestID: memory.requestID)
    }

    /// What the chat does with memory suggestions under an answer (see `LioMemoryCandidateGate`).
    var memoryCandidateGate: LioMemoryCandidateGate {
        guard storageAgreed else { return .hide }
        switch memoryChoice {
        case .granted: return .show
        case .withdrawn: return .hide
        // AI processing is what generates suggestions: while it is off nothing is asked (docs/privacy §3.3).
        case .undecided: return aiProcessing ? .ask : .hide
        }
    }

    /// Records the answer to the one question, or a later change under Me → Privacy, before it takes effect: a choice
    /// that could not be saved never looks made. Every change is a new user action with its own `request_id`; choosing
    /// what is already chosen changes nothing. The write to the server follows (`LioMemoryConsentSync`); until it
    /// succeeds the choice is on this device only, and a withdrawal already stops the suggestions here.
    @discardableResult
    func setMemory(_ granted: Bool, requestID: String = LioMemoryConsentSync.newRequestID(), at date: Date = .now,
                   isCurrent: @MainActor () -> Bool = { true }) -> Bool {
        guard isCurrent(), let record else { return false }
        let state: LioMemoryConsentWire.State = granted ? .granted : .withdrawn
        if record.memory?.state == state { return true }
        let memory = LioConsentStore.Record.Memory(state: state, changedAt: date, requestID: requestID,
                                                   textVersion: LioMemoryConsentCopy.textVersion, synced: false)
        return replace(memory)
    }

    /// The server answered the write with this `request_id`. A later choice has another id and stays unsynced.
    func markMemorySynced(requestID: String) {
        guard let memory = record?.memory, memory.requestID == requestID, !memory.synced else { return }
        _ = replace(LioConsentStore.Record.Memory(state: memory.state, changedAt: memory.changedAt, requestID: memory.requestID,
                                                  textVersion: memory.textVersion, synced: true))
    }

    private func replace(_ memory: LioConsentStore.Record.Memory) -> Bool {
        guard let record else { return false }
        let new = LioConsentStore.Record(version: 1, storageAgreedAt: record.storageAgreedAt, aiProcessing: record.aiProcessing,
                                         aiChangedAt: record.aiChangedAt, memory: memory)
        do { try store?.save(new) } catch { return false }
        self.record = new
        revision += 1
        return true
    }
}

enum LioMemoryChoice: Equatable { case undecided, granted, withdrawn }

/// What the chat does with the memory suggestions that come with an answer.
enum LioMemoryCandidateGate: Equatable {
    /// Shown as buttons under the answer.
    case show
    /// Not shown yet: the question "let Lio remember your preferences?" comes first.
    case ask
    /// Not shown, and nothing is asked.
    case hide
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

    /// What to do with memory suggestions (#1999). With the memory flag off, or in a build that keeps no consent, nothing
    /// is asked and nothing is withheld, as before.
    @MainActor func memoryCandidateGate(featureOn: Bool) -> LioMemoryCandidateGate {
        guard featureOn, let consent = self else { return .show }
        return consent.memoryCandidateGate
    }
}
