import Testing
@testable import CJShell

@Suite struct PluginPlaceholderTests {
    @Test func approvedBilingualCopyIsStaticAndComplete() {
        #expect(PluginPlaceholderCopy.title(.english) == "DiDi Ride-hailing")
        #expect(PluginPlaceholderCopy.title(.chinese) == "滴滴打车")
        #expect(PluginPlaceholderCopy.status(.english) == "Coming soon")
        #expect(PluginPlaceholderCopy.status(.chinese) == "即将推出")
        #expect(PluginPlaceholderCopy.detail(.english) == "Request rides in China from your trip. Not connected yet.")
        #expect(PluginPlaceholderCopy.detail(.chinese) == "未来可在行程中直接叫车。目前尚未接入。")
        #expect(PluginPlaceholderCopy.footer(.english) == "More plugins are planned. No tools are connected.")
        #expect(PluginPlaceholderCopy.footer(.chinese) == "更多插件将在后续版本提供。目前未接入任何工具。")
        #expect(PluginPlaceholderCopy.accessibilityLabel(.english) == "DiDi Ride-hailing, Coming soon, Request rides in China from your trip. Not connected yet.")
        #expect(PluginPlaceholderCopy.accessibilityLabel(.chinese) == "滴滴打车，即将推出，未来可在行程中直接叫车。目前尚未接入。")
    }
}
