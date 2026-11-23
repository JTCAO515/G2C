#if os(iOS) && DEBUG
import SwiftUI

struct LioFlightsPreviewView: View {
    let language: LioLanguage
    @State private var mode = Mode.number
    @State private var number = ""
    @State private var departure = ""
    @State private var arrival = ""
    @State private var date = Date()
    @State private var searched = false
    @State private var matches: [Flight] = []
    @AppStorage("lio.preview.flights.saved") private var watching = false

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
                Picker(language.text("Find flights by", "查询方式"), selection: $mode) {
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
                Button(language.text("Find flights", "查询航班")) { search() }
                    .buttonStyle(.plain)
                    .frame(minHeight: 44)
                if searched, matches.isEmpty {
                    Text(language.text("No flights found. Check the number or route.", "未找到航班，请核对航班号或起降城市。"))
                }
                ForEach(matches) { flight in card(flight) }
                if watching {
                    Text(language.text("My flights", "我的航班")).font(.headline)
                    card(flight)
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
    }

    private func field(_ title: String, text: Binding<String>) -> some View {
        TextField(title, text: text)
            .textInputAutocapitalization(.characters)
            .autocorrectionDisabled()
            .padding(.horizontal, 8)
            .frame(minHeight: 44)
            .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: 10))
    }

    private func search() {
        func normalized(_ text: String) -> String {
            text.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        }
        let found = mode == .number
            ? normalized(number) == flight.id
            : normalized(departure) == flight.departure && normalized(arrival) == flight.arrival
        matches = found ? [flight] : []
        searched = true
    }

    private func card(_ flight: Flight) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("\(flight.id) · \(flight.departure) → \(flight.arrival)").font(.headline)
            Text(language.text("Capital Airport / John F. Kennedy Airport", "首都机场 / 约翰·肯尼迪机场"))
            Text(language.text("Scheduled 19:10 · New departure 19:40", "计划 19:10 · 调整后 19:40"))
            Text(language.text("Terminal", "航站楼") + " \(flight.terminal) · " +
                 language.text("Gate", "登机口") + " \(flight.gate) · " +
                 language.text("Baggage", "行李转盘") + " \(flight.belt)")
            Button(watching ? language.text("Stop following", "取消关注") : language.text("Follow flight", "关注航班")) {
                watching.toggle()
            }
            .buttonStyle(.plain)
            .frame(minHeight: 44)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}
#endif
