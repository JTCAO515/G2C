import CJMessageHTTP
import Foundation
import Observation
#if os(iOS)
import SwiftUI
#endif

/// #1994 (58.1 T-1, App): the line under an answer that says what the automatic save did, and the one-time notice at
/// the account's first automatic save, behind `G2CAutosaveNoticeEnabled` (off unless the build says YES). Off, the App
/// reads and shows nothing of `rich.trip_receipt`. It also needs `LIO-answer-rich.1` (`G2CAnswerRichEnabled`): the
/// receipt is part of it. The server's own switch (`CJ_LIO_TRIP_AUTOSAVE`) decides which accounts get a receipt; the
/// App shows only what the server sent.
enum LioAutosaveNoticeFeature {
    static let infoKey = "G2CAutosaveNoticeEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    /// This switch alone.
    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-autosave-notice-preview")
        #else
        return false
        #endif
    }

    /// The whole feature: the switch and rich answers.
    static func active(notice: Bool, rich: Bool) -> Bool { notice && rich }
    static var activeInBuild: Bool { active(notice: enabledInBuild, rich: LioAnswerRichFeature.enabledInBuild) }
}

/// Whether this device has already told the account's traveller that chat trips are saved automatically: one small file
/// in the account's own message folder, beside the trip home's (the trip home's cleanup removes it with the account's
/// other files on account deletion, `LioTripHomeCleanup`). Signing out keeps it. Another account has another folder and
/// can neither read nor write this one. Nothing is uploaded.
///
/// Any doubt reads as "not shown yet": a missing, unreadable, damaged or newer file shows the notice again. One
/// notice too many is acceptable; a missed one is not (the privacy policy promises it, #2019).
@MainActor public struct LioAutosaveNoticeStore {
    public static let fileName = "autosave-notice.json"
    static let currentVersion = 1

    let directory: URL
    private let isCurrent: @MainActor () -> Bool
    private var file: URL { directory.appendingPathComponent(Self.fileName) }

    public init(directory: URL, isCurrent: @escaping @MainActor () -> Bool) {
        self.directory = directory
        self.isCurrent = isCurrent
    }

    /// Beside the trip home's file; nil when the build has no account folder (previews keep nothing).
    init?(tripHome: LioTripHomeStore?) {
        guard let tripHome else { return nil }
        self.init(directory: tripHome.directory, isCurrent: { tripHome.current })
    }

    var current: Bool { isCurrent() }

    struct Record: Codable, Equatable {
        let version: Int
        let acknowledgedAt: Date
    }

    /// The record, or nil for no file, a file that can not be read, a damaged one or one written by a newer app.
    func load() -> Record? {
        guard isCurrent(), let data = try? Data(contentsOf: file),
              let record = try? JSONDecoder().decode(Record.self, from: data), record.version == Self.currentVersion
        else { return nil }
        return record
    }

    func save(_ record: Record) throws {
        guard isCurrent() else { throw CancellationError() }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var storedDirectory = directory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try storedDirectory.setResourceValues(attributes)
        let data = try JSONEncoder().encode(record)
        #if os(iOS)
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file, options: .atomic)
        #endif
    }
}

/// The one-time notice: shown for the receipt the server marks as the account's first automatic save, until the
/// traveller taps "Got it" once on this device. A receipt that is not a saved first one never shows it, whatever the
/// file says; once acknowledged it is never shown again, also for later reads of the same receipt.
///
/// Acknowledging holds for the rest of the session even if the file can not be written (the notice must not nag), and
/// then shows again after a restart. Once the account is no longer the current one, nothing shows and nothing is written.
@MainActor @Observable
final class LioAutosaveNotice {
    @ObservationIgnored private let store: LioAutosaveNoticeStore?
    private(set) var acknowledged: Bool
    /// The last acknowledgement did not reach the device.
    private(set) var saveFailed = false

    /// `store` nil keeps the answer in memory for this session only (previews, builds without an account folder).
    init(store: LioAutosaveNoticeStore?) {
        self.store = store
        acknowledged = store?.load() != nil
    }

    private var visible: Bool { store?.current ?? true }

    func shows(for receipt: LioTimelineWire.TripReceipt?) -> Bool {
        guard let receipt, receipt.isFirstSave else { return false }
        return !acknowledged && visible
    }

    func acknowledge(at date: Date = .now) {
        guard visible, !acknowledged else { return }
        acknowledged = true
        do {
            try store?.save(.init(version: LioAutosaveNoticeStore.currentVersion, acknowledgedAt: date))
            saveFailed = false
        } catch {
            saveFailed = true
        }
    }
}

/// The wording. The one-time sentence is the coordinator's (issue #1994, ADR-0012) and is not in G4's `ui-copy.json` yet:
/// it and its button are placeholders until G4 adds keys. The headline lines are `ui-copy.json`
/// (`trip.canvas.toast.*`, `common.save_unknown.message`); the counts line and the reasons are placeholders in the same voice.
enum LioAutosaveCopy {
    static func notice(_ l: LioLanguage) -> String {
        l.text("Trips from your chats are saved to your trip automatically; you can undo or change them any time.",
               "对话里的行程会自动存进你的行程，可随时撤销或修改")
    }

