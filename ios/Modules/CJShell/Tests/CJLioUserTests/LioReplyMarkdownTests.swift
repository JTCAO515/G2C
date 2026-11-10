import Foundation
import SwiftUI
import Testing
@testable import CJLioUser

struct LioReplyMarkdownTests {
    @Test func rendersHeadingsListsBoldAndLinks() throws {
        let answer = try #require(LioReplyMarkdown.render("""
            ## 明天的天气
            A **sunny** day. [Forecast](https://weather.com.cn/)

            3. Bring water
            4. Wear a hat
               - A light hat is fine
            """))
        #expect(String(answer.characters) == "明天的天气\n\nA sunny day. Forecast\n3. Bring water\n4. Wear a hat\n  • A light hat is fine")
        let heading = try #require(answer.runs.first)
        #expect(heading.font != nil)
        let strong = try #require(answer.runs.first { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true })
        #expect(String(answer[strong.range].characters) == "sunny")
        let link = try #require(answer.runs.first { $0.link != nil })
        #expect(String(answer[link.range].characters) == "Forecast")
        #expect(link.link == URL(string: "https://weather.com.cn/"))
    }

    @Test func keepsPlainStreamingPrefixAndFiltersUnsafeContent() throws {
        let prefix = try #require(LioReplyMarkdown.render("北京明天"))
        #expect(String(prefix.characters) == "北京明天")
        let unsafeLinks = try #require(LioReplyMarkdown.render(
            "[Open](javascript:alert) and [More](https://user@example.com/)"))
        #expect(String(unsafeLinks.characters) == "Open and More")
        #expect(unsafeLinks.runs.allSatisfy { $0.link == nil })
        #expect(LioReplyMarkdown.render("This is **UN**KNOWN") == nil)
        #expect(LioReplyMarkdown.render("[Open](https://api-beta.go2china.space/v2/memories)") == nil)
    }

    @Test(arguments: [
        "https://api-beta.go2china.space./",
        "https://api-beta.go2china%2Espace./",
        "https://api-beta.go2china.space%E3%80%82/",
        "https://%EF%BD%81pi-beta.go2china.space/"
    ])
    func cannotDisplayAlternateSpellingsOfServiceHosts(_ address: String) {
        #expect(LioReplyMarkdown.render("[Forecast](\(address))") == nil)
        #expect(LioReplyMarkdown.render("See \(address)") == nil)
    }

    @Test func continuesAnOrderedItemAfterItsNestedList() throws {
        let answer = try #require(LioReplyMarkdown.render("""
            1. Outer
               - Inner

               Continued
            2. Next
            """))
        #expect(String(answer.characters) == "1. Outer\n  • Inner\n  Continued\n2. Next")
    }
}
