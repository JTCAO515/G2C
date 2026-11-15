import Foundation
import Testing
@testable import CJLioUser

@Suite struct LioStreamingMarkdownTests {
    @Test func rendererCharactersAndBytesAreKeptExactly() throws {
        for source in ["Hello **world**.\n\n• 北京\n• 上海", "# A plan\n\n1. Hotel\n2. Museum", "你好，世界。\n\n[Map](https://example.com/map)"] {
            let value = try #require(LioReplyMarkdown.render(source))
            let blocks = LioStreamingMarkdown.blocks(value, sourceEndsLine: source.hasSuffix("\n"), completed: true)
            #expect(Array(blocks.map(\.text).joined().utf8) == Array(String(value.characters).utf8))
        }
    }

    @Test func headingsAndListsStayAtomicAndWaitForClosingBoundaries() throws {
        let heading = try #require(LioReplyMarkdown.render("# Day 1"))
        let partial = LioStreamingMarkdown.blocks(heading, sourceEndsLine: false, completed: false)
        #expect(partial.count == 1)
        #expect(partial[0].atomic && !partial[0].sealed)
        let closed = LioStreamingMarkdown.blocks(heading, sourceEndsLine: true, completed: false)
        #expect(closed[0].sealed)

        let list = try #require(LioReplyMarkdown.render("1. Hotel\n2. Museum"))
        let lines = LioStreamingMarkdown.blocks(list, sourceEndsLine: false, completed: false)
        #expect(lines.count == 2)
        #expect(lines[0].atomic && lines[0].sealed)
        #expect(lines[1].atomic && !lines[1].sealed)
    }

    @Test func formattedLinksRemainInTheOriginalRenderer() throws {
        let value = try #require(LioReplyMarkdown.render("Try **a museum** and [a walk](https://example.com/walk)."))
        #expect(value.runs.contains { $0.link?.absoluteString == "https://example.com/walk" })
        #expect(value.runs.contains { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true })
        #expect(LioStreamingMarkdown.blocks(value, sourceEndsLine: false, completed: true).allSatisfy { !$0.atomic })
    }

    @Test func partialInlineMarkupWaitsAndFinishedMarkupRemainsFormatted() throws {
        for source in ["Try **an easy ", "Read [the guide", "Use `a quieter "] {
            let partial = try #require(LioReplyMarkdown.render(source))
            #expect(LioStreamingMarkdown.containsLiteralDelimiters(partial))
        }
        for source in ["Try **an easy pace**.", "Read [the_guide](https://example.com/guide).", "Use `gate_1`."] {
            let finished = try #require(LioReplyMarkdown.render(source))
            #expect(!LioStreamingMarkdown.containsLiteralDelimiters(finished))
        }
    }

    @Test func motionUsesTheApprovedPacingAndEntranceValues() {
        #expect(LioTheme.Motion.streamingStep == .milliseconds(20))
        #expect(LioTheme.Motion.reducedStreamingStep == .milliseconds(100))
        #expect(LioTheme.Motion.markdownStep == .milliseconds(40))
        #expect(LioTheme.Motion.glyphFade == .milliseconds(150))
        #expect(LioTheme.Motion.resultDelay == .milliseconds(200))
        #expect(LioEntranceStyle.result.scale == 0.98)
        #expect(LioEntranceStyle.result.offset == 0)
        #expect(LioTheme.Motion.animation(LioEntranceStyle.result.animation, reduceMotion: true) == nil)
    }
}
