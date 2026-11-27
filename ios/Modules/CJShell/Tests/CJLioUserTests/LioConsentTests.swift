import Foundation
import Testing
@testable import CJLioUser

/// #1747 (W4-3): nothing is allowed before the first page is answered; AI processing is a separate choice that can be
/// changed any time; choices stay per account on this device; and the wording is the approved text.
@MainActor
struct LioConsentTests {
    private final class Session { var current = true }

    private func store(_ root: URL, _ session: Session) -> LioConsentStore {
        LioConsentStore(directory: LioConsentStore.storageDirectory(inMessageDirectory: root), isCurrent: { session.current })
    }

    private func temporaryRoot() throws -> URL {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("consent-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        return root
    }

    @Test func flagIsOffUnlessTheBuildSaysYesAndIsRegistered() throws {
        #expect(LioConsentFeature.infoKey == "G2CConsentEnabled")
        #expect(!LioConsentFeature.enabled(infoValue: nil))
        #expect(!LioConsentFeature.enabled(infoValue: "NO"))
        #expect(!LioConsentFeature.enabled(infoValue: true))
        #expect(LioConsentFeature.enabled(infoValue: "YES"))
        #expect(!LioConsentFeature.enabledInBuild, "the test bundle sets no flag")
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(plist.contains("<key>G2CConsentEnabled</key><string>$(G2C_CONSENT_ENABLED)</string>"))
        #expect(!project.contains("G2C_CONSENT_ENABLED"), "off unless the release script passes it")
    }

    @Test func nothingIsAllowedUntilTheFirstPageIsAnswered() throws {
        let consent = LioConsent(store: nil, isCurrent: { true })
        #expect(!consent.storageAgreed && !consent.aiProcessing)
        #expect(!consent.setAIProcessing(true), "no switch before the page")
        #expect(!consent.aiProcessing)
        let none: LioConsent? = nil
        #expect(none.allowsAIProcessing, "a build that does not ask withholds nothing")
        #expect(!Optional(consent).allowsAIProcessing)
    }

    @Test(arguments: [true, false]) func agreeingRecordsTheChoiceAndAIProcessingStaysSeparate(ai: Bool) throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let session = Session()
        let consent = LioConsent(store: store(root, session), isCurrent: { session.current })
        #expect(consent.agree(aiProcessing: ai))
        #expect(consent.storageAgreed && consent.aiProcessing == ai)
        // Kept on this device: a new instance (a new launch) reads the same.
        let again = LioConsent(store: store(root, session), isCurrent: { session.current })
        #expect(again.storageAgreed && again.aiProcessing == ai)
    }

    @Test func aiProcessingCanBeTurnedOffAndOnAgainAndTheStorageAgreementStays() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let session = Session()
        let consent = LioConsent(store: store(root, session), isCurrent: { session.current })
        #expect(consent.agree(aiProcessing: true))
        let revision = consent.revision
        #expect(consent.setAIProcessing(false))
        #expect(!consent.aiProcessing && consent.storageAgreed && consent.revision > revision)
        #expect(!LioConsent(store: store(root, session), isCurrent: { session.current }).aiProcessing, "kept")
        #expect(consent.setAIProcessing(true))
        #expect(consent.aiProcessing)
    }

    @Test func aChoiceThatCannotBeSavedNeverLooksMade() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        // A file where the folder should be: the write fails.
        try Data("x".utf8).write(to: LioConsentStore.storageDirectory(inMessageDirectory: root))
        let session = Session()
        let consent = LioConsent(store: store(root, session), isCurrent: { session.current })
        #expect(!consent.agree(aiProcessing: true))
        #expect(!consent.storageAgreed && !consent.aiProcessing)
    }

    @Test func theChoicesAreKeptPerAccountOnThisDevice() throws {
        let rootA = try temporaryRoot(), rootB = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: rootA); try? FileManager.default.removeItem(at: rootB) }
        let session = Session()
        #expect(LioConsent(store: store(rootA, session), isCurrent: { session.current }).agree(aiProcessing: true))
        let other = LioConsent(store: store(rootB, session), isCurrent: { session.current })
        #expect(!other.storageAgreed, "another account has not agreed")
    }

    @Test func anAccountThatIsNoLongerCurrentAllowsNothingAndChangesNothing() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let session = Session()
        let consent = LioConsent(store: store(root, session), isCurrent: { session.current })
        #expect(consent.agree(aiProcessing: true))
        session.current = false
        #expect(!consent.storageAgreed && !consent.aiProcessing)
        #expect(!consent.agree(aiProcessing: false))
        #expect(!consent.setAIProcessing(false))
        #expect(throws: CancellationError.self) { try store(root, session).load() }
        #expect(throws: CancellationError.self) { try store(root, session).clear() }
    }

    @Test func aDamagedOrNewerFileReadsAsNoChoiceSoThePageComesBack() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let session = Session()
        let directory = LioConsentStore.storageDirectory(inMessageDirectory: root)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent(LioConsentStore.fileName)
        try Data("not json".utf8).write(to: file)
        #expect(!LioConsent(store: store(root, session), isCurrent: { true }).storageAgreed)
        try Data(#"{"version":2,"storageAgreedAt":0,"aiProcessing":true,"aiChangedAt":0}"#.utf8).write(to: file)
        #expect(!LioConsent(store: store(root, session), isCurrent: { true }).storageAgreed)
    }

    @Test func folderNamesStayStableForAccountCleanup() {
        #expect(LioConsentStore.directoryName == "consent")
        #expect(LioConsentStore.fileName == "consent.json")
    }

    // MARK: wording

    /// Every sentence on the pages is in the approved file, byte for byte (#1961).
    @Test func everyStringOnThePagesIsInTheApprovedText() throws {
        let repo = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let approved = try String(contentsOf: repo.appendingPathComponent("docs/privacy/consent-screens.md"), encoding: .utf8)
        for language in [LioLanguage.english, .chinese] {
            var strings = LioConsentCopy.items(language).map(\.body)
            strings += [LioConsentCopy.title(language), LioConsentCopy.agreeWithAI(language), LioConsentCopy.agreeWithoutAI(language),
                        LioConsentCopy.decline(language), LioConsentCopy.declined(language), LioConsentCopy.readPolicy(language),
                        LioConsentCopy.leave(language), LioConsentCopy.aiTitle(language), LioConsentCopy.aiOnDetail(language),
                        LioConsentCopy.aiOffDetail(language), LioConsentCopy.turnOffConfirm(language), LioConsentCopy.turnOff(language),
                        LioConsentCopy.cancel(language), LioConsentCopy.turnOnConfirm(language), LioConsentCopy.turnOn(language),
                        LioConsentCopy.aiOff(language)]
            for string in strings {
                // The approved file writes "Cancel" and "Turn on"-style buttons inside quotes; a bare word is found as such.
                #expect(approved.contains(string), "not in consent-screens.md: \(string)")
            }
        }
    }

    @Test func onlyThePageHeadingsAndTwoSmallControlsAreNotQuotedFromTheApprovedFile() {
        // The six item headings are the approved file's section headings (Chinese) with an English rendering written here;
        // "Privacy", "Back" and the save-failure alert are plain controls with no sentence in the file.
        #expect(LioConsentCopy.items(.chinese).map(\.heading) == [
            "谁在运营", "存在哪里（需要你同意才能使用账号相关功能）", "AI 处理（你来选，不开启也能使用 App）",
            "我们不做什么", "另行询问", "你的选择"])
        #expect(LioConsentCopy.items(.english).count == 6)
    }
}
