import Foundation

/// The wording under the six steps of going to China (#1979, 58.1): G4's 「去办」 copy, bundled as
/// `LioTodoContent.v1.json`. Nothing is fetched and nothing here is written by the app.
///
/// The file keeps G4's flat dotted keys (`trip.todo.step1.item2.title`) and fields. Statuses were set from the
/// coordinator's review (`coord/notes/todo-policy-review-1128.md`): `ready` is shown, `pending_review` waits for a
/// rewrite and is hidden, `skip` is never shown. Which entries are shown on a given day is decided by one pure
/// function, `visibleItems(in:_:)`, so it can be tested without a view.
///
/// Ticks are not touched: the six rows keep the keys they always had (`LioTripTask.stepKeys`), and the item ids
/// here (`trip.todo.stepN.itemM`) are content ids only, never tick keys.
struct LioTodoContent: Equatable, Sendable {
    static let version = "g2c-todo-content.1"
    static let maximumBytes = 256 * 1024
    /// The chip groups' step names in G4's file, in the order of `LioTripTask.stepKeys`.
    static let chipStepNames = ["entry", "arrival", "stay", "money", "network", "local_transit"]
    /// The cities a metro button may name; a city left out of a button simply gets no button (Chengdu, 11-28: its C9 link is a Wuhan page).
    static let cities = Set(["beijing", "shanghai", "guangzhou", "shenzhen", "chengdu", "chongqing"])

    struct Text: Equatable, Sendable {
        let zh: String
        let en: String
        func text(_ language: LioLanguage) -> String { language.text(en, zh) }
    }

    enum Status: String, Sendable {
        case ready
        case pendingReview = "pending_review"
        case skip
    }

    enum Field: String, CaseIterable, Sendable { case title, body, tip, button }

    /// What a button does. A hub or city action has no address of its own: it needs the hub or city the traveller
    /// is at, and without one the button is left out.
    enum Action: Equatable, Sendable {
        case openURL(URL)
        case openHubGuide
        case openCityMetroGuide([String: URL])
    }

    struct Entry: Equatable, Sendable {
        let key: String
        let text: Text
        let status: Status
        let sourceIDs: [String]
        /// Nil for the step's own lines, which cite no source.
        let volatility: String?
        /// The last day the rule it cites applies, `yyyy-MM-dd`; shown through that day, hidden after it.
        let expires: String?
        /// An IANA zone for `expires`; Beijing time when absent.
        let expiresZone: String?
        let action: Action?
    }

    struct Item: Equatable, Sendable, Identifiable {
        /// `trip.todo.step1.item2`
        let id: String
        let step: Int
        let number: Int
        let title: Entry
        let body: Entry
        let tip: Entry?
        let button: Entry?

        var entries: [Entry] { [title, body] + [tip, button].compactMap { $0 } }
    }

    struct Chip: Equatable, Sendable { let text: Text }

    struct Step: Equatable, Sendable {
        let number: Int
        let items: [Item]
        /// Shown instead of `reminder` once the traveller has ticked the step.
        let done: Entry
        let reminder: Entry
        /// The question wording by name (`nationality`, `date`, `flight_or_train`, `budget`).
        let prompts: [String: Entry]
        /// A slot for a passport-specific line; empty in 58.1 (`{nationality_note}`), so the row is hidden.
        let note: Entry?
        let chips: [Chip]
    }

    let steps: [Step]

    // MARK: - The bundled file

    /// Nil when the bundled file cannot be read or fails the checks; the trip home then shows its rows as before.
    static func bundled() -> LioTodoContent? { bundledContent }

