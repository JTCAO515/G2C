import Foundation
import Observation
import CJCleanupClient
import CJRunClient
#if os(iOS)
import SwiftUI
#endif

public enum AccountCleanupCommand: Sendable { case review, confirm, checkOriginal, cleanDevice, checkDevice, reportDevice, finalizeControls }
public struct AccountCleanupPresentation: Sendable {
    public var canReview = false
    public var canConfirm = false
    public var canRead = false
    public var canCleanDevice = false
    public var canReadDevice = false
    public var canReportDevice = false
    public var canFinalizeControls = false
    public var controlsFinalized = false
    public var controlsPending = false
    public var originalContentComplete = false
    public var preparing = false
    public var businessStopped = false
    public var unknown = false
    public var unavailable = false
    public var progress: AccountCleanupProgress?
    public var nativeOutcome: DeviceCleanupNativeOutcome?
    public var deviceState: DeviceCleanupResultState?
    public init() {}
}

/// Safe UI projection only. Credentials, native paths and original wire bytes
/// remain in the trusted composition root and canonical cleanup clients.
@MainActor @Observable public final class AccountCleanupContainerHost {
    public private(set) var presentation = AccountCleanupPresentation()
    public private(set) var busy = false
    @ObservationIgnored private var action: (@MainActor (AccountCleanupCommand) async -> Void)?
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private var generation = UUID()
    public init() {}
    public func bind(action: @escaping @MainActor (AccountCleanupCommand) async -> Void) { self.action = action }
    public func show(_ presentation: AccountCleanupPresentation) { self.presentation = presentation }
    public func invalidate() {
        generation = UUID(); task?.cancel(); task = nil; action = nil; busy = false
        var value = AccountCleanupPresentation(); value.unavailable = true; presentation = value
    }
    public func perform(_ command: AccountCleanupCommand) {
        guard !busy, let action else { return }
        let allowed: Bool
        switch command {
        case .review: allowed = presentation.canReview
        case .confirm: allowed = presentation.canConfirm
        case .checkOriginal: allowed = presentation.canRead
        case .cleanDevice: allowed = presentation.canCleanDevice
        case .checkDevice: allowed = presentation.canReadDevice
        case .reportDevice: allowed = presentation.canReportDevice
        case .finalizeControls: allowed = presentation.canFinalizeControls
        }
        guard allowed else { return }
        let captured = generation; busy = true
        task = Task { [weak self] in
            await action(command)
            guard let self, self.generation == captured else { return }
            self.busy = false; self.task = nil
        }
    }
}

