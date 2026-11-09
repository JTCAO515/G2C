import Foundation

/// Presentation state built from verified events. Transport EOF and client time
/// do not change the observed RUN stage.
struct DemoV2RunProjection {
    private(set) var answer = ""
    private(set) var status: DemoV2Dialogue.Event.Status?
    private(set) var sources: [DemoV2Dialogue.Event.Source] = []

    mutating func apply(_ event: DemoV2Dialogue.Event) {
        switch event.payload {
        case .answer(let delta):
            answer += delta.text
        case .status(let value):
            status = value
        case .source(let value):
            if let index = sources.firstIndex(where: { $0.source_id == value.source_id }) { sources[index] = value }
            else { sources.append(value) }
        case .card, .trip, .memory:
            break
        }
    }

    func activity(_ language: ShellLanguage) -> String? {
        guard let status else { return nil }
        switch status.stage {
        case .queued: return language.text("Waiting to start", "等待开始")
        case .running: return language.text("Preparing an answer", "正在准备回答")
        case .tool:
            switch status.tool_kind {
            case "place": return language.text("Looking up places", "正在查找地点")
            case "route": return language.text("Checking the route", "正在查询路线")
            case "weather": return language.text("Checking the weather", "正在查询天气")
            default: return language.text("Checking information", "正在核对资料")
            }
        case .completed: return language.text("Answer complete", "回答已完成")
        case .failed: return language.text("Couldn’t finish the answer", "未能完成回答")
        case .cancelled: return language.text("Answer cancelled", "已取消回答")
        case .contextInvalid: return language.text("Trip details changed. Check the original result.", "旅行信息已变化，请核对原结果。")
        case .unknown: return language.text("The result is still unknown", "结果暂未确认")
        }
    }
}
