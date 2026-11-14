import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

struct LioThinkingTests {
    @Test func phasesFollowTheResponseTimeBands() {
        for language in [LioLanguage.english, .chinese] {
            #expect(LioThinkingPhase.at(0, progress: nil, language: language) == .hidden)
            #expect(LioThinkingPhase.at(0.29, progress: nil, language: language) == .hidden)
            #expect(LioThinkingPhase.at(0.3, progress: nil, language: language) == .breathing)
            #expect(LioThinkingPhase.at(5.99, progress: "Checking the weather", language: language) == .breathing)
        }
        #expect(LioThinkingPhase.at(6, progress: nil, language: .chinese) == .status("正在整理信息…"))
        #expect(LioThinkingPhase.at(14.9, progress: nil, language: .chinese) == .status("正在整理信息…"))
        #expect(LioThinkingPhase.at(15, progress: nil, language: .chinese) == .status("这次要多想一会儿…"))
        #expect(LioThinkingPhase.at(6, progress: nil, language: .english) == .status("Pulling the details together…"))
        #expect(LioThinkingPhase.at(15, progress: nil, language: .english) == .status("This one is taking a little longer…"))
    }

    @Test func lineLProgressReplacesTheGeneralCopyOnlyWhenPresent() {
        #expect(LioThinkingPhase.at(7, progress: "正在比较几家酒店的位置", language: .chinese) == .status("正在比较几家酒店的位置"))
        #expect(LioThinkingPhase.at(20, progress: " ", language: .chinese) == .status("这次要多想一会儿…"))
        #expect(LioThinkingPhase.at(1, progress: "正在比较几家酒店的位置", language: .chinese) == .breathing)
    }

    @Test func lineLProgressMapsToTheIndicatorWithoutInventingDays() {
        #expect(LioThinkingInput(nil) == LioThinkingInput())
        #expect(LioThinkingInput(.waiting("正在比较几家酒店的位置")) == LioThinkingInput(progress: "正在比较几家酒店的位置"))
        #expect(LioThinkingInput(.planningStarted(text: "Planning your 3 days", days: 3))
                == LioThinkingInput(progress: "Planning your 3 days", planningDays: 3))
        #expect(LioThinkingInput(.planningStarted(text: "Planning", days: 0)).planningDays == nil)
    }

    @Test func announcementsAreChangesAtMostEveryFiveSeconds() {
        var throttle = LioAnnouncementThrottle()
        let start = Date(timeIntervalSince1970: 1_000)
        let steps: [(String, TimeInterval, Bool)] = [
            ("A", 0, true), ("A", 10, false), ("B", 4.9, false), ("B", 5, true), ("C", 9, false), ("C", 10, true)
        ]
        for (text, offset, expected) in steps {
            let announced = throttle.shouldAnnounce(text, at: start.addingTimeInterval(offset))
            #expect(announced == expected, "\(text) at \(offset)")
        }
    }

    #if os(iOS)
    @Test func dotsLiftAtMostThreePointsAndInTurn() {
        for step in 0..<240 {
            let time = Double(step) / 100
            for index in 0..<3 {
                let lift = LioRisingDots.lift(time, index: index)
                #expect(lift <= 0 && lift >= -3)
            }
        }
        #expect(LioRisingDots.lift(0.3, index: 0) < LioRisingDots.lift(0.3, index: 1))
    }
    #endif

    @MainActor
    @Test func timingRecordsDurationsOnlyOncePerMilestone() throws {
        let defaults = try #require(UserDefaults(suiteName: "lio.timing.tests.\(UUID().uuidString)"))
        let log = LioTimingLog(defaults: defaults)
        let turn = Data("turn".utf8)
        let sent = Date(timeIntervalSince1970: 2_000)
        log.start(turn, language: "zh-Hans", at: sent)
        #expect(log.sentAt(turn) == sent)
        #expect(log.indicatorStart(turn) == sent)
        log.mark(.indicator, turn, at: sent.addingTimeInterval(0.31))
        log.mark(.indicator, turn, at: sent.addingTimeInterval(3))
        log.mark(.firstText, turn, at: sent.addingTimeInterval(17.2))
        log.mark(.firstText, turn, at: sent.addingTimeInterval(18))
        #expect(log.entries().isEmpty)
        log.mark(.finished, turn, at: sent.addingTimeInterval(21.5))
        #expect(log.entries() == [LioTimingLog.Entry(sentAt: 2_000, language: "zh-Hans",
                                                     indicatorMs: 310, firstTextMs: 17_200, finishedMs: 21_500)])
        log.mark(.finished, turn, at: sent.addingTimeInterval(30))
        #expect(log.entries().count == 1)

        let stored = try #require(defaults.data(forKey: LioTimingLog.defaultsKey))
        let keys = try #require(try JSONSerialization.jsonObject(with: stored) as? [[String: Any]]).first.map { Set($0.keys) }
        #expect(keys == ["sent_at", "language", "indicator_ms", "first_text_ms", "finished_ms"])
    }

    @MainActor
    @Test func timingKeepsTheNewestFiftyAndSkipsRestoredTurns() throws {
        let defaults = try #require(UserDefaults(suiteName: "lio.timing.tests.\(UUID().uuidString)"))
        let log = LioTimingLog(defaults: defaults)
        let base = Date(timeIntervalSince1970: 3_000)
        for index in 0..<55 {
            let turn = Data("t\(index)".utf8)
            log.start(turn, language: "en", at: base.addingTimeInterval(Double(index)))
            log.mark(.finished, turn, at: base.addingTimeInterval(Double(index) + 1))
        }
        let entries = log.entries()
        #expect(entries.count == LioTimingLog.capacity)
        #expect(entries.first?.sentAt == 3_005)
        #expect(entries.last?.sentAt == 3_054)

        let restored = Data("restored".utf8)
        let seen = base.addingTimeInterval(100)
        #expect(log.indicatorStart(restored, now: seen) == seen)
        #expect(log.indicatorStart(restored, now: seen.addingTimeInterval(5)) == seen)
        log.mark(.finished, restored, at: seen.addingTimeInterval(9))
        #expect(log.entries().count == LioTimingLog.capacity)
        #expect(log.entries().last?.sentAt == 3_054)
    }
}
