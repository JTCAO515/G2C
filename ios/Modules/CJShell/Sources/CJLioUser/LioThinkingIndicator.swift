import CJMessageHTTP
import Foundation
import SwiftUI

/// What line L's `progress` field (#925) gives the waiting indicator: the phrase to show and, only for
/// `planning_started`, the day count for the trip-shaped placeholder. The app never supplies days itself.
struct LioThinkingInput: Equatable {
    let progress: String?
    let planningDays: Int?

    init(progress: String? = nil, planningDays: Int? = nil) {
        self.progress = progress
        self.planningDays = planningDays
    }

    init(_ wire: LioExplorationWire.Progress?) {
        switch wire {
        case .waiting(let text)?: self.init(progress: text)
        case .planningStarted(let text, let days)?: self.init(progress: text, planningDays: days > 0 ? days : nil)
        case nil: self.init()
        }
    }
}

/// What the waiting indicator shows at a given moment after sending (#913, Nielsen's response-time bands).
enum LioThinkingPhase: Equatable {
    /// 0–0.3 s: nothing, so a quick reply doesn't flash an indicator.
    case hidden
    /// 0.3–6 s: the breathing avatar and three rising dots.
    case breathing
    /// From 6 s: one line of status text.
    case status(String)

    static let showAfter: TimeInterval = 0.3
    static let statusAfter: TimeInterval = 6
    static let longAfter: TimeInterval = 15

    /// `progress` is the product-level phrase from line L when it exists; it replaces the general copy.
    static func at(_ elapsed: TimeInterval, progress: String?, language: LioLanguage) -> LioThinkingPhase {
        if elapsed < showAfter { return .hidden }
        if elapsed < statusAfter { return .breathing }
        if let progress = progress?.trimmingCharacters(in: .whitespacesAndNewlines), !progress.isEmpty {
            return .status(progress)
        }
        return .status(elapsed < longAfter
            ? language.text("Pulling the details together…", "正在整理信息…")
            : language.text("This one is taking a little longer…", "这次要多想一会儿…"))
    }

    var statusText: String? {
        if case .status(let text) = self { text } else { nil }
    }
}

/// Lets VoiceOver hear a changed status line at most once every five seconds.
struct LioAnnouncementThrottle {
    static let minimumInterval: TimeInterval = 5
    private var lastText: String?
    private var lastTime: Date?

    mutating func shouldAnnounce(_ text: String, at now: Date) -> Bool {
        guard text != lastText else { return false }
        if let lastTime, now.timeIntervalSince(lastTime) < Self.minimumInterval { return false }
        lastText = text
        lastTime = now
        return true
    }
}

#if os(iOS)
/// Replaces the old status line while Lio is working on a reply.
struct LioThinkingIndicator: View {
    let since: Date
    let progress: String?
    /// Days announced by line L's planning signal; shows a trip-shaped placeholder card.
    let planningDays: Int?
    let language: LioLanguage
    var onVisible: () -> Void = {}

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var onScreen = false
    @State private var breath = false
    @State private var announcer = LioAnnouncementThrottle()
    @State private var reportedVisible = false

    private var animating: Bool { onScreen && scenePhase == .active && !reduceMotion }

