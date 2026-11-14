import Foundation
import Testing
@testable import CJLioUser

@Suite struct LioStreamingBufferTests {
    @Test func chineseCharactersAndEnglishWordsKeepTheirOrder() {
        var buffer = LioStreamingBuffer()
        buffer.receive([.init(text: "北京 Hello world")], completed: false)
        #expect(buffer.text.isEmpty)
        buffer.advance(by: .milliseconds(19), reduceMotion: false)
        #expect(buffer.text.isEmpty)
        buffer.advance(by: .milliseconds(1), reduceMotion: false)
        #expect(buffer.text == "北")
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        #expect(buffer.text == "北京 ")
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        #expect(buffer.text == "北京 Hello ")
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        #expect(buffer.text == "北京 Hello world")
        #expect(!buffer.hasPending)
    }

    @Test func unfinishedWordsAndAtomicBlocksWaitForTheirBoundary() {
        var buffer = LioStreamingBuffer()
        buffer.receive([.init(text: "Hello wor", sealed: false)], completed: false)
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        #expect(buffer.text == "Hello ")
        buffer.receive([.init(text: "Hello world ", sealed: false),
                        .init(text: "\nDay 1", atomic: true, sealed: false)], completed: false)
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        #expect(buffer.text == "Hello world ")
        buffer.receive([.init(text: "Hello world "), .init(text: "\nDay 1", atomic: true)], completed: false)
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        #expect(buffer.text == "Hello world \nDay 1")
    }

    @Test func largeBacklogsAccelerateWithoutSkippingText() {
        var buffer = LioStreamingBuffer()
        let source = String(repeating: "word ", count: 100)
        buffer.receive([.init(text: source)], completed: false)
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        #expect(buffer.text == "word word word ")
        for _ in 0..<100 { buffer.advance(by: .milliseconds(20), reduceMotion: false) }
        #expect(buffer.text == source)
    }

    @Test func completionFlushesEvenAnUnsealedFinalBlockImmediately() {
        var buffer = LioStreamingBuffer()
        let source = String(repeating: "北京 ", count: 500)
        buffer.receive([.init(text: source, atomic: true, sealed: false)], completed: false)
        #expect(buffer.text.isEmpty)
        buffer.receive([.init(text: source, atomic: true, sealed: false)], completed: true)
        #expect(buffer.text == source)
        #expect(!buffer.hasPending)
    }

    @Test func reducedMotionAddsWholeChunksEveryHundredMilliseconds() {
        var buffer = LioStreamingBuffer()
        buffer.receive([.init(text: "北京 Hello world")], completed: false)
        buffer.advance(by: .milliseconds(99), reduceMotion: true)
        #expect(buffer.text.isEmpty)
        buffer.advance(by: .milliseconds(1), reduceMotion: true)
        #expect(buffer.text == "北京 Hello world")
    }

    @Test func updatesPreserveReleasedTextAndCorrectionsReplaceIt() {
        var buffer = LioStreamingBuffer()
        buffer.receive([.init(text: "Hello ")], completed: false)
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        buffer.receive([.init(text: "Hello world")], completed: false)
        #expect(buffer.text == "Hello ")
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        #expect(buffer.text == "Hello world")
        buffer.receive([.init(text: "Good morning")], completed: true)
        #expect(buffer.text == "Good morning")
    }

    @Test func graphemeClustersAndOriginalBytesArePreserved() {
        var buffer = LioStreamingBuffer()
        let source = "Cafe\u{301} 👨‍👩‍👧‍👦 𠮷野家"
        buffer.receive([.init(text: source)], completed: false)
        for _ in 0..<10 { buffer.advance(by: .milliseconds(20), reduceMotion: false) }
        #expect(Array(buffer.text.utf8) == Array(source.utf8))
    }

    @Test func aGraphemeSpanningTwoPresentationBlocksIsNotSplitOrSkipped() {
        var buffer = LioStreamingBuffer()
        buffer.receive([.init(text: "e"), .init(text: "\u{301} x")], completed: false)
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        #expect(Array(buffer.text.utf8) == Array("e\u{301}".utf8))
        buffer.advance(by: .milliseconds(40), reduceMotion: false)
        #expect(Array(buffer.text.utf8) == Array("e\u{301} x".utf8))
        #expect(!buffer.hasPending)
    }

    @Test func returningRevealsReadyTextWithoutCompletingAnUnfinishedHeading() {
        var buffer = LioStreamingBuffer()
        buffer.receive([.init(text: "Hello world\n"), .init(text: "Day 1", atomic: true, sealed: false)], completed: false)
        buffer.revealReady()
        #expect(buffer.text == "Hello world\n")
        buffer.receive([.init(text: "Hello world\n"), .init(text: "Day 1", atomic: true)], completed: false)
        buffer.advance(by: .milliseconds(20), reduceMotion: false)
        #expect(buffer.text == "Hello world\nDay 1")
    }
}
