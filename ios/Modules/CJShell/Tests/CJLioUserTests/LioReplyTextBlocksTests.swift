import Foundation
import SwiftUI
import Testing
@testable import CJLioUser

struct LioReplyTextBlocksTests {
    @Test func separatesHeadingStyleWhilePreservingInlineFormattingAndLinks() throws {
        let rendered = try #require(LioReplyMarkdown.render("**之前的回答**\n\nA **quiet** day. [More](https://example.com/)"))
        let blocks = LioReplyTextBlock.make(from: rendered)
        #expect(blocks.count == 2)
        #expect(blocks[0].font == Font.title3.weight(.semibold))
        #expect(blocks[1].font == nil)
        #expect(blocks.allSatisfy { $0.text.runs.allSatisfy { $0.font == nil } })
        #expect(blocks.map { $0.leadingSeparator + String($0.text.characters) }.joined() == String(rendered.characters))
        #expect(blocks[1].text.runs.contains { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true })
        #expect(blocks[1].text.runs.contains { $0.link == URL(string: "https://example.com/") })
    }

    @Test func preservesListIndentationAndBodyParagraphs() throws {
        let rendered = try #require(LioReplyMarkdown.render("## Plan\n\n1. Outer\n   - Inner\n\n   Continued\n2. Next\n\nA final note."))
        let blocks = LioReplyTextBlock.make(from: rendered)
        #expect(blocks.count == 2)
        #expect(String(blocks[1].text.characters).contains("  • Inner\n  Continued"))
        #expect(blocks.map { $0.leadingSeparator + String($0.text.characters) }.joined() == String(rendered.characters))
    }
}
