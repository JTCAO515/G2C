// Synthetic surrounding Shell ONLY for the localized Memory host harness.
// This is not the canonical ShellState and proves no whole-Shell/App behavior.
import Foundation
import Observation
public enum ShellLanguage: String, Sendable {
    case english, chinese
    public func text(_ english: String, _ chinese: String) -> String { self == .english ? english : chinese }
}
public enum MemoryRoute: Hashable { case memoryItems, memoryDetail }
public struct ShellGeneration: Equatable, Sendable { private let id = UUID() }
@MainActor @Observable public final class ShellState {
    public var generation = ShellGeneration()
    public var messageBindingBlocked = false
    public var memoryContainerHost: MemoryContainerHost?
    public var memoryPath: [MemoryRoute] = []
    public var language = ShellLanguage.english
    public init(preferences: UserDefaults = .standard) {}
    public func selectLanguage(_ language: ShellLanguage) { self.language = language }
    public func invalidateIdentity() {
        generation = ShellGeneration(); messageBindingBlocked = true
        memoryContainerHost?.invalidate()
    }
}
