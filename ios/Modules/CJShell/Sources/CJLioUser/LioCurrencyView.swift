#if os(iOS)
import CJRunClient
import SwiftUI

struct LioCurrencyView: View {
    let language: LioLanguage
    let load: @MainActor () async throws -> LioCurrencyRates
    @Environment(\.locale) private var locale
    @Environment(\.colorScheme) private var colorScheme
    @State private var snapshot: LioCurrencyRates?
    @State private var entry = LioCurrencyEntry()
    @FocusState private var focus: LioCurrencyField?
    @State private var origin: LioCurrencyRates.Currency = .cny
    @State private var destination: LioCurrencyRates.Currency = .usd
    @State private var refresh = 0
    @State private var isLoading = true
    @State private var loadProblem: LioCurrencyRelayFailure?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let snapshot {
                    converter(snapshot)
                    Text(language.text("Rate source", "汇率来源") + " · " + snapshot.source + " · " + snapshot.date)
                        .font(.footnote)
                        .foregroundStyle(LioTheme.inkSecondary)
                        .accessibilityIdentifier("lio.currency.source")
                    Text(language.text("For reference. Your bank or payment provider sets the actual rate.",
                                       "仅供参考，以银行或支付机构的实际汇率为准。"))
                        .font(.footnote)
                        .foregroundStyle(LioTheme.inkSecondary)
                        .accessibilityIdentifier("lio.currency.disclaimer")
                }

                if isLoading {
                    ProgressView(language.text("Getting exchange rates…", "正在获取汇率…"))
                } else if let loadProblem {
                    Text(message(loadProblem))
                        .accessibilityIdentifier("lio.currency.error")
                    if snapshot != nil {
                        Text(language.text("Showing the last available rates.", "正在显示上次获取的汇率。"))
                    }
                }

