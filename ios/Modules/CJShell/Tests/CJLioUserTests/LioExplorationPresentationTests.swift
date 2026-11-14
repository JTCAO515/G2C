import Testing
@testable import CJLioUser

struct LioExplorationPresentationTests {
    @Test func emptyNewBodyKeepsThePlainAnswer() {
        let value = LioExplorationPresentation(segments: [], profile: [], notices: [], exits: [], answer: "Plain legacy reply")
        #expect(value.plainAnswer(questionCount: 0) == "Plain legacy reply")
        #expect(value.plainAnswer(questionCount: 1) == nil)
    }

    @Test func profileAloneDoesNotConsumeTheAnswer() {
        let entry = LioExplorationPresentation.ProfileEntry(id: "pace", displayText: "Slow", state: .memory)
        let value = LioExplorationPresentation(segments: [], profile: [entry], notices: [], exits: [], answer: "已有正文")
        #expect(value.plainAnswer(questionCount: 0) == "已有正文")
        #expect(entry.annotation(.chinese) == "之前的偏好")
    }

    @Test func segmentsNoticesAndExitsSuppressTheCompatibilityProjection() {
        let source = LioSource(id: "weather", title: "Weather", url: nil)
        let notice = LioExplorationPresentation.Notice(id: "weather-day-1", text: "Bring a coat", severity: .info, source: source)
        let exit = LioExplorationPresentation.Exit(id: "plan_now", displayText: "Plan now", sendText: "Please make the plan")
        let values = [
            LioExplorationPresentation(segments: [.init(purpose: .direction, text: "先看看这些方向")], profile: [], notices: [], exits: [], answer: "projection"),
            LioExplorationPresentation(segments: [], profile: [], notices: [notice], exits: [], answer: "projection"),
            LioExplorationPresentation(segments: [], profile: [], notices: [], exits: [exit], answer: "projection")
        ]
        for value in values { #expect(value.plainAnswer(questionCount: 0) == nil) }
    }

    @Test func noEmptyPlainBubbleAndNoClaimOfSavingInAnnotations() {
        let empty = LioExplorationPresentation(segments: [], profile: [], notices: [], exits: [], answer: "")
        #expect(empty.plainAnswer(questionCount: 0) == nil)
        let known = LioExplorationPresentation.ProfileEntry(id: "city", displayText: "北京", state: .known)
        #expect(known.annotation(.chinese) == nil)
        let assumed = LioExplorationPresentation.ProfileEntry(id: "pace", displayText: "适中", state: .defaultValue)
        #expect(assumed.annotation(.chinese) == "暂按这个安排")
    }
}
