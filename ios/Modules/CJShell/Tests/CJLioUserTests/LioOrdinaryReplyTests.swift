import Foundation
import Testing
@testable import CJLioUser

struct LioOrdinaryReplyTests {
    @Test(arguments: [
        "地铁以原运行时刻作参考，出发前再查看站内公告。想去哪个站？",
        "Here '原运行时刻' means the published operating times. Which line do you need?",
        "我们仍在同一个会话上下文里，可以继续看第二天。想先看上午还是下午？",
        "我查询了北京明天的预报。你可以核实来源。"
    ])
    func ordinaryReplyUsesTheActualChatRendererWithoutChangingWords(_ source: String) throws {
        let rendered = try #require(LioReplyMarkdown.render(source))
        #expect(String(rendered.characters) == source)
    }

    @Test(arguments: [
        "message_id: 20be0897-2fe5-4136-bf73-5966edb64a3a",
        "<tool_call>amap_weather</tool_call>",
        "Forecast: https://%61pi-beta.go2china.space/v1/lio/timeline"
    ])
    func rendererStillWithholdsInternalDetails(_ source: String) {
        #expect(LioReplyMarkdown.render(source) == nil)
    }
}
