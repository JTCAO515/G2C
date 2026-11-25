import Foundation
import Testing
@testable import CJLioUser

/// Third-party ticket links (#1593, JT 2026-11-25 「增补门票品类（推荐）」): public search links without
/// an affiliate ID until the credentials are handed over; some venues stay official-channel only.
struct LioAttractionPartnerTests {
    private func rule(_ id: String) -> LioAttractionBookingRule {
        LioAttractionBookingRule.all.first { $0.id == id }!
    }

    /// The same rule with third-party links switched on, as a mis-edit of the table would do.
    private func allowingThirdParties(_ r: LioAttractionBookingRule) -> LioAttractionBookingRule {
        .init(id: r.id, nameEN: r.nameEN, nameZH: r.nameZH, cityEN: r.cityEN, cityZH: r.cityZH, aliases: r.aliases,
              requirement: r.requirement, windowDays: r.windowDays, releaseTime: r.releaseTime, passport: r.passport,
              closedWeekdays: r.closedWeekdays, openOnPublicHolidays: r.openOnPublicHolidays,
              limitsEN: r.limitsEN, limitsZH: r.limitsZH, notesEN: r.notesEN, notesZH: r.notesZH,
              officialChannel: r.officialChannel, partnerLinks: true, sources: r.sources, checkedOn: r.checkedOn)
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

    @Test func officialOnlyHoldsEvenIfTheTableIsMisedited() {
        // The lock is in the partner code, not only in the table's partnerLinks values.
        for id in LioAttractionPartner.officialOnly {
            #expect(LioAttractionPartner.links(for: allowingThirdParties(rule(id))).isEmpty, "\(id)")
        }
        #expect(!LioAttractionPartner.links(for: allowingThirdParties(rule("xian.beilin-museum"))).isEmpty)
    }

    @Test func pagesWithoutThirdPartyLinksSayOfficialChannelOnly() {
        #expect(LioAttractionPartner.paymentNote(.chinese, for: rule("beijing.palace-museum"))
                == "预约和付款都在官方渠道完成，Go2China 不售票。")
        #expect(LioAttractionPartner.paymentNote(.chinese, for: rule("beijing.mutianyu"))
                == "预约和付款在官方渠道或票务网站完成，Go2China 不售票。")
        #expect(LioAttractionPartner.paymentNote(.english, for: rule("beijing.palace-museum"))
                == "Booking and payment happen on the official channel; Go2China does not sell tickets.")
        #expect(LioAttractionPartner.paymentNote(.english, for: rule("beijing.mutianyu"))
                == "Booking and payment happen on the official channel or the ticket site; Go2China does not sell tickets.")
    }

    @Test func otherVenuesGetAPublicTripComSearchForTheirEnglishName() throws {
        let links = LioAttractionPartner.links(for: rule("beijing.mutianyu"))
        let trip = try #require(links.first { $0.partner == .tripCom })
        #expect(trip.url.absoluteString == "https://www.trip.com/things-to-do/list?keyword=Mutianyu%20Great%20Wall")
        let klook = try #require(links.first { $0.partner == .klook })
        #expect(klook.url.absoluteString == "https://www.klook.com/search/result/?query=Mutianyu%20Great%20Wall")
        #expect(links.map(\.partner) == [.tripCom, .klook])
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