    private static let bundledContent: LioTodoContent? = {
        guard let url = Bundle.module.url(forResource: "LioTodoContent.v1", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? decode(data)
    }()

    /// The step for a trip home row key (`entry`, `arrival`, `hotel`, `payment`, `internet`, `local`).
    func step(forTaskKey key: String) -> Step? {
        LioTripTask.stepKeys.firstIndex(of: key).flatMap { $0 < steps.count ? steps[$0] : nil }
    }
}

// MARK: - Checks on the way in

/// The first thing wrong with a content file: where, and what.
struct LioTodoContentError: Error, Equatable, CustomStringConvertible {
    let location: String
    let problem: String
    var description: String { "\(location): \(problem)" }
}

extension LioTodoContent {
    /// G4's limits in characters: (Chinese, English).
    static let limits: [String: (zh: Int, en: Int)] = [
        "title": (12, 40), "body": (40, 100), "button": (6, 100), "tip": (30, 100), "chip": (12, 24),
    ]
    private static let volatilities: Set<String> = ["low", "medium", "high"]
    private static var sourceID: NSRegularExpression { try! NSRegularExpression(pattern: #"^C9:[0-9]{2}$"#) }
    private static var placeholder: NSRegularExpression { try! NSRegularExpression(pattern: #"\{([a-z_]+)\}"#) }
    /// G4's words to avoid: promises, medical, religion and business topics, and telling a traveller they need no visa.
    private static var restricted: NSRegularExpression {
        try! NSRegularExpression(
            pattern: #"保证|一定|医疗|用药|宗教|商务|你可以免签|无需办签证|不需要签证|\b(?:guaranteed?|medical|medication|religion|business)\b|you (?:can enter visa-free|don[’']t need a visa)"#,
            options: [.caseInsensitive])
    }

    static func decode(_ data: Data) throws -> LioTodoContent {
        guard data.count <= maximumBytes else { throw fail("file", "larger than \(maximumBytes) bytes") }
        guard let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
            throw fail("file", "expected a JSON object")
        }
        guard Set(root.keys) == ["version", "entries", "chips"], root["version"] as? String == version else {
            throw fail("file", "expected version \(version) with entries and chips")
        }
        guard let entries = root["entries"] as? [String: Any], !entries.isEmpty else { throw fail("entries", "expected an object") }
        // A JSON object read into a dictionary keeps one of two equal keys, so count them in the text as well.
        let written = String(decoding: data, as: UTF8.self).components(separatedBy: "\"trip.").count - 1
        guard written == entries.count else { throw fail("entries", "an entry id is used twice") }

        var items: [Int: [Int: [Field: Entry]]] = [:]
        var stepLevel: [Int: [String: Entry]] = [:]
        for key in entries.keys.sorted() {
            guard let place = Place(key) else { throw fail(key, "not a step or item key") }
            guard let object = entries[key] as? [String: Any] else { throw fail(key, "expected an object") }
            let entry = try parseEntry(key: key, place: place, object)
            switch place {
            case .item(let step, let number, let field): items[step, default: [:]][number, default: [:]][field] = entry
            case .step(let step, let name): stepLevel[step, default: [:]][name] = entry
            }
        }

        let chipGroups = try parseChips(root["chips"])
        var steps: [Step] = []
        for number in 1...LioTripTask.stepKeys.count {
            let location = "step\(number)"
            var built: [Item] = []
            for itemNumber in (items[number] ?? [:]).keys.sorted() {
                let fields = items[number]![itemNumber]!
                let id = "trip.todo.step\(number).item\(itemNumber)"
                guard let title = fields[.title], let body = fields[.body] else { throw fail(id, "an item has a title and a body") }
                let item = Item(id: id, step: number, number: itemNumber, title: title, body: body, tip: fields[.tip], button: fields[.button])
                let first = item.entries[0]
                for other in item.entries.dropFirst() where !sameMetadata(first, other) {
                    throw fail(other.key, "status, sources, volatility and expiry must match the item's title")
                }
                built.append(item)
            }
            guard !built.isEmpty else { throw fail(location, "a step has at least one item") }
            let level = stepLevel[number] ?? [:]
            guard let done = level["done"], let reminder = level["reminder"] else { throw fail(location, "missing done or reminder line") }
            let prompts = level.filter { $0.key.hasPrefix("prompt.") }.reduce(into: [String: Entry]()) {
                $0[String($1.key.dropFirst("prompt.".count))] = $1.value
            }
            steps.append(Step(number: number, items: built, done: done, reminder: reminder, prompts: prompts,
                              note: level["nationality_note"], chips: chipGroups[number - 1]))
        }
        return LioTodoContent(steps: steps)
    }

    private enum Place {
        case item(step: Int, number: Int, field: Field)
        case step(Int, name: String)

        init?(_ key: String) {
            let parts = key.split(separator: ".", omittingEmptySubsequences: false).map(String.init)
            guard parts.count >= 4, parts[0] == "trip", parts[1] == "todo", parts[2].hasPrefix("step"),
                  let step = Int(parts[2].dropFirst(4)), (1...LioTripTask.stepKeys.count).contains(step) else { return nil }
            let rest = Array(parts[3...])
            if rest.count == 2, rest[0].hasPrefix("item"), let number = Int(rest[0].dropFirst(4)), (1...8).contains(number),
               let field = Field(rawValue: rest[1]) {
                self = .item(step: step, number: number, field: field)
            } else if rest.count == 1, ["done", "reminder", "nationality_note"].contains(rest[0]) {
                self = .step(step, name: rest[0])
            } else if rest.count == 2, rest[0] == "prompt", !rest[1].isEmpty,
                      rest[1].allSatisfy({ $0.isASCII && ($0.isLowercase || $0 == "_") }) {
                self = .step(step, name: "prompt.\(rest[1])")
            } else {
                return nil
            }
        }
    }

    private static func fail(_ location: String, _ problem: String) -> LioTodoContentError {
        LioTodoContentError(location: location, problem: problem)
    }

    private static func sameMetadata(_ lhs: Entry, _ rhs: Entry) -> Bool {
        lhs.status == rhs.status && lhs.sourceIDs == rhs.sourceIDs && lhs.volatility == rhs.volatility
            && lhs.expires == rhs.expires && lhs.expiresZone == rhs.expiresZone
    }

    private static func parseEntry(key: String, place: Place, _ object: [String: Any]) throws -> Entry {
        var allowed: Set<String> = ["zh", "en", "status", "source_ids", "volatility", "expires"]
        var field = ""
        var isNote = false
        switch place {
        case .item(_, _, let itemField):
            field = itemField.rawValue
            if itemField == .button { allowed.insert("action") }
        case .step(_, let name):
            field = "body"
            isNote = name == "nationality_note"
        }
        // The zone is optional; every other field is required.
        let keys = Set(object.keys).subtracting(["expires_tz"])
        guard keys == allowed else { throw fail(key, "unexpected or missing fields") }
        let limit = limits[field] ?? limits["body"]!
        let text = try parseText(zh: object["zh"], en: object["en"], key: key, limit: limit, placeholder: isNote ? "nationality_note" : nil)

        guard let rawStatus = object["status"] as? String, let status = Status(rawValue: rawStatus) else {
            throw fail(key, "status must be ready, pending_review or skip")
        }
        guard let sources = object["source_ids"] as? [String], Set(sources).count == sources.count,
              sources.allSatisfy({ matches(sourceID, $0) }) else { throw fail(key, "source_ids must be distinct C9 references") }
        if case .item = place, sources.isEmpty { throw fail(key, "an item has a source") }
        var volatility: String?
        switch (object["volatility"], place) {
        case (let text as String, .item) where volatilities.contains(text): volatility = text
        case (is NSNull, .step): volatility = nil
        default: throw fail(key, "volatility must be low, medium or high for an item and null for a step line")
        }
        if case .step = place, !sources.isEmpty { throw fail(key, "a step line cites no source") }
        var expires: String?
        switch object["expires"] {
        case is NSNull: expires = nil
        case let text as String: expires = text
        default: throw fail(key, "expires must be a date or null")
        }
        var zone: String?
        if let raw = object["expires_tz"] {
            guard let identifier = raw as? String, expires != nil else { throw fail(key, "expires_tz goes with an expires date") }
            zone = identifier
        }
        var action: Action?
        if field == "button" {
            action = try parseAction(object["action"], key: key, sources: sources)
        }
        return Entry(key: key, text: text, status: status, sourceIDs: sources, volatility: volatility, expires: expires,
                     expiresZone: zone, action: action)
    }

    private static func matches(_ regex: NSRegularExpression, _ text: String) -> Bool {
        regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) != nil
    }

    /// One printable line in each language, within G4's limits and free of its restricted words. `placeholder` is the
    /// one slot a line may carry (`{nationality_note}`); every other line carries none.
    private static func parseText(zh: Any?, en: Any?, key: String, limit: (zh: Int, en: Int), placeholder name: String?) throws -> Text {
        func line(_ value: Any?, _ language: String, _ max: Int) throws -> String {
            let location = "\(key).\(language)"
            guard let text = value as? String, !text.isEmpty, text == text.trimmingCharacters(in: .whitespaces),
                  !text.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) || CharacterSet.newlines.contains($0) })
            else { throw fail(location, "expected one printable line") }
            guard text.unicodeScalars.count <= max else { throw fail(location, "\(text.unicodeScalars.count) characters, at most \(max)") }
            guard !matches(restricted, text) else { throw fail(location, "contains a restricted word or promise") }
            let range = NSRange(text.startIndex..., in: text)
            let slots = placeholder.matches(in: text, range: range).compactMap { Range($0.range(at: 1), in: text).map { String(text[$0]) } }
            guard slots == (name.map { [$0] } ?? []) else { throw fail(location, "wrong placeholder") }
            let plain = placeholder.stringByReplacingMatches(in: text, range: range, withTemplate: "")
            guard !plain.contains("{"), !plain.contains("}") else { throw fail(location, "stray brace") }
            return text
        }
        return Text(zh: try line(zh, "zh", limit.zh), en: try line(en, "en", limit.en))
    }

