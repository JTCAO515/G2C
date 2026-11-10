import Foundation

/// A display check only. Original timeline data and its state remain intact.
public enum LioPublicDisplay {
    private static let serviceDetails = #"运行|投递|上下文|回执|候选|版本号|核实|对账|读取|查询|确认结果|原(?:请求|操作|动作|字节)|(?:高德天气|后台|服务)接口|(?<![A-Za-z])(?:RUN|UNKNOWN|Needs|(?i:backend|payload|idempotency|scope|reconciliation|request\s+id|(?:signed|operation|request)\s+receipt|original\s+(?:request|action|operation)))(?![A-Za-z])"#
    private static let serviceURL = #"(?i:https?://(?:restapi\.amap\.com|api(?:-beta)?\.go2china\.space))(?=[/:?#\s)>，。]|$)"#

    public static func permitsText(_ text: String) -> Bool {
        text.range(of: serviceDetails, options: .regularExpression) == nil
            && text.range(of: serviceURL, options: .regularExpression) == nil
    }

    public static func permitsSource(_ url: URL) -> Bool {
        guard let host = url.host?.lowercased() else { return false }
        return host != "restapi.amap.com" && host != "api-beta.go2china.space" && host != "api.go2china.space"
    }
}
