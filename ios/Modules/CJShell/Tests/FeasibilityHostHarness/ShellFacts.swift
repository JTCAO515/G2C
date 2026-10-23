// Synthetic local facts ONLY. Does not validate real ShellState lifecycle/root wiring.
import Foundation
import Observation
public struct ShellGeneration: Equatable, Sendable { private let id = UUID() }
public enum ShellLanguage { case english, chinese
    public func text(_ en: String, _ zh: String) -> String { self == .english ? en : zh }
}
@MainActor @Observable public final class ShellState {
    public var generation = ShellGeneration()
    var messageBindingBlocked = false
    weak var needsContainerHost: NeedsContainerHost?
}
