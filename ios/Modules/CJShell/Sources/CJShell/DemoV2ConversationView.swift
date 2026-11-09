#if os(iOS)
import SwiftUI
import CJRunClient

// Presentation values. The service adapter will map verified events and receipts to these values.
struct DemoV2Message: Identifiable {
    let id: String
    let fromUser: Bool
    let text: String
    var status: String?
    var sources: [DemoV2Source] = []
    var card: DemoV2Card?
}

struct DemoV2Source: Identifiable {
    let id: String
    let title: String
    let details: String
    var link: URL? = nil
}

struct DemoV2Day: Identifiable {
    let id: String
    let title: String
    let stops: [Stop]
    var date: String? = nil

    struct Stop: Identifiable {
        let id: String
        let time: String
        let place: String
        let source: String
        var locked: Bool? = false
        var location: String? = nil
    }
}

enum DemoV2Card {
    case needs([Detail])
    case itinerary([DemoV2Day])
    case changes(before: String, after: String, locked: String?)
    case memory(String)

    struct Detail: Identifiable {
        let id: String
        let label: String
        let value: String
    }
}

enum DemoV2CardAction {
    case confirmNeeds, editNeeds, adoptTrip, reviseTrip, applyChange, remember, dismissMemory
}

enum DemoV2DeliveryNotice: Equatable {
    case offline, dailyLimit, unknown, notObserved, rejected

    func text(_ language: ShellLanguage) -> String {
        switch self {
        case .offline:
            language.text("You’re offline. Check your connection. Your draft is still here.",
                          "网络暂不可用，请检查连接。草稿已保留。")
        case .dailyLimit:
            language.text("You’ve used today’s 40 questions. Try again tomorrow.",
                          "今天的 40 个问题已用完，明天再试。")
        case .unknown:
            language.text("We can’t confirm the result yet. Check the original action.",
                          "暂时无法确认结果，请核对原操作。")
        case .notObserved:
            language.text("The original receipt hasn’t appeared yet. You can check it again.",
                          "暂未看到原回执，可以继续核对原操作。")
        case .rejected:
            language.text("We couldn’t complete this request. Review your draft and try again.",
                          "暂时无法完成。请检查草稿后重试。")
        }
    }

    var allowsOriginalCheck: Bool { self == .unknown || self == .notObserved }
}

struct DemoV2ConversationView: View {
    let language: ShellLanguage
    let messages: [DemoV2Message]
    let activeCardID: String?
    @Binding var draft: String
    let canSend: Bool
    let onSend: () -> Void
    let onAction: (String, DemoV2CardAction) -> Void
    var deliveryNotice: DemoV2DeliveryNotice? = nil
    var onCheckOriginal: (() -> Void)? = nil

    @State private var source: DemoV2Source?
    @FocusState private var composing: Bool

    private var examples: [String] {
        [
            language.text("How do I take the metro in Shanghai?", "在上海怎么坐地铁？"),
            language.text("Plan a three-day trip to Beijing.", "帮我规划北京三天两晚的旅行。"),
            language.text("Where should I stay to explore Chengdu’s old town?", "在成都住哪里方便逛老城区？"),
            language.text("I like taking trips slowly and staying in quiet hotels.", "我旅行时喜欢慢一点，也喜欢安静的酒店。")
        ]
    }