    private static func parseAction(_ value: Any?, key: String, sources: [String]) throws -> Action {
        guard let object = value as? [String: Any], let kind = object["kind"] as? String else {
            throw fail(key, "a button has an action")
        }
        func https(_ text: Any?) -> URL? {
            guard let text = text as? String, let url = URL(string: text), url.scheme == "https", url.host?.isEmpty == false,
                  url.user == nil, url.password == nil else { return nil }
            return url
        }
        switch kind {
        case "open_url":
            guard Set(object.keys) == ["kind", "url", "source_id"], let url = https(object["url"]),
                  let source = object["source_id"] as? String, sources.contains(source) else {
                throw fail(key, "open_url has an https address and one of the item's sources")
            }
            return .openURL(url)
        case "open_hub_guide":
            guard Set(object.keys) == ["kind", "data", "url_field"], object["data"] as? String == "C7/hubs.json",
                  object["url_field"] as? String == "official_url" else { throw fail(key, "open_hub_guide has the wrong fields") }
            return .openHubGuide
        case "open_city_metro_guide":
            guard Set(object.keys) == ["kind", "source_by_city", "url_by_city"],
                  let byCity = object["source_by_city"] as? [String: String], !byCity.isEmpty, Set(byCity.keys).isSubset(of: cities),
                  byCity.values.allSatisfy({ sources.contains($0) }),
                  let urls = object["url_by_city"] as? [String: String], Set(urls.keys) == Set(byCity.keys) else {
                throw fail(key, "open_city_metro_guide has cities among the six, each with a source and an address")
            }
            var resolved: [String: URL] = [:]
            for (city, text) in urls {
                guard let url = https(text) else { throw fail(key, "the address for \(city) is not https") }
                resolved[city] = url
            }
            return .openCityMetroGuide(resolved)
        default:
            throw fail(key, "this action is not supported")
        }
    }

