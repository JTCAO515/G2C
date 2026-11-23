#if os(iOS)
import SwiftUI

struct LioPaymentGuideView: View {
    let language: LioLanguage

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                ForEach(LioPaymentGuideProvider.allCases) { provider in
                    NavigationLink {
                        LioPaymentProviderGuideView(provider: provider, language: language)
                    } label: {
                        Label(provider.title(in: language), systemImage: "wallet.pass")
                            .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
                            .padding(.horizontal, 16)
                            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                            .foregroundStyle(LioTheme.ink)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.payment.provider." + provider.rawValue)
                }
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Payment Setup Guide", "支付开通指南"))
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct LioPaymentProviderGuideView: View {
    let provider: LioPaymentGuideProvider
    let language: LioLanguage

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(provider.steps(in: language)) { step in
                    card(step)
                }

                NavigationLink {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(LioPaymentGuideProvider.problems(in: language)) { problem in
                                card(problem)
                            }
                        }
                        .foregroundStyle(LioTheme.ink)
                        .padding(18)
                    }
                    .background(LioTheme.paper)
                    .navigationTitle(language.text("Common problems", "常见失败原因"))
                    .navigationBarTitleDisplayMode(.inline)
                } label: {
                    Label(language.text("Common problems", "常见失败原因"), systemImage: "questionmark.circle")
                        .foregroundStyle(LioTheme.ink)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.payment.problems")

                Link(destination: provider.officialInstructions) {
                    Label(language.text("Official setup guide", "官方开通指南"), systemImage: "arrow.up.right")
                        .foregroundStyle(LioTheme.ink)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.payment.official")
            }
            .foregroundStyle(LioTheme.ink)
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(provider.title(in: language))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func card(_ step: LioPaymentGuideStep) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(step.title, systemImage: step.icon)
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
            Text(step.detail)
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.payment.step." + step.id)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}
#endif
