#if os(iOS) && DEBUG
import SwiftUI

struct LioWeatherPreviewView: View {
    let language: LioLanguage
    @State private var city = City.beijing
    @State private var locationUnavailable = false
    @State private var showHourly = false

    private enum City: CaseIterable {
        case beijing, chengdu, shanghai

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .beijing: language.text("Beijing", "北京")
            case .chengdu: language.text("Chengdu", "成都")
            case .shanghai: language.text("Shanghai", "上海")
            }
        }

        var conditions: (current: Int, low: Int, high: Int) {
            switch self {
            case .beijing: (8, 3, 11)
            case .chengdu: (16, 13, 20)
            case .shanghai: (13, 9, 17)
            }
        }

        var rain: Int { self == .chengdu ? 70 : 20 }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Menu {
                        ForEach(City.allCases, id: \.self) { option in
                            Button(option.title(language)) {
                                city = option
                                locationUnavailable = false
                            }
                        }
                    } label: {
                        Label(city.title(language), systemImage: "chevron.down")
                            .frame(minWidth: 44, minHeight: 44)
                    }
                    .accessibilityIdentifier("lio.weather.city")
                    Spacer()
                    Button(language.text("Use my location", "使用当前位置")) { locationUnavailable = true }
                        .buttonStyle(.plain)
                        .frame(minHeight: 44)
                }
                if locationUnavailable {
                    Text(language.text("Location is unavailable. Choose a city instead.", "无法取得位置，请选择城市。"))
                }
                current
                forecast
                advice
                Text(language.text("Sample forecast", "示例天气"))
                    .font(.footnote)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Weather", "天气"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private var current: some View {
        tile(language.text("Now", "当前")) {
            Label("\(city.conditions.current) °C", systemImage: city.rain > 50 ? "cloud.rain" : "cloud.sun")
                .font(.title2.bold())
                .accessibilityIdentifier("lio.weather.current")
            Text(language.text("Low", "最低") + " \(city.conditions.low) °C · " +
                 language.text("High", "最高") + " \(city.conditions.high) °C")
            Text(language.text("Chance of rain", "降水概率") + " \(city.rain)%")
            Text(language.text("Sample trip: day 1", "示例行程：第 1 天"))
                .font(.subheadline)
        }
    }

    private var forecast: some View {
        VStack(spacing: 14) {
            tile(language.text("Next hours", "逐小时")) {
                ForEach(1...(showHourly ? 24 : 3), id: \.self) { hour in
                    HStack {
                        Text(language.text("In \(hour) hr", "\(hour) 小时后"))
                        Spacer()
                        Text("\(city.conditions.current + hour % 4) °C")
                    }
                }
                Button(showHourly
                       ? language.text("Show fewer hours", "收起逐小时天气")
                       : language.text("Show 24 hours", "查看 24 小时")) {
                    showHourly.toggle()
                }
                .buttonStyle(.plain)
                .frame(minHeight: 44)
            }
            tile(language.text("Seven-day forecast", "未来七天")) {
                ForEach(0..<7, id: \.self) { day in
                    HStack {
                        Text(day == 0 ? language.text("Today", "今天") : language.text("Day \(day + 1)", "第 \(day + 1) 天"))
                        Spacer()
                        Text("\(city.conditions.low + day % 3)–\(city.conditions.high + day % 2) °C")
                    }
                }
            }
        }
    }

    private var advice: some View {
        tile(language.text("Advice and alerts", "生活建议和预警")) {
            if city.rain > 50 {
                Text(language.text("Bring an umbrella.", "建议带伞。"))
                Text(language.text("Sample alert · Heavy rain", "示例预警 · 强降雨"))
            } else {
                Text(language.text("Take a light jacket.", "建议带件薄外套。"))
                Text(language.text("No active alerts in this sample.", "本示例无生效预警。"))
            }
        }
    }

    private func tile<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline).accessibilityAddTraits(.isHeader)
            content()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}
#Preview {
    NavigationStack {
        LioWeatherPreviewView(language: .english)
    }
}
#endif