    private static func parseChips(_ value: Any?) throws -> [[Chip]] {
        guard let groups = value as? [[String: Any]], groups.count == chipStepNames.count else {
            throw fail("chips", "expected one group for each of the six steps")
        }
        var seen: (zh: Set<String>, en: Set<String>) = ([], [])
        var result: [[Chip]] = []
        for (index, group) in groups.enumerated() {
            let name = chipStepNames[index]
            guard Set(group.keys) == ["step", "chips"], group["step"] as? String == name,
                  let chips = group["chips"] as? [[String: Any]], (3...4).contains(chips.count) else {
                throw fail("chips.\(name)", "expected the step's name and three or four chips")
            }
            var built: [Chip] = []
            for (position, chip) in chips.enumerated() {
                let key = "chips.\(name)[\(position + 1)]"
                guard Set(chip.keys) == ["zh", "en"] else { throw fail(key, "expected zh and en") }
                let text = try parseText(zh: chip["zh"], en: chip["en"], key: key, limit: limits["chip"]!, placeholder: nil)
                guard seen.zh.insert(text.zh.lowercased()).inserted, seen.en.insert(text.en.lowercased()).inserted else {
                    throw fail(key, "the same chip is used twice")
                }
                built.append(Chip(text: text))
            }
            result.append(built)
        }
        return result
    }
}

// MARK: - What is shown today

/// What the filter needs to know about the traveller and the day.
struct LioTodoContext: Equatable, Sendable {
    var now: Date
    /// The trip's city (a metro catalogue id), when chosen; picks the metro guide's address.
    var cityID: String?
    /// The confirmed arrival hub's official page, when a hub is confirmed; nothing confirms one yet.
    var hubGuideURL: URL?
    /// The passport-specific line for `{nationality_note}`; none in 58.1.
    var nationalityNote: LioTodoContent.Text?

