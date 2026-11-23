#if os(iOS) && DEBUG
import SwiftUI

struct LioNearbyPreviewView: View {
    let language: LioLanguage
    @State private var query = ""
    @State private var center: String?
    @State private var radius = 500
    @State private var nearest = false
    @State private var categories = Set(LioNearbyPlace.Category.allCases)
    @State private var locationUnavailable = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Button(language.text("Use my location", "使用当前位置")) { locationUnavailable = true }
                    .frame(minHeight: 44)
                    .buttonStyle(.plain)
                if locationUnavailable {
                    Text(language.text("Location is unavailable. Enter a place to continue.", "无法取得位置，请输入地点。"))
                }
                HStack {
                    TextField(language.text("Enter a place", "输入地点"), text: $query)
                        .textFieldStyle(.roundedBorder)
                        .frame(minHeight: 44)
                    Button(language.text("Search", "搜索")) {
                        center = query.trimmingCharacters(in: .whitespacesAndNewlines)
                        locationUnavailable = false
                    }
                    .buttonStyle(.plain)
                    .frame(minHeight: 44)
                    .disabled(query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                if let center {
                    Text(language.text("Nearby", "附近") + " · " + center).font(.headline)
                    filters
                    results
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Nearby", "附近"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private var filters: some View {
        HStack(spacing: 10) {
            Menu(language.text("Categories", "分类")) {
                ForEach(LioNearbyPlace.Category.allCases, id: \.self) { category in
                    Toggle(category.title(language), isOn: Binding(
                        get: { categories.contains(category) },
                        set: { selected in
                            if selected { categories.insert(category) } else { categories.remove(category) }
                        }
                    ))
                }
            }
            .frame(minHeight: 44)
            Menu(radius == 500 ? "500 m" : "\(radius / 1000) km") {
                ForEach([500, 1000, 3000], id: \.self) { distance in
                    Button(distance == 500 ? "500 m" : "\(distance / 1000) km") { radius = distance }
                }
            }
            .frame(minHeight: 44)
            Menu(nearest ? language.text("Nearest", "距离优先") : language.text("Recommended", "综合")) {
                Button(language.text("Nearest", "距离优先")) { nearest = true }
                Button(language.text("Recommended", "综合")) { nearest = false }
            }
            .frame(minHeight: 44)
        }
    }

    private var results: some View {
        let places = LioNearbyPlace.filter(LioNearbyPlace.fixture, categories: categories, radius: radius, nearest: nearest)
        return VStack(alignment: .leading, spacing: 10) {
            if places.isEmpty {
                Text(language.text("No places in this area.", "该范围内没有地点。"))
            }
            ForEach(places) { place in
                NavigationLink {
                    LioNearbyPlacePreview(language: language, place: place)
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(place.name).font(.headline)
                        if let name = place.englishName { Text(name) }
                        Text(place.category.title(language) + " · \(place.meters) m").font(.subheadline)
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .padding(10)
                    .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                }
                .buttonStyle(.plain)
            }
            Text(language.text("Sample places", "示例地点")).font(.footnote)
        }
    }
}

private struct LioNearbyPlacePreview: View {
    let language: LioLanguage
    let place: LioNearbyPlace
    @State private var operation: LioNearbyPlace.Operation?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text(place.name).font(.title.bold())
                Text(place.address)
                if let rating = place.rating {
                    Label(rating, systemImage: "star")
                }
                if let cost = place.cost {
                    Text(language.text("Per person", "人均") + " · " + cost)
                }
                if let isOpen = place.isOpen {
                    Text(isOpen ? language.text("Open", "营业中") : language.text("Closed", "已打烊"))
                }
                ForEach(LioNearbyPlace.Operation.allCases, id: \.self) { item in
                    Button(item.title(language)) { operation = item }
                        .buttonStyle(.plain)
                        .frame(minHeight: 44)
                }
                if let operation {
                    Text(operation == .showAddress
                         ? place.name + "\n" + place.address
                         : language.text("This action is unavailable with sample places.", "示例地点暂不支持此操作。"))
                        .font(operation == .showAddress ? .title : .body)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Place details", "地点详情"))
        .navigationBarTitleDisplayMode(.inline)
    }
}
#endif