                if !isLoading {
                    Button { refresh += 1 } label: {
                        Label(language.text("Refresh rates", "更新汇率"), systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(LioSecondaryButtonStyle())
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
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .principal) {
                RunReadableText(text: language.text("Currency Converter", "汇率换算"), style: .headline, color: LioTheme.ink)
                    .fixedSize()
                    .accessibilityAddTraits(.isHeader)
            }
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button(language.text("Done", "完成")) { focus = nil }
                    .accessibilityIdentifier("lio.currency.keyboardDone")
            }
        }
        .task(id: refresh) {
            isLoading = true
            defer { if !Task.isCancelled { isLoading = false } }
            do {
                let rates = try await load()
                try Task.checkCancellation()
                snapshot = rates
                if !rates.currencies.contains(origin) { origin = .cny }
                if !rates.currencies.contains(destination) { destination = .eur }
                loadProblem = nil
            } catch is CancellationError {
                return
            } catch {
                guard !Task.isCancelled else { return }
                loadProblem = error as? LioCurrencyRelayFailure ?? .unavailable
            }
        }
    }

    private func message(_ failure: LioCurrencyRelayFailure) -> String {
        switch failure {
        case .signInRequired:
            language.text("Sign in again to get exchange rates.", "请重新登录后获取汇率。")
        case .unavailableForAccount:
            language.text("Exchange rates aren’t available for this account.", "此账号暂时无法使用汇率换算。")
        case .offline:
            language.text("Connect to the internet to get exchange rates.", "请联网后获取汇率。")
        case .timedOut:
            language.text("Getting exchange rates took too long. Try again.", "汇率获取超时，请重试。")
        case .unavailable:
            language.text("Exchange rates are unavailable. Try again.", "暂时无法获取汇率，请重试。")
        }
    }

    private func converter(_ rates: LioCurrencyRates) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            ZStack {
                VStack(spacing: 0) {
                    amountRow(.origin, rates: rates)
                    Divider().overlay(LioTheme.hairline)
                    amountRow(.destination, rates: rates)
                }
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                swapButton
            }
            quickAmountRow
            if let line = rateLine(rates) {
                Text(line)
                    .font(.subheadline)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.currency.unitRate")
            }
            if invalidEntry(rates) {
                Text(language.text("Enter a valid amount.", "请输入有效金额。"))
                    .font(.subheadline)
                    .foregroundStyle(LioTheme.vermilion)
                    .accessibilityIdentifier("lio.currency.invalid")
            }
        }
    }

    private var swapButton: some View {
        Button {
            // Exchange the rows: each amount stays with its currency.
            let previous = origin
            origin = destination
            destination = previous
            entry.active = entry.active == .origin ? .destination : .origin
        } label: {
            Image(systemName: "arrow.up.arrow.down")
                .font(.body.weight(.bold))
                .foregroundStyle(LioTheme.onVermilion)
                .frame(width: 44, height: 44)
                .background(LioTheme.vermilion, in: Circle())
                .overlay(Circle().stroke(LioTheme.paper, lineWidth: 4))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(language.text("Swap currencies", "互换货币"))
        .accessibilityIdentifier("lio.currency.swap")
    }

    private func amountRow(_ field: LioCurrencyField, rates: LioCurrencyRates) -> some View {
        let currency = field == .origin ? origin : destination
        return HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                currencyMenu(field == .origin ? language.text("From", "从") : language.text("To", "到"),
                             selection: field == .origin ? $origin : $destination,
                             options: rates.currencies)
                Text(currency.name(language))
                    .font(.caption)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .lineLimit(1)
            }
            TextField("0", text: binding(for: field, rates: rates))
                .keyboardType(.decimalPad)
                .focused($focus, equals: field)
                .multilineTextAlignment(.trailing)
                .font(.system(.largeTitle, design: .rounded).weight(.semibold))
                .monospacedDigit()
                .minimumScaleFactor(0.5)
                .foregroundStyle(entry.active == field ? LioTheme.ink : LioTheme.ink.opacity(0.85))
                .frame(maxWidth: .infinity, alignment: .trailing)
                .accessibilityLabel(language.text("Amount in", "金额，币种") + " " + currency.rawValue)
                .accessibilityIdentifier(field == .origin ? "lio.currency.amount" : "lio.currency.result")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 18)
        .contentShape(Rectangle())
        .onTapGesture { focus = field }
    }

    /// The typed field shows what was typed; the other shows the converted amount.
    private func binding(for field: LioCurrencyField, rates: LioCurrencyRates) -> Binding<String> {
        Binding(
            get: {
                if entry.active == field { return entry.text }
                return entry.derivedText(rates: rates, origin: origin, destination: destination, locale: locale) ?? ""
            },
            set: { newValue in
                entry.active = field
                entry.text = newValue
            }
        )
    }

    private func invalidEntry(_ rates: LioCurrencyRates) -> Bool {
        !entry.text.isEmpty
            && entry.derivedText(rates: rates, origin: origin, destination: destination, locale: locale) == nil
    }

    private var quickAmountRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(origin.quickAmounts, id: \.self) { amount in
                    Button {
                        entry.active = .origin
                        entry.text = LioCurrencyEntry.text(for: amount, locale: locale)
                        focus = nil
                    } label: {
                        Text(amount.formatted(.number.locale(locale)))
                            .font(.subheadline.weight(.semibold))
                            .monospacedDigit()
                            .foregroundStyle(LioTheme.ink)
                            .padding(.horizontal, 16)
                            .frame(minHeight: 44)
                            .lioCard(Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(amount.formatted(.number.locale(locale)) + " " + origin.rawValue)
                    .accessibilityIdentifier("lio.currency.quick.\(amount)")
                }
            }
        }
        .accessibilityIdentifier("lio.currency.quickAmounts")
    }

    private func rateLine(_ rates: LioCurrencyRates) -> String? {
        guard let rate = rates.unitRate(from: origin, to: destination) else { return nil }
        let formatted = rate.formatted(.number.precision(.significantDigits(4)).locale(locale))
        return "1 \(origin.rawValue) ≈ \(formatted) \(destination.rawValue)"
    }

    private func currencyMenu(_ label: String, selection: Binding<LioCurrencyRates.Currency>,
                              options: [LioCurrencyRates.Currency]) -> some View {
        Menu {
            ForEach(options, id: \.self) { currency in
                Button {
                    selection.wrappedValue = currency
                } label: {
                    Text("\(currency.flag) \(currency.rawValue) · \(currency.name(language))")
                }
            }
        } label: {
            HStack(spacing: 6) {
                Text(selection.wrappedValue.flag).font(.title2)
                Text(selection.wrappedValue.rawValue)
                    .font(.headline)
                    .foregroundStyle(LioTheme.ink)
                Image(systemName: "chevron.down")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(LioTheme.inkSecondary)
            }
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
