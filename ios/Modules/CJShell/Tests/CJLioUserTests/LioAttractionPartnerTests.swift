import Foundation
import Testing
@testable import CJLioUser

/// Third-party ticket links (#1593, JT 2026-11-25 「增补门票品类（推荐）」): public search links without
/// an affiliate ID until the credentials are handed over; some venues stay official-channel only.
struct LioAttractionPartnerTests {
    private func rule(_ id: String) -> LioAttractionBookingRule {
        LioAttractionBookingRule.all.first { $0.id == id }!
    }

    @Test func officialOnlyVenuesNeverGetThirdPartyLinks() {
        // JT: the Palace Museum, National Museum, Mao Memorial Hall, Tian'anmen and Shaanxi History Museum
        // stay on their official channels.
        let officialOnly = ["beijing.palace-museum", "beijing.national-museum", "beijing.mao-mausoleum",
                            "beijing.tiananmen-rostrum", "beijing.tiananmen-square", "xian.shaanxi-history-museum"]
        for id in officialOnly {
            #expect(LioAttractionPartner.links(for: rule(id)).isEmpty, "\(id) is official-channel only")
        }
        #expect(Set(LioAttractionPartner.officialOnly) == Set(officialOnly))
    }

    @Test func otherVenuesGetAPublicTripComSearchForTheirEnglishName() throws {
        let links = LioAttractionPartner.links(for: rule("beijing.mutianyu"))
        let trip = try #require(links.first { $0.partner == .tripCom })
        #expect(trip.url.absoluteString == "https://www.trip.com/things-to-do/list?keyword=Mutianyu%20Great%20Wall")
        let terracotta = try #require(LioAttractionPartner.links(for: rule("xian.qin-mausoleum-museum")).first)
        #expect(terracotta.url.absoluteString == "https://www.trip.com/things-to-do/list?keyword=Terracotta%20Warriors")
    }

    @Test func onlyTheSightNameLeavesThePhone() throws {
        for item in LioAttractionBookingRule.all {
            for link in LioAttractionPartner.links(for: item) {
                let components = try #require(URLComponents(url: link.url, resolvingAgainstBaseURL: false))
                #expect(components.scheme == "https")
                #expect(components.queryItems?.count == 1, "\(item.id): only the search term")
                let lower = link.url.absoluteString.lowercased()
                #expect(!lower.contains("allianceid") && !lower.contains("sid=") && !lower.contains("aid="),
                        "no affiliate ID before the credentials are handed over")
            }
        }
    }

    @Test func venuesWithoutThirdPartyTicketsGetNoLinks() {
        #expect(LioAttractionPartner.links(for: rule("shanghai.museum-east")).isEmpty)
        #expect(LioAttractionPartner.links(for: rule("xian.beilin-museum")).isEmpty)
    }

    @Test func disclosureIsShownOnlyOnceAffiliateLinksAreLive() {
        #expect(LioAttractionPartner.affiliateLinks == false)
        #expect(LioAttractionPartner.disclosure(.chinese) == nil)
        #expect(LioAttractionPartner.disclosure(.english, affiliate: true) == LioHotelResults.disclosure(.english))
    }
}