    var body: some View {
        ScrollViewReader { scroll in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if messages.isEmpty { welcome }
                    ForEach(messages) { message in
                        messageView(message)
                    }
                    Color.clear.frame(height: 1).accessibilityHidden(true).id("demo-v2-latest")
                }
                .padding(16)
            }
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .bottom, spacing: 0) { composer }
            .onChange(of: messages.last?.id) { _, _ in scroll.scrollTo("demo-v2-latest", anchor: .bottom) }
        }
        .sheet(item: $source) { selection in
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        ShellCardHeading(title: selection.title, symbol: "doc.text")
                        RunSelectableText(text: selection.details)
                        if let link = selection.link {
                            Link(destination: link) {
                                ShellActionLabel(title: language.text("Open original source", "打开原始来源"), symbol: "arrow.up.right.square")
                            }
                            .buttonStyle(ShellActionButtonStyle())
                        }
                    }
                    .padding(16)
                }
                .navigationTitle(language.text("Source", "来源"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button(language.text("Done", "完成")) { source = nil }
                    }
                }
            }
        }
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 12) {
            ShellCardHeading(title: language.text("What would you like to do in China?", "想在中国做什么？"), symbol: "bubble.left")
            ForEach(examples, id: \.self) { example in
                action(example, symbol: "arrow.up.left") {
                    draft = example
                    composing = true
                }
            }
        }
        .shellCard()
    }

    private func messageView(_ message: DemoV2Message) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if let status = message.status {
                Label(status, systemImage: "clock")
                    .font(.footnote)
                    .accessibilityIdentifier("demo.v2.run-status")
            }
            if !message.text.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(message.fromUser ? language.text("You", "你") : language.text("Assistant", "助手"))
                        .font(.footnote.weight(.semibold))
                    RunSelectableText(text: message.text)
                }
                .shellCard(fill: message.fromUser ? Color.accentColor.opacity(0.12) : Color(uiColor: .secondarySystemBackground))
                .padding(message.fromUser ? .leading : .trailing, 24)
            }
            ForEach(message.sources) { item in
                action(item.title, symbol: "doc.text") { source = item }
            }
            if let card = message.card {
                cardView(card, id: message.id, enabled: activeCardID == message.id)
            }
        }
    }

    private func cardView(_ card: DemoV2Card, id: String, enabled: Bool) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            switch card {
            case .needs(let details):
                ShellCardHeading(title: language.text("Trip details", "旅行需求"), symbol: "list.clipboard")
                ForEach(details) { detail in
                    Text(detail.label).font(.footnote.weight(.semibold))
                    RunReadableText(text: detail.value)
                }
                decision(language.text("Confirm", "确认"), symbol: "checkmark", id: id, event: .confirmNeeds)
                decision(language.text("Edit", "修改"), symbol: "pencil", id: id, event: .editNeeds, primary: false)
            case .itinerary(let days):
                ShellCardHeading(title: language.text("Suggested itinerary", "行程建议"), symbol: "map")
                ForEach(days) { day in DemoV2DayCard(day: day, language: language) }
                decision(language.text("Use this plan", "采用"), symbol: "checkmark", id: id, event: .adoptTrip)
                decision(language.text("Keep editing", "我再改改"), symbol: "pencil", id: id, event: .reviseTrip, primary: false)
            case .changes(let before, let after, let locked):
                ShellCardHeading(title: language.text("Proposed changes", "修改建议"), symbol: "pencil")
                Text(language.text("Before", "修改前")).font(.footnote.weight(.semibold))
                RunReadableText(text: before)
                Text(language.text("After", "修改后")).font(.footnote.weight(.semibold))
                RunReadableText(text: after)
                if let locked { Label(locked, systemImage: "lock") }
                decision(language.text("Apply changes", "采用"), symbol: "checkmark", id: id, event: .applyChange)
            case .memory(let text):
                ShellCardHeading(title: language.text("Remember this preference?", "记住这个偏好吗？"), symbol: "bookmark")
                RunReadableText(text: text)
                decision(language.text("Remember", "记住"), symbol: "bookmark.fill", id: id, event: .remember)
                decision(language.text("No thanks", "不用"), symbol: "xmark", id: id, event: .dismissMemory, primary: false)
            }
        }
        .disabled(!enabled)
        .shellCard()
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let notice = deliveryNotice {
                VStack(alignment: .leading, spacing: 6) {
                    RunReadableText(text: notice.text(language), style: .caption)
                        .accessibilityIdentifier("demo.v2.delivery-notice")
                    if notice.allowsOriginalCheck, let onCheckOriginal {
                        action(language.text("Check original action", "核对原操作"), symbol: "magnifyingglass", perform: onCheckOriginal)
                    }
                }
                .padding(.horizontal, 16)
            }
            composerRow
        }
        .padding(.vertical, 8)
        .background(.background)
    }

    private var composerRow: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextField(language.text("Ask anything", "问点什么"), text: $draft, axis: .vertical)
                .focused($composing)
                .lineLimit(1...4)
                .padding(12)
                .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
                .accessibilityIdentifier("demo.v2.draft")
            if canSend {
                Button {
                    composing = false
                    onSend()
                } label: {
                    Label(language.text("Send", "发送"), systemImage: "arrow.up")
                }
                .buttonStyle(AssistantSendButtonStyle())
                .accessibilityIdentifier("demo.v2.send")
            } else {
                Image(systemName: "arrow.up")
                    .frame(width: 44, height: 44)
                    .foregroundStyle(.secondary)
                    .accessibilityHidden(true)
            }
        }
        .padding(.horizontal, 16)
    }

    private func decision(_ title: String, symbol: String, id: String, event: DemoV2CardAction,
                          primary: Bool = true) -> some View {
        action(title, symbol: symbol, primary: primary) { onAction(id, event) }
    }

    private func action(_ title: String, symbol: String, primary: Bool = false,
                        perform: @escaping () -> Void) -> some View {
        Button(action: perform) { ShellActionLabel(title: title, symbol: symbol) }
            .buttonStyle(ShellActionButtonStyle(emphasized: primary))
    }
}