    init(now: Date, cityID: String? = nil, hubGuideURL: URL? = nil, nationalityNote: LioTodoContent.Text? = nil) {
        self.now = now
        self.cityID = cityID
        self.hubGuideURL = hubGuideURL
        self.nationalityNote = nationalityNote
    }
}

extension LioTodoContent {
    enum Hidden: Equatable, Sendable {
        /// The coordinator's review left it out for now.
        case skipped
        /// Waiting for G4 to rewrite it.
        case awaitingRewrite
        case expired
        /// The expiry day or zone cannot be read, so the line is treated as past.
        case unreadableExpiry
        /// It still carries a `{slot}` nobody filled.
        case unresolvedPlaceholder
    }

    struct VisibleButton: Equatable, Sendable {
        let text: Text
        let destination: URL
    }

    struct VisibleItem: Equatable, Sendable, Identifiable {
        let id: String
        let title: Text
        let body: Text
        let tip: Text?
        /// Nil when the button's target is not known yet (no hub or city): the short text stays, the button does not.
        let button: VisibleButton?
    }

    /// Why an entry is not shown, or nil when it is. This is the whole rule for one line.
    static func hidden(_ entry: Entry, _ context: LioTodoContext) -> Hidden? {
        switch entry.status {
        case .skip: return .skipped
        case .pendingReview: return .awaitingRewrite
        case .ready: break
        }
        let slot = "{"
        if entry.text.zh.contains(slot) || entry.text.en.contains(slot) { return .unresolvedPlaceholder }
        guard let day = entry.expires else { return nil }
        // The last day counts: a rule that runs through 31 Dec shows all of 31 Dec.
        guard let last = LioTripDay(day) else { return .unreadableExpiry }
        let zone: TimeZone
        if let identifier = entry.expiresZone {
            guard let named = TimeZone(identifier: identifier) else { return .unreadableExpiry }
            zone = named
        } else {
            zone = LioTripChecklist.beijing
        }
        return LioTripDay(date: context.now, timeZone: zone) > last ? .expired : nil
    }

    /// Why an item is not shown, or nil when it is: any of its lines being hidden hides the item.
    static func hidden(_ item: Item, _ context: LioTodoContext) -> Hidden? {
        item.entries.lazy.compactMap { hidden($0, context) }.first
    }

    /// The items of a step shown today, in order.
    static func visibleItems(in step: Step, _ context: LioTodoContext) -> [VisibleItem] {
        step.items.compactMap { item in
            guard hidden(item, context) == nil else { return nil }
            return VisibleItem(id: item.id, title: item.title.text, body: item.body.text, tip: item.tip?.text,
                               button: item.button.flatMap { button(for: $0, context) })
        }
    }

    private static func button(for entry: Entry, _ context: LioTodoContext) -> VisibleButton? {
        let destination: URL?
        switch entry.action {
        case .openURL(let url): destination = url
        case .openHubGuide: destination = context.hubGuideURL
        case .openCityMetroGuide(let urls): destination = context.cityID.flatMap { urls[$0] }
        case nil: destination = nil
        }
        return destination.map { VisibleButton(text: entry.text, destination: $0) }
    }

    /// The step's one status line: the "done" line once ticked, else the reminder.
    static func stateLine(in step: Step, done: Bool, _ context: LioTodoContext) -> Text? {
        let entry = done ? step.done : step.reminder
        return hidden(entry, context) == nil ? entry.text : nil
    }

    /// A question's wording by name (`date`, `flight_or_train`, …), or nil when it is not shown.
    static func prompt(_ name: String, in step: Step, _ context: LioTodoContext) -> Text? {
        step.prompts[name].flatMap { hidden($0, context) == nil ? $0.text : nil }
    }

    /// The passport-specific line, with `{nationality_note}` filled; hidden whole while nothing fills it.
    static func note(in step: Step, _ context: LioTodoContext) -> Text? {
        guard let entry = step.note, entry.status == .ready, let fill = context.nationalityNote,
              entry.text.zh == "{nationality_note}", entry.text.en == "{nationality_note}",
              !fill.zh.isEmpty, !fill.en.isEmpty else { return nil }
        let resolved = Entry(key: entry.key, text: fill, status: entry.status, sourceIDs: entry.sourceIDs, volatility: entry.volatility,
                         expires: entry.expires, expiresZone: entry.expiresZone, action: nil)
        return hidden(resolved, context) == nil ? fill : nil
    }
}
