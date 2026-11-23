#if os(iOS)
import SwiftUI

struct LioCurrencyView: View {
    let language: LioLanguage
    let load: @MainActor () async throws -> LioCurrencyRates
    @Environment(\.locale) private var locale
    @State private var snapshot: LioCurrencyRates?
    @State private var amount = "100"
    @State private var origin: LioCurrencyRates.Currency = .cny
    @State private var destination: LioCurrencyRates.Currency = .usd
    @State private var refresh = 0
    @State private var isLoading = true
    @State private var loadFailed = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let snapshot {
                    converter(snapshot)
                    Text(language.text("Rate source", "汇率来源") + " · " + snapshot.source + " · " + snapshot.date)
                        .font(.footnote)
                        .accessibilityIdentifier("lio.currency.source")
                }

                if isLoading {
                    ProgressView(language.text("Getting exchange rates…", "正在获取汇率…"))
                } else if loadFailed {
                    Text(snapshot == nil
                         ? language.text("Exchange rates are unavailable.", "暂时无法获取汇率。")
                         : language.text("Couldn't refresh. Showing the last available rates.", "暂时无法更新，显示上次获取的汇率。"))
                        .accessibilityIdentifier("lio.currency.error")
                }

                if !isLoading {
                    Button { refresh += 1 } label: {
                        Label(language.text("Refresh rates", "更新汇率"), systemImage: "arrow.clockwise")
                            .frame(minHeight: 44)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.currency.refresh")
                }
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .scrollDismissesKeyboard(.interactively)
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Currency Converter", "汇率换算"))
        .navigationBarTitleDisplayMode(.inline)
        .task(id: refresh) {
            isLoading = true
            defer { if !Task.isCancelled { isLoading = false } }
            do {
                let rates = try await load()
                try Task.checkCancellation()
                snapshot = rates
                if !rates.currencies.contains(origin) { origin = .cny }
                if !rates.currencies.contains(destination) { destination = .eur }
                loadFailed = false
            } catch {
                guard !Task.isCancelled else { return }
                loadFailed = true
            }
        }
    }

    private func converter(_ rates: LioCurrencyRates) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(language.text("Amount", "金额"))
                .font(.headline)
            TextField(language.text("Amount", "金额"), text: $amount)
                .keyboardType(.decimalPad)
                .accessibilityIdentifier("lio.currency.amount")
            HStack {
                currencyMenu(language.text("From", "从"), selection: $origin, options: rates.currencies)
                Button {
                    let previous = origin
                    origin = destination
                    destination = previous
                } label: {
                    Image(systemName: "arrow.left.arrow.right")
                        .frame(width: 50, height: 50)
                        .contentShape(Rectangle())
                        .background(LioTheme.surfaceSunken, in: Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(language.text("Swap currencies", "互换货币"))
                .accessibilityIdentifier("lio.currency.swap")
                currencyMenu(language.text("To", "到"), selection: $destination, options: rates.currencies)
            }
            if let number = try? Decimal(amount, format: .number.locale(locale)),
               let converted = rates.convert(number, from: origin, to: destination) {
                Text(converted.formatted(.number.precision(.fractionLength(destination.fractionDigits))) + " " + destination.rawValue)
                    .font(.title2.bold())
                    .accessibilityIdentifier("lio.currency.result")
            } else {
                Text(language.text("Enter a valid amount.", "请输入有效金额。"))
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func currencyMenu(_ label: String, selection: Binding<LioCurrencyRates.Currency>,
                              options: [LioCurrencyRates.Currency]) -> some View {
        Menu {
            ForEach(options, id: \.self) { currency in
                Button(currency.rawValue) { selection.wrappedValue = currency }
            }
        } label: {
            Label(selection.wrappedValue.rawValue, systemImage: "chevron.down")
                .foregroundStyle(LioTheme.ink)
                .frame(minHeight: 44)
        }
        .accessibilityLabel(label + " " + selection.wrappedValue.rawValue)
    }
}
#if DEBUG
#Preview {
    NavigationStack {
        LioCurrencyView(language: .english, load: LioCurrencyRates.fixture)
    }
}
#endif
#endif
