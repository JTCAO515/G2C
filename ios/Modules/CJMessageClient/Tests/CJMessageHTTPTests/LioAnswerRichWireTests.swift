import CJMessageClient
import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJMessageHTTP

/// #1991: `rich` (LIO-answer-rich.1) on the v2 timeline: the declaration, the 400 fallback and the entities.
@MainActor
struct LioAnswerRichWireTests {
    private let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"

    private func row(status: String = "completed", answer: String = "上午去故宫，下午去景山公园。", rich: String?) -> String {
        let answerJSON = String(decoding: (try? JSONEncoder().encode(answer)) ?? Data(), as: UTF8.self)
        return """
            {"message_id":"m1","text":"Q","answer":\(answerJSON),"status":"\(status)","sources":[]\(rich.map { ",\"rich\":" + $0 } ?? "")}
            """
    }

    private func page(_ rows: String) -> Data {
        Data("""
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[\(rows)],"next_before":null}
            """.utf8)
    }

    private func decoded(_ row: String) throws -> LioTimelineWire.Message {
        try #require(try LioTimelineWire.decodePage(page(row), for: conversation, version: .v2).messages.first)
    }

    private func rich(_ entities: String, version: String = "LIO-answer-rich.1", extra: String = "") -> String {
        "{\"version\":\"\(version)\"\(entities.isEmpty ? "" : ",\"entities\":" + entities)\(extra)}"
    }

    private let gugong = #"{"type":"place","start":2,"end":4,"place_id":"pl_bj_gugong"}"#
    private let jingshan = #"{"type":"place","start":7,"end":11,"place_id":"pl_bj_jingshan"}"#

    // MARK: Decoding

    @Test func rowsWithoutRichReadAsBefore() throws {
        #expect(try decoded(row(rich: nil)).rich == nil)
    }

    @Test func entitiesAreProjectedInOrderForACompletedRow() throws {
        let message = try decoded(row(rich: rich("[\(gugong),\(jingshan)]")))
        #expect(message.rich?.entities == [
            .init(start: 2, end: 4, placeID: "pl_bj_gugong"), .init(start: 7, end: 11, placeID: "pl_bj_jingshan")])
        #expect(message.answer == "上午去故宫，下午去景山公园。", "the answer is never changed by rich")
    }

    @Test func richOnlyShowsOnACompletedRowWithAnAnswer() throws {
        let body = rich("[\(gugong)]")
        for status in ["sending", "answering"] {
            #expect(try decoded(row(status: status, rich: body)).rich == nil, "\(status)")
        }
        #expect(try decoded(row(status: "completed", answer: "", rich: body)).rich == nil, "no answer, nothing to link")
        let failed = row(status: "failed", rich: body).replacingOccurrences(of: "\"sources\":[]", with: "\"sources\":[],\"failure\":\"unavailable\"")
        #expect(try decoded(failed).rich == nil)
    }

    @Test func unknownKeysAndUnknownPartsAreIgnored() throws {
        let value = rich("[\(gugong)]", extra: #","cards":[{"type":"hotel"}],"future":{"a":1},"memory":"x""#)
        #expect(try decoded(row(rich: value)).rich?.entities.map(\.placeID) == ["pl_bj_gugong"])
        let extraKey = #"{"type":"place","start":2,"end":4,"place_id":"pl_bj_gugong","text":"故宫"}"#
        #expect(try decoded(row(rich: rich("[\(extraKey)]"))).rich?.entities.count == 1, "an extra key on an entity is not a reason to drop it")
    }

    @Test(arguments: [
        #"{"version":"LIO-answer-rich.2","entities":[{"type":"place","start":2,"end":4,"place_id":"pl_bj_gugong"}]}"#,
        #"{"version":"lio-answer-rich.1","entities":[{"type":"place","start":2,"end":4,"place_id":"pl_bj_gugong"}]}"#,
        #"{"version":"LIO-answer-rich.1"}"#,
        #"{"version":"LIO-answer-rich.1","entities":[]}"#,
        #"{"version":"LIO-answer-rich.1","entities":{}}"#,
        #"{"version":"LIO-answer-rich.1","entities":"nope"}"#,
        #"{"version":"LIO-answer-rich.1","entities":null}"#,
        #"{"entities":[{"type":"place","start":2,"end":4,"place_id":"pl_bj_gugong"}]}"#,
        "\"rich\"", "[]", "7", "null",
    ]) func wrongVersionEmptyOrBrokenRichReadsAsNoRichAndNeverFailsThePage(value: String) throws {
        let message = try decoded(row(rich: value))
        #expect(message.rich == nil)
        #expect(message.answer == "上午去故宫，下午去景山公园。")
    }

    @Test func moreThanTwentyEntitiesAreDroppedWhole() throws {
        let many = (0..<21).map { #"{"type":"place","start":\#($0 * 2),"end":\#($0 * 2 + 2),"place_id":"pl_bj_p\#($0)"}"# }
        #expect(try decoded(row(answer: String(repeating: "甲乙", count: 30), rich: rich("[\(many.joined(separator: ","))]"))).rich == nil)
        let twenty = Array(many.prefix(20)).joined(separator: ",")
        #expect(try decoded(row(answer: String(repeating: "甲乙", count: 30), rich: rich("[\(twenty)]"))).rich?.entities.count == 20)
    }

    /// One bad entity costs only itself.
    @Test(arguments: [
        #"{"type":"place","start":5,"end":5,"place_id":"pl_bj_x"}"#,
        #"{"type":"place","start":5,"end":6,"place_id":"pl_bj_x"}"#,
        #"{"type":"place","start":5,"end":38,"place_id":"pl_bj_x"}"#,
        #"{"type":"place","start":-1,"end":7,"place_id":"pl_bj_x"}"#,
        #"{"type":"place","start":5.5,"end":7,"place_id":"pl_bj_x"}"#,
        #"{"type":"place","start":"5","end":7,"place_id":"pl_bj_x"}"#,
        #"{"type":"place","start":true,"end":7,"place_id":"pl_bj_x"}"#,
        #"{"type":"place","start":5,"end":200001,"place_id":"pl_bj_x"}"#,
        #"{"type":"place","start":9,"end":7,"place_id":"pl_bj_x"}"#,
        #"{"type":"poi","start":5,"end":7,"place_id":"pl_bj_x"}"#,
        #"{"start":5,"end":7,"place_id":"pl_bj_x"}"#,
        #"{"type":"place","start":5,"end":7}"#,
        #"{"type":"place","start":5,"end":7,"place_id":"PL_BJ_X"}"#,
        #"{"type":"place","start":5,"end":7,"place_id":"pl_bj_"}"#,
        #"{"type":"place","start":5,"end":7,"place_id":"pl_b_x"}"#,
        #"{"type":"place","start":5,"end":7,"place_id":"pl_bj__x"}"#,
        #"{"type":"place","start":5,"end":7,"place_id":"pl_bj_x y"}"#,
        #"{"type":"place","start":5,"end":7,"place_id":7}"#,
        #""place""#, "null", "7", "[]",
    ]) func aBadEntityIsDroppedAndTheGoodOnesStay(bad: String) throws {
        let value = rich("[\(bad),\(gugong)]")
        #expect(try decoded(row(rich: value)).rich?.entities == [.init(start: 2, end: 4, placeID: "pl_bj_gugong")])
        #expect(try decoded(row(rich: rich("[\(bad)]"))).rich == nil, "nothing left, no rich")
    }

    @Test func entitiesThatAreNotAnArrayReadAsNone() throws {
        for value in [#"{"version":"LIO-answer-rich.1","entities":{"a":1}}"#, #"{"version":"LIO-answer-rich.1","entities":"x"}"#] {
            #expect(try decoded(row(rich: value)).rich == nil)
        }
    }

    @Test func aPlaceIdLongerThanSixtyFourCharactersIsDropped() throws {
        let long = "pl_bj_" + String(repeating: "a", count: 58)
        #expect(long.utf8.count == 64 && LioTimelineWire.validPlaceID(long))
        #expect(!LioTimelineWire.validPlaceID(long + "a"))
        for good in ["pl_bj_gugong", "pl_cq_changjiang_suodao", "pl_bj_798", "pl_sh_a1_b2"] {
            #expect(LioTimelineWire.validPlaceID(good), "\(good)")
        }
        for bad in ["", "pl_", "pl_bj", "pl_bj_", "pl__x", "pl_BJ_x", "pl_bj_X", "pl_bj_a-b", "pl_bj_a_", "xx_bj_a", "pl_b1_x", "pl_bj_故宫"] {
            #expect(!LioTimelineWire.validPlaceID(bad), "\(bad)")
        }
    }

    // MARK: Declaring support

    @Test func richIsDeclaredOnTheV2TimelineOnlyAndTakesTheFollowupsPlace() async throws {
        let exit = RichExit()
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint(),
                                                validateMessage: {}, lio: true)
        _ = try await transport.readLio(conversationID: conversation, before: nil, bearer: "fixture", version: .v2)
        _ = try await transport.readLio(conversationID: conversation, before: "one", bearer: "fixture", version: .v2,
                                        declaresAnswerRich: true)
        _ = try await transport.readLio(conversationID: conversation, before: nil, bearer: "fixture", version: .v2,
                                        declaresAnswerLayout: true, declaresAnswerRich: true)
        _ = try await transport.readLio(conversationID: conversation, before: nil, bearer: "fixture", version: .v2,
                                        declaresAnswerLayout: true)
        _ = try await transport.readLio(conversationID: nil, before: nil, bearer: "fixture", version: .v1, declaresAnswerRich: true)
        _ = try await transport.readLio(conversationID: conversation, before: nil, bearer: "fixture", version: .v3,
                                        declaresAnswerRich: true)
        let paths = await exit.paths
        #expect(paths == [
            "/v2/lio/timeline?conversation_id=\(conversation)",
            "/v2/lio/timeline?conversation_id=\(conversation)&before=one&accepts=LIO-answer-rich.1",
            "/v2/lio/timeline?conversation_id=\(conversation)&accepts=LIO-answer-rich.1",
            "/v2/lio/timeline?conversation_id=\(conversation)&accepts=LIO-answer-followups.1",
            "/v1/lio/timeline", "/v3/lio/timeline?conversation_id=\(conversation)"
        ], "one accepts value, and only on v2")
        #expect(!paths.contains { $0.components(separatedBy: "accepts=").count > 2 }, "never twice")
    }

    @Test func aServerThatAnswers400ToRichIsReadAgainWithFollowupsAndRichWaitsFifteenMinutes() async throws {
        let exit = RichExit(rejectsRich: true)
        let client = try client(exit)
        let first = try await client.timeline(conversationID: nil, version: .v2, declaresAnswerRich: true)
        #expect(first.messages.isEmpty)
        let second = try await client.timeline(conversationID: nil, version: .v2, declaresAnswerRich: true)
        #expect(second.messages.isEmpty)
        #expect(await exit.paths == [
            "/v2/lio/timeline?accepts=LIO-answer-rich.1",
            "/v2/lio/timeline?accepts=LIO-answer-followups.1",
            "/v2/lio/timeline?accepts=LIO-answer-followups.1",
        ], "the first read tried rich once; later reads go straight to followups.1")
    }

    @Test func aServerThatKnowsRichIsAskedOnceAndKeepsBeingAsked() async throws {
        let exit = RichExit()
        let client = try client(exit)
        _ = try await client.timeline(conversationID: nil, version: .v2, declaresAnswerRich: true)
        _ = try await client.timeline(conversationID: nil, version: .v2, declaresAnswerRich: true)
        #expect(await exit.paths == ["/v2/lio/timeline?accepts=LIO-answer-rich.1", "/v2/lio/timeline?accepts=LIO-answer-rich.1"])
    }

    @Test func aBuildWithoutRichSendsExactlyWhatItSentBefore() async throws {
        let exit = RichExit(rejectsRich: true)
        let client = try client(exit)
        _ = try await client.timeline(conversationID: nil, version: .v2)
        _ = try await client.timeline(conversationID: nil, version: .v2, declaresAnswerLayout: true)
        #expect(await exit.paths == ["/v2/lio/timeline", "/v2/lio/timeline?accepts=LIO-answer-followups.1"])
    }

    @Test func aRefusedRichThatStillFailsFollowupsIsAnOrdinaryFailure() async throws {
        let exit = RichExit(rejectsRich: true, rejectsFollowups: true)
        let client = try client(exit)
        await #expect(throws: MessageHTTPFailure.invalidResponse) {
            _ = try await client.timeline(conversationID: nil, version: .v2, declaresAnswerRich: true)
        }
    }

    @Test func theDeclarationPausesForFifteenMinutesAndThenTriesAgain() {
        var declaration = LioAnswerRichDeclaration()
        let start = Date(timeIntervalSince1970: 1_000_000)
        #expect(declaration.allows(at: start))
        declaration.refused(at: start)
        #expect(!declaration.allows(at: start))
        #expect(!declaration.allows(at: start.addingTimeInterval(899)))
        #expect(declaration.allows(at: start.addingTimeInterval(900)))
        #expect(LioAnswerRichDeclaration() == LioAnswerRichDeclaration(), "a restart starts with rich allowed")
    }

    // MARK: Harness

    private func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                            maximumRequestBytes: 16_384, maximumResponseBytes: 4_500_000)
    }

    private func client(_ exit: RichExit) throws -> LioTimelineHTTP {
        let scope = try StorageScope(environment: "synthetic-rich", account: "synthetic-owner")
        let recovery = MessageRecovery(storage: RichStore())
        let lease = try recovery.activate(scope)
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint(),
                                                validateMessage: {}, lio: true)
        return LioTimelineHTTP(scope: scope, lease: lease, credentials: RichCredentials(), transport: transport)
    }
}

@MainActor private final class RichStore: SecureMessageStorage {
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {}
}

@MainActor private final class RichCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}

private actor RichExit: ClientTransport {
    private(set) var paths: [String] = []
    let rejectsRich: Bool
    let rejectsFollowups: Bool

    init(rejectsRich: Bool = false, rejectsFollowups: Bool = false) {
        self.rejectsRich = rejectsRich
        self.rejectsFollowups = rejectsFollowups
    }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let path = request.path ?? ""
        paths.append(path)
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        if (rejectsRich && path.contains("accepts=LIO-answer-rich.1"))
            || (rejectsFollowups && path.contains("accepts=LIO-answer-followups.1")) {
            response = HTTPResponse(status: .badRequest)
            response.headerFields[.contentType] = "application/json"
            return (response, HTTPBody("{}"))
        }
        return (response, HTTPBody(#"{"version":"LIO-timeline.2","conversation_id":null,"messages":[],"next_before":null}"#))
    }
}
