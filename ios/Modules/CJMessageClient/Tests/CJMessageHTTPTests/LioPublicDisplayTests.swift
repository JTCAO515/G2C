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

    @Test func preservesTravelLanguageAndPublicAttribution() throws {
        #expect(LioPublicDisplay.permitsText("草原夜间偏凉。"))
        #expect(LioPublicDisplay.permitsText("Trains run frequently. Your itinerary needs a little more time."))
        #expect(LioPublicDisplay.permitsText("Keep your hotel receipt."))
        #expect(LioPublicDisplay.permitsText("暂时没有可用的天气预报。"))
        #expect(LioPublicDisplay.permitsSource(try #require(URL(string: "https://weather.com.cn/"))))
        #expect(!LioPublicDisplay.permitsSource(try #require(URL(string: "https://restapi.amap.com/v3/weather/weatherInfo"))))
        #expect(!LioPublicDisplay.permitsSource(try #require(URL(string: "https://api-beta.go2china.space/v1/lio/timeline"))))
    }
}
