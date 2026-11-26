import Foundation
import Observation

/// Where to go in the app, with parameters (#1724): a registered tool and the values its page starts from, such
/// as `transport` with `from` and `to`. Routes come from chat answers, the trip home and links, so they are checked
/// here once: the tool must be registered, and only the parameters its entry declares are kept.
struct LioRoute: Hashable, Sendable, Identifiable {
    static let scheme = "go2china"
    static let maximumParameters = 8
    static let maximumKeyLength = 32
    static let maximumValueLength = 200

    let tool: LioTool
    let parameters: [String: String]

    var id: Self { self }

    subscript(key: String) -> String? { parameters[key] }

    /// A route to a registered tool, or nil. Keys the tool does not take, empty values and values longer than
    /// `maximumValueLength` are dropped; values are trimmed.
    init?(tool: LioTool, parameters: [String: String] = [:], entries: [LioToolEntry] = LioToolRegistry.entries) {
        guard let entry = LioToolRegistry.entry(for: tool, in: entries) else { return nil }
        var kept: [String: String] = [:]
        for key in parameters.keys.sorted() where entry.parameters.contains(key) && key.count <= Self.maximumKeyLength {
            guard kept.count < Self.maximumParameters, let raw = parameters[key] else { break }
            let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty, value.count <= Self.maximumValueLength,
                  !value.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else { continue }
            kept[key] = value
        }
        self.tool = tool
        self.parameters = kept
    }

    /// `go2china://tool/<tool>?<key>=<value>…`, or nil for any other link. A repeated key keeps its first value.
    init?(url: URL, entries: [LioToolEntry] = LioToolRegistry.entries) {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              components.scheme?.lowercased() == Self.scheme, components.host?.lowercased() == "tool",
              components.user == nil, components.password == nil, components.port == nil, components.fragment == nil
        else { return nil }
        let path = components.path.split(separator: "/", omittingEmptySubsequences: true)
        guard path.count == 1 else { return nil }
        var parameters: [String: String] = [:]
        for item in components.queryItems ?? [] where parameters[item.name] == nil {
            if let value = item.value { parameters[item.name] = value }
        }
        self.init(tool: LioTool(String(path[0])), parameters: parameters, entries: entries)
    }

    /// The link form of this route, as `init(url:)` reads it.
    var url: URL? {
        var components = URLComponents()
        components.scheme = Self.scheme
        components.host = "tool"
        components.path = "/" + tool.rawValue
        if !parameters.isEmpty {
            components.queryItems = parameters.keys.sorted().map { URLQueryItem(name: $0, value: parameters[$0]) }
        }
        return components.url
    }
}

/// The four tabs (#1724). The tab container shows them; `LioRouter` says which one is selected.
public enum LioTab: Hashable, Sendable {
    case chat, trips, tools, me

    /// Chat, except that Debug builds accept `--lio-initial-tab tools` for local screenshots.
    static func initial(arguments: [String] = ProcessInfo.processInfo.arguments) -> LioTab {
        #if DEBUG
        if let index = arguments.firstIndex(of: "--lio-initial-tab"), index + 1 < arguments.count {
            switch arguments[index + 1] {
            case "trips": return .trips
            case "tools": return .tools
            case "memory", "me": return .me
            default: break
            }
        }
        #endif
        return .chat
    }
}

/// The selected tab and the Tools tab's open pages (#1724). Chat, the trip home and links open tools through
/// `open(_:)`, so none of them needs to know how the Tools tab is built.
@MainActor @Observable
final class LioRouter {
    var tab: LioTab
    /// Pages open in the Tools tab, first page first.
    var toolsPath: [LioRoute] = []
    /// False when this build hides the Tools tab; then no route opens.
    let toolsShown: Bool

    init(tab: LioTab = .initial(), toolsShown: Bool) {
        self.tab = toolsShown || tab != .tools ? tab : .chat
        self.toolsShown = toolsShown
    }

    /// Shows the route's page in the Tools tab, on top of the tool list. False when the Tools tab is hidden.
    @discardableResult
    func open(_ route: LioRoute) -> Bool {
        guard toolsShown else { return false }
        toolsPath = [route]
        tab = .tools
        return true
    }

    /// Opens a `go2china://tool/…` link. False for any other link or a tool that is not registered.
    @discardableResult
    func open(url: URL) -> Bool {
        guard let route = LioRoute(url: url) else { return false }
        return open(route)
    }
}
