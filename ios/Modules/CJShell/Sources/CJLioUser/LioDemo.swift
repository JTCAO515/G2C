import Foundation

extension LioService {
    /// Local sample content. No credentials or paid calls. Each chat has its own sample plan.
    public static var demo: LioService {
        let session = LioDemo.Session()
        return LioService { question in
            AsyncStream { continuation in
                let task = Task {
                    defer { continuation.finish() }
                    do {
                        try await Task.sleep(for: .milliseconds(450))
                        let reply = await session.reply(to: question)
                        if let activity = reply.activity {
                            continuation.yield(.activity(activity))
                            try await Task.sleep(for: .milliseconds(650))
                        }
                        for part in reply.parts {
                            try await Task.sleep(for: .milliseconds(220))
                            continuation.yield(.text(part))
                        }
                        if let source = reply.source { continuation.yield(.source(source)) }
                        if let itinerary = reply.itinerary {
                            await session.save(itinerary)
                            continuation.yield(.savedItinerary(itinerary))
                        }
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
        var itinerary: LioItinerary? = nil
    }

    actor Session {
        private var askedAboutPace = false
        private var saved: LioItinerary?

        func reply(to question: LioQuestion) -> Reply {
            let lang = question.language
            let text = question.text.lowercased()
            if askedAboutPace {
                if text.contains("slow") || text.contains("慢") || text.contains("轻松") {
                    return plan(lang, relaxed: true)
                }
                if text.contains("sights") || text.contains("busy") || text.contains("景点") {
                    return plan(lang, relaxed: false)
                }
            }
            if (text.contains("beijing") || text.contains("北京"))
                && (text.contains("plan") || text.contains("规划")) {
                askedAboutPace = true
                return Reply(parts: [
                    lang.text("For three days in Beijing, would you rather take it slow or see more sights?",
                              "北京三天，你想慢慢逛，还是多看几个景点？")
                ])
            }
            return LioDemo.reply(to: question)
        }

        func save(_ itinerary: LioItinerary) {
            saved = itinerary
            askedAboutPace = false
        }

        private func plan(_ language: LioLanguage, relaxed: Bool) -> Reply {
            let extra: [LioItinerary.Stop] = relaxed ? [] : [
                .init(id: "gallery", name: language.text("Gallery stop", "看看画廊"), time: "13:00",
                      point: .init(latitude: 39.925, longitude: 116.395), fixed: false)
            ]
            let itinerary = LioItinerary(
                id: saved?.id ?? "sample-beijing",
                title: language.text("Three days in Beijing", "北京三日行"),
                description: relaxed
                    ? language.text("I kept the pace easy and left each afternoon flexible.", "按你想慢慢逛的节奏，我把每天下午留得宽松一些。")
                    : language.text("I grouped nearby stops so you can see more each day.", "按你想多看几个景点的想法，我把相近的地点排在同一天。"),
                days: [
                    .init(number: 1, stops: [
                        .init(id: "old-town-walk", name: language.text("Old town walk", "老城散步"), time: "10:00",
                              point: .init(latitude: 39.93, longitude: 116.39), fixed: false),
                        .init(id: "hotel", name: language.text("Hotel check-in", "酒店入住"), time: "15:00",
                              point: nil, fixed: true)
                    ]),
                    .init(number: 2, stops: [
                        .init(id: "museum", name: language.text("Museum visit", "逛博物馆"), time: relaxed ? "10:30" : "09:00",
                              point: .init(latitude: 39.91, longitude: 116.40), fixed: false)
                    ] + extra + [
                        .init(id: "park", name: language.text("Afternoon in a park", "下午逛公园"), time: "15:00",
                              point: .init(latitude: 39.92, longitude: 116.39), fixed: false)
                    ]),
                    .init(number: 3, stops: [
                        .init(id: "market", name: language.text("Morning market", "逛早市"), time: "09:30",
                              point: .init(latitude: 39.89, longitude: 116.41), fixed: false)
                    ])
                ])
            return Reply(parts: [
                language.text("Here’s a sample itinerary for your three days.", "这是给你安排的三天演示行程。")
            ], itinerary: itinerary)
        }
    }

    private static func reply(to question: LioQuestion) -> Reply {
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
