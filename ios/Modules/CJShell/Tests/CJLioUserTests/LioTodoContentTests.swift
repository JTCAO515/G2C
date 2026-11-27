import Foundation
import Testing
@testable import CJLioUser

/// #1979 / G4: the words under the six steps of 「去办」. The file's checks, the one pure function that says what is
/// shown today, and that the six rows keep the tick keys they always had (views are not compiled on macOS, so the
/// rules live here, in both languages).
struct LioTodoContentTests {
    private static let shanghai = TimeZone(identifier: "Asia/Shanghai")!

    private static func at(_ text: String, in zone: TimeZone = shanghai) -> Date {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = zone
        formatter.dateFormat = "yyyy-MM-dd HH:mm"
        return formatter.date(from: text)!
    }

    private static var resourceURL: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Sources/CJLioUser/Resources/LioTodoContent.v1.json")
    }

    private static func bundled() throws -> LioTodoContent { try #require(LioTodoContent.bundled()) }

    private static func ids(_ items: [LioTodoContent.VisibleItem]) -> [String] {
        items.map { $0.id.replacingOccurrences(of: "trip.todo.", with: "") }
    }

    // MARK: - The bundled file

    @Test func theBundledFileLoadsAndIsTheFileInTheSources() throws {
        let content = try Self.bundled()
        #expect(content.steps.count == 6)
        #expect(try LioTodoContent.decode(Data(contentsOf: Self.resourceURL)) == content)
        for step in content.steps {
            #expect(!step.items.isEmpty && !step.chips.isEmpty, "step \(step.number)")
            #expect((3...4).contains(step.chips.count), "step \(step.number)")
        }
        // Item ids are unique across the file.
        let ids = content.steps.flatMap { $0.items.map(\.id) }
        #expect(Set(ids).count == ids.count)
    }

    @Test func everyDateInTheBundledFileCanBeRead() throws {
        for step in try Self.bundled().steps {
            for entry in step.items.flatMap(\.entries) + [step.done, step.reminder] where entry.expires != nil {
                #expect(entry.expires.flatMap(LioTripDay.init) != nil, "\(entry.key)")
            }
        }
    }

    @Test func statusesFollowTheCoordinatorsReview() throws {
        let content = try Self.bundled()
        func status(_ step: Int, _ item: Int) -> LioTodoContent.Status? {
            content.steps[step - 1].items.first { $0.number == item }?.title.status
        }
        // coord/notes/todo-policy-review-1128.md
        #expect(status(1, 7) == .skip)
        #expect(status(4, 6) == .pendingReview)
        #expect(status(4, 7) == .pendingReview)
        for (step, item) in [(1, 6), (3, 5), (3, 6), (4, 8), (5, 6), (6, 6), (6, 7)] {
            #expect(status(step, item) == .ready, "step\(step).item\(item)")
        }
        // The two dated waiver lines keep their public end day; nothing else expires.
        let expiring = content.steps.flatMap { $0.items.flatMap(\.entries) }.filter { $0.expires != nil }
        #expect(Set(expiring.map(\.key)) == ["trip.todo.step1.item6.title", "trip.todo.step1.item6.body",
                                                   "trip.todo.step1.item6.button", "trip.todo.step1.item7.title",
                                                   "trip.todo.step1.item7.body", "trip.todo.step1.item7.button"])
        #expect(Set(expiring.compactMap(\.expires)) == ["2026-12-31", "2027-12-31"])
    }

    @Test func todayTheReviewedItemsAreShownAndTheHeldOnesAreNot() throws {
        let content = try Self.bundled()
        let context = LioTodoContext(now: Self.at("2026-11-28 10:00"))
        let shown = content.steps.map { Self.ids(LioTodoContent.visibleItems(in: $0, context)) }
        #expect(shown[0] == ["step1.item1", "step1.item2", "step1.item3", "step1.item4", "step1.item5", "step1.item6"])
        #expect(shown[1] == (1...5).map { "step2.item\($0)" })
        #expect(shown[2] == (1...6).map { "step3.item\($0)" })
        // item6 and item7 wait for G4's rewrite: the numbers in them are not shown.
        #expect(shown[3] == ["step4.item1", "step4.item2", "step4.item3", "step4.item4", "step4.item5", "step4.item8"])
        #expect(shown[4] == (1...6).map { "step5.item\($0)" })
        #expect(shown[5] == (1...7).map { "step6.item\($0)" })
    }

    // MARK: - What the filter hides

    private static func entry(_ key: String = "trip.todo.step1.item1.title", status: LioTodoContent.Status = .ready,
                              zh: String = "标题", en: String = "Title", expires: String? = nil,
                              zone: String? = nil) -> LioTodoContent.Entry {
        .init(key: key, text: .init(zh: zh, en: en), status: status, sourceIDs: ["C9:01"], volatility: "low",
              expires: expires, expiresZone: zone, action: nil)
    }

    @Test func statusDecidesFirst() {
        let context = LioTodoContext(now: Self.at("2026-11-28 10:00"))
        #expect(LioTodoContent.hidden(Self.entry(), context) == nil)
        #expect(LioTodoContent.hidden(Self.entry(status: .skip), context) == .skipped)
        #expect(LioTodoContent.hidden(Self.entry(status: .pendingReview), context) == .awaitingRewrite)
        // A skipped line stays skipped whatever its date says.
        #expect(LioTodoContent.hidden(Self.entry(status: .skip, expires: "2099-01-01"), context) == .skipped)
    }

    @Test func aLineWithAnUnfilledSlotIsHidden() {
        let context = LioTodoContext(now: Self.at("2026-11-28 10:00"))
        #expect(LioTodoContent.hidden(Self.entry(zh: "{nationality_note}", en: "{nationality_note}"), context) == .unresolvedPlaceholder)
        #expect(LioTodoContent.hidden(Self.entry(zh: "好", en: "See {nationality_note}"), context) == .unresolvedPlaceholder)
    }

    @Test func theDayItRunsThroughIsShownAndTheNextDayIsNot() {
        let line = Self.entry(expires: "2026-12-31")
        func hidden(_ now: String, in zone: TimeZone = Self.shanghai) -> LioTodoContent.Hidden? {
            LioTodoContent.hidden(line, LioTodoContext(now: Self.at(now, in: zone)))
        }
        #expect(hidden("2026-12-30 08:00") == nil)
        #expect(hidden("2026-12-31 00:00") == nil)
        #expect(hidden("2026-12-31 23:59") == nil)
        #expect(hidden("2027-01-01 00:00") == .expired)
        #expect(hidden("2027-03-01 12:00") == .expired)
    }

    @Test func theDayIsBeijingsNotThePhonesZone() {
        let line = Self.entry(expires: "2026-12-31")
        // 17:30 UTC on 31 Dec is already 1 Jan in Beijing, and 09:30 the same morning in Los Angeles.
        let instant = Self.at("2026-12-31 17:30", in: TimeZone(identifier: "UTC")!)
        #expect(LioTodoContent.hidden(line, LioTodoContext(now: instant)) == .expired)
        // 15:30 UTC on 31 Dec is 23:30 in Beijing: still the last day.
        let earlier = Self.at("2026-12-31 15:30", in: TimeZone(identifier: "UTC")!)
        #expect(LioTodoContent.hidden(line, LioTodoContext(now: earlier)) == nil)
    }

    @Test func aLineCanNameItsOwnZone() {
        let instant = Self.at("2026-12-31 17:30", in: TimeZone(identifier: "UTC")!)
        let los = Self.entry(expires: "2026-12-31", zone: "America/Los_Angeles")
        #expect(LioTodoContent.hidden(los, LioTodoContext(now: instant)) == nil)
        let late = Self.at("2027-01-01 09:00", in: TimeZone(identifier: "UTC")!)
        #expect(LioTodoContent.hidden(los, LioTodoContext(now: late)) == .expired)
        #expect(LioTodoContent.hidden(Self.entry(expires: "2026-12-31", zone: "Nowhere/City"), LioTodoContext(now: instant))
                == .unreadableExpiry)
    }

    @Test(arguments: ["", "soon", "2026-13-01", "2026-02-30", "2026-1-5", "26-12-31", "2026/12/31", "2026-12-31T00:00:00Z",
                      " 2026-12-31"])
    func aDateThatCannotBeReadCountsAsPast(text: String) {
        let context = LioTodoContext(now: Self.at("2026-11-28 10:00"))
        #expect(LioTodoContent.hidden(Self.entry(expires: text), context) == .unreadableExpiry, "\(text)")
    }

    @Test func anItemIsHiddenWhenAnyOfItsLinesIs() throws {
        let content = try Self.bundled()
        let item = try #require(content.steps[0].items.first { $0.number == 6 })
        #expect(item.entries.count == 3)
        #expect(LioTodoContent.hidden(item, LioTodoContext(now: Self.at("2026-12-31 12:00"))) == nil)
        #expect(LioTodoContent.hidden(item, LioTodoContext(now: Self.at("2027-01-01 12:00"))) == .expired)
        let after = LioTodoContent.visibleItems(in: content.steps[0], LioTodoContext(now: Self.at("2027-01-01 12:00")))
        #expect(Self.ids(after) == (1...5).map { "step1.item\($0)" })
    }

    @Test func theSkippedWaiverExtensionStaysOutOnAnyDay() throws {
        let content = try Self.bundled()
        for day in ["2026-11-28 10:00", "2027-06-01 10:00", "2027-12-31 10:00"] {
            let shown = LioTodoContent.visibleItems(in: content.steps[0], LioTodoContext(now: Self.at(day)))
            #expect(!Self.ids(shown).contains("step1.item7"), "\(day)")
        }
    }

    // MARK: - Buttons, lines, slots

    @Test func aHubButtonWaitsForAConfirmedHubAndAMetroButtonForTheCity() throws {
        let content = try Self.bundled()
        let now = Self.at("2026-11-28 10:00")
        func item(_ step: Int, _ number: Int, _ context: LioTodoContext) throws -> LioTodoContent.VisibleItem {
            try #require(LioTodoContent.visibleItems(in: content.steps[step - 1], context).first { $0.id.hasSuffix(".item\(number)") })
        }
        // No hub confirmed: the short text stays, the button does not.
        let plain = LioTodoContext(now: now)
        #expect(try item(2, 4, plain).button == nil)
        #expect(try item(2, 4, plain).body.zh.contains("进城路线"))
        #expect(try item(6, 1, plain).button == nil)
        #expect(try item(6, 3, plain).button == nil)
        #expect(try item(6, 3, plain).tip != nil)
        let hub = URL(string: "https://example.gov.cn/hub")!
        #expect(try item(2, 4, .init(now: now, hubGuideURL: hub)).button?.destination == hub)
        #expect(try item(6, 1, .init(now: now, hubGuideURL: hub)).button?.text.en == "Check the hub guide")
        // The metro page is the trip city's own; a city with no page gets no button.
        let beijing = try #require(try item(6, 3, .init(now: now, cityID: "beijing")).button)
        #expect(beijing.destination.host == "english.beijing.gov.cn")
        #expect(try item(6, 3, .init(now: now, cityID: "shanghai")).button?.destination.host == "english.shanghai.gov.cn")
        #expect(try item(6, 3, .init(now: now, cityID: "xian")).button == nil)
        // A plain link button always shows.
        #expect(try item(3, 4, plain).button?.destination.host == "www.nia.gov.cn")
    }

    @Test func everyLinkIsHttpsWithAHost() throws {
        for step in try Self.bundled().steps {
            for case let entry? in step.items.map(\.button) {
                switch entry.action {
                case .openURL(let url): #expect(url.scheme == "https" && url.host?.isEmpty == false, "\(entry.key)")
                case .openCityMetroGuide(let urls):
                    #expect(Set(urls.keys) == Set(LioTodoContent.cities), "\(entry.key)")
                    #expect(urls.values.allSatisfy { $0.scheme == "https" && $0.host?.isEmpty == false })
                case .openHubGuide: break
                case nil: Issue.record("\(entry.key) has no action")
                }
            }
        }
    }

    @Test func theStepLineIsTheDoneLineOnceTickedAndTheReminderBefore() throws {
        let step = try Self.bundled().steps[3]
        let context = LioTodoContext(now: Self.at("2026-11-28 10:00"))
        #expect(LioTodoContent.stateLine(in: step, done: false, context)?.zh == "买东西前，先确认手上的付款方式。")
        #expect(LioTodoContent.stateLine(in: step, done: true, context)?.en == "Payment prep marked as done.")
    }

    @Test func thePassportNoteRowIsHiddenWholeAndNeverShownAsASlot() throws {
        let step = try Self.bundled().steps[0]
        #expect(step.note?.text.zh == "{nationality_note}")
        let context = LioTodoContext(now: Self.at("2026-11-28 10:00"))
        #expect(LioTodoContent.note(in: step, context) == nil)
        // Every line the traveller can see is free of braces, in both languages.
        for step in try Self.bundled().steps {
            let shown = LioTodoContent.visibleItems(in: step, context)
            for item in shown {
                let text = [item.title, item.body, item.tip, item.button?.text].compactMap { $0 }.flatMap { [$0.zh, $0.en] }
                #expect(text.allSatisfy { !$0.contains("{") && !$0.contains("}") }, "\(item.id)")
            }
        }
        // Once a note is given for the slot, the row shows it.
        let note = LioTodoContent.Text(zh: "请按护照核对。", en: "Check for your passport.")
        #expect(LioTodoContent.note(in: step, LioTodoContext(now: context.now, nationalityNote: note)) == note)
        #expect(LioTodoContent.note(in: try Self.bundled().steps[1], LioTodoContext(now: context.now, nationalityNote: note)) == nil)
    }

    @Test func questionWordingIsLookedUpByName() throws {
        let content = try Self.bundled()
        let context = LioTodoContext(now: Self.at("2026-11-28 10:00"))
        #expect(LioTodoContent.prompt("date", in: content.steps[1], context)?.zh == "你哪天到中国？")
        #expect(LioTodoContent.prompt("flight_or_train", in: content.steps[1], context)?.en == "Flight or train number, if known?")
        #expect(LioTodoContent.prompt("nationality", in: content.steps[0], context)?.zh == "这次用哪国护照？")
        #expect(LioTodoContent.prompt("date", in: content.steps[0], context) == nil)
    }

    @Test func chipsAreOneGroupPerStepInTheRowOrderAndSendTheirOwnLanguage() throws {
        let content = try Self.bundled()
        #expect(content.steps[0].chips.first?.text.zh == "去哪查入境规定？")
        #expect(content.steps[0].chips.first?.text.en == "Link to entry rules?")
        #expect(content.steps[5].chips.contains { $0.text.en == "Book rail with passport?" })
        for language in [LioLanguage.english, .chinese] {
            let all = content.steps.flatMap(\.chips).map { $0.text.text(language) }
            #expect(Set(all).count == all.count)
            #expect(all.count == content.steps.map(\.chips.count).reduce(0, +))
        }
    }

    // MARK: - The six rows and their ticks

    @Test func theSixStepsAreTheSixRowKeysInOrder() throws {
        let content = try Self.bundled()
        #expect(LioTripTask.stepKeys == ["entry", "arrival", "hotel", "payment", "internet", "local"])
        for (index, key) in LioTripTask.stepKeys.enumerated() {
            #expect(content.step(forTaskKey: key)?.number == index + 1, "\(key)")
        }
        #expect(content.step(forTaskKey: "medical-card") == nil)
        #expect(content.step(forTaskKey: "booking.x") == nil)
        #expect(LioTodoContent.chipStepNames.count == LioTripTask.stepKeys.count)
    }

    @Test func contentIdsNeverBecomeTickKeysSoOldProgressIsUntouched() throws {
        let content = try Self.bundled()
        let contentIDs = Set(content.steps.flatMap { $0.items.map(\.id) } + content.steps.flatMap { $0.items.flatMap { $0.entries.map(\.key) } })
        #expect(contentIDs.isDisjoint(with: LioTripTask.stepKeys))
        // Ticks written by every earlier build: the row keys, the arrival-step names and a stale key.
        let tick = Date(timeIntervalSince1970: 1_795_000_000)
        let old = LioTripTicks(done: ["entry": tick, "payment": tick, "local": tick, "arrival-card": tick, "trip.todo.step1.item1": tick,
                                      "trip.todo.step9.item9": tick])
        let list = LioTripChecklist(.init(now: Self.at("2026-11-26 10:00"), timeZone: Self.shanghai, ticks: old,
                                          entry: .missingDetails, arrivalChecklist: .init(done: [], total: 6), hotelSaved: false,
                                          routableTools: [.metro, .hotels]))
        func done(_ key: String) -> Bool? { list.tasks.first { $0.key == key }?.isDone }
        #expect(done("entry") == true)
        #expect(done("payment") == true)
        #expect(done("local") == true)
        // A key that is a content id (or a leftover) ticks nothing.
        #expect(done("arrival") == false)
        #expect(done("hotel") == false)
        #expect(done("internet") == false)
        #expect(list.tasks.map(\.key).filter { $0.hasPrefix("trip.todo") }.isEmpty)
    }

    // MARK: - The checks on the way in

    private func edited(_ change: (inout [String: Any], inout [[String: Any]]) -> Void) throws -> Data {
        let original = try Data(contentsOf: Self.resourceURL)
        var root = try #require(JSONSerialization.jsonObject(with: original) as? [String: Any])
        var entries = try #require(root["entries"] as? [String: Any])
        var chips = try #require(root["chips"] as? [[String: Any]])
        change(&entries, &chips)
        root["entries"] = entries
        root["chips"] = chips
        return try JSONSerialization.data(withJSONObject: root)
    }

    private func mutate(_ key: String, _ change: @escaping (inout [String: Any]) -> Void) throws -> Data {
        try edited { entries, _ in
            var entry = entries[key] as! [String: Any]
            change(&entry)
            entries[key] = entry
        }
    }

    private func problem(_ data: Data) -> LioTodoContentError? {
        do { _ = try LioTodoContent.decode(data); return nil } catch let error as LioTodoContentError { return error } catch { return nil }
    }

    @Test func aUnchangedFileHasNoProblem() throws {
        #expect(problem(try edited { _, _ in }) == nil)
    }

    @Test func aFileThatIsNotTheRightShapeIsRejected() throws {
        #expect(problem(Data("[]".utf8))?.location == "file")
        #expect(problem(Data("not json".utf8))?.location == "file")
        let original = try String(contentsOf: Self.resourceURL, encoding: .utf8)
        #expect(problem(Data(original.replacingOccurrences(of: "g2c-todo-content.1", with: "g2c-todo-content.2").utf8))?.location == "file")
        #expect(problem(Data(original.replacingOccurrences(of: "\"chips\":", with: "\"extra\":1,\"chips\":").utf8))?.location == "file")
        #expect(problem(Data(repeating: 0x20, count: LioTodoContent.maximumBytes + 1))?.problem.contains("larger") == true)
    }

    @Test func anEntryIdUsedTwiceIsRejected() throws {
        var text = try String(contentsOf: Self.resourceURL, encoding: .utf8)
        let line = #""trip.todo.step1.item1.title": {"zh":"标题","en":"Title","status":"ready","source_ids":["C9:01"],"volatility":"high","expires":null},"#
        text = text.replacingOccurrences(of: #""entries": {"#, with: #""entries": {"# + "\n" + line, options: [], range: text.range(of: #""entries": {"#))
        #expect(problem(Data(text.utf8))?.problem == "an entry id is used twice")
    }

    @Test func keysOutsideTheSixStepsAreRejected() throws {
        for key in ["trip.todo.step7.item1.title", "trip.todo.step1.item9.title", "trip.todo.step1.item1.label",
                    "trip.todo.step1.extra", "trip.other.step1.done", "trip.todo.step1.prompt.", "trip.todo.step1.prompt.Date"] {
            let data = try edited { entries, _ in
                entries[key] = ["zh": "好", "en": "Ok", "status": "ready", "source_ids": ["C9:01"], "volatility": "low", "expires": NSNull()]
            }
            #expect(problem(data)?.location == key, "\(key)")
        }
    }

    @Test func requiredTextInBothLanguagesWithinTheLimits() throws {
        let key = "trip.todo.step1.item1.title"
        func bad(_ change: @escaping (inout [String: Any]) -> Void) throws -> String? { problem(try mutate(key, change))?.location }
        #expect(try bad { $0["zh"] = nil } == "\(key)")
        #expect(try bad { $0["en"] = "" } == "\(key).en")
        #expect(try bad { $0["zh"] = " 前后有空格 " } == "\(key).zh")
        #expect(try bad { $0["en"] = "Two\nlines" } == "\(key).en")
        #expect(try bad { $0["zh"] = String(repeating: "字", count: 13) } == "\(key).zh")
        #expect(try bad { $0["en"] = String(repeating: "a", count: 41) } == "\(key).en")
        #expect(try bad { $0["zh"] = 5 } == "\(key).zh")
        // At the limit is fine.
        #expect(try bad { $0["zh"] = String(repeating: "字", count: 12) } == nil)
    }

    @Test func g4sRestrictedWordsAreRejectedInBothLanguages() throws {
        let key = "trip.todo.step1.item1.body"
        for (zh, en) in [("一定能入境。", "Fine."), ("好。", "We guarantee entry."), ("你可以免签。", "Ok."), ("好。", "You can enter visa-free."),
                         ("好。", "You don’t need a visa."), ("查医疗卡。", "Ok."), ("好。", "Business visas.")] {
            #expect(problem(try mutate(key) { $0["zh"] = zh; $0["en"] = en })?.problem == "contains a restricted word or promise", "\(zh) \(en)")
        }
        // The same words inside other words are not the restricted ones.
        #expect(problem(try mutate(key) { $0["en"] = "Check the guaranteed-free list." }) != nil)
        #expect(problem(try mutate(key) { $0["en"] = "Check the unbusinesslike list." }) == nil)
    }

    @Test func aSlotIsOnlyAllowedInThePassportNote() throws {
        #expect(problem(try mutate("trip.todo.step1.item1.body") { $0["en"] = "See {nationality_note}" })?.problem == "wrong placeholder")
        #expect(problem(try mutate("trip.todo.step1.item1.body") { $0["zh"] = "见{花括号" })?.problem == "stray brace")
        #expect(problem(try mutate("trip.todo.step1.nationality_note") { $0["zh"] = "没有槽" })?.problem == "wrong placeholder")
        #expect(problem(try mutate("trip.todo.step1.nationality_note") { $0["en"] = "{other_note}" })?.problem == "wrong placeholder")
    }

    @Test func statusSourcesVolatilityAndDateAreChecked() throws {
        let key = "trip.todo.step2.item1.title"
        #expect(problem(try mutate(key) { $0["status"] = "approved" })?.location == key)
        #expect(problem(try mutate(key) { $0["source_ids"] = ["C9:1"] })?.location == key)
        #expect(problem(try mutate(key) { $0["source_ids"] = ["C9:01", "C9:01"] })?.location == key)
        #expect(problem(try mutate(key) { $0["source_ids"] = [] })?.problem == "an item has a source")
        #expect(problem(try mutate(key) { $0["volatility"] = "extreme" })?.location == key)
        #expect(problem(try mutate(key) { $0["expires"] = 20261231 })?.location == key)
        #expect(problem(try mutate(key) { $0["expires_tz"] = "Asia/Shanghai" })?.problem == "expires_tz goes with an expires date")
        #expect(problem(try mutate(key) { $0["extra"] = true })?.location == key)
        // A date that is not a date is accepted by the file check (the filter hides it), a missing one is not.
        let soon = try edited { entries, _ in
            for field in ["title", "body"] {
                var entry = entries["trip.todo.step2.item1.\(field)"] as! [String: Any]
                entry["expires"] = "soon"
                entries["trip.todo.step2.item1.\(field)"] = entry
            }
        }
        #expect(problem(soon) == nil)
        #expect(problem(try mutate(key) { $0["expires"] = nil })?.location == key)
    }

    @Test func anItemsLinesAgreeWithEachOther() throws {
        // Hiding one line of an item while another stays would show half of it.
        #expect(problem(try mutate("trip.todo.step2.item2.body") { $0["status"] = "pending_review" })?.location == "trip.todo.step2.item2.body")
        #expect(problem(try mutate("trip.todo.step2.item2.body") { $0["expires"] = "2030-01-01" })?.location == "trip.todo.step2.item2.body")
        #expect(problem(try edited { entries, _ in entries["trip.todo.step2.item2.title"] = nil })?.problem == "an item has a title and a body")
        #expect(problem(try edited { entries, _ in entries["trip.todo.step2.item2.body"] = nil })?.problem == "an item has a title and a body")
    }

    @Test func eachStepKeepsItsLinesAndItems() throws {
        #expect(problem(try edited { entries, _ in entries["trip.todo.step3.done"] = nil })?.problem == "missing done or reminder line")
        #expect(problem(try edited { entries, _ in
            for key in entries.keys where key.hasPrefix("trip.todo.step5.item") { entries[key] = nil }
        })?.problem == "a step has at least one item")
    }

    @Test func buttonsNeedARealTarget() throws {
        let key = "trip.todo.step3.item4.button"
        func action(_ change: @escaping (inout [String: Any]) -> Void) throws -> LioTodoContentError? {
            problem(try mutate(key) { entry in
                var action = entry["action"] as! [String: Any]
                change(&action)
                entry["action"] = action
            })
        }
        #expect(try action { $0["url"] = "http://www.nia.gov.cn/x" }?.location == key)
        #expect(try action { $0["url"] = "https://user:pw@www.nia.gov.cn/x" }?.location == key)
        #expect(try action { $0["url"] = "https:///nohost" }?.location == key)
        #expect(try action { $0["source_id"] = "C9:99" }?.location == key)
        #expect(try action { $0["kind"] = "open_app" }?.problem == "this action is not supported")
        #expect(try action { $0["extra"] = 1 }?.location == key)
        #expect(problem(try mutate(key) { $0["action"] = nil })?.location == key)
        // Only buttons carry an action.
        #expect(problem(try mutate("trip.todo.step3.item4.body") { $0["action"] = ["kind": "open_hub_guide"] })?.location == "trip.todo.step3.item4.body")
        let metro = "trip.todo.step6.item3.button"
        func city(_ change: @escaping (inout [String: Any]) -> Void) throws -> LioTodoContentError? {
            problem(try mutate(metro) { entry in
                var action = entry["action"] as! [String: Any]
                var urls = action["url_by_city"] as! [String: Any]
                change(&urls)
                action["url_by_city"] = urls
                entry["action"] = action
            })
        }
        #expect(try city { $0["beijing"] = nil }?.location == metro)
        #expect(try city { $0["beijing"] = "http://example.com" }?.location == metro)
        #expect(try city { $0["lhasa"] = "https://example.com" }?.location == metro)
    }

    @Test func chipsAreCheckedLikeCopy() throws {
        func bad(_ change: @escaping (inout [[String: Any]]) -> Void) throws -> String? {
            problem(try edited { _, chips in change(&chips) })?.location
        }
        #expect(try bad { $0.removeLast() } == "chips")
        #expect(try bad { $0[0]["step"] = "money" } == "chips.entry")
        #expect(try bad { var group = $0[0]["chips"] as! [[String: Any]]; group.removeLast(2); $0[0]["chips"] = group } == "chips.entry")
        #expect(try bad { var group = $0[0]["chips"] as! [[String: Any]]; group[0]["en"] = String(repeating: "a", count: 25); $0[0]["chips"] = group } == "chips.entry[1].en")
        #expect(try bad { var group = $0[0]["chips"] as! [[String: Any]]; group[0]["zh"] = String(repeating: "字", count: 13); $0[0]["chips"] = group } == "chips.entry[1].zh")
        // The same sentence twice, even in another step.
        #expect(try bad {
            var group = $0[1]["chips"] as! [[String: Any]]
            group[0]["zh"] = "入境卡去哪填？"
            $0[1]["chips"] = group
        } == "chips.arrival[1]")
        #expect(try bad { var group = $0[0]["chips"] as! [[String: Any]]; group[0]["extra"] = 1; $0[0]["chips"] = group } == "chips.entry[1]")
    }
}
