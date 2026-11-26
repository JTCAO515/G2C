import Testing
@testable import CJLioUser

struct LioBusinessCardTests {
    @Test func theMeetingCardNeedsWhoItIsFor() {
        #expect(!LioMeetingCardInput().isReady)
        #expect(!LioMeetingCardInput(contact: "  \n ", time: "14:00").isReady)
        #expect(LioMeetingCardInput(contact: "李明").isReady)
    }

    @Test func theMeetingCardIsChineseLargeWithTimeAndPlaceAndEnglishUnderIt() {
        let card = LioShowCardContent.meeting(.init(contact: " 广州某某贸易有限公司 李明 ", time: "14:00",
                                                    address: "琶洲展馆 A 区"))
        #expect(card.leadZH == "您好，我约了人见面，请帮我联系或带路：")
        #expect(card.mainZH == "广州某某贸易有限公司 李明")
        #expect(card.detailsZH == ["时间：14:00", "地点：琶洲展馆 A 区"])
        #expect(card.english.first?.hasPrefix("I'm here to meet") == true)
        #expect(card.english.dropFirst() == ["Time: 14:00", "Place: 琶洲展馆 A 区"])
    }

    @Test func emptyOptionalLinesAreLeftOut() {
        let card = LioShowCardContent.meeting(.init(contact: "Mr. Li, ABC Trading", time: " ", address: ""))
        #expect(card.mainZH == "Mr. Li, ABC Trading")
        #expect(card.detailsZH.isEmpty)
        #expect(card.english.count == 1)
    }
}
