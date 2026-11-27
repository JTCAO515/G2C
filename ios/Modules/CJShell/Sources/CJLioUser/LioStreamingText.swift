import Foundation
import SwiftUI

/// Line boundaries from the existing Markdown result; no second parser or wire format.
enum LioStreamingMarkdown {
    /// Keep the last admitted prefix while a streaming line still contains literal
    /// delimiters. The existing renderer decides the final interpretation at completion.
    static func containsLiteralDelimiters(_ value: AttributedString) -> Bool {
        value.runs.contains { run in
            guard run.inlinePresentationIntent == nil, run.link == nil else { return false }
            let text = String(value[run.range].characters)
            return text.contains("**") || text.contains("[") || text.contains("`") || text.contains("_")
        }
    }

    static func blocks(_ value: AttributedString, sourceEndsLine: Bool, completed: Bool) -> [LioStreamingBlock] {
        var result: [LioStreamingBlock] = []
        var start = value.startIndex
        while start < value.endIndex {
            let newline = value.characters[start...].firstIndex(of: "\n")
            let end = newline.map { value.characters.index(after: $0) } ?? value.endIndex
            let line = value[start..<end]
            let text = String(line.characters)
            let trimmed = text.trimmingCharacters(in: .whitespaces)
            let heading = line.runs.contains { $0.font != nil }
            let list = trimmed.hasPrefix("• ") || trimmed.range(of: #"^[0-9]+\. "#, options: .regularExpression) != nil
            result.append(.init(text: text, atomic: heading || list,
                                sealed: newline != nil || completed || sourceEndsLine))
            start = end
        }
        return result
    }
}

#if os(iOS)
/// Paces the existing, admitted Markdown output. Network and message state stay in the parent.
struct LioStreamingText: View {
    let source: String
    /// Words of `source` the server named as places (#1991): drawn as tappable words.
    let places: [LioPlaceSpan]
    let streaming: Bool
    let language: LioLanguage
    let presentationActive: Bool
    let identifier: String
    let onFirstVisible: () -> Void
    let onComplete: () -> Void
    let onLayout: () -> Void
    @State private var animate: Bool
    @State private var onScreen = false
    @State private var appeared = false
    @State private var firstVisible = false
    @State private var completed = false
    @State private var parsedSource: String?
    @State private var parsedPlaces: [LioPlaceSpan] = []
    @State private var parsedCompleted = false
    @State private var rendered: AttributedString?
    @State private var rejected = false
    @State private var buffer = LioStreamingBuffer()
    @State private var lastTick: ContinuousClock.Instant?
    @State private var lastParse: ContinuousClock.Instant?
    @State private var births: [Birth] = []
    @State private var layoutRevision = 0
    @State private var paintTime = ContinuousClock.now
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private struct Birth {
        let range: Range<Int>
        let at: ContinuousClock.Instant
    }

    init(source: String, places: [LioPlaceSpan] = [], streaming: Bool, animate: Bool, language: LioLanguage,
         presentationActive: Bool = true,
         identifier: String = "lio.answer", onFirstVisible: @escaping () -> Void = {},
         onComplete: @escaping () -> Void = {}, onLayout: @escaping () -> Void = {}) {
        self.source = source
        self.places = places
        self.streaming = streaming
        self.language = language
        self.presentationActive = presentationActive
        self.identifier = identifier
        self.onFirstVisible = onFirstVisible
        self.onComplete = onComplete
        self.onLayout = onLayout
        _animate = State(initialValue: animate)
    }

    private var visible: Bool { onScreen && scenePhase == .active && presentationActive }
    private var sourceChanged: Bool {
        guard let parsedSource else { return true }
        return !source.utf8.elementsEqual(parsedSource.utf8)
    }
    private var ticking: Bool {
        visible && (sourceChanged || places != parsedPlaces || buffer.hasPending || !births.isEmpty || (!streaming && !completed))
    }

    // `completed` is established by report() only while this presentation is
    // visible. A later source change must not reuse that older completion.
    private var hasCompleteBody: Bool {
        completed && !streaming && parsedCompleted && !buffer.hasPending
            && births.isEmpty && !sourceChanged && !rejected
    }

