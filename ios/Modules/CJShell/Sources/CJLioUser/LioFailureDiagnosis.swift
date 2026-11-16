import CJMessageClient
import CJMessageHTTP
import Foundation

/// Explains why a conversation could not open, for the person and for on-device notes.
/// Classification is presentation only: it never retries, clears, signs out or
/// changes the outcome of the original failure.
public struct LioFailureDiagnosis: Sendable, Equatable {
    public enum Category: String, Sendable, Equatable, CaseIterable, Codable {
        case network, signIn, service, localRecord, unclear
    }

    /// Where in opening a conversation the failure happened.
    public enum Stage: String, Sendable, Equatable, CaseIterable, Codable {
        case sessionCheck, selectedChat, localRecord, firstSendLookup, timeline, history, send
    }

    public let category: Category
    public let stage: Stage
    public let request: LioTimelineHTTP.RequestKind?
    public let httpStatus: Int?
    /// The service's request reference (`X-Request-ID`), when a response arrived.
    public let serverReference: String?

    public init(category: Category, stage: Stage, request: LioTimelineHTTP.RequestKind?, httpStatus: Int?,
                serverReference: String? = nil) {
        self.category = category
        self.stage = stage
        self.request = request
        self.httpStatus = httpStatus
        self.serverReference = serverReference
    }

    /// `observation` must be the client's record of the request that belongs to this stage, if any.
    public static func classify(_ error: any Error, stage: Stage,
                                observation: LioTimelineHTTP.Observation?) -> Self {
        let status = observation?.httpStatus
        var stage = stage
        if case MessageHTTPFailure.credentialsUnavailable = error { stage = .sessionCheck }
        if case RecoveryError.inactive = error { stage = .sessionCheck }
        let category: Category
        if let status, status == 401 || status == 403 {
            category = .signIn
        } else if let status, status == 429 || (500...599).contains(status) {
            category = .service
        } else if let error = error as? URLError, networkCodes.contains(error.code) {
            category = .network
        } else if status == nil, observation?.offline == true, !(error is RecoveryError) {
            category = .network
        } else if let error = error as? RecoveryError, damagedRecord.contains(error) {
            category = .localRecord
        } else {
            category = .unclear
        }
        return Self(category: category, stage: stage, request: observation?.kind, httpStatus: status,
                    serverReference: observation?.serverReference)
    }

    /// The account host's saved sign-in check, which uses its own request outside this client.
    public static func sessionCheck(httpStatus: Int?, error: (any Error)?) -> Self {
        let category: Category
        if let httpStatus, httpStatus == 401 || httpStatus == 403 { category = .signIn }
        else if let httpStatus, httpStatus == 429 || (500...599).contains(httpStatus) { category = .service }
        else if let error = error as? URLError, networkCodes.contains(error.code) { category = .network }
        else { category = .unclear }
        return Self(category: category, stage: .sessionCheck, request: nil, httpStatus: httpStatus)
    }

    private static let networkCodes: Set<URLError.Code> = [
        .notConnectedToInternet, .networkConnectionLost, .cannotFindHost, .cannotConnectToHost,
        .dnsLookupFailed, .timedOut, .internationalRoamingOff, .dataNotAllowed, .callIsActive
    ]

    private static let damagedRecord: Set<RecoveryError> = [
        .invalidSnapshot, .receiptMismatch, .legacyStorageFormat, .keyMismatch, .unsafeDirectory
    ]

    func message(_ language: LioLanguage) -> String {
        switch category {
        case .network:
            language.text("You seem to be offline, so this conversation couldn’t open.",
                          "网络似乎没有连接，所以这段对话暂时打不开。")
        case .signIn:
            language.text("Your sign-in has expired or was turned off, so this conversation couldn’t open.",
                          "登录已过期或已被停用，所以这段对话暂时打不开。")
        case .service:
            language.text("Our service is having a problem or is under maintenance. This isn’t your connection.",
                          "服务暂时出错或正在维护，不是你的网络问题。")
        case .localRecord:
            language.text("The conversation record saved on this device couldn’t be opened.",
                          "这台设备上保存的对话记录打不开。")
        case .unclear:
            language.text("This conversation couldn’t open, and the cause isn’t clear yet.",
                          "这段对话暂时打不开，具体情况还不清楚。")
        }
    }

    func nextStep(_ language: LioLanguage) -> String {
        switch category {
        case .network:
            language.text("Check your connection, then try again. Your messages and draft stay on this device.",
                          "请检查网络后重试。你的消息和草稿仍保留在本机。")
        case .signIn:
            language.text("You’ll need to sign in again to continue. Please take a screenshot first.",
                          "需要重新登录后才能继续，请先截图此页。")
        case .service:
            language.text("Please try again later. Your messages and draft stay on this device.",
                          "请稍后再试。你的消息和草稿仍保留在本机。")
        case .localRecord:
            language.text("Please don’t delete the app. Take a screenshot and let us know.",
                          "请先不要删除应用，截图此页并告诉我们。")
        case .unclear:
            language.text("Try again. If it still doesn’t open, take a screenshot and note the time.",
                          "请重试；如果仍打不开，请截图并记下时间。")
        }
    }
}
