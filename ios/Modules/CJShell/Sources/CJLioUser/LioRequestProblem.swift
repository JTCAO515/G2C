import CJMessageClient
import CJMessageHTTP
import Foundation

/// Safe metadata only: no error description, URL, message, credential or original ID.
public enum LioProblemCause: String, Codable, Sendable, Equatable {
    case inactiveSession, unavailableCredentials, network, responseFormat, localRecord, cancelled, http, unknown
}

public struct LioRequestProblem: Error, Sendable, Equatable {
    public let diagnosis: LioFailureDiagnosis
    public let origin: LioFailureDiagnosis.Stage
    public let cause: LioProblemCause
    public let errorCode: Int?

    var needsReconnect: Bool { cause == .inactiveSession || cause == .unavailableCredentials }

    func message(_ language: LioLanguage) -> String {
        if needsReconnect {
            return language.text("Reconnect to keep chatting. Your messages and draft haven’t been cleared.",
                                 "这段对话需要重新连接。消息和草稿没有被清除。")
        }
        if cause == .responseFormat && diagnosis.category == .unclear {
            return language.text("The service reply couldn’t be read. Please try again later.",
                                 "服务返回的内容暂时无法显示，请稍后再试。")
        }
        if origin == .firstSendLookup && cause == .unknown {
            return language.text("This message’s reply hasn’t been confirmed yet.", "这条消息的回复还没有确认。")
        }
        return diagnosis.message(language)
    }

    func nextStep(_ language: LioLanguage) -> String {
        if origin == .firstSendLookup {
            return language.text("Read this message’s result again. It won’t be sent twice.", "请再次查看这条消息的回复，不会重复发送。")
        }
        if needsReconnect {
            return language.text("Reconnect to continue with the same chat.", "请重新连接，继续这段对话。")
        }
        return diagnosis.nextStep(language)
    }

    public init(_ error: any Error, stage: LioFailureDiagnosis.Stage,
         observation: LioTimelineHTTP.Observation? = nil) {
        if let failure = error as? Self { self = failure; return }
        diagnosis = .classify(error, stage: stage, observation: observation)
        origin = stage
        errorCode = (error as? URLError)?.code.rawValue
        if error is CancellationError { cause = .cancelled }
        else if case RecoveryError.inactive = error { cause = .inactiveSession }
        else if case MessageHTTPFailure.credentialsUnavailable = error { cause = .unavailableCredentials }
        else if error is URLError { cause = .network }
        else if let status = observation?.httpStatus, status != 200 { cause = .http }
        else if case MessageHTTPFailure.invalidResponse = error { cause = .responseFormat }
        else if error is DecodingError { cause = .responseFormat }
        else if diagnosis.category == .localRecord { cause = .localRecord }
        else { cause = .unknown }
    }
}
