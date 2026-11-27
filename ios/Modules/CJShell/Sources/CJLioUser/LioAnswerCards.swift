import CJMessageHTTP
import Foundation

/// Words of the tool cards under an answer (#1993). The card titles are the contract's fixed labels
/// (`LIO-answer-rich.1`, `cards` table; `LioTimelineWire.Card.Kind.labels`). The rest is not in
/// `codex-inbox/G4/ui-copy.json`, so its wording is a placeholder for the copy review (`isPlaceholder`);
/// "not in this version" is `LioAnswerLayoutFeature.unavailableText`, the same words the answer's buttons use.
enum LioAnswerCardCopy: String, CaseIterable, Sendable {
    case referenceRate = "card.currency.reference_rate"
    case asOf = "card.currency.as_of"
    case opensHint = "card.opens.hint"
    case groupLabel = "card.group.accessibility"

    var isPlaceholder: Bool { true }

    private var words: (en: String, zh: String) {
        switch self {
        case .referenceRate: ("Reference rate", "参考汇率")
        case .asOf: ("as of", "截至")
        case .opensHint: ("Opens the tool", "打开对应的工具")
        case .groupLabel: ("Tools for this answer", "这条回答的工具")
        }
    }

    func text(_ language: LioLanguage) -> String { language == .chinese ? words.zh : words.en }
}

/// What one tool card says and where it goes, in one language (#1993). Plain data, so the wording, the route and the
/// "not in this version" case can be tested without a screen; `LioAnswerCards` only lays it out.
///
/// Everything shown comes from the server's card (its type, its display data and its parameters); the model's text
/// is never read. A tap opens the type's own tool through `LioRoute`, which keeps only the parameters the tool's
/// registry entry declares and refuses a tool that is not registered.
struct LioAnswerCardPresentation: Equatable, Identifiable {
    let card: LioTimelineWire.Card
    let language: LioLanguage

    var id: LioTimelineWire.Card.Kind { card.kind }

    var title: String { language.text(card.kind.labels.en, card.kind.labels.zh) }

    var symbol: String {
        switch card.kind {
        case .taxi: "car.fill"
        case .metro: "tram.fill"
        case .transport: "train.side.front.car"
        case .currency: "yensign.circle"
        }
    }

    /// The line under the title: the destination, the city, the two cities or the reference rate; nil when the card
    /// has nothing to add.
    var detail: String? {
        switch card.detail {
        case .none:
            guard card.kind == .taxi else { return nil }
            let zh = card.parameters["destination"], en = card.parameters["destinationEN"]
            return language == .english ? en ?? zh : zh
        case .metro(let city):
            return name(city)
        case .transport(let from, let to):
            return name(from) + " → " + name(to)
        case .currency(let quote, let rate, let day):
            guard let rate else { return nil }
            var parts = ["1 \(quote) ≈ ¥\(rate)", LioAnswerCardCopy.referenceRate.text(language)]
            if let day { parts[1] += language == .english ? ", \(LioAnswerCardCopy.asOf.text(language)) \(day)" : "，\(LioAnswerCardCopy.asOf.text(language))\(day)" }
            return parts.joined(separator: " · ")
        }
    }

    private func name(_ city: LioTimelineWire.CardCity) -> String { language == .english ? city.en : city.zh }

    /// The route a tap opens, or nil when the tool is not one this App registers. Only the parameters the tool's
    /// registry entry declares are kept.
    func route(entries: [LioToolEntry] = LioToolRegistry.entries) -> LioRoute? {
        LioRoute(tool: LioTool(card.kind.tool), parameters: card.parameters, entries: entries)
    }

    /// The route to open, only when this build shows the tool and a router can open it (`routable` is the set of
    /// tools it can open). Otherwise nil: the card is shown with "not in this version" and is not a button.
    func openable(in routable: Set<LioTool>, entries: [LioToolEntry] = LioToolRegistry.entries) -> LioRoute? {
        guard let route = route(entries: entries), routable.contains(route.tool) else { return nil }
        return route
    }

    /// What VoiceOver reads: the title, the line under it and, for a card that cannot open, why.
    func spoken(opens: Bool) -> String {
        var parts = [title]
        if let detail { parts.append(detail) }
        if !opens { parts.append(LioAnswerLayoutFeature.unavailableText(language)) }
        return parts.joined(separator: language.text(". ", "。"))
    }
}

#if os(iOS)
import SwiftUI

/// The tool cards under an answer (#1993): one row per card, in the contract's order. A card whose tool this build can
/// open is a button (it opens the tool with the card's parameters); one whose tool it cannot is shown with "not in this
/// version" and does nothing. Identifiers are `lio.answer.card.<type>`.
struct LioAnswerCards: View {
    let cards: [LioTimelineWire.Card]
    let language: LioLanguage
    /// The tools a route can open here (shown in this build, and a router is present).
    let routable: Set<LioTool>
    let open: (LioRoute) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            ForEach(cards.map { LioAnswerCardPresentation(card: $0, language: language) }) { card in
                row(card)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(LioAnswerCardCopy.groupLabel.text(language))
    }

    @ViewBuilder private func row(_ card: LioAnswerCardPresentation) -> some View {
        if let route = card.openable(in: routable) {
            Button { open(route) } label: { content(card, opens: true) }
                .buttonStyle(.plain)
                .accessibilityLabel(card.spoken(opens: true))
                .accessibilityHint(LioAnswerCardCopy.opensHint.text(language))
                .accessibilityIdentifier("lio.answer.card.\(card.card.kind.rawValue)")
        } else {
            content(card, opens: false)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(card.spoken(opens: false))
                .accessibilityIdentifier("lio.answer.card.\(card.card.kind.rawValue)")
        }
    }

    private func content(_ card: LioAnswerCardPresentation, opens: Bool) -> some View {
        HStack(alignment: .center, spacing: LioTheme.Spacing.sm) {
            Image(systemName: card.symbol)
                .font(.title3)
                .foregroundStyle(opens ? LioTheme.vermilion : LioTheme.inkSecondary)
                .frame(width: 28)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                Text(card.title).font(.headline).foregroundStyle(opens ? LioTheme.ink : LioTheme.inkSecondary)
                if let detail = card.detail {
                    Text(detail).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
                if !opens {
                    Text(LioAnswerLayoutFeature.unavailableText(language)).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                }
            }
            .multilineTextAlignment(.leading)
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: LioTheme.Spacing.xs)
            if opens {
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold))
                    .foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
            }
        }
        .padding(.horizontal, LioTheme.Spacing.md)
        .padding(.vertical, LioTheme.Spacing.sm)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}
#endif
