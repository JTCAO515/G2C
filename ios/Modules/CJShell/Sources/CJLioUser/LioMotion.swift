import SwiftUI

/// How a view enters the Lio conversation. Every style is skipped when Reduce Motion is on.
enum LioEntranceStyle: Equatable {
    /// The traveller's message rises 8pt from the message field and fades in.
    case rise
    /// Lio's reply fades in.
    case fade
    /// The first frame's avatar grows from 80% and fades in.
    case launch
    /// A saved result grows from 98% after the answer finishes.
    case result

    var animation: Animation {
        switch self {
        case .rise: LioTheme.Motion.enter
        case .fade: LioTheme.Motion.change
        case .launch: LioTheme.Motion.launch
        case .result: LioTheme.Motion.emphasis
        }
    }

    var offset: CGFloat { self == .rise ? 8 : 0 }
    var scale: CGFloat { self == .launch ? 0.8 : self == .result ? 0.98 : 1 }
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

#if os(iOS)
extension View {
    /// Whether any part of this view is inside the nearest scroll view's visible area. The chat stacks every
    /// message eagerly (#1501), so `onAppear` no longer means "on screen" there.
    func lioOnScreenChange(_ action: @escaping (Bool) -> Void) -> some View {
        onGeometryChange(for: Bool.self) { proxy in
            guard let visible = proxy.bounds(of: .scrollView) else { return true }
            // A placeholder that is still empty (a result waiting for its entrance) counts by its position.
            let size = CGSize(width: max(proxy.size.width, 1), height: max(proxy.size.height, 1))
            return visible.intersects(CGRect(origin: .zero, size: size))
        } action: { action($0) }
    }
}
#endif

/// Which part of a turn is still waiting for its entrance.
struct LioEntranceKey: Hashable {
    /// `answerTail` is the second bubble of a two-bubble answer (#1727): its own fade, so the first bubble finishing
    /// does not end the second one's.
    enum Part: Hashable { case question, answer, answerTail, card, memory }
    let turn: Data
    let part: Part
}

/// The first-frame avatar animation plays once per process, not on every sign-in or new home.
@MainActor
enum LioLaunchMotion {
    static var played = false
}
