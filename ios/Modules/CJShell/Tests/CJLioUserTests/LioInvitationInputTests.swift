import Foundation
import Testing
@testable import CJLioUser

struct LioInvitationInputTests {
    @Test(arguments: ["G2C@01", "G2C@99", "CJ_Tester@01", "CJ_Tester@99",
                      "D1-aaaaaaaaaaaa.bbbbbbbbbbbbbbbbbbbbbb"])
    func supportedServerFormatsRemainLiteral(_ value: String) {
        #expect(LioInvitationInput.accepts(value))
    }

    @Test(arguments: ["", "G2C@00", "G2C@1", "G2C@123", "g2c@12", "CJtester@12", "CJ_TESTER@12",
                      "CJ_Tester@00", " G2C@12", "G2C@12 ", "G2C@12\n", "G2C@１２", "G2C＠12",
                      "CJ_Tester@\t12", "D1-aaaaaaaaaaaa.bbbbbbbbbbbbbbbbbbbbbb "])
    func unsupportedInputIsRejectedWithoutNormalizing(_ value: String) {
        #expect(!LioInvitationInput.accepts(value))
    }

    @Test func bothLanguagesExplainTheCaseSensitiveShortCodeFormatWithoutEchoingInput() {
        for language in [LioLanguage.english, .chinese] {
            let notice = LioInvitationInput.formatMessage(language)
            #expect(notice.contains("G2C@") && notice.contains("CJ_Tester@"))
            #expect(notice.contains("01–99"))
            #expect(!notice.contains("g2c@12") && !notice.contains("CJtester@12"))
        }
    }
}
