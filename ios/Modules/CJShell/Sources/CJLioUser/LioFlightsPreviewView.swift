#if os(iOS) && DEBUG
import SwiftUI

struct LioFlightsPreviewView: View {
    let language: LioLanguage
    @State private var mode = Mode.number
    @State private var number = ""
    @State private var departure = ""
    @State private var arrival = ""
    @State private var date = Date()
    @State private var searchedDate = Date()
    @State private var showsAirport = false
    @State private var searched = false
    @State private var matches: [Flight] = []
    @AppStorage("lio.preview.flights.saved-date") private var watchedDate: Double = 0

    private enum Mode: Hashable { case number, route }

    private struct Flight: Identifiable {
        let id: String
        let departure: String
        let arrival: String
        let terminal: String
        let gate: String
        let belt: String
    }

    private let flight = Flight(id: "CA981", departure: "PEK", arrival: "JFK",
                                terminal: "T3", gate: "E19", belt: "8")

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Picker(language.text("Find flights by", "查找方式"), selection: $mode) {
                    Text(language.text("Flight number", "航班号")).tag(Mode.number)
                    Text(language.text("Route", "起降城市")).tag(Mode.route)
                }
                .pickerStyle(.segmented)
                switch mode {
                case .number:
                    field(language.text("Flight number, e.g. CA981", "航班号，例如 CA981"), text: $number)
                case .route:
                    field(language.text("Departure, e.g. PEK", "出发地，例如 PEK"), text: $departure)
                    field(language.text("Arrival, e.g. JFK", "到达地，例如 JFK"), text: $arrival)
                }
                DatePicker(language.text("Flight date", "航班日期"), selection: $date, displayedComponents: [.date])
                Button(language.text("Find flights", "查航班")) { search() }
                    .buttonStyle(.plain)
                    .frame(minHeight: 44)
                if searched, matches.isEmpty {
                    Text(language.text("No flights found. Check the number or route.", "未找到航班，请核对航班号或起降城市。"))
                }
                ForEach(matches) { flight in card(flight, date: searchedDate) }
                if watchedDate != 0 {
                    Text(language.text("My flights", "我的航班")).font(.headline)
                    card(flight, date: Date(timeIntervalSince1970: watchedDate))
                }
                Text(language.text("Sample flight data", "示例航班数据")).font(.footnote)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .scrollDismissesKeyboard(.interactively)
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Flights", "航班"))
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showsAirport) {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(language.text("Beijing Capital Airport · T3", "北京首都机场 · T3")).font(.headline)
                        Text(language.text("Before leaving the airport, follow signs to ground transport. Check the airport’s latest information for your terminal.",
                                           "离开机场前请看地面交通指引，并按航站楼核对机场的最新信息。"))
                        Text(language.text("Sample airport information", "示例机场信息")).font(.footnote)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(18)
                }
                .foregroundStyle(LioTheme.ink)
                .background(LioTheme.paper)
                .navigationTitle(language.text("Airport information", "机场信息"))
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button(language.text("Done", "完成")) { showsAirport = false }
                    }
                }
            }
        }
    }

    private func field(_ title: String, text: Binding<String>) -> some View {
        TextField(title, text: text)
            .textInputAutocapitalization(.characters)
            .autocorrectionDisabled()
            .padding(.horizontal, 8)
            .frame(minHeight: 44)
            .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
    }

    private func search() {
        func normalized(_ text: String) -> String {
            text.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        }
        let found = mode == .number
            ? normalized(number) == flight.id
            : normalized(departure) == flight.departure && normalized(arrival) == flight.arrival
        searchedDate = date
        matches = found ? [flight] : []
        searched = true
    }

    private func card(_ flight: Flight, date: Date) -> some View {
        let watching = watchedDate == date.timeIntervalSince1970
        return VStack(alignment: .leading, spacing: 8) {
            Text("\(flight.id) · \(flight.departure) → \(flight.arrival)").font(.headline)
            Text(language.text("Capital Airport / John F. Kennedy Airport", "首都机场 / 约翰·肯尼迪机场"))
            Text(date.formatted(date: .abbreviated, time: .omitted)).font(.subheadline)
            Text(language.text("Scheduled 19:10 · New departure 19:40", "计划 19:10 · 调整后 19:40"))
            Text(language.text("Terminal", "航站楼") + " \(flight.terminal) · " +
                 language.text("Gate", "登机口") + " \(flight.gate) · " +
                 language.text("Baggage", "行李转盘") + " \(flight.belt)")
            Button(watching ? language.text("Stop following", "取消关注") : language.text("Follow flight", "关注航班")) {
                watchedDate = watching ? 0 : date.timeIntervalSince1970
            }
            .buttonStyle(.plain)
            .frame(minHeight: 44)
            Button(language.text("Airport information", "机场信息")) { showsAirport = true }
                .buttonStyle(.plain)
                .frame(minHeight: 44)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}
#Preview {
    NavigationStack {
        LioFlightsPreviewView(language: .english)
    }
}
#endif
