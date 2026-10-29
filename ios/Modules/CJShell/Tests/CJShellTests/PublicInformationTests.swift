import Foundation
import Testing
@testable import CJShell

@Suite @MainActor struct PublicInformationTests {
    @Test func betaPlansDoNotGrantAccessAcrossLanguageSwitches() throws {
        let state = ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString)))
        let original = state.presentation, generation = state.generation
        for language in [ShellLanguage.chinese, .english] {
            state.selectLanguage(language)
            #expect(ShellBetaInformation.plans(language).contains("Early Access"))
            #expect(!ShellBetaInformation.plans(language).contains("US$"))
            #expect(state.presentation == original && state.generation == generation && !state.canSend)
        }
    }
    @Test func contactsOpenOnlyAddressedMailWithoutPrefilledPrivateContent() throws {
        for contact in ShellContact.allCases {
            let url = try #require(contact.emailURL)
            let parts = try #require(URLComponents(url: url, resolvingAgainstBaseURL: false))
            #expect(parts.scheme == "mailto" && parts.path == contact.address)
            #expect(parts.host == nil && parts.user == nil && parts.password == nil)
            #expect(parts.query == nil && parts.fragment == nil)
        }
        #expect(ShellContact.support.address == "hello@go2china.space")
        #expect(ShellContact.allCases.count == 1)
    }
    @Test func informationalRoutesAndLanguageChangesDoNotGrantSendingOrEraseDraft() throws {
        let state = ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString)))
        state.selectedTab = .memory; state.draft = "SYNTHETIC unsent / 未发送"
        let generation = state.generation, presentation = state.presentation
        for route in [MemoryRoute.help, .privacy, .support] {
            state.memoryPath = [route]
            for language in [ShellLanguage.english, .chinese] {
                state.selectLanguage(language)
                _ = ShellContact.allCases.map { $0.title(language) }
                #expect(state.memoryPath == [route] && state.selectedTab == .memory)
                #expect(state.generation == generation && state.presentation == presentation)
                #expect(!state.canSend && state.draft == "SYNTHETIC unsent / 未发送")
            }
        }
        #expect(ShellTab.allCases.count == 4)
    }
}
