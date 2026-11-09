import Foundation

extension LioService {
    /// Local sample content. No network, credentials or paid calls.
    public static let demo = LioService { question in
        AsyncStream { continuation in
            let task = Task {
                defer { continuation.finish() }
                do {
                    try await Task.sleep(for: .milliseconds(450))
                    let reply = LioDemo.reply(to: question)
                    if let activity = reply.activity {
                        continuation.yield(.activity(activity))
                        try await Task.sleep(for: .milliseconds(650))
                    }
                    for part in reply.parts {
                        try await Task.sleep(for: .milliseconds(220))
                        continuation.yield(.text(part))
                    }
                    if let source = reply.source { continuation.yield(.source(source)) }
                    continuation.yield(.finished)
                } catch is CancellationError {
                    // Closing the view cancels the local demonstration.
                } catch {
                    continuation.yield(.failed(.unfinished))
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}

enum LioDemo {
    static func examples(_ language: LioLanguage) -> [String] {
        [
            language.text("How do I take the metro in Shanghai?", "在上海怎么坐地铁？"),
            language.text("Plan a three-day trip to Beijing.", "帮我规划北京三天两晚的旅行。"),
            language.text("Where should I stay to explore Chengdu’s old town?", "在成都住哪里方便逛老城区？"),
            language.text("I like slow trips and quiet hotels.", "我喜欢慢一点的旅行，也喜欢安静的酒店。")
        ]
    }

    struct Reply {
        var activity: LioActivity? = nil
        let parts: [String]
        var source: LioSource? = nil
    }

    static func reply(to question: LioQuestion) -> Reply {
        let lang = question.language
        let text = question.text.lowercased()
        if text.contains("metro") || text.contains("地铁") {
            return Reply(activity: .directions, parts: [
                lang.text("Start by finding the station nearest you. ", "先找离你最近的地铁站。"),
                lang.text("Follow the line number and the name of the last stop to find the right platform. ",
                          "进站后，看线路编号和终点站名称，就能找到正确方向的站台。"),
                lang.text("Tell me where you’re starting and where you want to go.", "告诉我你从哪儿出发、想去哪里吧。")
            ], source: LioSource(id: "sample-metro", title: lang.text("Metro signs · Demo example", "地铁指示牌 · 演示示例"), url: nil))
        }
        if text.contains("beijing") || text.contains("北京") {
            return Reply(parts: [
                lang.text("When are you visiting Beijing? ", "你打算什么时候去北京？"),
                lang.text("And would you rather see the main sights or take it slow?", "你想多逛几个景点，还是每天轻松一点？")
            ])
        }
        if text.contains("chengdu") || text.contains("成都") {
            return Reply(activity: .places, parts: [
                lang.text("Would you rather be near a metro stop or on a quiet street? ",
                          "你更想住在地铁站附近，还是安静一点的街区？"),
                lang.text("That will help narrow down where to stay.", "我可以按你更在意的那一点来推荐。")
            ])
        }
        if text.contains("quiet") || text.contains("安静") {
            return Reply(parts: [
                lang.text("Got it. You’d like some room to breathe between stops and somewhere quiet to sleep.",
                          "明白了，你喜欢在景点之间留点空闲，晚上住在安静的地方。")
            ])
        }
        return Reply(parts: [
            lang.text("I can show a few sample replies here. Try asking how to take the metro in Shanghai.",
                      "这里可以试几个示例。你可以问我在上海怎么坐地铁。")
        ])
    }
}