#if os(iOS)
private struct AccountCleanupHostKey: EnvironmentKey {
    static let defaultValue: AccountCleanupContainerHost? = nil
}
extension EnvironmentValues {
    public var accountCleanupHost: AccountCleanupContainerHost? {
        get { self[AccountCleanupHostKey.self] }
        set { self[AccountCleanupHostKey.self] = newValue }
    }
}
struct AccountCleanupControls: View {
    let host: AccountCleanupContainerHost
    let language: ShellLanguage
    @State private var confirmation = false
    private var value: AccountCleanupPresentation { host.presentation }
    var body: some View {
        Section {
            if host.busy || value.preparing { ProgressView().accessibilityLabel(language.text("Checking original cleanup", "正在核对原清理操作")) }
            if value.unavailable {
                text(language.text("Secure cleanup information is unavailable. Nothing is marked complete.", "安全清理信息不可用，未标记清理完成。"), "unavailable")
            }
            if value.unknown {
                text(language.text("The original result is unknown. Check it before another action; the request will not be sent again.", "原操作结果未知。继续前请核对结果，不会再次发送原请求。"), "unknown")
            }
            if value.businessStopped || value.progress != nil {
                text(value.businessStopped ? language.text("Account access has stopped.", "账号已停止使用。") : language.text("Account access has not been revoked.", "账号尚未撤权。"), "access")
            }
            if value.businessStopped && value.progress == nil && !value.originalContentComplete {
                text(language.text("Online cleanup has not been verified on this device.", "本机尚未核实线上清理进度。"), "progress")
            }
            if value.originalContentComplete && value.progress == nil {
                text(language.text("The original listed online content was confirmed clear; other-device and backup obligations remain separate.", "原操作列出的线上内容已确认清理；其他设备与备份仍需分别核验。"), "progress")
            }
            if let progress = value.progress {
                text(language.text("Online cleanup: ", "线上清理：") + status(progress.onlineStatus ?? progress.status), "progress")
                let confirmed = progress.steps.filter { $0.state == .confirmed }.count
                text(language.text("Listed areas confirmed: \(confirmed) of \(progress.steps.count).", "已核实清理范围：\(confirmed)/\(progress.steps.count)。"), "areas")
            }
            if let outcome = value.nativeOutcome {
                text(language.text("This device: ", "本机清理：") + nativeStatus(outcome), "native")
            }
            if let device = value.deviceState {
                text(language.text("Original device receipt: ", "原设备回执：") + deviceStatus(device), "deviceReceipt")
            }
            if value.controlsFinalized {
                text(language.text("Original private cleanup records on this device were removed and verified. Only a nonsecret terminal hash marker remains.", "本机原有私有清理记录已移除并核验，仅保留无秘密的终态哈希标记。"), "controls")
            } else if value.controlsPending {
                text(language.text("Original recovery records are retained until server content, this device's receipt and exact local record checks are all verified.", "原恢复记录仍保留，需核实服务端内容、本机回执及确切本机记录后才能收口。"), "controls")
            }
            if value.canReview { button(language.text("Review account deletion", "查看注销范围"), .review, "review") }
            if value.canConfirm {
                Toggle(language.text("I understand that this deletes this G2C account and its data.", "我已了解，此操作会注销本 G2C 账号并删除其数据。"), isOn: $confirmation)
                    .accessibilityIdentifier("account.cleanup.consent")
                Button(role: .destructive) { confirmation = false; host.perform(.confirm) } label: {
                    RunReadableText(text: language.text("Confirm account deletion", "确认注销账号"))
                        .frame(minHeight: 44)
                }.disabled(host.busy || !confirmation).accessibilityIdentifier("account.cleanup.confirm")
            }
            if value.canRead { button(language.text("Check original cleanup", "核对原清理操作"), .checkOriginal, "read") }
            if value.canCleanDevice { button(language.text("Clear this device's account data", "清理本机账号数据"), .cleanDevice, "cleanDevice") }
            if value.canReportDevice { button(language.text("Send this device's verified result", "提交本机已核实的清理结果"), .reportDevice, "reportDevice") }
            if value.canReadDevice { button(language.text("Check original device cleanup", "核对原设备清理"), .checkDevice, "readDevice") }
            if value.canFinalizeControls { button(language.text("Verify and finish private cleanup records", "核验并收口私有清理记录"), .finalizeControls, "finalizeControls") }
        } header: { ShellSectionHeading(title: language.text("Account deletion", "账号注销")).accessibilityIdentifier("account.cleanup.heading") }
    }
    private func text(_ value: String, _ id: String) -> some View {
        RunReadableText(text: value).frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityIdentifier("account.cleanup." + id)
    }
    private func button(_ title: String, _ command: AccountCleanupCommand, _ id: String) -> some View {
        Button { host.perform(command) } label: { RunReadableText(text: title).frame(minHeight: 44) }
            .disabled(host.busy).accessibilityIdentifier("account.cleanup." + id)
    }
    private func status(_ value: AccountCleanupStatus) -> String {
        switch value {
        case .awaitingConfirmation: language.text("Awaiting your confirmation", "等待本人确认")
        case .blocked: language.text("Blocked", "受阻")
        case .inProgress: language.text("In progress", "进行中")
        case .unknown: language.text("Unknown", "未知")
        case .failed: language.text("Failed", "失败")
        case .complete: language.text("Confirmed for the listed online domains", "列出的线上范围已核实")
        }
    }
    private func stepStatus(_ value: AccountCleanupStepState) -> String {
        switch value {
        case .pending: language.text("Pending", "待处理")
        case .inProgress: language.text("In progress", "进行中")
        case .unknown: language.text("Unknown", "未知")
        case .failed: language.text("Failed", "失败")
        case .confirmed: language.text("Confirmed", "已核实")
        }
    }
    private func nativeStatus(_ value: DeviceCleanupNativeOutcome) -> String {
        switch value {
        case .unknown: language.text("Unknown", "未知")
        case .failed: language.text("Failed", "失败")
        case .confirmed: language.text("The original local targets are clear", "原调用指定的本机目标已清理")
        }
    }
    private func deviceStatus(_ value: DeviceCleanupResultState) -> String {
        switch value {
        case .pending: language.text("Pending", "待回执")
        case .unknown: language.text("Unknown", "未知")
        case .failed: language.text("Failed", "失败")
        case .confirmed: language.text("Acknowledged for this device", "本机回执已确认")
        }
    }
}
#endif
