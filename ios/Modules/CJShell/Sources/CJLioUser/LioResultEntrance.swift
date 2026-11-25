import SwiftUI

#if os(iOS)
/// Presentation delay only; the caller supplies an already saved itinerary.
struct LioResultEntrance<Content: View>: View {
    let onShown: () -> Void
    let presentationActive: Bool
    @ViewBuilder let content: (Bool) -> Content
    @State private var fresh: Bool
    @State private var phase: Phase
    @State private var onScreen = false
    @State private var started: ContinuousClock.Instant?
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private enum Phase { case waiting, entering, shown }

    init(fresh: Bool, presentationActive: Bool = true, onShown: @escaping () -> Void, @ViewBuilder content: @escaping (Bool) -> Content) {
        self.onShown = onShown
        self.presentationActive = presentationActive
        self.content = content
        _fresh = State(initialValue: fresh)
        _phase = State(initialValue: fresh ? .waiting : .shown)
    }

    private var active: Bool { onScreen && scenePhase == .active && presentationActive }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if phase != .waiting {
                content(fresh)
                    .lioEntrance(.result, active: phase == .entering && active) {
                        guard active, phase == .entering else { return }
                        phase = .shown
                        onShown()
                    }
            }
        }
        .background {
            TimelineView(.animation(minimumInterval: LioTheme.Motion.streamingStep / .seconds(1), paused: !active || phase != .waiting)) { context in
              Color.clear.frame(width: 0, height: 0)
            .onChange(of: context.date, initial: true) { _, _ in
                guard active, phase == .waiting else { return }
                if reduceMotion { phase = .entering }
                else if let started, ContinuousClock.now - started >= LioTheme.Motion.resultDelay { phase = .entering }
            }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
        // Visible in the chat, not merely inserted: a result that arrives while the reader is scrolled away waits.
        .lioOnScreenChange { visible in
            guard visible != onScreen else { return }
            onScreen = visible
            started = visible ? .now : nil
            if visible, active, reduceMotion, phase == .waiting { phase = .entering }
        }
        // No reset on disappear: geometry reports only changes, so a tab switch must not clear a visible card.
        // Covered tabs and sheets pause through `presentationActive`.
        .onChange(of: active) { _, active in
            if active { started = .now }
            else if phase == .entering { phase = .waiting }
        }
        .onChange(of: reduceMotion) { _, reduced in if reduced && active && phase == .waiting { phase = .entering } }
    }
}
#endif
