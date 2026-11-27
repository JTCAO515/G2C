import CJMessageHTTP
import Foundation
#if os(iOS)
import SwiftUI
#endif

/// #1999 (M-1, App): the first-time question "let Lio remember your preferences?" and the traveller's choice, behind
/// `G2CMemoryConsentEnabled` (off unless the build says YES). With the flag off nothing is asked, nothing is withheld
/// and nothing is written to the server: the chat shows suggestions exactly as before. The flag only does something in a
/// build that also keeps the account's consent (`G2CConsentEnabled`), because the choice is kept in that file.
enum LioMemoryConsentFeature {
    static let infoKey = "G2CMemoryConsentEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-memory-consent-preview")
        #else
        return false
        #endif
    }
}

/// Carries the device's choice to the server (`PUT /v1/lio/memory/consent`). The device decides what the chat shows at
/// once; the server is told afterwards, with the same `request_id` on every retry. Until it has answered, a withdrawal
/// already hides the suggestions here, but the server may still prepare them: the screen says so (`syncing`).
@MainActor
enum LioMemoryConsentSync {
    /// One per user action. `A-Za-z0-9._:-`, at most 128 characters.
    static func newRequestID() -> String { "mc-" + UUID().uuidString.lowercased() }

    enum Result: Equatable {
        /// Nothing is waiting for the server (it has answered, or there was never anything to write).
        case upToDate
        /// The server refused in a way retrying cannot change (400, 401, 403, 409). Not retried until the next launch.
        case refused(Int)
        /// No answer (offline, 503, an answer that is not the contract's), the session ended, or the task was cancelled.
        case unavailable
    }

    /// Writes the unsynced choice, newest first if the traveller changed their mind meanwhile, one request at a time.
    /// `pause` is called between failed attempts and returns false when waiting was cut short.
    static func run(consent: LioConsent, client: LioMemoryConsentClient?, attempts: Int = 4,
                    isCurrent: @MainActor () -> Bool = { true },
                    pause: (Int) async -> Bool = { failures in
                        (try? await Task.sleep(for: .seconds(min(60, 2 << failures)))) != nil
                    }) async -> Result {
        guard let client else { return consent.memoryUnsynced == nil ? .upToDate : .unavailable }
        var failures = 0
        while let request = consent.memoryUnsynced {
            guard !Task.isCancelled, isCurrent() else { return .unavailable }
            do {
                switch try await client.put(request) {
                case .accepted(let receipt) where receipt.state == request.state:
                    consent.markMemorySynced(requestID: request.requestID)
                    continue
                case .accepted:
                    failures += 1
                case .refused(let status):
                    return .refused(status)
                }
            } catch {
                if error is CancellationError || Task.isCancelled { return .unavailable }
                failures += 1
            }
            guard failures < attempts, await pause(failures) else { return .unavailable }
        }
        return .upToDate
    }
}

/// The wording of the question and of the switch under Me → Privacy. The short lines are `ui-copy.json` (G4,
/// `memory.consent.*`, `memory.settings.toggle.*`); the paragraph behind "Read about memory" is the approved text of
/// `docs/privacy/consent-screens.md` §3.3, and a test holds it to that file.
enum LioMemoryConsentCopy {
    /// The version of the consent text the App shows, sent as `consent_text_version`. Only the version leaves the device.
    static let textVersion = "memory-2026-11"

    static func title(_ l: LioLanguage) -> String { l.text("Let Lio remember your preferences?", "要让Lio记住你的偏好吗？") }
    static func lines(_ l: LioLanguage) -> [String] {
        [l.text("Your chats are sent to AI to suggest things to remember.", "对话会发给AI生成记忆建议。"),
         l.text("Suggestions are stored on our servers with your account.", "建议随账号保存在服务器上。"),
         l.text("Lio uses this suggestion in future chats only if you tap Remember.", "点「记住」后，此建议才用于日后对话。")]
    }
    static func turnOn(_ l: LioLanguage) -> String { l.text("Turn on memory", "开启记忆") }
    static func notNow(_ l: LioLanguage) -> String { l.text("Not now", "暂不开启") }
    static func details(_ l: LioLanguage) -> String { l.text("Read about memory", "查看记忆说明") }
    static func detailsText(_ l: LioLanguage) -> String {
        l.text("Once on, Lio suggests preferences and facts it could remember from your chats (the chat content goes to the AI model for this). These suggestions are stored on our servers with your account; they become memories used in later chats only when you tap Remember. You can view, edit and delete memories at any time, or turn this off under Me. Please do not let it remember health, ID or religious information, or information that identifies other people.",
               "开启后，Lio 会根据对话提出可以记住的偏好与事实（为此，对话内容会发给 AI 模型）。这些建议会随你的账号保存在服务器上；你点「记住」后才成为记忆，用于以后的对话。你可以随时查看、修改和删除记忆，或在「我的」里关闭。请不要让它记住健康、证件、宗教等敏感信息，或可识别他人的信息。")
    }

