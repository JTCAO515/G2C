import Foundation
import Testing
@testable import CJLioUser

/// #1727: the two-bubble layout and the server's buttons, behind `G2CAnswerLayoutEnabled`.
struct LioAnswerLayoutTests {
    @Test func flagIsOffUnlessTheBuildSaysYes() {
        #expect(LioAnswerLayoutFeature.infoKey == "G2CAnswerLayoutEnabled")
        #expect(!LioAnswerLayoutFeature.enabled(infoValue: nil))
        #expect(!LioAnswerLayoutFeature.enabled(infoValue: "NO"))
        #expect(!LioAnswerLayoutFeature.enabled(infoValue: true))
        #expect(LioAnswerLayoutFeature.enabled(infoValue: "YES"))
        #expect(!LioAnswerLayoutFeature.enabledInBuild, "the test bundle sets no flag")
    }

    @Test func infoPlistReadsTheFlagFromABuildSettingThatNoConfigurationSets() throws {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(plist.contains("<key>G2CAnswerLayoutEnabled</key><string>$(G2C_ANSWER_LAYOUT_ENABLED)</string>"))
        #expect(!project.contains("G2C_ANSWER_LAYOUT_ENABLED"), "off unless the release script passes it")
    }

    @Test func anAnswerIsCutAtItsFirstBlankLine() {
        let parts = LioAnswerParts("先找最近的地铁站。\n\n进站后看线路编号。\n\n告诉我你从哪儿出发。")
        #expect(parts.head == "先找最近的地铁站。")
        #expect(parts.tail == "进站后看线路编号。\n\n告诉我你从哪儿出发。", "only the first blank line cuts")
    }

    @Test func extraNewlinesAroundTheCutBelongToNeitherBubble() {
        let parts = LioAnswerParts("One.\n\n\n\nTwo.")
        #expect(parts.head == "One." && parts.tail == "Two.")
    }

    @Test func noBlankLineMeansOneBubble() {
        #expect(LioAnswerParts("One.\nTwo.") == LioAnswerParts(whole: "One.\nTwo."))
        #expect(LioAnswerParts("One.").tail == nil)
    }

    /// While streaming, the head only ever grows: a lone newline at the end is left out until the cut is known.
    @Test func theHeadNeverShrinksWhileTheAnswerStreams() {
        let steps = ["On", "One.", "One.\n", "One.\n\n", "One.\n\nT", "One.\n\nTwo"]
        var previous = ""
        for step in steps {
            let head = LioAnswerParts(step).head
            #expect(head.hasPrefix(previous), "\(previous) then \(head)")
            previous = head
        }
        #expect(LioAnswerParts("One.\n\n").tail == nil, "no second bubble until it has text")
        #expect(LioAnswerParts("One.\n\nT").tail == "T")
    }

    @Test func theWholeAnswerPathIsByteForByteTheSource() {
        let source = "One.\n\nTwo.\n"
        #expect(LioAnswerParts(whole: source).head == source && LioAnswerParts(whole: source).tail == nil)
    }

    // MARK: routes from server buttons

    @Test func registeredToolsOpenAndUnknownOnesDoNot() {
        #expect(LioRoute(tool: LioTool("payment-guide"), parameters: [:]) != nil)
        #expect(LioRoute(tool: LioTool("taxi"), parameters: [:]) != nil)
        #expect(LioRoute(tool: LioTool("trip"), parameters: ["trip_id": "t1"]) == nil, "not in this build's registry")
        #expect(LioRoute(tool: LioTool("no-such-tool"), parameters: [:]) == nil)
    }

    @Test func aTaxiButtonCarriesOnlyTheParametersTheTaxiToolDeclares() throws {
        let route = try #require(LioRoute(tool: LioTool("taxi"), parameters: [
            "destination": "故宫博物院", "lat": "39.918058", "lng": "116.397026", "address": "景山前街4号",
            "destinationEN": "Palace Museum", "evil": "x"]))
        #expect(route.parameters.keys.sorted() == ["address", "destination", "destinationEN", "lat", "lng"])
    }

    @Test func aValueMadeOfManyCombiningMarksIsDroppedByTheByteBound() throws {
        // One user-visible character of 700 bytes passes a character count of 200 but not the byte bound.
        let tower = "a" + String(repeating: "\u{0301}", count: 400)
        #expect(tower.count == 1 && tower.utf8.count > LioRoute.maximumValueBytes)
        let route = try #require(LioRoute(tool: LioTool("taxi"), parameters: ["destination": tower, "lat": "39.9", "lng": "116.4"]))
        #expect(route.parameters["destination"] == nil)
        #expect(route.parameters["lat"] == "39.9")
    }
}
