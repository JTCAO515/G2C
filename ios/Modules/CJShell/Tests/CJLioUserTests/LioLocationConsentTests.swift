import Foundation
import Testing
@testable import CJLioUser

/// #1748 (W4-4): location is read only after the in-app choice, for the current account, and a result that comes back
/// after the choice or the account changed is dropped.
@MainActor
struct LioLocationConsentTests {
    private final class Session {
        var current = true
    }

    /// Counts reads, so a test can tell that nothing was read.
    private final class Reader {
        var reads = 0
        var resume: (() -> Void)?
    }

    private func store(_ root: URL, _ session: Session) -> LioLocationConsentStore {
        LioLocationConsentStore(directory: LioLocationConsentStore.storageDirectory(inMessageDirectory: root),
                                isCurrent: { session.current })
    }

    private func temporaryRoot() throws -> URL {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("location-consent-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        return root
    }

    @Test func flagIsOffUnlessTheBuildSaysYes() {
        #expect(LioLocationConsentFeature.infoKey == "G2CLocationConsentEnabled")
        #expect(!LioLocationConsentFeature.enabled(infoValue: nil))
        #expect(!LioLocationConsentFeature.enabled(infoValue: "NO"))
        #expect(!LioLocationConsentFeature.enabled(infoValue: ""))
        #expect(LioLocationConsentFeature.enabled(infoValue: "YES"))
        #expect(!LioLocationConsentFeature.enabledInBuild, "the test bundle sets no flag")
    }

    @Test func infoPlistReadsTheFlagFromABuildSettingThatNoConfigurationSets() throws {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(plist.contains("<key>G2CLocationConsentEnabled</key><string>$(G2C_LOCATION_CONSENT_ENABLED)</string>"))
        #expect(!project.contains("G2C_LOCATION_CONSENT_ENABLED"), "off unless a release turns it on")
    }

    @Test func nothingIsReadBeforeTheTravellerAllowsIt() async throws {
        let consent = LioLocationConsent(store: nil, isCurrent: { true })
        let reader = Reader()
        let read = consent.gate { reader.reads += 1; return 1 }
        await #expect(throws: LioLocationConsentFailure.consentNeeded) { try await read() }
        #expect(reader.reads == 0)
        // Declining records nothing: the next read still asks first.
        await #expect(throws: LioLocationConsentFailure.consentNeeded) { try await read() }
        #expect(reader.reads == 0)
        #expect(consent.allow())
        #expect(try await read() == 1)
        #expect(reader.reads == 1)
    }

    @Test func turningItOffStopsReadsAtOnce() async throws {
        let consent = LioLocationConsent(store: nil, isCurrent: { true })
        consent.allow()
        let reader = Reader()
        let read = consent.gate { reader.reads += 1; return "here" }
        #expect(try await read() == "here")
        consent.withdraw()
        #expect(!consent.allowed)
        await #expect(throws: LioLocationConsentFailure.consentNeeded) { try await read() }
        #expect(reader.reads == 1)
    }

    @Test func aResultThatArrivesAfterTurningItOffIsDropped() async throws {
        let consent = LioLocationConsent(store: nil, isCurrent: { true })
        consent.allow()
        let read = consent.gate { () async throws -> String in
            consent.withdraw() // the traveller turns location off while the read is under way
            return "late"
        }
        await #expect(throws: LioLocationConsentFailure.withdrawn) { try await read() }
    }

    @Test func aResultThatArrivesAfterAllowingAgainIsStillDropped() async throws {
        let consent = LioLocationConsent(store: nil, isCurrent: { true })
        consent.allow()
        let read = consent.gate { () async throws -> String in
            consent.withdraw()
            consent.allow() // off and on again: the read began under the earlier choice
            return "late"
        }
        await #expect(throws: LioLocationConsentFailure.withdrawn) { try await read() }
    }

    @Test func switchingAccountsStopsReadsAndDropsLateResults() async throws {
        let session = Session()
        let consent = LioLocationConsent(store: nil, isCurrent: { session.current })
        consent.allow()
        let late = consent.gate { () async throws -> Int in
            session.current = false // signed out or switched while the read was under way
            return 7
        }
        await #expect(throws: LioLocationConsentFailure.withdrawn) { try await late() }
        #expect(!consent.allowed)
        let reader = Reader()
        let next = consent.gate { reader.reads += 1; return 8 }
        await #expect(throws: LioLocationConsentFailure.consentNeeded) { try await next() }
        #expect(reader.reads == 0)
        #expect(!consent.allow(), "nothing is recorded for an account that is no longer current")
    }

    @Test func readFailuresPassThroughUnchanged() async {
        struct Denied: Error, Equatable {}
        let consent = LioLocationConsent(store: nil, isCurrent: { true })
        consent.allow()
        let read = consent.gate { () async throws -> Int in throw Denied() }
        await #expect(throws: Denied()) { try await read() }
    }

    @Test func theChoiceIsKeptPerAccountOnThisDevice() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let session = Session()
        let first = LioLocationConsent(store: store(root, session), isCurrent: { session.current })
        #expect(!first.allowed)
        let when = Date(timeIntervalSince1970: 1_800_000_000)
        #expect(first.allow(at: when))
        // A new session for the same account reads the same choice.
        let again = LioLocationConsent(store: store(root, session), isCurrent: { session.current })
        #expect(again.allowed)
        #expect(try store(root, session).load() == when)
        // Another account's folder has no choice.
        let other = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: other) }
        #expect(!LioLocationConsent(store: store(other, session), isCurrent: { true }).allowed)
        // Turning it off removes the file.
        again.withdraw()
        #expect(try store(root, session).load() == nil)
        #expect(!LioLocationConsent(store: store(root, session), isCurrent: { session.current }).allowed)
    }

    @Test func aDamagedOrNewerFileReadsAsNotAllowed() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let session = Session()
        let directory = LioLocationConsentStore.storageDirectory(inMessageDirectory: root)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent(LioLocationConsentStore.fileName)
        try Data("not json".utf8).write(to: file)
        #expect(!LioLocationConsent(store: store(root, session), isCurrent: { true }).allowed)
        try Data(#"{"version":2,"allowedAt":0}"#.utf8).write(to: file)
        #expect(!LioLocationConsent(store: store(root, session), isCurrent: { true }).allowed)
    }

    /// The app going to the background builds a new session for the same account without rebuilding the home screen:
    /// the choice must follow the screen's latest check, or it would read as "not allowed" until a restart.
    @Test func aChoiceFollowsTheHomeScreensLatestSessionAfterTheAppComesBack() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let first = Session(), later = Session()
        let consent = LioLocationConsent(store: store(root, first), isCurrent: { first.current })
        #expect(consent.allow())
        first.current = false // backgrounded: the first session ends
        #expect(!consent.allowed, "an ended session allows nothing")
        consent.rebind(isCurrent: { later.current }) // the home screen's next render
        #expect(consent.allowed, "same account, new session: the choice is back")
        // A change is recorded through the new session too.
        consent.withdraw()
        #expect(!consent.allowed)
        #expect(consent.allow())
        #expect(consent.allowed)
        #expect(LioLocationConsent(store: store(root, later), isCurrent: { later.current }).allowed, "kept on disk")
    }

    @Test func theStoreRefusesAnAccountThatIsNoLongerCurrent() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let session = Session()
        session.current = false
        #expect(throws: CancellationError.self) { try store(root, session).load() }
        #expect(throws: CancellationError.self) { try store(root, session).allow(at: .now) }
        #expect(throws: CancellationError.self) { try store(root, session).clear() }
        #expect(!FileManager.default.fileExists(atPath: LioLocationConsentStore.storageDirectory(inMessageDirectory: root).path))
    }

    @Test func folderNamesStayStableForAccountCleanup() {
        #expect(LioLocationConsentStore.directoryName == "location-consent")
        #expect(LioLocationConsentStore.fileName == "location-consent.json")
    }
}