    static func gotIt(_ l: LioLanguage) -> String { l.text("Got it", "知道了") }

    /// The first line of the receipt row.
    static func headline(_ receipt: LioTimelineWire.TripReceipt, _ l: LioLanguage) -> String {
        switch receipt.status {
        case .saved:
            if receipt.committedVersion == 1 { return l.text("Trip created", "行程已新建") }
            guard let summary = receipt.summary else { return l.text("Added to your trip", "已加入行程") }
            if summary.added > 0 { return l.text("Added to your trip", "已加入行程") }
            if summary.updated == 0, summary.removed == 0, summary.wishlistAdded > 0 {
                return l.text("Added to “Want to go”", "已加入「想去」")
            }
            return l.text("Trip updated", "行程已更新")
        case .notSaved: return l.text("This wasn’t saved to your trip.", "这次未保存到行程。")
        case .unknown: return l.text("We can’t confirm whether this was saved.", "还没确认是否保存。")
        }
    }

    /// The lines under the headline: what changed (counts only, from the server's summary) and what became of the undo,
    /// or why nothing was saved.
    static func details(_ receipt: LioTimelineWire.TripReceipt, _ l: LioLanguage) -> [String] {
        switch receipt.status {
        case .saved:
            [receipt.summary.flatMap { counts($0, l) }, receipt.undo.flatMap { undoNote($0.state, l) }].compactMap { $0 }
        case .notSaved:
            switch receipt.reason {
            case .conflict: [l.text("Your trip had just changed.", "行程刚有新改动。")]
            case .protected: [l.text("It would have changed something you edited.", "它会改到你自己调整过的地方。")]
            case .tooLarge: [l.text("That was too many changes at once.", "这次改动太多了。")]
            case nil: []
            }
        case .unknown: []
        }
    }

    static func undoNote(_ state: LioTimelineWire.TripReceipt.Undo.State, _ l: LioLanguage) -> String? {
        switch state {
        case .expired: l.text("It’s too late to undo this change.", "这次改动已超过撤销时间。")
        case .superseded: l.text("The trip has changed since then, so this can’t be undone.", "行程有新改动，无法撤销这次。")
        case .undone: l.text("Undone", "已撤销")
        case .available, .unavailable: nil
        }
    }

    static func counts(_ summary: LioTimelineWire.TripReceipt.Summary, _ l: LioLanguage) -> String? {
        var parts: [String] = []
        if summary.added > 0 { parts.append(l.text("\(summary.added) added", "新增 \(summary.added) 个地点")) }
        if summary.updated > 0 { parts.append(l.text("\(summary.updated) updated", "更新 \(summary.updated) 个")) }
        if summary.removed > 0 { parts.append(l.text("\(summary.removed) removed", "移除 \(summary.removed) 个")) }
        if summary.wishlistAdded > 0 {
            parts.append(l.text("\(summary.wishlistAdded) added to Want to go", "「想去」加入 \(summary.wishlistAdded) 个"))
        }
        if summary.legsUpdated > 0 { parts.append(l.text("\(summary.legsUpdated) routes updated", "更新 \(summary.legsUpdated) 段路线")) }
        return parts.isEmpty ? nil : parts.joined(separator: l.text(", ", "，"))
    }
}

#if os(iOS)
/// What sits under the answer: the receipt line, and for the account's first save the one-time card.
struct LioTripReceiptBlock: View {
    let receipt: LioTimelineWire.TripReceipt
    let language: LioLanguage
    let showsNotice: Bool
    let gotIt: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            LioTripReceiptLine(receipt: receipt, language: language)
            if showsNotice { LioAutosaveNoticeCard(language: language, gotIt: gotIt) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// "Added to your trip", with the counts or the state of the undo under it. There is no Undo button in this build: the
/// undo route the receipt points to is not sent from here yet.
struct LioTripReceiptLine: View {
    let receipt: LioTimelineWire.TripReceipt
    let language: LioLanguage

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xxs) {
            Image(systemName: receipt.status == .saved ? "checkmark.circle" : "exclamationmark.circle")
                .font(.footnote)
                .foregroundStyle(receipt.status == .saved ? LioTheme.gold : LioTheme.inkSecondary)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(LioAutosaveCopy.headline(receipt, language))
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                ForEach(LioAutosaveCopy.details(receipt, language), id: \.self) { line in
                    Text(line).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lio.autosave.line")
    }
}

/// Said once per account on this device, in the chat, under the receipt line: a card, not a sheet, so the answer stays
/// readable and nothing has to be dismissed before the next question.
struct LioAutosaveNoticeCard: View {
    let language: LioLanguage
    let gotIt: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text(LioAutosaveCopy.notice(language))
                .font(.subheadline).foregroundStyle(LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("lio.autosave.notice.text")
            Button(action: gotIt) {
                Text(LioAutosaveCopy.gotIt(language))
                    .font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.vermilion)
                    .frame(minWidth: 44, minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.autosave.notice.ok")
        }
        .padding(LioTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.small))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("lio.autosave.notice")
    }
}
#endif
