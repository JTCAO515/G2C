import CJMessageHTTP
import Foundation
import Testing

struct LioPublicDisplayTests {
    @Test(arguments: [
        "北京预报：https://restapi.amap.com/v3/weather/weatherInfo",
        "Please verify the request ID with the backend.",
        "This RUN is still UNKNOWN.",
        "消息投递还在等待原回执。",
        "已生成规划候选，请等待。",
        "message_id: 20be0897-2fe5-4136-bf73-5966edb64a3a",
        "Conversation 20be0897-2fe5-4136-bf73-5966edb64a3a",
        "运行20be0897-2fe5-4136-bf73-5966edb64a3a已完成。",
        "会话20be0897-2fe5-4136-bf73-5966edb64a3a已完成。",
        "The input_sha256 is synthetic.",
        "<tool_call>amap_weather</tool_call>",
        "Calling Amap now.",
        "工具调用：高德天气"
    ])
    func withholdsTechnicalReplies(_ text: String) {
        #expect(!LioPublicDisplay.permitsText(text))
    }

    @Test(arguments: [
        "https://api-beta.go2china.space./v1/lio/timeline",
        "https://API.GO2CHINA.SPACE%2E/",
        "https://restapi.amap.com./",
        "https://api-beta.go2china.space%E3%80%82/",
        "https://api-beta.go2china.space%EF%BC%8E/",
        "https://api-beta.go2china%E3%80%82space/",
        "https://%EF%BD%81pi-beta.go2china.space/",
        "https://ap%C2%ADi.go2china.space/"
    ])
    func withholdsRootQualifiedServiceAddresses(_ address: String) throws {
        let url = try #require(URL(string: address))
        #expect(!LioPublicDisplay.permitsText("Forecast: \(address)"))
        #expect(!LioPublicDisplay.permitsSource(url))
    }

    @Test(arguments: [
        "See https://a'bc@api-beta.go2china.space/",
        "See https://a(b)@api.go2china.space",
        "See \"https://api-beta.go2china.space\".",
        "See (https://%61pi-beta.go2china.space).Forecast",
        "See (https://ap%C2%ADi.go2china.space).Forecast",
        "请看（https://%61pi-beta.go2china.space）天气",
        "https://weather.com.cn)[Forecast](https://%EF%BD%81pi-beta.go2china.space%E3%80%82/)"
    ])
    func findsServiceHostsInsideTextPunctuation(_ text: String) {
        #expect(!LioPublicDisplay.permitsText(text))
    }

    @Test(arguments: [
        "地铁以原运行时刻作参考，出发前再查看站内公告。想去哪个站？",
        "Here '原运行时刻' means the published operating times. Which line do you need?",
        "我们仍在同一个会话上下文里，可以继续看第二天。想先看上午还是下午？",
        "我查询了北京明天的预报。你可以核实来源。",
        "Here are two hotel candidates. Check the version number on your ticket.",
        "请保留酒店回执，出发前核实候选餐厅的营业时间。"
    ])
    func preservesOrdinaryTravelWords(_ text: String) {
        #expect(LioPublicDisplay.permitsText(text))
    }

    @Test func preservesTravelScopeWithoutExposingAServiceScopeField() {
        #expect(LioPublicDisplay.permitsText("Double-check the scope of the visa-free transit policy with your airline."))
        #expect(!LioPublicDisplay.permitsText(#"{"scope":"internal-travel-owner"}"#))
        #expect(!LioPublicDisplay.permitsText("scope: internal-travel-owner"))
    }

    @Test func preservesTravelLanguageAndPublicAttribution() throws {
        #expect(LioPublicDisplay.permitsText("草原夜间偏凉。"))
        #expect(LioPublicDisplay.permitsText("Trains run frequently. Your itinerary needs a little more time."))
        #expect(LioPublicDisplay.permitsText("Keep your hotel receipt."))
        #expect(LioPublicDisplay.permitsText("暂时没有可用的天气预报。"))
        #expect(LioPublicDisplay.permitsSource(try #require(URL(string: "https://weather.com.cn/"))))
        #expect(LioPublicDisplay.permitsSource(try #require(URL(string: "https://weather.com.cn./"))))
        #expect(LioPublicDisplay.permitsSource(try #require(URL(string: "https://ma%C3%B1ana.example/"))))
        #expect(LioPublicDisplay.permitsText("Open https://ma%C3%B1ana.example/ for more."))
        #expect(LioPublicDisplay.permitsText("请看（https://ma%C3%B1ana.example）天气"))
        #expect(!LioPublicDisplay.permitsSource(try #require(URL(string: "https://restapi.amap.com/v3/weather/weatherInfo"))))
        #expect(!LioPublicDisplay.permitsSource(try #require(URL(string: "https://api-beta.go2china.space/v1/lio/timeline"))))
    }
}
