import Foundation

/// A display check only. Original timeline data and its state remain intact.
public enum LioPublicDisplay {
    // Match internal control markers, not ordinary travel words such as 查询 or 上下文.
    private static let serviceDetails = #"规划候选|消息投递|原回执|原(?:请求|操作|动作|字节)|(?:高德天气|后台|服务)接口|(?<![A-Za-z0-9_])(?:RUN|NEEDS|INTENT|RLS|UNKNOWN|Needs|(?i:backend|payload|idempotency|scope(?=["'`]?\s*[:=])|reconciliation|request\s+id|(?:signed|operation|request)\s+receipt|original\s+(?:request|action|operation)|run_id|message_id|conversation_id|scope_id|trip_id|job_id|attempt_id|operation_id|candidate_id|source_id|input_sha256|TripProposal|message-send|commit_unknown))(?![A-Za-z0-9_])|(?i:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"#
    private static let serviceURL = #"(?i:https?://(?:restapi\.amap\.com|api(?:-beta)?\.go2china\.space)(?:\.|%2e)?)(?=[/:?#\s)>，。]|$)"#
    private static let executionDetails = #"<\s*/?\s*(?:think|analysis|tool_call|tool_result|function_call)(?:\s|>)|\b(?:tool_calls?|function_call)\b|\b(?:calling|invoking)\s+amap\b|工具调用|调用\s*(?:高德|amap)"#
    private static let serviceHosts: Set<String> = ["restapi.amap.com", "api-beta.go2china.space", "api.go2china.space"]
    private static let urlWrapping = CharacterSet(charactersIn: "\"')]}`，。,.!;:")

    public static func permitsText(_ text: String) -> Bool {
        guard text.range(of: serviceDetails, options: .regularExpression) == nil,
              text.range(of: executionDetails, options: [.regularExpression, .caseInsensitive]) == nil,
              text.range(of: serviceURL, options: .regularExpression) == nil else { return false }
        var next = text.startIndex
        while let scheme = text.range(of: "https?://", options: [.regularExpression, .caseInsensitive],
                                      range: next..<text.endIndex) {
            // Keep punctuation in user information until URL parses the host.
            // Continue after the scheme so adjacent URLs can still be found.
            next = scheme.upperBound
            let authority = text[next...].prefix { !$0.isWhitespace && !"/?#<>，".contains($0) }
            func containsServiceHost(_ authority: Substring) -> Bool {
                let candidate = (String(text[scheme]) + String(authority)).trimmingCharacters(in: urlWrapping)
                guard let url = URL(string: candidate), let host = normalizedHost(url) else { return false }
                return serviceHosts.contains(host)
            }
            if containsServiceHost(authority) { return false }
            // Also check the original prose boundary. A closing parenthesis or
            // quote can be followed immediately by text that is not part of the URL.
            let wrapped = authority.prefix { !"()（）[]{}\"'".contains($0) }
            if wrapped.endIndex != authority.endIndex, containsServiceHost(wrapped) { return false }
        }
        return true
    }

    public static func permitsSource(_ url: URL) -> Bool {
        guard let host = normalizedHost(url) else { return false }
        return !serviceHosts.contains(host)
    }

    private static func normalizedHost(_ url: URL) -> String? {
        guard let decoded = url.host, !decoded.isEmpty else { return nil }
        let ascii: String
        if decoded.utf8.allSatisfy({ $0 < 128 }) {
            ascii = decoded
        } else {
            // URL.host can expose decoded Unicode from a percent-encoded host.
            // Set the host separately so Foundation applies IDNA before comparison.
            var components = URLComponents()
            components.scheme = "https"
            components.host = decoded
            guard let host = components.url?.host, host.utf8.allSatisfy({ $0 < 128 }) else { return nil }
            ascii = host
        }
        let host = ascii.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        return host.isEmpty ? nil : host
    }
}
