import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

/// #1999 (M-1, App): the one-time question before the first memory suggestion, the choice kept per account on the
/// device, the withdrawal that hides suggestions at once, and the write to the server that follows (red line: privacy).
@MainActor
struct LioMemoryConsentTests {
    private func temporaryRoot() throws -> URL {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("memory-consent-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        return root
    }

    private func consent(_ root: URL) -> LioConsent {
        LioConsent(store: LioConsentStore(directory: LioConsentStore.storageDirectory(inMessageDirectory: root)))
    }

    private func agreed(_ root: URL, ai: Bool = true) -> LioConsent {
        let value = consent(root)
        #expect(value.agree(aiProcessing: ai))
        return value
    }

    // MARK: the flag

    @Test func flagIsOffUnlessTheBuildSaysYes() {
        #expect(LioMemoryConsentFeature.infoKey == "G2CMemoryConsentEnabled")
        #expect(!LioMemoryConsentFeature.enabled(infoValue: nil))
        #expect(!LioMemoryConsentFeature.enabled(infoValue: "NO"))
        #expect(!LioMemoryConsentFeature.enabled(infoValue: true))
        #expect(LioMemoryConsentFeature.enabled(infoValue: "YES"))
        #expect(!LioMemoryConsentFeature.enabledInBuild, "the test bundle sets no flag")
    }

    @Test func infoPlistReadsTheFlagFromABuildSettingThatNoConfigurationSets() throws {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(plist.contains("<key>G2CMemoryConsentEnabled</key><string>$(G2C_MEMORY_CONSENT_ENABLED)</string>"))
        #expect(!project.contains("G2C_MEMORY_CONSENT_ENABLED"), "off unless the release script passes it")
    }

    @Test func flagIsListedAndNotOnInTheRelease() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let manifestURL = root.appendingPathComponent("tooling/release/app_flags.json")
        let manifest = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any])
        let flags = try #require(manifest["flags"] as? [[String: String]])
        #expect(flags.contains(["setting": "G2C_MEMORY_CONSENT_ENABLED", "plist": "G2CMemoryConsentEnabled"]))
        let release = try #require(manifest["release"] as? [String: Any])
        #expect(!(try #require(release["on"] as? [String])).contains("G2C_MEMORY_CONSENT_ENABLED"),
                "turning it on for a build is JT's decision")
    }

    // MARK: what the chat does with suggestions

    @Test func aTravellerWhoHasNotBeenAskedIsAskedBeforeAnySuggestionShows() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.memoryChoice == .undecided)
        #expect(value.memoryCandidateGate == .ask)
        #expect(value.memoryUnsynced == nil, "asking writes nothing: only an answer does")
    }

    @Test func nothingIsAskedWhileAIProcessingIsOff() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root, ai: false)
        #expect(value.memoryCandidateGate == .hide, "suggestions need the AI model (docs/privacy §3.3)")
        #expect(value.setAIProcessing(true))
        #expect(value.memoryCandidateGate == .ask)
    }

    @Test func nothingIsAskedBeforeTheFirstConsentPageIsAnswered() {
        let value = LioConsent(store: nil)
        #expect(value.memoryCandidateGate == .hide)
        #expect(!value.setMemory(true), "no choice before the page")
        #expect(value.memoryChoice == .undecided)
    }

    @Test func turningItOnShowsSuggestionsAndTurningItOffHidesThemAtOnce() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(true))
        #expect(value.memoryChoice == .granted && value.memoryCandidateGate == .show)
        #expect(value.setMemory(false))
        #expect(value.memoryChoice == .withdrawn && value.memoryCandidateGate == .hide)
        // "Not now" at the first question is the same answer: hidden, and never asked again.
        let notNow = agreed(try temporaryRoot())
        #expect(notNow.setMemory(false))
        #expect(notNow.memoryCandidateGate == .hide)
    }

    @Test func withdrawingStaysWithdrawnWhenAIProcessingComesBackOn() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(true) && value.setMemory(false))
        #expect(value.setAIProcessing(false) && value.setAIProcessing(true))
        #expect(value.memoryChoice == .withdrawn && value.memoryCandidateGate == .hide, "AI processing does not undo it")
        #expect(value.setMemory(true) && value.setAIProcessing(false))
        #expect(value.memoryChoice == .granted, "and turning AI off does not erase a choice")
    }

    @Test func withTheFlagOffOrNoConsentKeptNothingIsAskedAndNothingWithheld() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value: LioConsent? = agreed(root)
        #expect(value.memoryCandidateGate(featureOn: false) == .show, "flag off: as before")
        #expect(value.memoryCandidateGate(featureOn: true) == .ask)
        let none: LioConsent? = nil
        #expect(none.memoryCandidateGate(featureOn: true) == .show, "a build that keeps no consent withholds nothing")
        #expect(none.memoryCandidateGate(featureOn: false) == .show)
    }

    // MARK: the choice is kept per account, on the device

    @Test func theChoiceIsKeptAcrossLaunchesAndIsPerAccount() throws {
        let rootA = try temporaryRoot(), rootB = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: rootA); try? FileManager.default.removeItem(at: rootB) }
        let first = agreed(rootA)
        #expect(first.setMemory(true))
        let again = consent(rootA)
        #expect(again.memoryChoice == .granted && again.memoryCandidateGate == .show)
        // Another account on the same device has not been asked.
        let other = agreed(rootB)
        #expect(other.memoryChoice == .undecided && other.memoryCandidateGate == .ask)
        #expect(other.setMemory(false))
        #expect(consent(rootA).memoryChoice == .granted, "and cannot change the first account's choice")
    }

    @Test func theChoiceLivesInTheConsentFileSoAccountCleanupErasesIt() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(true))
        let directory = LioConsentStore.storageDirectory(inMessageDirectory: root)
        let names = try FileManager.default.contentsOfDirectory(atPath: directory.path)
        #expect(names == [LioConsentStore.fileName], "no second store")
        // What cleanup does (LioConsentCleanup removes this one file): the choice is gone with it.
        try FileManager.default.removeItem(at: directory.appendingPathComponent(LioConsentStore.fileName))
        let after = consent(root)
        #expect(after.memoryChoice == .undecided && !after.storageAgreed)
    }

    @Test func anOlderFileWithoutTheMemoryFieldStillReadsAndMeansNotAskedYet() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let directory = LioConsentStore.storageDirectory(inMessageDirectory: root)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try Data(#"{"version":1,"storageAgreedAt":0,"aiProcessing":true,"aiChangedAt":0}"#.utf8)
            .write(to: directory.appendingPathComponent(LioConsentStore.fileName))
        let value = consent(root)
        #expect(value.storageAgreed && value.aiProcessing)
        #expect(value.memoryChoice == .undecided && value.memoryCandidateGate == .ask)
    }

    @Test func aChoiceThatCannotBeSavedNeverLooksMade() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        // Replace the folder with a file: the next write fails.
        let directory = LioConsentStore.storageDirectory(inMessageDirectory: root)
        try FileManager.default.removeItem(at: directory)
        try Data("x".utf8).write(to: directory)
        #expect(!value.setMemory(true))
        #expect(value.memoryChoice == .undecided && value.memoryUnsynced == nil)
    }

    @Test func aChoiceFromASessionThatIsNotCurrentIsRefusedAndNothingIsWritten() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        let refused = value.setMemory(true, isCurrent: { false })
        #expect(!refused)
        #expect(value.memoryChoice == .undecided && consent(root).memoryChoice == .undecided)
    }

    // MARK: every change is its own action, written with the same id until the server answers

    @Test func everyChangeIsANewUserActionAndChoosingTheSameAgainChangesNothing() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(true, requestID: "mc-one"))
        #expect(value.memoryUnsynced?.requestID == "mc-one" && value.memoryUnsynced?.state == .granted)
        #expect(value.memoryUnsynced?.textVersion == LioMemoryConsentCopy.textVersion)
        let revision = value.revision
        #expect(value.setMemory(true, requestID: "mc-ignored"))
        #expect(value.revision == revision && value.memoryUnsynced?.requestID == "mc-one", "nothing to write twice")
        #expect(value.setMemory(false, requestID: "mc-two"))
        #expect(value.memoryUnsynced?.requestID == "mc-two" && value.memoryUnsynced?.state == .withdrawn)
        #expect(value.setMemory(true, requestID: "mc-three"), "a new consent after a withdrawal gets a new id")
        #expect(value.memoryUnsynced?.requestID == "mc-three")
    }

    @Test func theServersAnswerMarksOnlyTheChoiceItBelongsTo() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(true, requestID: "mc-one"))
        #expect(value.setMemory(false, requestID: "mc-two"))
        value.markMemorySynced(requestID: "mc-one")
        #expect(value.memoryUnsynced?.requestID == "mc-two", "a late answer for the old choice does not settle the new one")
        value.markMemorySynced(requestID: "mc-two")
        #expect(value.memoryUnsynced == nil)
        #expect(consent(root).memoryUnsynced == nil && consent(root).memoryChoice == .withdrawn)
    }

    @Test func aChoiceWaitingForTheServerSurvivesARelaunch() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        #expect(agreed(root).setMemory(false, requestID: "mc-w"))
        let relaunched = consent(root)
        #expect(relaunched.memoryUnsynced?.requestID == "mc-w", "the withdrawal is still owed to the server")
        #expect(relaunched.memoryCandidateGate == .hide)
    }

    // MARK: the write to the server

    @MainActor private final class Server {
        var received: [LioMemoryConsentWire.Request] = []
        var results: [Result<LioMemoryConsentClient.Outcome, any Error>] = []
        func client() -> LioMemoryConsentClient {
            LioMemoryConsentClient(send: { [self] request in
                received.append(request)
                let next = results.isEmpty ? .success(.accepted(.init(state: request.state, recorded: true))) : results.removeFirst()
                return try next.get()
            }, read: { .accepted(.init(state: .withdrawn, recorded: false)) })
        }
    }
    private struct Offline: Error {}

    @Test func anAcceptedWriteSettlesTheChoice() async throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(true, requestID: "mc-a"))
        let server = Server()
        let result = await LioMemoryConsentSync.run(consent: value, client: server.client())
        #expect(result == .upToDate && value.memoryUnsynced == nil)
        #expect(server.received.map(\.requestID) == ["mc-a"] && server.received.map(\.state) == [.granted])
        // Nothing left: a second run writes nothing.
        _ = await LioMemoryConsentSync.run(consent: value, client: server.client())
        #expect(server.received.count == 1)
    }

    @Test func anUnansweredWriteIsRetriedWithTheSameIdAndTheChoiceStaysUnsyncedUntilItSucceeds() async throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(false, requestID: "mc-w"))
        let server = Server()
        server.results = [.failure(Offline()), .failure(Offline())]
        var pauses: [Int] = []
        let result = await LioMemoryConsentSync.run(consent: value, client: server.client(), pause: { pauses.append($0); return true })
        #expect(result == .upToDate && value.memoryUnsynced == nil)
        #expect(server.received.count == 3 && Set(server.received.map(\.requestID)) == ["mc-w"])
        #expect(pauses == [1, 2])
        #expect(value.memoryChoice == .withdrawn, "hidden on the device throughout")
    }

    @Test func itGivesUpAfterTheAttemptsAndKeepsTheChoiceForTheNextLaunch() async throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(false, requestID: "mc-w"))
        let server = Server()
        server.results = Array(repeating: .failure(Offline()), count: 10)
        let result = await LioMemoryConsentSync.run(consent: value, client: server.client(), attempts: 3, pause: { _ in true })
        #expect(result == .unavailable && server.received.count == 3)
        #expect(consent(root).memoryUnsynced?.requestID == "mc-w" && consent(root).memoryCandidateGate == .hide)
    }

    @Test(arguments: [400, 401, 403, 409]) func aRefusalRetryingCannotChangeStopsTheRetries(status: Int) async throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(true))
        let server = Server()
        server.results = [.success(.refused(status: status))]
        let result = await LioMemoryConsentSync.run(consent: value, client: server.client(), pause: { _ in true })
        #expect(result == .refused(status) && server.received.count == 1)
        #expect(value.memoryUnsynced != nil && value.memoryChoice == .granted)
    }

    @Test func aReceiptForTheWrongStateIsNotTakenAsTheAnswer() async throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(false))
        let server = Server()
        server.results = [.success(.accepted(.init(state: .granted, recorded: true)))]
        let result = await LioMemoryConsentSync.run(consent: value, client: server.client(), attempts: 1, pause: { _ in true })
        #expect(result == .unavailable && value.memoryUnsynced != nil, "a withdrawal is never settled by a granted receipt")
    }

    @Test func aChangeMadeWhileWritingIsWrittenNext() async throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(true, requestID: "mc-1"))
        var received: [String] = []
        let client = LioMemoryConsentClient(send: { request in
            received.append(request.requestID + ":" + request.state.rawValue)
            if request.requestID == "mc-1" { _ = value.setMemory(false, requestID: "mc-2") }
            return .accepted(.init(state: request.state, recorded: true))
        }, read: { .accepted(.init(state: .withdrawn, recorded: false)) })
        let result = await LioMemoryConsentSync.run(consent: value, client: client)
        #expect(result == .upToDate)
        #expect(received == ["mc-1:granted", "mc-2:withdrawn"], "one request at a time, the newest choice last")
        #expect(value.memoryChoice == .withdrawn && value.memoryUnsynced == nil)
    }

    @Test func withoutAClientOrWhenTheSessionEndedNothingIsSentAndNothingIsLost() async throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let value = agreed(root)
        #expect(value.setMemory(true))
        let noClient = await LioMemoryConsentSync.run(consent: value, client: nil)
        #expect(noClient == .unavailable)
        let server = Server()
        let ended = await LioMemoryConsentSync.run(consent: value, client: server.client(), isCurrent: { false })
        #expect(ended == .unavailable)
        #expect(server.received.isEmpty && value.memoryUnsynced != nil)
        let settled = agreed(try temporaryRoot())
        let nothingOwed = await LioMemoryConsentSync.run(consent: settled, client: nil)
        #expect(nothingOwed == .upToDate)
    }

    @Test func requestIdsAndTheTextVersionFitTheContract() {
        for _ in 0..<20 {
            #expect(LioMemoryConsentWire.Request(state: .granted, textVersion: LioMemoryConsentCopy.textVersion,
                                                 requestID: LioMemoryConsentSync.newRequestID()) != nil)
        }
        #expect(LioMemoryConsentSync.newRequestID() != LioMemoryConsentSync.newRequestID())
    }

    // MARK: the server's prompt marker

    @Test func theMarkerOnlyReachesATurnWhenRichIsOn() {
        let marked = LioTimelineWire.Message(id: "m1", question: "我喜欢慢节奏", answer: "好的。", state: .completed, activity: nil,
                                             sources: [], trip: nil, memoryTags: [],
                                             rich: .init(entities: [], memoryPrompt: true))
        #expect(LioTimelineTurn(marked, richEnabled: true).memoryPrompt)
        #expect(!LioTimelineTurn(marked, richEnabled: false).memoryPrompt, "rich off: never read")
        let plain = LioTimelineWire.Message(id: "m2", question: "Q", answer: "A", state: .completed, activity: nil,
                                            sources: [], trip: nil, memoryTags: [])
        #expect(!LioTimelineTurn(plain, richEnabled: true).memoryPrompt)
    }

    // MARK: wording

    @Test func theParagraphBehindTheDetailsButtonIsTheApprovedText() throws {
        let repo = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let approved = try String(contentsOf: repo.appendingPathComponent("docs/privacy/consent-screens.md"), encoding: .utf8)
        for language in [LioLanguage.english, .chinese] {
            #expect(approved.contains(LioMemoryConsentCopy.detailsText(language)), "not in consent-screens.md §3.3")
        }
        #expect(approved.contains(LioMemoryConsentCopy.title(.english)))
        #expect(approved.contains(LioMemoryConsentCopy.turnOn(.english)) && approved.contains(LioMemoryConsentCopy.notNow(.english)))
        #expect(approved.contains(LioMemoryConsentCopy.turnOn(.chinese)) && approved.contains(LioMemoryConsentCopy.notNow(.chinese)))
    }

    @Test func theWithdrawalLineDoesNotPromiseWhatTheServerDoesNot() {
        // ui-copy.json says that turning it off "stops Lio using saved memories"; LIO-memory-consent.1 leaves items already
        // remembered untouched, so the line the App shows must not say so.
        for language in [LioLanguage.english, .chinese] {
            let text = LioMemoryConsentCopy.settingOffDetail(language)
            #expect(!text.contains("stops using") && !text.contains("停止使用"))
        }
    }
}
