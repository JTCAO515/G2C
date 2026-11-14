import SwiftUI

/// How a view enters the Lio conversation. Every style is skipped when Reduce Motion is on.
enum LioEntranceStyle: Equatable {
    /// The traveller's message rises 8pt from the message field and fades in.
    case rise
    /// Lio's reply fades in.
    case fade
    /// The first frame's avatar grows from 80% and fades in.
    case launch

    var animation: Animation {
        switch self {
        case .rise: LioTheme.Motion.enter
        case .fade: LioTheme.Motion.change
        case .launch: LioTheme.Motion.launch
        }
    }

    var offset: CGFloat { self == .rise ? 8 : 0 }
    var scale: CGFloat { self == .launch ? 0.8 : 1 }
}

/// Plays an entrance once, the first time the view appears while `active`. Views that appear later
/// (scrolled back into view, restored history) show at once, so nothing replays.
struct LioEntrance: ViewModifier {
    let style: LioEntranceStyle
    let finished: () -> Void
    @State private var shown: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    init(style: LioEntranceStyle, active: Bool, finished: @escaping () -> Void) {
        self.style = style
        self.finished = finished
        _shown = State(initialValue: !active)
    }

    func body(content: Content) -> some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: shown ? 0 : style.offset)
            .scaleEffect(shown ? 1 : style.scale)
            .onAppear {
                guard !shown else { return }
                withAnimation(LioTheme.Motion.animation(style.animation, reduceMotion: reduceMotion)) { shown = true }
                finished()
            }
    }
}

extension View {
    func lioEntrance(_ style: LioEntranceStyle, active: Bool, finished: @escaping () -> Void = {}) -> some View {
        modifier(LioEntrance(style: style, active: active, finished: finished))
    }
}

/// Which part of a turn is still waiting for its entrance.
struct LioEntranceKey: Hashable {
    enum Part: Hashable { case question, answer }
    let turn: Data
    let part: Part
}

/// The first-frame avatar animation plays once per process, not on every sign-in or new home.
@MainActor
enum LioLaunchMotion {
    static var played = false
}
