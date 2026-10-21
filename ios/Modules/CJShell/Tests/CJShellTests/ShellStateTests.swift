import Foundation
import Testing
@testable import CJShell

@Suite @MainActor struct ShellStateTests {
    private func preferences() throws -> UserDefaults {
        try #require(UserDefaults(suiteName: "cj.shell.tests.\(UUID().uuidString)"))
    }

    @Test func languagePreservesNavigationDraftAndReferences() throws {
        let defaults = try preferences()
        defer { defaults.removeObject(forKey: ShellState.languageKey) }
        let state = ShellState(preferences: defaults)
        state.selectedTab = .memory
        state.memoryPath = [.group(.facts), .language]
        state.draft = "去北京 / Beijing 🧳"
        state.context = ShellContext(conversationReference: "fixture-conversation", tripReference: "fixture-trip")
        let context = state.context
        for language in [ShellLanguage.chinese, .english, .chinese] {
            state.selectLanguage(language)
            #expect(state.selectedTab == .memory)
            #expect(state.memoryPath == [.group(.facts), .language])
            #expect(state.draft == "去北京 / Beijing 🧳")
            #expect(state.context == context)
        }
        #expect(ShellState(preferences: defaults).language == .chinese)
        #expect(defaults.dictionaryRepresentation()["draft"] == nil)
    }

    @Test func tabSwitchPreservesDraftAndMemoryPath() throws {
        let state = ShellState(preferences: try preferences())
        state.memoryPath = [.privacy]
        state.draft = "unsent"
        for tab in ShellTab.allCases { state.selectedTab = tab }
        #expect(state.draft == "unsent")
        #expect(state.memoryPath == [.privacy])
        #expect(ShellTab.allCases.map(\.rawValue) == ["assistant", "trips", "plugins", "memory"])
        #expect(ShellTab.allCases.map { $0.title(.english) } == ["Assistant", "Trips", "Plugins", "Memory"])
        #expect(ShellTab.allCases.map { $0.title(.chinese) } == ["助手", "行程", "插件", "记忆"])
    }

    @Test func unavailableSendNeverClaimsSuccess() throws {
        let state = ShellState(preferences: try preferences())
        for draft in ["", " \n ", "Hello", "你好"] {
            state.draft = draft
            #expect(!state.canSend)
            #expect(state.draft == draft)
        }
        #expect(state.hasDraft)
        #expect(state.assistantState == .notConnected)
        #expect(state.context == ShellContext())
    }

    @Test func invalidPreferenceIsVisibleAndNotSilentlyRewritten() throws {
        let defaults = try preferences()
        defer { defaults.removeObject(forKey: ShellState.languageKey) }
        defaults.set("unsupported", forKey: ShellState.languageKey)
        let state = ShellState(preferences: defaults)
        #expect(state.invalidStoredLanguage)
        #expect(state.language == .english)
        #expect(defaults.string(forKey: ShellState.languageKey) == "unsupported")
        state.selectLanguage(.chinese)
        #expect(!state.invalidStoredLanguage)
    }

    @Test func unknownWireValuesAreRejected() {
        for payload in ["\"signedIn\"", "\"saved\"", "\"success\""] {
            #expect(throws: (any Error).self) {
                try JSONDecoder().decode(ShellPageState.self, from: Data(payload.utf8))
            }
        }
        #expect(ShellTab(rawValue: "account") == nil)
        #expect(ShellLanguage(rawValue: "fr") == nil)
    }
}
