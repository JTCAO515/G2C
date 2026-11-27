import CJMessageHTTP
import Foundation
import SwiftUI

/// #1727: a finished answer in two bubbles with fixed buttons under them, behind `G2CAnswerLayoutEnabled` (off unless the
/// build says YES). With the flag off the App never asks for it, never reads it and nothing on screen changes.
enum LioAnswerLayoutFeature {
    static let infoKey = "G2CAnswerLayoutEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-answer-layout-preview")
        #else
        return false
        #endif
    }

    static func unavailableText(_ language: LioLanguage) -> String {
        language.text("This tool isn't in this version yet.", "这个版本还没有这个工具。")
    }
}

/// An answer cut at its first blank line. `tail` is nil until the blank line has arrived, and for an answer without one.
struct LioAnswerParts: Equatable {
    let head: String
    let tail: String?
    /// How many Unicode scalar values the head has, and where in the whole answer the tail starts (also in scalars).
    /// The server's place ranges (LIO-answer-rich.1) count scalars over the whole answer; these give each bubble its own.
    let headScalars: Int
    let tailStart: Int?

    /// One bubble, the answer exactly as received (the path with the flag off or without a `split` layout).
    init(whole source: String) {
        head = source; tail = nil
        headScalars = source.unicodeScalars.count; tailStart = nil
    }

    /// Cuts at the first `\n\n`. Newlines around the cut belong to neither bubble. While the first newline of the cut is
    /// the last character received the head already leaves it out, so the head only ever grows as the answer streams.
    init(_ source: String) {
        guard let cut = source.range(of: "\n\n") else {
            head = source.hasSuffix("\n") ? String(source.dropLast()) : source
            tail = nil
            headScalars = head.unicodeScalars.count; tailStart = nil
            return
        }
        head = String(source[..<cut.lowerBound])
        let rest = source[cut.upperBound...].drop(while: { $0 == "\n" })
        tail = rest.isEmpty ? nil : String(rest)
        headScalars = head.unicodeScalars.count
        tailStart = rest.isEmpty ? nil : source.unicodeScalars.distance(from: source.startIndex, to: rest.startIndex)
    }

    /// The part of `spans` (ranges over the whole answer) that lies in the head, and the part in the tail with
    /// its ranges moved to the tail's own start. A span that is in neither (it would cross the cut) is left out.
    func places(_ spans: [LioPlaceSpan]) -> (head: [LioPlaceSpan], tail: [LioPlaceSpan]) {
        let inHead = spans.filter { $0.end <= headScalars }
        guard let tailStart else { return (inHead, []) }
        let inTail = spans.filter { $0.start >= tailStart }
            .map { LioPlaceSpan(start: $0.start - tailStart, end: $0.end - tailStart, placeID: $0.placeID) }
        return (inHead, inTail)
    }
}

#if os(iOS)
/// The server's buttons under a finished answer. Each opens its tool through the router; a tool this build does not
/// have shows "not in this version" instead of an error.
struct LioAnswerFollowups: View {
    let actions: [LioTimelineWire.Followup]
    var chips: [LioTimelineWire.Chip] = []
    let open: (LioTimelineWire.Followup) -> Void
    var ask: (LioTimelineWire.Chip) -> Void = { _ in }
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            if !actions.isEmpty { row { buttons } }
            if !chips.isEmpty { row { questions } }
        }
    }

    @ViewBuilder private func row<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) { content() }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: LioTheme.Spacing.xs) { content() }
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) { content() }
            }
        }
    }

    /// Short questions to send with a tap. One older than the server's ticket (24 hours) is shown but cannot be tapped.
    private var questions: some View {
        ForEach(chips.indices, id: \.self) { index in
            let chip = chips[index]
            Button { ask(chip) } label: {
                Text(chip.label)
                    .font(.subheadline)
                    .foregroundStyle(chip.ticket == nil ? LioTheme.inkSecondary : LioTheme.ink)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, LioTheme.Spacing.md)
                    .frame(minHeight: 44)
                    .lioCard(Capsule())
                    .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .disabled(chip.ticket == nil)
            .accessibilityIdentifier("lio.answer.chip.\(index)")
        }
    }

    private var buttons: some View {
        ForEach(actions.indices, id: \.self) { index in
            Button { open(actions[index]) } label: {
                Text(actions[index].label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(LioTheme.vermilion)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, LioTheme.Spacing.md)
                    .frame(minHeight: 44)
                    .overlay(Capsule().stroke(LioTheme.vermilion.opacity(0.5), lineWidth: 1))
                    .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.answer.followup.\(index)")
        }
    }
}
#endif