    var body: some View {
        Group {
                if rejected {
                    Text(language.text("This reply can’t be shown right now.", "这条回答暂时无法显示。"))
                        .accessibilityIdentifier("lio.reply.unavailable")
                } else if let rendered {
                    Text(display(rendered, at: paintTime))
                        .textSelection(.enabled)
                        .accessibilityIdentifier(identifier)
                        .accessibilityValue(hasCompleteBody
                            ? language.text("Reply complete", "回复已完成")
                            : language.text("Replying…", "正在回复…"))
                } else {
                    Text("")
                }
        }
            // #1869: SwiftUI sizes a Chinese reply's lines from the system (Latin) font, about 4 pt per line short of what
            // the glyphs need, which the accessibility audit reports as clipped. PingFang carries the CJK line metrics.
            // Still the body size, scaling with Dynamic Type.
            .font(language == .chinese ? Font.custom("PingFangSC-Regular", size: 17, relativeTo: .body) : .body)
            .foregroundStyle(LioTheme.ink)
            .lineSpacing(4)
            .fixedSize(horizontal: false, vertical: true)
        .background {
            TimelineView(.animation(minimumInterval: (reduceMotion ? LioTheme.Motion.reducedStreamingStep
                                                     : LioTheme.Motion.streamingStep) / .seconds(1), paused: !ticking)) { context in
                Color.clear.frame(width: 0, height: 0)
                    .onChange(of: context.date, initial: true) { _, _ in step() }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
        .onAppear {
            onScreen = true
            let returning = appeared
            appeared = true
            reconcile(force: true)
            if returning || !animate { buffer.revealReady(); births = []; layoutRevision += 1 }
            report()
        }
        .onDisappear { onScreen = false; lastTick = nil; births = [] }
        .onChange(of: source) { _, _ in reconcile(force: !streaming || !animate) }
        .onChange(of: places) { _, _ in reconcile(force: true) }
        .onChange(of: streaming) { _, streaming in if !streaming { reconcile(force: true) } }
        .onChange(of: scenePhase) { _, _ in resumeIfVisible() }
        .onChange(of: presentationActive) { _, _ in resumeIfVisible() }
        .onChange(of: reduceMotion) { _, reduceMotion in if reduceMotion { births = [] } }
        .onChange(of: layoutRevision) { _, _ in onLayout() }
    }

    private func resumeIfVisible() {
        lastTick = nil
        births = []
        if visible {
            reconcile(force: true)
            buffer.revealReady()
            layoutRevision += 1
            report()
        }
    }

    private func step() {
        guard visible else { return }
        let now = ContinuousClock.now
        paintTime = now
        reconcile(force: false)
        if let lastTick, animate, !completed {
            let before = buffer.visibleCharacterCount
            if buffer.advance(by: now - lastTick, reduceMotion: reduceMotion) { layoutRevision += 1 }
            recordBirth(from: before, at: now)
        }
        lastTick = now
        births.removeAll { now - $0.at >= LioTheme.Motion.glyphFade }
        report()
    }

    private func reconcile(force: Bool) {
        guard sourceChanged || places != parsedPlaces || (!streaming && !parsedCompleted) else { return }
        let now = ContinuousClock.now
        if !force, let lastParse, now - lastParse < LioTheme.Motion.markdownStep { return }
        lastParse = now
        parsedSource = source
        parsedPlaces = places
        parsedCompleted = !streaming
        let value = LioReplyMarkdown.render(source, places: places)
        if streaming, let value, LioStreamingMarkdown.containsLiteralDelimiters(value) { return }
        rejected = value == nil
        rendered = value
        layoutRevision += 1
        let before = buffer.visibleCharacterCount
        let wasPending = buffer.hasPending
        if let value {
            buffer.receive(LioStreamingMarkdown.blocks(value, sourceEndsLine: source.hasSuffix("\n"),
                                                       completed: !streaming), completed: !streaming)
            if !animate || completed { buffer.revealReady() }
        } else {
            buffer.receive([], completed: true)
        }
        if !wasPending { lastTick = now }
        if buffer.visibleCharacterCount < before { births = [] }
        recordBirth(from: before, at: now)
        report()
    }

    private func recordBirth(from previous: Int, at now: ContinuousClock.Instant) {
        let end = buffer.visibleCharacterCount
        if animate, !completed, !reduceMotion, visible, end > previous {
            births.append(Birth(range: previous..<end, at: now))
        }
    }

    private func display(_ value: AttributedString, at now: ContinuousClock.Instant) -> AttributedString {
        let count = buffer.visibleCharacterCount
        let end = value.characters.index(value.startIndex, offsetBy: count)
        var shown = AttributedString(value[value.startIndex..<end])
        for birth in births {
            let lower = min(birth.range.lowerBound, count)
            let upper = min(birth.range.upperBound, count)
            let start = shown.characters.index(shown.startIndex, offsetBy: lower)
            let end = shown.characters.index(shown.startIndex, offsetBy: upper)
            let alpha = min(1, max(0, (now - birth.at) / LioTheme.Motion.glyphFade))
            for run in shown[start..<end].runs {
                shown[run.range].foregroundColor = (run.link == nil ? LioTheme.ink : LioTheme.vermilion).opacity(alpha)
            }
        }
        return shown
    }

    private func report() {
        guard visible else { return }
        let textIsVisible = buffer.visibleCharacterCount > 0 && (births.first.map { ContinuousClock.now - $0.at >= LioTheme.Motion.streamingStep } ?? true)
        if !firstVisible, rejected || textIsVisible {
            firstVisible = true
            onFirstVisible()
        }
        if !streaming, parsedCompleted, !buffer.hasPending, births.isEmpty, !sourceChanged, !completed {
            completed = true
            onComplete()
        }
    }
}
#endif
