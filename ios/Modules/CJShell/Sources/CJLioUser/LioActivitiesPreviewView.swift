#if os(iOS) && DEBUG
import SwiftUI

struct LioActivitiesPreviewView: View {
    let language: LioLanguage
    @State private var city = City.beijing
    @State private var keyword = ""
    @State private var sort = Sort.recommended

    private enum City: CaseIterable, Hashable {
        case beijing, chengdu

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .beijing: language.text("Beijing", "北京")
            case .chengdu: language.text("Chengdu", "成都")
            }
        }
    }

    private enum Sort: CaseIterable, Hashable {
        case recommended, price, rating

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .recommended: language.text("Popular", "热门")
            case .price: language.text("Price", "价格")
            case .rating: language.text("Rating", "评分")
            }
        }
    }

    private struct Activity: Identifiable {
        let id: String
        let name: String
        let chineseName: String
        let city: City
        let price: Int
        let rating: Double
        let meetingPoint: String
    }

    private let activities: [Activity] = [
        .init(id: "wall", name: "Great Wall day trip", chineseName: "长城一日游",
              city: .beijing, price: 199, rating: 4.8, meetingPoint: "示例集合点 · 北京"),
        .init(id: "museum", name: "Museum visit", chineseName: "博物馆参观",
              city: .beijing, price: 60, rating: 4.5, meetingPoint: "示例集合点 · 北京"),
        .init(id: "panda", name: "Panda base visit", chineseName: "熊猫基地参观",
              city: .chengdu, price: 85, rating: 4.9, meetingPoint: "示例集合点 · 成都"),
    ]

    private var matches: [Activity] {
        let query = keyword.trimmingCharacters(in: .whitespacesAndNewlines)
        let found = activities.filter { activity in
            activity.city == city &&
            (query.isEmpty || activity.name.localizedCaseInsensitiveContains(query)
             || activity.chineseName.contains(query))
        }
        switch sort {
        case .recommended: return found
        case .price: return found.sorted { $0.price < $1.price }
        case .rating: return found.sorted { $0.rating > $1.rating }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Menu {
                        ForEach(City.allCases, id: \.self) { option in
                            Button(option.title(language)) { city = option }
                        }
                    } label: {
                        Label(city.title(language), systemImage: "location").frame(minHeight: 44)
                    }
                    Spacer()
                    Menu {
                        ForEach(Sort.allCases, id: \.self) { option in
                            Button(option.title(language)) { sort = option }
                        }
                    } label: {
                        Label(sort.title(language), systemImage: "arrow.up.arrow.down").frame(minHeight: 44)
                    }
                }
                TextField(language.text("Search activities", "搜索玩乐"), text: $keyword)
                    .padding(.horizontal, 10)
                    .frame(minHeight: 44)
                    .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                if matches.isEmpty {
                    Text(language.text("No activities match your search.", "未找到符合条件的玩乐。"))
                }
                ForEach(matches) { activity in
                    NavigationLink {
                        detail(activity)
                    } label: {
                        card(activity)
                    }
                    .buttonStyle(.plain)
                }
                Text(language.text("Sample activities and prices", "示例活动及价格")).font(.footnote)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .scrollDismissesKeyboard(.interactively)
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Activities", "玩乐"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func card(_ activity: Activity) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(language.text(activity.name, activity.chineseName)).font(.headline)
            Text("¥\(activity.price) · " + activity.rating.formatted(.number.precision(.fractionLength(1))))
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func detail(_ activity: Activity) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                card(activity)
                Text(language.text("What’s included", "活动包含")).font(.headline)
                Text(language.text("Sample admission and meeting instructions", "示例门票和集合说明"))
                Text(language.text("Meeting point", "集合地点")).font(.headline)
                Text(activity.meetingPoint)
                Text(language.text("Availability and cancellation", "可订日期及取消政策")).font(.headline)
                Text(language.text("Check the official booking page for the current terms.", "实时条款请查看官方预订页。"))
                Text(language.text("Booking links are unavailable for sample activities.", "示例活动暂无预订链接。"))
                Text(language.text("Booking and payment happen on Klook.", "预订和付款在 Klook 完成。"))
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Activity details", "活动详情"))
        .navigationBarTitleDisplayMode(.inline)
    }
}
#Preview {
    NavigationStack {
        LioActivitiesPreviewView(language: .english)
    }
}
#endif