    // Me → Privacy
    static func settingTitle(_ l: LioLanguage) -> String { l.text("Let Lio remember preferences", "让Lio记住偏好") }
    static func settingOnDetail(_ l: LioLanguage) -> String { l.text("When on, Lio can suggest memories from your chats.", "开启后，Lio可从对话提出记忆建议。") }
    static func settingFailed(_ l: LioLanguage) -> String { l.text("Couldn’t change the memory setting.", "没能更改记忆设置。") }

    // Not in ui-copy.json: placeholders for the coordinator to confirm.
    /// The off line of ui-copy.json says Lio "stops using saved memories". A withdrawal does not do that (contract: items
    /// already remembered are not touched; stopping or erasing them stays with "My memory"), so this line says what is true.
    static func settingOffDetail(_ l: LioLanguage) -> String {
        l.text("Off: Lio no longer suggests memories. What you already saved stays; change or delete it under My memory.",
               "已关闭：Lio 不再提出记忆建议。已记住的内容不受影响，可在「我的记忆」里停用或删除。")
    }
    static func turnOff(_ l: LioLanguage) -> String { l.text("Turn off memory", "关闭记忆") }
    static func syncing(_ l: LioLanguage) -> String {
        l.text("Saving your choice with your account… Until that finishes, Lio may still prepare suggestions on the server; they are not shown.",
               "正在把你的选择保存到账号……完成前服务器可能仍会准备建议，但不会显示。")
    }
}

#if os(iOS)
/// The one-time question, in the chat where the first suggestion would be. Two answers, none preselected; "Not now" is
/// an answer (the server is told the account has chosen, and nothing is asked again). The wording is `LioMemoryConsentCopy`.
struct LioMemoryConsentCard: View {
    let language: LioLanguage
    let turnOn: () -> Void
    let notNow: () -> Void
    @State private var showsDetails = false

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            HStack(alignment: .top, spacing: LioTheme.Spacing.xs) {
                Image(systemName: "bookmark").foregroundStyle(LioTheme.gold).accessibilityHidden(true)
                Text(LioMemoryConsentCopy.title(language))
                    .font(.headline).foregroundStyle(LioTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("lio.memory.consent.title")
            }
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                ForEach(LioMemoryConsentCopy.lines(language), id: \.self) { line in
                    Text(line).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("lio.memory.consent.lines")
            Button { showsDetails.toggle() } label: {
                Text(LioMemoryConsentCopy.details(language))
                    .font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.vermilion)
                    .frame(minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.memory.consent.details")
            if showsDetails {
                Text(LioMemoryConsentCopy.detailsText(language))
                    .font(.footnote).foregroundStyle(LioTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("lio.memory.consent.details-text")
            }
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                Button(action: turnOn) {
                    Text(LioMemoryConsentCopy.turnOn(language))
                        .font(.body.weight(.semibold)).foregroundStyle(LioTheme.onVermilion)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .padding(.horizontal, LioTheme.Spacing.sm)
                        .background(LioTheme.vermilion, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                        .contentShape(Rectangle())
                }
                .accessibilityIdentifier("lio.memory.consent.accept")
                Button(action: notNow) {
                    Text(LioMemoryConsentCopy.notNow(language))
                        .font(.body.weight(.semibold)).foregroundStyle(LioTheme.vermilion)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .padding(.horizontal, LioTheme.Spacing.sm)
                        .overlay(RoundedRectangle(cornerRadius: LioTheme.Radius.card)
                            .stroke(LioTheme.vermilion, lineWidth: LioTheme.outlineWidth))
                        .contentShape(Rectangle())
                }
                .accessibilityIdentifier("lio.memory.consent.defer")
            }
            .buttonStyle(.plain)
        }
        .padding(LioTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.small))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("lio.memory.consent")
    }
}
#endif
