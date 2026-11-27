import Foundation
import Testing
@testable import CJMessageHTTP

/// #1994: `rich.trip_receipt` (LIO-answer-rich.1) as the App reads it: the fields it uses, the limits, a broken receipt
/// dropped whole without failing the page, and the contract's own examples.
struct LioTripReceiptWireTests {
    private let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"

    private var root: URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { url.deleteLastPathComponent() }
        return url
    }

    private func page(rich: String, status: String = "completed", failure: String? = nil, answer: String = "好的，已经帮你排好了。",
                      extra: String = "") -> Data {
        let failureJSON = failure.map { #","failure":"\#($0)""# } ?? ""
        return Data("""
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[
            {"message_id":"m1","text":"Q","answer":"\(answer)","status":"\(status)"\(failureJSON),"sources":[]\(extra),"rich":\(rich)}],"next_before":null}
            """.utf8)
    }

    private func message(rich: String, status: String = "completed", failure: String? = nil, answer: String = "好的，已经帮你排好了。",
                         extra: String = "") throws -> LioTimelineWire.Message {
        try #require(try LioTimelineWire.decodePage(page(rich: rich, status: status, failure: failure, answer: answer, extra: extra),
                                                    for: conversation, version: .v2).messages.first)
    }

    private func receipt(_ body: String, status: String = "completed", failure: String? = nil, answer: String = "好的，已经帮你排好了。",
                         extra: String = "") throws -> LioTimelineWire.TripReceipt? {
        try message(rich: #"{"version":"LIO-answer-rich.1","trip_receipt":\#(body)}"#, status: status, failure: failure,
                    answer: answer, extra: extra).rich?.tripReceipt
    }

    private let undoID = "undo-114b97123ea4b9ac35e69d3f8fd0ea64056a4c28"
    private let until = "2026-11-28T03:04:05.678+00:00"
    private let day1 = #"{"day":1,"city":{"id":"beijing","zh":"北京","en":"Beijing"},"added":3,"updated":0,"removed":0}"#

    private func restoreUndo(version: Int = 7, saveID: String = "lio-plan-run-5c1f") -> String {
        let undoID = LioTimelineWire.undoActionID(forSave: saveID)
        return #"{"state":"available","action_id":"\#(undoID)","until":"\#(until)","target":{"trip_id":"trip-9a1b","expected_version":\#(version),"original_hash":"\#(String(repeating: "a", count: 64))","content_version":"structured.4","restore_version":\#(version - 1),"restore_hash":"\#(String(repeating: "b", count: 64))","restore_content_version":"structured.4"}}"#
    }

    private func saved(version: Int = 7, first: String = "", summary: String? = nil, undo: String? = nil, actionID: String = "lio-plan-run-5c1f",
                       tripID: String = "trip-9a1b") -> String {
        let summaryJSON = summary.map { #","summary":\#($0)"# } ?? ""
        return #"{"status":"saved","action_id":"\#(actionID)","trip_id":"\#(tripID)","committed_version":\#(version)\#(first)\#(summaryJSON),"undo":\#(undo ?? restoreUndo(version: version, saveID: actionID))}"#
    }

    private func summary(days: String? = nil, wishlist: Int = 0, legs: Int = 0) -> String {
        #"{"days":[\#(days ?? day1)],"wishlist_added":\#(wishlist),"legs_updated":\#(legs)}"#
    }

    // MARK: Reading

    @Test func aSavedReceiptIsReadWithItsSummaryAndUndo() throws {
        let value = try #require(try receipt(saved(summary: summary(wishlist: 2, legs: 1))))
        #expect(value.status == .saved && value.actionID == "lio-plan-run-5c1f")
        #expect(value.tripID == "trip-9a1b" && value.committedVersion == 7)
        #expect(!value.firstAutosave && !value.isFirstSave, "the flag is only ever sent as true; absent is not first")
        #expect(value.summary == .init(days: [.init(day: 1, city: .init(id: "beijing", zh: "北京", en: "Beijing"), added: 3)],
                                       wishlistAdded: 2, legsUpdated: 1))
        #expect(value.summary?.added == 3 && value.summary?.updated == 0 && value.summary?.removed == 0)
        #expect(value.undo == .init(state: .available, kind: .restore, actionID: undoID, until: until,
                                    target: .init(tripID: "trip-9a1b", expectedVersion: 7, originalHash: String(repeating: "a", count: 64),
                                                  contentVersion: "structured.4",
                                                  restore: .init(version: 6, hash: String(repeating: "b", count: 64), contentVersion: "structured.4"))))
    }

    @Test func theFirstAutosaveFlagIsReadOnlyWhenItIsTrue() throws {
        let first = try #require(try receipt(saved(first: #","first_autosave":true"#)))
        #expect(first.firstAutosave && first.isFirstSave)
        // `false` is not in the contract (the field is only ever true): a broken receipt, dropped whole.
        for bad in [#","first_autosave":false"#, #","first_autosave":"true""#, #","first_autosave":1"#, #","first_autosave":null"#,
                    #","first_autosave":[true]"#] {
            #expect(try receipt(saved(first: bad)) == nil, "\(bad)")
        }
    }

    @Test func theFlagNeverCountsOnAReceiptThatSavedNothing() throws {
        let notSaved = try #require(try receipt(#"{"status":"not_saved","action_id":"lio-plan-run-5c1f","first_autosave":true}"#))
        #expect(notSaved.status == .notSaved && !notSaved.firstAutosave && !notSaved.isFirstSave)
        let unknown = try #require(try receipt(#"{"status":"unknown","action_id":"lio-plan-run-5c1f","first_autosave":true}"#))
        #expect(unknown.status == .unknown && !unknown.firstAutosave && !unknown.isFirstSave)
    }

    @Test func aNotSavedReceiptKeepsItsReasonAndAnUnknownReasonIsNoReason() throws {
        for (text, reason) in [("conflict", LioTimelineWire.TripReceipt.Reason.conflict), ("protected", .protected), ("too_large", .tooLarge)] {
            #expect(try receipt(#"{"status":"not_saved","action_id":"a1","reason":"\#(text)"}"#)?.reason == reason)
        }
        #expect(try receipt(#"{"status":"not_saved","action_id":"a1"}"#)?.reason == nil)
        let odd = try #require(try receipt(#"{"status":"not_saved","action_id":"a1","reason":"disabled"}"#))
        #expect(odd.status == .notSaved && odd.reason == nil, "still not saved, with no reason")
        #expect(try receipt(#"{"status":"not_saved","action_id":"a1","reason":7}"#)?.status == .notSaved)
    }

    @Test func everyUndoStateIsRead() throws {
        for state in ["expired", "superseded", "undone"] {
            let value = try #require(try receipt(saved(undo: #"{"state":"\#(state)","until":"\#(until)"}"#)))
            #expect(value.undo?.state == ["expired": .expired, "superseded": .superseded, "undone": .undone][state])
            #expect(value.undo?.actionID == nil && value.undo?.until == until)
        }
        let unavailable = try #require(try receipt(saved(undo: #"{"state":"unavailable"}"#)))
        #expect(unavailable.undo == .init(state: .unavailable), "no until is fine only here")
        #expect(try receipt(saved(undo: #"{"state":"unavailable","until":"\#(until)"}"#))?.undo?.until == until)
    }

    @Test func aTripThatThisSaveCreatedCanOnlyBeWithdrawn() throws {
        let created = #"{"state":"available","kind":"withdraw_created","action_id":"\#(undoID)","until":"\#(until)","target":{"trip_id":"trip-9a1b","expected_version":1,"original_hash":"\#(String(repeating: "c", count: 64))","content_version":"structured.4"}}"#
        let value = try #require(try receipt(saved(version: 1, first: #","first_autosave":true"#, undo: created)))
        #expect(value.undo?.kind == .withdrawCreated && value.isFirstSave)
        #expect(try receipt(saved(version: 2, undo: created)) == nil, "withdraw_created is for version 1")
        #expect(try receipt(saved(version: 1, undo: restoreUndo(version: 2))) == nil, "version 1 has nothing before it to restore")
        let noKind = created.replacingOccurrences(of: #""kind":"withdraw_created","#, with: "")
        #expect(try receipt(saved(version: 1, undo: noKind)) == nil, "withdraw_created needs its kind")
        #expect(try receipt(saved(version: 3, undo: restoreUndo(version: 3).replacingOccurrences(of: #""action_id""#, with: #""kind":"restore","action_id""#)))?.undo?.kind == .restore)
    }

    @Test func theUndoNeedsItsExactTargetAndTheIdTheServerDerives() throws {
        let hash = String(repeating: "a", count: 64)
        func restore(_ target: String) -> String {
            #"{"state":"available","action_id":"\#(undoID)","until":"\#(until)","target":\#(target)}"#
        }
        let fields = #""trip_id":"trip-9a1b","expected_version":7,"original_hash":"\#(hash)","content_version":"structured.4","restore_version":6,"restore_hash":"\#(hash)","restore_content_version":"structured.3""#
        let value = try #require(try receipt(saved(undo: restore("{" + fields + "}"))))
        #expect(value.undo?.target?.restore == .init(version: 6, hash: hash, contentVersion: "structured.3"))
        let bad: [(String, String)] = [
            ("no target", #"{"state":"available","action_id":"\#(undoID)","until":"\#(until)"}"#),
            ("extra field", restore("{" + fields + #","title":"x"}"#)),
            ("a field missing", restore(#"{"trip_id":"trip-9a1b","expected_version":7,"original_hash":"\#(hash)","content_version":"structured.4","restore_version":6,"restore_hash":"\#(hash)"}"#)),
            ("not the committed version", restore("{" + fields.replacingOccurrences(of: #""expected_version":7"#, with: #""expected_version":6"#).replacingOccurrences(of: #""restore_version":6"#, with: #""restore_version":5"#) + "}")),
            ("restores a version other than the previous", restore("{" + fields.replacingOccurrences(of: #""restore_version":6"#, with: #""restore_version":4"#) + "}")),
            ("restore version 0", restore("{" + fields.replacingOccurrences(of: #""restore_version":6"#, with: #""restore_version":0"#) + "}")),
            ("upper case hash", restore("{" + fields.replacingOccurrences(of: hash, with: String(repeating: "A", count: 64)) + "}")),
            ("short hash", restore("{" + fields.replacingOccurrences(of: #""original_hash":"\#(hash)""#, with: #""original_hash":"abc""#) + "}")),
            ("unknown content version", restore("{" + fields.replacingOccurrences(of: "structured.4", with: "structured.9") + "}")),
            ("version a string", restore("{" + fields.replacingOccurrences(of: #""expected_version":7"#, with: #""expected_version":"7""#) + "}")),
            ("trip id bad", restore("{" + fields.replacingOccurrences(of: "trip-9a1b", with: "trip 1") + "}")),
            ("id not derived from the save id", #"{"state":"available","action_id":"undo-\#(String(repeating: "0", count: 40))","until":"\#(until)","target":{\#(fields)}}"#),
        ]
        for (name, undo) in bad { #expect(try receipt(saved(undo: undo)) == nil, "\(name)") }
        let created = #"{"state":"available","kind":"withdraw_created","action_id":"\#(undoID)","until":"\#(until)","target":"#
        let four = #""trip_id":"trip-9a1b","expected_version":1,"original_hash":"\#(hash)","content_version":"structured.1""#
        let withdraw = try #require(try receipt(saved(version: 1, undo: created + "{" + four + "}}")))
        #expect(withdraw.undo?.target == .init(tripID: "trip-9a1b", expectedVersion: 1, originalHash: hash, contentVersion: "structured.1"))
        for (name, target) in [("restore fields", "{" + four + #","restore_version":0,"restore_hash":"\#(hash)","restore_content_version":"structured.1""# + "}"),
                               ("version 2", "{" + four.replacingOccurrences(of: #""expected_version":1"#, with: #""expected_version":2"#) + "}"),
                               ("no hash", #"{"trip_id":"trip-9a1b","expected_version":1,"content_version":"structured.1"}"#)] {
            #expect(try receipt(saved(version: 1, undo: created + target + "}")) == nil, "withdraw_created: \(name)")
        }
    }

    // MARK: Rows

    @Test func theReceiptRidesOnAFailedRowToo() throws {
        let body = saved(first: #","first_autosave":true"#)
        let limit = try message(rich: #"{"version":"LIO-answer-rich.1","trip_receipt":\#(body)}"#, status: "failed", failure: "quota", answer: "")
        #expect(limit.state == .serviceLimit && limit.rich?.tripReceipt?.isFirstSave == true)
        let unavailable = try message(rich: #"{"version":"LIO-answer-rich.1","trip_receipt":\#(body)}"#, status: "failed", failure: "unavailable", answer: "")
        #expect(unavailable.state == .unavailable && unavailable.rich?.tripReceipt?.status == .saved)
        // Nothing else of `rich` is read where there is no answer to point into.
        let place = #"{"type":"place","start":0,"end":2,"place_id":"pl_bj_gugong"}"#
        let both = try message(rich: #"{"version":"LIO-answer-rich.1","entities":[\#(place)],"trip_receipt":\#(body)}"#,
                               status: "failed", failure: "unavailable", answer: "")
        #expect(both.rich?.entities.isEmpty == true && both.rich?.tripReceipt != nil)
    }

    @Test func aRowStillBeingAnsweredCarriesNoReceipt() throws {
        let rich = #"{"version":"LIO-answer-rich.1","trip_receipt":\#(saved())}"#
        #expect(try message(rich: rich, status: "answering").rich == nil)
        #expect(try message(rich: rich, status: "sending").rich == nil)
    }

    @Test func aPlanReplyKeepsItsReceiptAndDropsTheCards() throws {
        let trip = #","trip":{"trip_id":"trip-1","title":"北京三日","days":[]}"#
        let taxi = #"{"type":"taxi","label":"打车去这里","open":{"tool":"taxi","parameters":{}}}"#
        let rich = #"{"version":"LIO-answer-rich.1","cards":[\#(taxi)],"trip_receipt":\#(saved())}"#
        let value = try message(rich: rich, extra: trip).rich
        #expect(value?.tripReceipt?.status == .saved && value?.cards.isEmpty == true)
    }

    @Test func aCompletedRowWithoutAnAnswerStillCarriesItsReceiptButNothingElse() throws {
        let place = #"{"type":"place","start":0,"end":2,"place_id":"pl_bj_gugong"}"#
        let rich = #"{"version":"LIO-answer-rich.1","entities":[\#(place)],"memory":{"prompt":"consent"},"trip_receipt":\#(saved())}"#
        let value = try message(rich: rich, answer: "").rich
        #expect(value?.tripReceipt != nil && value?.entities.isEmpty == true && value?.memoryPrompt == false)
    }

    @Test func theReceiptIsReadSeparatelyFromTheOtherParts() throws {
        let place = #"{"type":"place","start":0,"end":2,"place_id":"pl_bj_gugong"}"#
        let good = try message(rich: #"{"version":"LIO-answer-rich.1","entities":[\#(place)],"trip_receipt":\#(saved())}"#).rich
        #expect(good?.entities.count == 1 && good?.tripReceipt != nil)
        let bad = try message(rich: #"{"version":"LIO-answer-rich.1","entities":[\#(place)],"trip_receipt":{"status":"pending"}}"#).rich
        #expect(bad?.entities.count == 1 && bad?.tripReceipt == nil, "a broken receipt leaves the entities alone")
        let onlyBad = try message(rich: #"{"version":"LIO-answer-rich.1","trip_receipt":{"status":"pending"}}"#)
        #expect(onlyBad.rich == nil && onlyBad.answer == "好的，已经帮你排好了。", "nothing good left: no rich, and the answer is still there")
    }

    // MARK: A broken receipt is dropped whole, and never fails the page

    @Test(arguments: [
        #"{"status":"pending","action_id":"a1"}"#,
        #"{"status":"saved","action_id":"a1"}"#,
        #"{"action_id":"a1"}"#,
        #"{"status":"unknown"}"#,
        #"{"status":"unknown","action_id":""}"#,
        #"{"status":"unknown","action_id":"_a"}"#,
        #"{"status":"unknown","action_id":"a b"}"#,
        #"{"status":"unknown","action_id":7}"#,
        #"{"status":7,"action_id":"a1"}"#,
        #""saved""#, "[]", "7", "null", "true",
    ]) func aReceiptThatIsNotOneIsDroppedAndThePageStands(body: String) throws {
        let value = try message(rich: #"{"version":"LIO-answer-rich.1","trip_receipt":\#(body)}"#)
        #expect(value.rich == nil && value.state == .completed && value.answer == "好的，已经帮你排好了。", "\(body)")
    }

    @Test func aSavedReceiptThatBreaksARuleIsDroppedWhole() throws {
        let cases: [(String, String)] = [
            ("no undo", #"{"status":"saved","action_id":"a1","trip_id":"t1","committed_version":2}"#),
            ("no trip id", #"{"status":"saved","action_id":"a1","committed_version":2,"undo":{"state":"unavailable"}}"#),
            ("trip id empty", saved(tripID: "")),
            ("trip id bad", saved(tripID: "trip 1")),
            ("version 0", saved(version: 0, undo: #"{"state":"unavailable"}"#)),
            ("version negative", saved(version: -1, undo: #"{"state":"unavailable"}"#)),
            ("version too large", saved(version: Int.max, undo: #"{"state":"unavailable"}"#)),
            ("version a string", #"{"status":"saved","action_id":"a1","trip_id":"t1","committed_version":"2","undo":{"state":"unavailable"}}"#),
            ("undo not an object", saved(undo: #""available""#)),
            ("undo state unknown", saved(undo: #"{"state":"pending"}"#)),
            ("undo state missing", saved(undo: #"{"until":"\#(until)"}"#)),
            ("expired without until", saved(undo: #"{"state":"expired"}"#)),
            ("until without milliseconds", saved(undo: #"{"state":"expired","until":"2026-11-28T03:04:05+00:00"}"#)),
            ("until not UTC", saved(undo: #"{"state":"expired","until":"2026-11-28T03:04:05.678+08:00"}"#)),
            ("until a number", saved(undo: #"{"state":"expired","until":20261128}"#)),
            ("available without id", saved(undo: #"{"state":"available","until":"\#(until)"}"#)),
            ("available without until", saved(undo: #"{"state":"available","action_id":"\#(undoID)"}"#)),
            ("undo id of 44 characters", saved(undo: #"{"state":"available","action_id":"undo-\#(String(repeating: "a", count: 39))","until":"\#(until)"}"#)),
            ("undo id upper case", saved(undo: #"{"state":"available","action_id":"undo-\#(String(repeating: "A", count: 40))","until":"\#(until)"}"#)),
            ("undo id wrong prefix", saved(undo: #"{"state":"available","action_id":"redo-\#(String(repeating: "a", count: 40))","until":"\#(until)"}"#)),
            ("undo kind delete", saved(undo: #"{"state":"available","kind":"delete","action_id":"\#(undoID)","until":"\#(until)"}"#)),
            ("summary not an object", saved(summary: "[]")),
            ("summary without days", saved(summary: #"{"wishlist_added":0,"legs_updated":0}"#)),
            ("summary without wishlist", saved(summary: #"{"days":[],"legs_updated":0}"#)),
            ("a day that changed nothing", saved(summary: summary(days: #"{"day":1,"city":null,"added":0,"updated":0,"removed":0}"#))),
            ("day 0", saved(summary: summary(days: #"{"day":0,"city":null,"added":1,"updated":0,"removed":0}"#))),
            ("day 61", saved(summary: summary(days: #"{"day":61,"city":null,"added":1,"updated":0,"removed":0}"#))),
            ("days not ascending", saved(summary: summary(days: #"{"day":2,"city":null,"added":1,"updated":0,"removed":0},{"day":1,"city":null,"added":1,"updated":0,"removed":0}"#))),
            ("a day twice", saved(summary: summary(days: #"{"day":1,"city":null,"added":1,"updated":0,"removed":0},{"day":1,"city":null,"added":1,"updated":0,"removed":0}"#))),
            ("a count of 100", saved(summary: summary(days: #"{"day":1,"city":null,"added":100,"updated":0,"removed":0}"#))),
            ("a negative count", saved(summary: summary(days: #"{"day":1,"city":null,"added":-1,"updated":2,"removed":0}"#))),
            ("wishlist 100", saved(summary: summary(wishlist: 100))),
            ("legs 100", saved(summary: summary(legs: 100))),
            ("a city that is not an object", saved(summary: summary(days: #"{"day":1,"city":"北京","added":1,"updated":0,"removed":0}"#))),
            ("a city id in capitals", saved(summary: summary(days: #"{"day":1,"city":{"id":"Beijing","zh":"北京","en":"Beijing"},"added":1,"updated":0,"removed":0}"#))),
            ("a city id of two letters", saved(summary: summary(days: #"{"day":1,"city":{"id":"bj","zh":"北京","en":"Beijing"},"added":1,"updated":0,"removed":0}"#))),
            ("a city name over 12", saved(summary: summary(days: #"{"day":1,"city":{"id":"beijing","zh":"\#(String(repeating: "北", count: 13))","en":"Beijing"},"added":1,"updated":0,"removed":0}"#))),
            ("a city name with a line break", saved(summary: summary(days: #"{"day":1,"city":{"id":"beijing","zh":"北\n京","en":"Beijing"},"added":1,"updated":0,"removed":0}"#))),
            ("an English city over 24", saved(summary: summary(days: #"{"day":1,"city":{"id":"beijing","zh":"北京","en":"\#(String(repeating: "B", count: 25))"},"added":1,"updated":0,"removed":0}"#))),
        ]
        for (name, body) in cases {
            let value = try message(rich: #"{"version":"LIO-answer-rich.1","trip_receipt":\#(body)}"#)
            #expect(value.rich == nil, "\(name)")
            #expect(value.state == .completed, "\(name): the answer stays")
        }
    }

    @Test func theLimitsAreExact() throws {
        let fourteen = (1...14).map { #"{"day":\#($0),"city":null,"added":1,"updated":0,"removed":0}"# }.joined(separator: ",")
        #expect(try receipt(saved(summary: summary(days: fourteen)))?.summary?.days.count == 14)
        let fifteen = (1...15).map { #"{"day":\#($0),"city":null,"added":1,"updated":0,"removed":0}"# }.joined(separator: ",")
        #expect(try receipt(saved(summary: summary(days: fifteen))) == nil, "15 days")
        #expect(try receipt(saved(summary: summary(days: #"{"day":60,"city":null,"added":99,"updated":99,"removed":99}"#, wishlist: 99, legs: 99)))?.summary?.days.first?.day == 60)
        #expect(try receipt(saved(summary: #"{"days":[],"wishlist_added":0,"legs_updated":0}"#))?.summary?.days.isEmpty == true, "zero days is allowed")
        let id128 = "a" + String(repeating: "b", count: 127)
        #expect(try receipt(saved(actionID: id128))?.actionID == id128)
        #expect(try receipt(saved(actionID: id128 + "c")) == nil, "129 characters")
        #expect(try receipt(saved(tripID: id128))?.tripID == id128)
        #expect(try receipt(saved(tripID: id128 + "c")) == nil)
        #expect(try receipt(saved(actionID: "a.b:c_d-1"))?.actionID == "a.b:c_d-1")
        let city12 = String(repeating: "北", count: 12), city24 = String(repeating: "B", count: 24)
        let long = summary(days: #"{"day":1,"city":{"id":"beijing","zh":"\#(city12)","en":"\#(city24)"},"added":1,"updated":0,"removed":0}"#)
        #expect(try receipt(saved(summary: long))?.summary?.days.first?.city?.en == city24)
        #expect(try receipt(saved(version: 9223372036854775806, undo: #"{"state":"unavailable"}"#))?.committedVersion == 9223372036854775806)
    }

    @Test func extraKeysAreIgnoredAndNoPlaceNameOrUserTextIsKept() throws {
        let body = #"{"status":"saved","action_id":"a1","trip_id":"t1","committed_version":2,"note":"去故宫","title":"北京三日","summary":{"days":[{"day":1,"city":null,"added":1,"updated":0,"removed":0,"places":["故宫"]}],"wishlist_added":0,"legs_updated":0,"text":"x"},"undo":{"state":"expired","until":"\#(until)","target":{"secret":1}}}"#
        let value = try #require(try receipt(body))
        #expect(value.summary == .init(days: [.init(day: 1, added: 1)]) && value.undo == .init(state: .expired, until: until))
        let dumped = String(describing: value)
        #expect(!dumped.contains("故宫") && !dumped.contains("北京三日") && !dumped.contains("secret"))
    }

    @Test func aReceiptOnAnOtherVersionOfRichIsIgnored() throws {
        let value = try message(rich: #"{"version":"LIO-answer-rich.2","trip_receipt":\#(saved())}"#)
        #expect(value.rich == nil)
    }

    // MARK: The contract's examples

    private func examples() throws -> (answers: [String: String], valid: [[String: Any]], invalid: [[String: Any]]) {
        let data = try Data(contentsOf: root.appendingPathComponent("contracts/message/lio-answer-rich-examples.1.json"))
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        return (try #require(object["answers"] as? [String: String]), try #require(object["valid"] as? [[String: Any]]),
                try #require(object["invalid"] as? [[String: Any]]))
    }

    private func receiptOf(_ example: [String: Any], _ answers: [String: String]) throws -> (present: Bool, value: LioTimelineWire.TripReceipt?) {
        guard let rich = example["rich"] as? [String: Any], rich["trip_receipt"] != nil else { return (false, nil) }
        let json = String(decoding: try JSONSerialization.data(withJSONObject: rich), as: UTF8.self)
        let answer = answers[example["answer"] as? String ?? ""] ?? "好的，已经帮你排好了。"
        let escaped = String(decoding: try JSONEncoder().encode(answer), as: UTF8.self)
        let body = Data("""
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[
            {"message_id":"m1","text":"Q","answer":\(escaped),"status":"completed","sources":[],"rich":\(json)}],"next_before":null}
            """.utf8)
        let row = try #require(try LioTimelineWire.decodePage(body, for: conversation, version: .v2).messages.first)
        return (true, row.rich?.tripReceipt)
    }

    @Test func everyValidReceiptExampleIsRead() throws {
        let all = try examples()
        var seen: [String: LioTimelineWire.TripReceipt] = [:]
        for example in all.valid {
            let result = try receiptOf(example, all.answers)
            guard result.present, let name = example["name"] as? String else { continue }
            seen[name] = try #require(result.value, "\(name)")
        }
        #expect(seen.count == 14, "the contract has 14 valid examples with a receipt")
        #expect(seen["saved, undo available"]?.isFirstSave == false)
        #expect(seen["first save of a new trip: undo withdraws it, first automatic save"]?.isFirstSave == true)
        #expect(seen["first save of a new trip: undo withdraws it, first automatic save"]?.undo?.kind == .withdrawCreated)
        #expect(seen["a later save that is the account's first automatic save"]?.isFirstSave == true)
        #expect(seen["a later save that is the account's first automatic save"]?.committedVersion == 7)
        #expect(seen["first save of a new trip, already superseded"]?.isFirstSave == false, "the contract's example sends no flag")
        #expect(seen["first save of a new trip, already superseded"]?.undo?.state == .superseded)
        #expect(seen["saved, a day without a city"]?.summary?.days.first?.city == nil)
        #expect(seen["saved, expired"]?.undo?.state == .expired && seen["saved, undone"]?.undo?.state == .undone)
        #expect(seen["saved, unavailable"]?.undo?.state == .unavailable)
        #expect(seen["not saved, protected"]?.reason == .protected && seen["not saved, no reason"]?.reason == nil)
        #expect(seen["unknown (a failed row carries only this)"]?.status == .unknown)
        #expect(seen.values.filter(\.isFirstSave).count == 2)
    }

    /// What the contract calls invalid but the App does not look at, because it does not use the field or the state makes
    /// it moot. They are read as the receipt they otherwise are; none of them can start the one-time notice. The undo
    /// target and the derived undo id are checked now that the App sends the undo.
    private static let notChecked: Set<String> = [
        "undo expired with a target",
        "first_autosave on a not-saved receipt", "first_autosave on an unknown receipt",
        "not saved with a summary", "not saved reason disabled", "summary carries a place name",
    ]

    @Test func everyInvalidReceiptExampleIsDroppedOrIsOneTheAppDoesNotLookAt() throws {
        let all = try examples()
        var accepted: Set<String> = []
        var checked = 0
        for example in all.invalid {
            let result = try receiptOf(example, all.answers)
            guard result.present, let name = example["name"] as? String else { continue }
            // Only the examples that are invalid because of the receipt itself.
            guard let rich = example["rich"] as? [String: Any], rich.keys.sorted() == ["trip_receipt", "version"] else { continue }
            checked += 1
            if result.value != nil { accepted.insert(name) }
        }
        #expect(checked >= 25, "the contract has about 29 invalid receipt examples; saw \(checked)")
        #expect(accepted.isSubset(of: Self.notChecked), "read although invalid, and not on the list: \(accepted.subtracting(Self.notChecked).sorted())")
    }

    @Test func noInvalidExampleCanStartTheNoticeExceptThroughAFieldTheAppDoesNotCheck() throws {
        let all = try examples()
        for example in all.invalid {
            let result = try receiptOf(example, all.answers)
            guard result.present, let value = result.value, value.isFirstSave, let name = example["name"] as? String else { continue }
            #expect(Self.notChecked.contains(name), "\(name) starts the notice")
        }
    }
}