extension DemoV2Dialogue.Event.TripCandidate {
    func displayedDays(language: ShellLanguage, sourceLabels: [String: String]) -> [DemoV2Day] {
        days.enumerated().map { index, day in
            let title = day.date == nil ? language.text("Date to confirm", "日期待确认")
                : language.text("Day \(index + 1)", "第 \(index + 1) 天")
            let stops = day.items.map { item in
                let start = item.starts_at ?? language.text("Start unknown", "开始时间未知")
                let end = item.ends_at ?? language.text("End unknown", "结束时间未知")
                let zone = item.time_zone ?? language.text("Time zone unknown", "时区未知")
                let names = item.source_ids.compactMap { sourceLabels[$0] }
                let source = names.count == item.source_ids.count && !names.isEmpty ? names.joined(separator: " · ")
                    : language.text("No verified source available", "暂无可核实来源")
                return DemoV2Day.Stop(id: item.item_id, time: "\(start) – \(end) · \(zone)",
                                      place: item.label, source: source, locked: item.fixed,
                                      location: item.place ?? language.text("Place to confirm", "地点待确认"))
            }
            return DemoV2Day(id: day.date ?? "unknown-day-\(index)", title: title, stops: stops, date: day.date)
        }
    }
}

struct DemoV2DayCard: View {
    let day: DemoV2Day
    let language: ShellLanguage
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                expanded.toggle()
            } label: {
                ShellActionLabel(title: day.title, symbol: "calendar", detail: day.date,
                                 accessory: expanded ? "chevron.down" : "chevron.right")
            }
            .buttonStyle(ShellActionButtonStyle())
            .accessibilityLabel(day.title)
            .accessibilityValue([expanded ? language.text("Expanded", "已展开") : language.text("Collapsed", "已折叠"), day.date]
                .compactMap { $0 }.joined(separator: " · "))
            if expanded {
                ForEach(day.stops) { stop in
                    VStack(alignment: .leading, spacing: 4) {
                        ShellCardHeading(title: stop.place, symbol: stop.locked == true ? "lock" : "mappin")
                        if stop.locked == true { Text(language.text("Fixed", "固定安排")).font(.footnote) }
                        if stop.locked == nil { Text(language.text("Fixed status unknown", "固定状态未知")).font(.footnote) }
                        if let location = stop.location { RunReadableText(text: location) }
                        RunReadableText(text: stop.time)
                        RunReadableText(text: stop.source, style: .caption)
                    }
                    .padding(.horizontal, 12)
                }
            }
        }
    }
}
#endif
