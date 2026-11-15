import CJMessageClient
@testable import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LioFailureDiagnosisTests {
    private func observed(_ kind: LioTimelineHTTP.RequestKind, _ status: Int?, offline: Bool = false) -> LioTimelineHTTP.Observation {
        LioTimelineHTTP.Observation(kind: kind, httpStatus: status, offline: offline)
    }

    @Test func eachCauseHasItsOwnCategory() {
        let unknown = MessageHTTPFailure.exchangeUnknown
        #expect(LioFailureDiagnosis.classify(URLError(.notConnectedToInternet), stage: .timeline,
                                             observation: observed(.timeline, nil)).category == .network)
        #expect(LioFailureDiagnosis.classify(URLError(.timedOut), stage: .timeline, observation: nil).category == .network)
        #expect(LioFailureDiagnosis.classify(unknown, stage: .firstSendLookup,
                                             observation: observed(.firstLookup, nil, offline: true)).category == .network)
        #expect(LioFailureDiagnosis.classify(unknown, stage: .firstSendLookup,
                                             observation: observed(.firstLookup, 401)).category == .signIn)
        #expect(LioFailureDiagnosis.classify(unknown, stage: .firstSendLookup,
                                             observation: observed(.firstLookup, 403)).category == .signIn)
        for status in [429, 500, 502, 503] {
            #expect(LioFailureDiagnosis.classify(unknown, stage: .timeline,
                                                 observation: observed(.timeline, status)).category == .service)
        }
        for damaged in [RecoveryError.invalidSnapshot, .receiptMismatch, .legacyStorageFormat, .keyMismatch, .unsafeDirectory] {
            #expect(LioFailureDiagnosis.classify(damaged, stage: .localRecord, observation: nil).category == .localRecord)
        }
        // Not proven damaged or offline: say so instead of guessing.
        for error: any Error in [unknown, MessageHTTPFailure.invalidResponse, RecoveryError.keyUnavailable,
                                 RecoveryError.persistenceUnknown, RecoveryError.queryOnly, URLError(.cancelled)] {
            #expect(LioFailureDiagnosis.classify(error, stage: .selectedChat, observation: nil).category == .unclear)
        }
        #expect(LioFailureDiagnosis.classify(unknown, stage: .firstSendLookup,
                                             observation: observed(.firstLookup, 200)).category == .unclear)
        #expect(LioFailureDiagnosis.classify(unknown, stage: .firstSendLookup,
                                             observation: observed(.firstLookup, 409)).category == .unclear)
    }

    @Test func onlyAServerRejectionAsksToSignInAgain() {
        for category in LioFailureDiagnosis.Category.allCases where category != .signIn {
            let diagnosis = LioFailureDiagnosis(category: category, stage: .selectedChat, request: nil, httpStatus: nil)
            #expect(!diagnosis.nextStep(.english).localizedCaseInsensitiveContains("sign in"))
            #expect(!diagnosis.nextStep(.chinese).contains("登录"))
        }
        let expired = LioFailureDiagnosis(category: .signIn, stage: .firstSendLookup, request: .firstLookup, httpStatus: 401)
        #expect(expired.nextStep(.english).contains("sign in again"))
        #expect(expired.nextStep(.chinese).contains("重新登录"))
        // A network message never blames sign-in, and the old single message is gone.
        let offline = LioFailureDiagnosis(category: .network, stage: .timeline, request: .timeline, httpStatus: nil)
        #expect(offline.message(.chinese) != "暂时无法打开对话，请联网后重试。")
        let messages = LioFailureDiagnosis.Category.allCases.map {
            LioFailureDiagnosis(category: $0, stage: .selectedChat, request: nil, httpStatus: nil).message(.chinese)
        }
        #expect(Set(messages).count == messages.count)
    }

    @Test func missingCredentialsOrAnInactiveLeaseAreSessionChecks() {
        #expect(LioFailureDiagnosis.classify(MessageHTTPFailure.credentialsUnavailable, stage: .firstSendLookup,
                                             observation: nil).stage == .sessionCheck)
        #expect(LioFailureDiagnosis.classify(RecoveryError.inactive, stage: .localRecord, observation: nil)
                == LioFailureDiagnosis(category: .unclear, stage: .sessionCheck, request: nil, httpStatus: nil))
        #expect(LioFailureDiagnosis.sessionCheck(httpStatus: 401, error: nil).category == .signIn)
        #expect(LioFailureDiagnosis.sessionCheck(httpStatus: 503, error: nil).category == .service)
        #expect(LioFailureDiagnosis.sessionCheck(httpStatus: nil, error: URLError(.networkConnectionLost)).category == .network)
        #expect(LioFailureDiagnosis.sessionCheck(httpStatus: 404, error: nil)
                == LioFailureDiagnosis(category: .unclear, stage: .sessionCheck, request: nil, httpStatus: 404))
    }

    private func log(_ suite: String = UUID().uuidString, build: String = "45") -> (LioDiagnosticLog, UserDefaults) {
        let defaults = UserDefaults(suiteName: "synthetic-notes-" + suite)!
        return (LioDiagnosticLog(defaults: defaults, build: build), defaults)
    }

    @Test func notesAreBoundedNewestFirstAndSurviveRelaunch() {
        let suite = UUID().uuidString
        let (notes, _) = log(suite)
        let start = Date(timeIntervalSince1970: 1_800_000_000)
        for index in 0..<(LioDiagnosticLog.limit + 5) {
            notes.record(.init(category: .service, stage: .timeline, request: .timeline, httpStatus: 500 + index % 3),
                         at: start.addingTimeInterval(Double(index) * 120))
        }
        #expect(notes.entries.count == LioDiagnosticLog.limit)
        #expect(notes.entries.first?.time == start.addingTimeInterval(Double(LioDiagnosticLog.limit + 4) * 120))
        let (relaunched, _) = log(suite)
        #expect(relaunched.entries == notes.entries)
    }

    @Test func repeatedPollingFailureIsKeptOncePerWindow() {
        let (notes, _) = log()
        let start = Date(timeIntervalSince1970: 1_800_000_000)
        let failure = LioFailureDiagnosis(category: .network, stage: .timeline, request: .timeline, httpStatus: nil)
        notes.record(failure, at: start)
        notes.record(failure, at: start.addingTimeInterval(5))
        #expect(notes.entries.count == 1)
        notes.record(.init(category: .service, stage: .timeline, request: .timeline, httpStatus: 503), at: start.addingTimeInterval(6))
        notes.record(failure, at: start.addingTimeInterval(7))
        #expect(notes.entries.count == 3)
        notes.record(failure, at: start.addingTimeInterval(7 + LioDiagnosticLog.repeatWindow))
        #expect(notes.entries.count == 4)
    }

    @Test func unreadableSavedNotesStartEmptyWithoutFailing() {
        let suite = UUID().uuidString
        let (_, defaults) = log(suite)
        defaults.set(Data("not notes".utf8), forKey: "g2c.lio.problem-notes.v1")
        let (notes, _) = log(suite)
        #expect(notes.entries.isEmpty)
        #expect(notes.text(.english) == "No problems noted.")
    }

    @Test func copiedTextHasOnlyCategoriesStagesStatusTimeAndBuild() throws {
        let (notes, defaults) = log(build: "45")
        notes.record(.init(category: .signIn, stage: .firstSendLookup, request: .firstLookup, httpStatus: 401))
        notes.record(.init(category: .localRecord, stage: .localRecord, request: nil, httpStatus: nil))
        let text = notes.text(.chinese)
        #expect(text.contains("构建 45 · localRecord · localRecord · - · HTTP - · ref -"))
        #expect(text.contains("signIn · firstSendLookup · first-send-lookup · HTTP 401 · ref -"))
        // The stored form has exactly these fields: no token, invitation, identifier or message text.
        let stored = try #require(defaults.data(forKey: "g2c.lio.problem-notes.v1"))
        let entries = try #require(JSONSerialization.jsonObject(with: stored) as? [[String: Any]])
        for entry in entries {
            #expect(Set(entry.keys).isSubset(of: ["category", "stage", "request", "httpStatus", "reference", "time", "build"]))
        }
    }
}
