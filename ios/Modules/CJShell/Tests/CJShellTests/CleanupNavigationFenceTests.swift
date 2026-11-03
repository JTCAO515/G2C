import Foundation
import Observation
import Testing
@testable import CJShell

@MainActor struct CleanupNavigationFenceTests {
    private func shell() throws -> ShellState {
        ShellState(preferences: try #require(UserDefaults(suiteName: "cleanup-navigation-" + UUID().uuidString)))
    }
    @Test func cleanupRetiresPrivateStateWithoutPoppingItsOriginalSurface() throws {
        let value = try shell()
        value.memoryPath = [.account, .accountDeletion]
        value.draft = "private original editor"
        value.messageBindingBlocked = false
        let old = value.generation
        var navigationChanges = 0
        withObservationTracking { _ = value.memoryPath } onChange: {
            MainActor.assumeIsolated { navigationChanges += 1 }
        }
        let retired = value.retireBusinessForCleanup()
        #expect(retired != old && value.generation == retired)
        #expect(value.messageBindingBlocked && value.draft.isEmpty)
        #expect(value.memoryPath == [.account, .accountDeletion] && navigationChanges == 0)
        _ = value.retireBusinessForCleanup()
        #expect(value.memoryPath == [.account, .accountDeletion] && navigationChanges == 0)
        _ = value.invalidateIdentity()
        #expect(value.memoryPath.isEmpty) // Real identity changes never preserve the old cleanup screen.
    }
    @Test func cleanupDoesNotRetainAnArbitraryPrivateNavigationStack() throws {
        let value = try shell()
        value.memoryPath = [.manualMemory, .memoryItems]
        _ = value.retireBusinessForCleanup()
        #expect(value.memoryPath == [.accountDeletion])
    }
}
