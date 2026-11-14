import SwiftUI

#if os(iOS)
/// Presentation delay only; the caller supplies an already saved itinerary.
struct LioResultEntrance<Content: View>: View {
    let onShown: () -> Void
    @ViewBuilder let content: (Bool) -> Content
    @State private var fresh: Bool
    @State private var revealed: Bool
    @State private var onScreen = false
    @State private var started: ContinuousClock.Instant?
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    init(fresh: Bool, onShown: @escaping () -> Void, @ViewBuilder content: @escaping (Bool) -> Content) {
        self.onShown = onShown
        self.content = content
        _fresh = State(initialValue: fresh)
        _revealed = State(initialValue: !fresh)
    }

    private var active: Bool { onScreen && scenePhase == .active }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if revealed {
                content(fresh)
                    .lioEntrance(.result, active: fresh, finished: onShown)
            }
        }
        .background {
            TimelineView(.animation(minimumInterval: LioTheme.Motion.streamingStep / .seconds(1), paused: !active || revealed)) { context in
              Color.clear.frame(width: 0, height: 0)
            .onChange(of: context.date, initial: true) { _, _ in
                guard active, !revealed else { return }
                if reduceMotion { revealed = true }
                else if let started, ContinuousClock.now - started >= LioTheme.Motion.resultDelay { revealed = true }
            }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
        .onAppear { onScreen = true; started = .now; if reduceMotion { revealed = true } }
        .onDisappear { onScreen = false; started = nil }
        .onChange(of: active) { _, active in if active { started = .now } }
        .onChange(of: reduceMotion) { _, reduced in if reduced { revealed = true } }
    }
}
#endif
