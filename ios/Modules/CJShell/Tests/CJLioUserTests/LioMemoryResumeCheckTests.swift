import CJMessageClient
import Foundation
import Testing
@testable import CJLioUser

/// #1450 (JT, build 54): after returning from the background the chat showed "Couldn’t show your saved choice."
/// The pending-choice check ran before the session came back, with the previous journal lease, and its failure
/// was shown to the traveller. It must wait for the session and never surface its own failure.
@MainActor
@Suite struct LioMemoryResumeCheckTests {
    @Test func waitsForTheSessionBeforeChecking() {
        var checked = false
        let result = LioMemoryResumeCheck.pendingChoice(sessionReady: false, check: { checked = true; return true },
                                                        failed: { _ in Issue.record("no failure expected") })
        #expect(result == nil && !checked)
    }

    @Test func aStaleLeaseIsRecordedButNotShown() {
        var failures: [Error] = []
        let result = LioMemoryResumeCheck.pendingChoice(sessionReady: true, check: { throw RecoveryError.inactive },
                                                        failed: { failures.append($0) })
        #expect(result == nil)
        #expect(failures.count == 1)
    }

    @Test func reportsAWaitingChoiceOnceTheSessionIsBack() {
        #expect(LioMemoryResumeCheck.pendingChoice(sessionReady: true, check: { true }, failed: { _ in }) == true)
        #expect(LioMemoryResumeCheck.pendingChoice(sessionReady: true, check: { false }, failed: { _ in }) == false)
    }
}