    var body: some View {
        TimelineView(.periodic(from: since, by: 0.25)) { context in
            let phase = LioThinkingPhase.at(context.date.timeIntervalSince(since), progress: progress, language: language)
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                row(phase)
                if let planningDays, phase != .hidden {
                    LioItinerarySkeleton(days: planningDays, since: since, animating: animating)
                        .transition(.opacity)
                }
            }
            .opacity(phase == .hidden ? 0 : 1)
            .animation(LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion), value: phase)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(language.text("Lio is replying…", "Lio 正在回复…"))
            .accessibilityValue(phase.statusText ?? "")
            .accessibilityAddTraits(.isStaticText)
            .accessibilityIdentifier("lio.progress")
            .onChange(of: phase, initial: true) { _, phase in
                if phase != .hidden, !reportedVisible {
                    reportedVisible = true
                    onVisible()
                }
                if let text = phase.statusText, announcer.shouldAnnounce(text, at: context.date) {
                    AccessibilityNotification.Announcement(text).post()
                }
            }
        }
        .onAppear { onScreen = true }
        .onDisappear { onScreen = false }
        .onChange(of: animating, initial: true) { _, animating in
            if animating {
                withAnimation(LioTheme.Motion.breathing) { breath = true }
            } else {
                var still = Transaction(animation: nil)
                still.disablesAnimations = true
                withTransaction(still) { breath = false }
            }
        }
    }

    private func row(_ phase: LioThinkingPhase) -> some View {
        HStack(spacing: LioTheme.Spacing.xs) {
            LioPortrait(size: 22)
                .scaleEffect(breath ? 1.04 : 1)
            if let text = phase.statusText {
                LioShimmerText(text: text, animating: animating)
            } else {
                LioRisingDots(animating: animating)
            }
        }
        .frame(minHeight: 28)
    }
}

/// Three dots rising one after another; still when paused.
struct LioRisingDots: View {
    let animating: Bool

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: !animating)) { context in
            let time = context.date.timeIntervalSinceReferenceDate
            HStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .fill(LioTheme.inkSecondary)
                        .frame(width: 6, height: 6)
                        .offset(y: animating ? Self.lift(time, index: index) : 0)
                }
            }
            .frame(height: 14)
        }
    }

    /// Each dot lifts up to 3pt once per 1.2 s cycle, a fifth of a cycle after the previous dot.
    static func lift(_ time: TimeInterval, index: Int) -> CGFloat {
        let cycle = 1.2
        let phase = (time / cycle - Double(index) * 0.2).truncatingRemainder(dividingBy: 1)
        let wave = phase < 0.5 ? sin(phase * 2 * .pi) : 0
        return -3 * CGFloat(max(0, wave))
    }
}

/// Status text in `inkSecondary` with a highlight sweeping through in `ink`; plain text when paused.
struct LioShimmerText: View {
    let text: String
    let animating: Bool

    var body: some View {
        let label = Text(text).font(.footnote)
        label
            .foregroundStyle(LioTheme.inkSecondary)
            .overlay {
                if animating {
                    TimelineView(.animation(minimumInterval: 1 / 30)) { context in
                        let progress = context.date.timeIntervalSinceReferenceDate
                            .truncatingRemainder(dividingBy: LioTheme.Motion.breathingCycle) / LioTheme.Motion.breathingCycle
                        label
                            .foregroundStyle(LioTheme.ink)
                            .mask {
                                LinearGradient(stops: [
                                    .init(color: .clear, location: 0),
                                    .init(color: .black, location: 0.5),
                                    .init(color: .clear, location: 1)
                                ], startPoint: .leading, endPoint: .trailing)
                                .frame(width: 80)
                                .offset(x: -80 + progress * 400)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            }
                    }
                    .accessibilityHidden(true)
                }
            }
    }
}

/// A placeholder with the trip card's shape: a title bar, then per day a heading and two stops.
/// Days fill in one by one; the real card replaces it when it arrives.
struct LioItinerarySkeleton: View {
    let days: Int
    let since: Date
    let animating: Bool

    var body: some View {
        TimelineView(.periodic(from: since, by: 0.6)) { context in
            let shown = animating ? min(days, 1 + Int(context.date.timeIntervalSince(since) / 0.6)) : days
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                bar(width: 140, height: 16)
                ForEach(0..<max(days, 0), id: \.self) { day in
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                        bar(width: 90, height: 12)
                        bar(width: 220, height: 10)
                        bar(width: 180, height: 10)
                    }
                    .opacity(day < shown ? 1 : 0.35)
                }
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        }
        .accessibilityHidden(true)
    }

    private func bar(width: CGFloat, height: CGFloat) -> some View {
        Capsule().fill(LioTheme.surfaceSunken).frame(maxWidth: width).frame(height: height)
    }
}
#endif
