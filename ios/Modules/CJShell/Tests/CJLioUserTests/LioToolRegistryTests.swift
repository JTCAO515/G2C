import Foundation
import SwiftUI
import Testing
@testable import CJLioUser

/// #1724: tools are declared once in `LioToolRegistry`, and routes with parameters open them.
@MainActor
struct LioToolRegistryTests {
    /// A tool declared only by this entry, as a new tool would be.
    private static let example = LioToolEntry(LioTool("example"), symbol: "star",
                                              name: ("Example", "示例"), summary: ("One sentence", "一句话"),
                                              gate: .build(infoKey: "G2CExampleEnabled"),
                                              parameters: ["city"]) { _, _ in EmptyView() }
    private static let entries = LioToolRegistry.entries + [example]

    private func context(info: [String: String] = [:], arguments: [String] = []) -> LioToolContext {
        var context = LioToolContext(language: .english)
        context.info = { info[$0] }
        context.arguments = arguments
        return context
    }

    @Test func registryKeepsTheCardOrderAndNamesFromBeforeTheRegistry() {
        #expect(LioTool.allCases == [.returnHotel, .arrival, .localSupport, .taxi, .hotels, .roadbook, .transport,
                                     .attractionBooking, .menuOrder, .nearby, .currency, .metro, .payment,
                                     .translation, .showCards])
        #expect(Set(LioTool.allCases.map(\.rawValue)).count == LioTool.allCases.count)
        #expect(LioTool.metro.name(.chinese) == "地铁指南")
        #expect(LioTool.transport.summary(.english) == "Compare trains, flights and buses")
        #expect(LioTool.hotels.symbol == "bed.double")
    }

    @Test func onlyTaxiHotelsTransportBookingAndShowCardsTakeParametersSoFar() {
        let taking = LioToolRegistry.entries.filter { !$0.parameters.isEmpty }
        #expect(taking.map(\.tool) == [.taxi, .hotels, .transport, .attractionBooking, .showCards])
        // #1765: the trip home's meeting item lands on Show Cards' Business section.
        #expect(LioToolRegistry.entry(for: .showCards)?.parameters == ["section"])
        // #1740: a trip place opens the taxi with its destination and the booking tool with its sight.
        #expect(LioToolRegistry.entry(for: .taxi)?.parameters == ["destination", "destinationEN", "address", "lat", "lng"])
        #expect(LioToolRegistry.entry(for: .attractionBooking)?.parameters == ["sight"])
        #expect(LioToolRegistry.entry(for: .transport)?.parameters == ["from", "to"])
        #expect(LioToolRegistry.entry(for: .hotels)?.parameters == ["city"])
    }

    @Test func aNewToolDeclaredOnceIsHiddenUntilItsBuildKeySaysYes() {
        let off = context().availability(entries: Self.entries)
        #expect(!LioToolCatalog.visible(off, entries: Self.entries).contains(Self.example.tool))

        let no = context(info: ["G2CExampleEnabled": "NO"]).availability(entries: Self.entries)
        #expect(!LioToolCatalog.visible(no, entries: Self.entries).contains(Self.example.tool))

        let on = context(info: ["G2CExampleEnabled": "YES"]).availability(entries: Self.entries)
        #expect(LioToolCatalog.visible(on, entries: Self.entries).last == Self.example.tool)
        #expect(Self.example.tool.identifier == "lio.tools.example")
    }

    @Test func debugPreviewArgumentShowsOneNewTool() {
        let preview = context(arguments: ["--lio-tool-preview", "example"]).availability(entries: Self.entries)
        #expect(preview.enabled == [Self.example.tool])
        let other = context(arguments: ["--lio-tool-preview", "taxi"]).availability(entries: Self.entries)
        #expect(other.enabled.isEmpty)
    }

    @Test func aBuildGateCanRequireAService() {
        struct Client: Sendable { let name: String }
        let needsClient = LioToolEntry(LioTool("needs-client"), symbol: "star", name: ("A", "甲"), summary: ("B", "乙"),
                                       gate: .build(infoKey: "G2CNeedsClientEnabled") { $0.services.get(Client.self) != nil }) { _, _ in
            EmptyView()
        }
        var context = context(info: ["G2CNeedsClientEnabled": "YES"])
        #expect(context.availability(entries: [needsClient]).enabled.isEmpty)
        context.services = LioToolServices().with(Client(name: "relay"))
        #expect(context.availability(entries: [needsClient]).enabled == [needsClient.tool])
        #expect(context.services.get(Client.self)?.name == "relay")
        #expect(LioToolServices().with(Optional<Client>.none).get(Client.self) == nil)
    }

    @Test func routesKeepOnlyTheParametersTheToolDeclares() throws {
        let route = try #require(LioRoute(tool: .transport, parameters: ["from": " Shanghai ", "to": "北京", "date": "x"]))
        #expect(route.parameters == ["from": "Shanghai", "to": "北京"])
        #expect(route["to"] == "北京")
        #expect(LioRoute(tool: .metro, parameters: ["city": "Guangzhou"])?.parameters == [:])
        #expect(LioRoute(tool: LioTool("unknown")) == nil)
        #expect(LioRoute(tool: Self.example.tool, entries: Self.entries) != nil)
    }

    @Test func routesDropEmptyLongAndControlValues() {
        let long = String(repeating: "a", count: LioRoute.maximumValueLength + 1)
        #expect(LioRoute(tool: .transport, parameters: ["from": long, "to": "  "])?.parameters == [:])
        #expect(LioRoute(tool: .transport, parameters: ["from": "Shang\u{0}hai", "to": "Bei\njing"])?.parameters == [:])
        let longest = String(repeating: "a", count: LioRoute.maximumValueLength)
        #expect(LioRoute(tool: .hotels, parameters: ["city": longest])?["city"] == longest)
    }

    @Test func linksOpenRegisteredToolsOnly() throws {
        let link = try #require(URL(string: "go2china://tool/transport?from=Shanghai&to=%E5%8C%97%E4%BA%AC&from=Xian"))
        let route = try #require(LioRoute(url: link))
        #expect(route.tool == .transport)
        #expect(route.parameters == ["from": "Shanghai", "to": "北京"])
        #expect(route.url.flatMap { LioRoute(url: $0) } == route)

        for text in ["https://tool/transport", "go2china://trip/transport", "go2china://tool/", "go2china://tool/a/b",
                     "go2china://tool/unknown", "go2china://tool/transport#x", "go2china://user@tool/transport",
                     "go2china://tool:8080/transport"] {
            #expect(URL(string: text).flatMap { LioRoute(url: $0) } == nil, "\(text)")
        }
        #expect(URL(string: "GO2CHINA://TOOL/taxi").flatMap { LioRoute(url: $0) }?.tool == .taxi)
    }

    @Test func routerOpensToolsInTheToolsTab() throws {
        let router = LioRouter(tab: .chat, toolsShown: true)
        let route = try #require(LioRoute(tool: .hotels, parameters: ["city": "Chengdu"]))
        #expect(router.open(route))
        #expect(router.tab == .tools)
        #expect(router.toolsPath == [route])
        // A second route replaces the first page rather than stacking on it.
        #expect(router.open(try #require(LioRoute(tool: .taxi))))
        #expect(router.toolsPath.map(\.tool) == [.taxi])
        #expect(router.open(url: try #require(URL(string: "go2china://tool/currency"))))
        #expect(router.toolsPath.map(\.tool) == [.currency])
        #expect(!router.open(url: try #require(URL(string: "go2china://tool/unknown"))))
        #expect(router.toolsPath.map(\.tool) == [.currency])
    }

    @Test func routerOpensNothingWhenTheBuildHidesTools() throws {
        let router = LioRouter(tab: .tools, toolsShown: false)
        #expect(router.tab == .chat)
        #expect(!router.open(try #require(LioRoute(tool: .taxi))))
        #expect(router.tab == .chat && router.toolsPath.isEmpty)
    }

    @Test func initialTabFollowsTheDebugArgumentOnly() {
        #expect(LioTab.initial(arguments: []) == .chat)
        #expect(LioTab.initial(arguments: ["--lio-initial-tab"]) == .chat)
        #expect(LioTab.initial(arguments: ["--lio-initial-tab", "other"]) == .chat)
        #if DEBUG
        #expect(LioTab.initial(arguments: ["--lio-initial-tab", "tools"]) == .tools)
        #expect(LioTab.initial(arguments: ["--lio-initial-tab", "memory"]) == .me)
        #expect(LioTab.initial(arguments: ["--lio-initial-tab", "trips"]) == .trips)
        #endif
    }
}
