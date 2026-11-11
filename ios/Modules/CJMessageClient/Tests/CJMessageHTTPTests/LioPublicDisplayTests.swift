import CJMessageHTTP
import Foundation
import Testing

struct LioPublicDisplayTests {
    @Test(arguments: [
        "我查询了北京明天的预报。你可以核实来源。",
        "北京预报：https://restapi.amap.com/v3/weather/weatherInfo",
        "Please verify the request ID with the backend.",
        "This RUN is still UNKNOWN."
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
