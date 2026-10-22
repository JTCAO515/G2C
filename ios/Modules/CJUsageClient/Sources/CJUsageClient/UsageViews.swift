import SwiftUI

public enum UsageLanguage: Sendable {
    case english, chinese
    func text(_ english: String, _ chinese: String) -> String { self == .english ? english : chinese }
}

public extension UsageSnapshot.Status {
    func label(_ language: UsageLanguage) -> String {
        switch self {
        case .reserved: language.text("Usage is reserved; no execution is confirmed.", "已预留用量，尚未确认执行。")
        case .unknown: language.text("Usage is awaiting reconciliation. Do not resend.", "用量待核对，请勿重新发送。")
        case .released: language.text("Unstarted work was cancelled; its reservation was released.", "未开始的任务已取消，预留用量已释放。")
        case .settled: language.text("Usage was recorded from the original receipt.", "已根据原回执记录用量。")
        }
    }
}
public extension UsageFailure {
    func label(_ language: UsageLanguage) -> String {
        switch self {
        case .unavailable: language.text("Usage status is unavailable. Original source or configuration is missing.", "用量状态不可用，缺少原始来源或配置。")
        case .stale: language.text("Selection or session changed. Read the current original attempt explicitly.", "选择或会话已变化，请手动查询当前原调用。")
        case .invalidResponse: language.text("Usage status could not be verified. No usage amount is confirmed.", "用量状态无法核验，尚未确认用量数值。")
        case .exchangeFailed: language.text("Could not read usage status. Do not resend the original action.", "无法读取用量状态，请勿重新发送原操作。")
        case .rejected: language.text("Usage status is unavailable for this request. Do not resend the original action.", "本次请求无法获取用量状态，请勿重新发送原操作。")
        }
    }
}

/// Embeddable read-only component. The host action must call prepare synchronously
/// before scheduling read. This view performs no on-appear request or automatic poll.
public struct UsageStatusView: View {
    private let state: UsageState
    private let language: UsageLanguage
    private let readOriginal: () -> Void
    public init(state: UsageState, language: UsageLanguage, readOriginal: @escaping () -> Void) {
        self.state = state; self.language = language; self.readOriginal = readOriginal
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(language.text("Original attempt usage", "原调用用量")).font(.headline)
            switch state {
            case .unavailable: Text(UsageFailure.unavailable.label(language))
            case .loading: ProgressView(language.text("Reading status…", "正在读取状态…"))
            case .failed(let failure): Text(failure.label(language))
            case .loaded(let value):
                Text(value.status.label(language))
                if value.cancelled { Text(language.text("This attempt was cancelled. Existing records remain readable.", "此调用已取消，已有记录仍可查询。")) }
                if value.exceeded { Text(language.text("A usage or output limit was exceeded. This record does not permit another call.", "用量或输出已超过限制，此记录不代表允许再次调用。")) }
                Text(language.text("Unit identifier: ", "单位标识：") + value.unit)
                Text(language.text("Originally reserved: ", "原预留：") + value.reservedUnits)
                Text(language.text("Confirmed usage: ", "已确认用量：") + (value.confirmedUnits ?? language.text("Unknown", "未知")))
                Text(language.text("Confirmed output: ", "已确认输出：") + (value.confirmedOutput ?? language.text("Unknown", "未知")))
            }
            Text(language.text("Historical record only. Units are not currency, payment, current balance or permission to start another call.", "仅为历史记录，单位不代表货币、付款、当前余额或再次调用许可。"))
                .font(.footnote)
            Button(language.text("Read original attempt status", "查询原调用状态"), action: readOriginal)
                .disabled(state == .loading)
        }
        .textSelection(.enabled)
    }
}
