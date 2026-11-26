import Foundation
import SwiftUI

/// #1753 (W4-9): one line under each finished answer saying it was written by AI. Behind `G2CAIDisclosureEnabled`,
/// off unless the build says YES (approved by the coordinator under JT's pre-authorisation, 2026-11-26).
enum LioAIDisclosureFeature {
    static let infoKey = "G2CAIDisclosureEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-ai-disclosure-preview")
        #else
        return false
        #endif
    }

    static func text(_ language: LioLanguage) -> String {
        language.text("AI-generated and may be wrong. Double-check anything important.",
                      "由 AI 生成，可能有误，重要信息请自行确认。")
    }
}

/// #1753 (W4-9): a "Not helpful" control under each finished answer, then optional details. Behind
/// `G2CAnswerFeedbackEnabled`, off unless the build says YES (wording approved by the coordinator under JT's
/// pre-authorisation, 2026-11-26). Independent of the AI line: either, both or neither may show.
enum LioAnswerFeedbackFeature {
    static let infoKey = "G2CAnswerFeedbackEnabled"
    static let detailsCharacterLimit = 500
    static let detailsByteLimit = 6000
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-answer-feedback-preview")
        #else
        return false
        #endif
    }

    /// The fixed line sent for "Not helpful", in the language the app is showing. No chat text goes with it.
    static func problem(_ language: LioLanguage) -> String {
        language.text("This answer didn't help.", "这条回答没帮上忙。")
    }

    /// What is sent for the typed details: control characters other than line breaks and tabs removed (the
    /// server counts U+001C–U+001F as blank, so a line of only those would be refused for good), then trimmed.
    /// Empty means there is nothing to send.
    static func cleanedDetails(_ text: String) -> String {
        var scalars = String.UnicodeScalarView()
        scalars.append(contentsOf: text.unicodeScalars.filter {
            $0 == "\n" || $0 == "\t" || $0.properties.generalCategory != .control
        })
        return limitedDetails(String(scalars).trimmingCharacters(in: .whitespacesAndNewlines))
    }

    /// Details stay within 500 characters and 6000 UTF-8 bytes, whichever comes first.
    static func limitedDetails(_ text: String) -> String {
        var value = String(text.prefix(detailsCharacterLimit))
        while value.utf8.count > detailsByteLimit { value.removeLast() }
        return value
    }

    enum Copy {
        static func notHelpful(_ language: LioLanguage) -> String { language.text("Not helpful", "没帮上") }
        static func thanks(_ language: LioLanguage) -> String { language.text("Thanks, we got it.", "已收到，谢谢。") }
        static func addDetails(_ language: LioLanguage) -> String { language.text("Add details", "补充说明") }
        static func detailsPrompt(_ language: LioLanguage) -> String {
            language.text("What went wrong? Don't include personal details.", "哪里不对？请不要填写个人信息。")
        }
        static func notSent(_ language: LioLanguage) -> String {
            language.text("Not sent. Tap to try again.", "没发出去，点此重试。")
        }
        static func full(_ language: LioLanguage) -> String {
            language.text("Feedback is full for now.", "反馈已满，暂不能提交。")
        }
    }
}

/// Which of an answer's two feedback lines a call is about: the fixed "Not helpful", or the details after it.
public enum LioAnswerFeedbackStep: Hashable, Sendable { case notHelpful, details }

/// How one feedback call ended. `notSent` covers every case where it is not known to have arrived.
public enum LioAnswerFeedbackOutcome: Equatable, Sendable { case sent, notSent, full, unavailable }

/// What sends answer feedback for Lio. The host keeps one for the signed-in session and handles one call at a time.
/// Each call names only the answer's message; Lio never passes chat text, place or device details.
@MainActor public protocol LioAnswerFeedbackSending: AnyObject {
    /// The fixed "Not helpful" line for this message's answer.
    func notHelpful(messageID: String, problem: String) async -> LioAnswerFeedbackOutcome
    /// What the traveller typed after "Not helpful" went through.
    func addDetails(messageID: String, text: String) async -> LioAnswerFeedbackOutcome
    /// Tries the same step again with the text first sent for it. A line already saved on this device for this
    /// message and text is only looked up, never sent as a new one, even by a host made after the app came back.
    func retry(_ step: LioAnswerFeedbackStep, messageID: String, text: String) async -> LioAnswerFeedbackOutcome
}

/// Where one answer's feedback stands. Kept by `LioHome` per turn, so it survives scrolling and re-rendering.
enum LioAnswerFeedbackPhase: Equatable {
    case ready, sending(LioAnswerFeedbackStep), sent, detailsSent, notSent(LioAnswerFeedbackStep), full

    init(_ outcome: LioAnswerFeedbackOutcome, after step: LioAnswerFeedbackStep) {
        switch outcome {
        case .sent: self = step == .notHelpful ? .sent : .detailsSent
        case .notSent, .unavailable: self = .notSent(step)
        case .full: self = .full
        }
    }

    var isSending: Bool { if case .sending = self { true } else { false } }
}

#if DEBUG
/// Debug preview stand-in for the host (`--lio-preview --lio-answer-feedback-preview`). Nothing leaves the device.
/// With `--lio-answer-feedback-fail-once` the first call does not go through, so the retry path can be shown.
@MainActor public final class LioAnswerFeedbackPreview: LioAnswerFeedbackSending {
    public static let launch: LioAnswerFeedbackPreview? = {
        let arguments = ProcessInfo.processInfo.arguments
        guard arguments.contains("--lio-answer-feedback-preview") else { return nil }
        return LioAnswerFeedbackPreview(failsFirst: arguments.contains("--lio-answer-feedback-fail-once"))
    }()

    private var failsNext: Bool
    public init(failsFirst: Bool) { failsNext = failsFirst }

    public func notHelpful(messageID: String, problem: String) async -> LioAnswerFeedbackOutcome { await answer() }
    public func addDetails(messageID: String, text: String) async -> LioAnswerFeedbackOutcome { await answer() }
    public func retry(_ step: LioAnswerFeedbackStep, messageID: String, text: String) async -> LioAnswerFeedbackOutcome {
        await answer()
    }

    private func answer() async -> LioAnswerFeedbackOutcome {
        try? await Task.sleep(for: .milliseconds(300))
        if failsNext { failsNext = false; return .notSent }
        return .sent
    }
}
#endif

#if os(iOS)
/// What follows a finished answer: the AI line and the feedback control, each when the build shows it.
struct LioAnswerFooter: View {
    struct Feedback {
        let phase: LioAnswerFeedbackPhase
        /// False while another answer's feedback is on its way (one at a time).
        let enabled: Bool
        let notHelpful: () -> Void
        let addDetails: () -> Void
        let retry: () -> Void
    }

    let language: LioLanguage
    let showsDisclosure: Bool
    var feedback: Feedback?
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        if showsDisclosure || feedback != nil {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                if showsDisclosure {
                    // One wrapping text element (the symbol is inline), so it grows with Dynamic Type instead of clipping.
                    (Text(Image(systemName: "sparkles")) + Text(" ")
                        + Text(LioAIDisclosureFeature.text(language)))
                        .font(.footnote)
                        .foregroundStyle(LioTheme.inkSecondary)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityLabel(LioAIDisclosureFeature.text(language))
                        .accessibilityIdentifier("lio.answer.ai-disclosure")
                }
                if let feedback { feedbackRow(feedback) }
            }
        }
    }

    @ViewBuilder
    private func feedbackRow(_ feedback: Feedback) -> some View {
        let row = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: LioTheme.Spacing.xxs))
            : AnyLayout(HStackLayout(spacing: LioTheme.Spacing.sm))
        row {
            switch feedback.phase {
            case .ready, .sending(.notHelpful):
                action(Text(Image(systemName: "hand.thumbsdown")) + Text(" ")
                       + Text(LioAnswerFeedbackFeature.Copy.notHelpful(language)),
                       label: LioAnswerFeedbackFeature.Copy.notHelpful(language),
                       id: "lio.answer.feedback.not-helpful",
                       enabled: feedback.enabled && feedback.phase == .ready, perform: feedback.notHelpful)
            case .sent, .sending(.details):
                note(LioAnswerFeedbackFeature.Copy.thanks(language), id: "lio.answer.feedback.sent")
                action(Text(LioAnswerFeedbackFeature.Copy.addDetails(language)),
                       label: LioAnswerFeedbackFeature.Copy.addDetails(language),
                       id: "lio.answer.feedback.details",
                       enabled: feedback.enabled && feedback.phase == .sent, perform: feedback.addDetails)
            case .detailsSent:
                note(LioAnswerFeedbackFeature.Copy.thanks(language), id: "lio.answer.feedback.sent")
            case .notSent:
                action(Text(LioAnswerFeedbackFeature.Copy.notSent(language)),
                       label: LioAnswerFeedbackFeature.Copy.notSent(language),
                       id: "lio.answer.feedback.retry", enabled: feedback.enabled, perform: feedback.retry)
            case .full:
                note(LioAnswerFeedbackFeature.Copy.full(language), id: "lio.answer.feedback.full")
            }
            if feedback.phase.isSending {
                ProgressView()
                    .controlSize(.small)
                    .tint(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.answer.feedback.sending")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func action(_ text: Text, label: String, id: String, enabled: Bool,
                        perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            text
                .font(.footnote.weight(.semibold))
                .foregroundStyle(enabled ? LioTheme.vermilion : LioTheme.inkSecondary)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .accessibilityLabel(label)
        .accessibilityIdentifier(id)
    }

    private func note(_ text: String, id: String) -> some View {
        Text(text)
            .font(.footnote)
            .foregroundStyle(LioTheme.inkSecondary)
            .multilineTextAlignment(.leading)
            .fixedSize(horizontal: false, vertical: true)
            .frame(minHeight: 44)
            .accessibilityIdentifier(id)
    }
}

/// The optional details after "Not helpful": one field, then Send.
struct LioAnswerFeedbackDetailsSheet: View {
    let language: LioLanguage
    let onSend: (String) -> Void
    @State private var text = ""
    @FocusState private var typing: Bool
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize

    private var trimmed: String { LioAnswerFeedbackFeature.cleanedDetails(text) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            let controls = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: LioTheme.Spacing.xs))
                : AnyLayout(HStackLayout(spacing: LioTheme.Spacing.sm))
            controls {
                Button { dismiss() } label: {
                    Text(language.text("Cancel", "取消"))
                        .font(.body)
                        .foregroundStyle(LioTheme.vermilion)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.answer.feedback.details.cancel")
                if !typeSize.isAccessibilitySize { Spacer() }
                Button(action: send) {
                    Text(language.text("Send", "发送"))
                        .font(.headline)
                        .foregroundStyle(trimmed.isEmpty ? LioTheme.inkSecondary : LioTheme.vermilion)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(trimmed.isEmpty)
                .accessibilityIdentifier("lio.answer.feedback.details.send")
            }
            .tint(LioTheme.vermilion)
            .padding(.horizontal, LioTheme.Spacing.md)
            .padding(.top, LioTheme.Spacing.sm)
            Form {
                Section {
                    TextField(LioAnswerFeedbackFeature.Copy.detailsPrompt(language), text: $text, axis: .vertical)
                        .lineLimit(3...8)
                        .focused($typing)
                        .accessibilityIdentifier("lio.answer.feedback.details.text")
                        .onChange(of: text) { _, value in
                            let limited = LioAnswerFeedbackFeature.limitedDetails(value)
                            if limited != value { text = limited }
                        }
                } header: {
                    Text(LioAnswerFeedbackFeature.Copy.addDetails(language))
                        .foregroundStyle(LioTheme.inkSecondary)
                } footer: {
                    Text("\(text.count)/\(LioAnswerFeedbackFeature.detailsCharacterLimit)")
                        .foregroundStyle(LioTheme.inkSecondary)
                        .accessibilityIdentifier("lio.answer.feedback.details.count")
                }
                .lioRow()
            }
            .lioPage()
            .tint(LioTheme.vermilion)
        }
        .background(LioTheme.paper)
        .task { typing = true }
    }

    private func send() {
        guard !trimmed.isEmpty else { return }
        onSend(trimmed)
        dismiss()
    }
}
#endif
