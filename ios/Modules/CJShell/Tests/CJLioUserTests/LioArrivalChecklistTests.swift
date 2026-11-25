import Foundation
import Testing
@testable import CJLioUser

struct LioArrivalChecklistTests {
    @Test func stepsFollowTheFirstHoursInOrder() {
        #expect(LioArrivalStep.allCases == [.entry, .payment, .internet, .transfer, .taxi, .emergency])
        for language in [LioLanguage.english, .chinese] {
            let titles = LioArrivalStep.allCases.map { $0.title(language) }
            #expect(Set(titles).count == titles.count)
            #expect(LioArrivalStep.allCases.allSatisfy { !$0.summary(language).isEmpty })
        }
        #expect(Set(LioArrivalStep.allCases.map(\.identifier)).count == LioArrivalStep.allCases.count)
    }

    @Test func progressTicksRoundTripThroughStorage() {
        var progress = LioArrivalProgress(stored: "")
        #expect(progress.doneCount == 0)
        progress.toggle(.payment)
        progress.toggle(.entry)
        #expect(progress.isDone(.entry) && progress.isDone(.payment) && !progress.isDone(.taxi))
        #expect(progress.stored == "entry,payment")
        let restored = LioArrivalProgress(stored: progress.stored)
        #expect(restored == progress)
        progress.toggle(.entry)
        #expect(!progress.isDone(.entry))
        #expect(LioArrivalProgress(stored: "entry,unknown,,taxi").stored == "entry,taxi")
    }

    @Test func hotelComesFromTheTripsFirstMatchedStay() {
        func place(_ name: String, address: String?, matched: Bool) -> LioRichItinerary.Place {
            .init(nameZH: name, nameEN: name + " EN", address: address, matched: matched, point: nil)
        }
        let hotels: [LioRichItinerary.Hotel] = [
            .init(id: "a", place: place("未核实酒店", address: "某路 1 号", matched: false), note: nil),
            .init(id: "b", place: place("示例酒店", address: "示例路 8 号", matched: true), note: nil),
        ]
        let hotel = LioArrivalHotel(hotels: hotels)
        #expect(hotel == LioArrivalHotel(nameZH: "示例酒店", nameEN: "示例酒店 EN", addressZH: "示例路 8 号", source: .trip))
        #expect(LioArrivalHotel(hotels: [hotels[0]]) == nil)
        #expect(LioArrivalHotel(hotels: []) == nil)
    }

    @Test func typedHotelNeedsANameAndIsTrimmed() {
        #expect(LioArrivalHotel(typedName: "  ", address: "示例路") == nil)
        let typed = LioArrivalHotel(typedName: " 示例酒店 ", address: "  ")
        #expect(typed == LioArrivalHotel(nameZH: "示例酒店", nameEN: nil, addressZH: nil, source: .typed))
        #expect(typed?.driverRequestZH == "请送我到这家酒店")
    }

    @Test func featureIsOffUnlessTheBuildSaysYes() {
        #expect(LioArrivalFeature.infoKey == "G2CArrivalModeEnabled")
        #expect(LioArrivalFeature.enabled(infoValue: "YES"))
        for value: Any? in [nil, "NO", "yes", "1", true] {
            #expect(!LioArrivalFeature.enabled(infoValue: value))
        }
    }

    /// Guidance only: no sales, no partner or promotion links, unless JT approves one.
    @Test func internetAndPaymentGuidanceCarryNoLinks() {
        for language in [LioLanguage.english, .chinese] {
            let texts = LioArrivalInternetOption.allCases.flatMap { [$0.title(language), $0.detail(language)] }
                + [LioArrivalInternetOption.footnote(language)]
            #expect(texts.allSatisfy { !$0.isEmpty })
            #expect(texts.allSatisfy { !$0.localizedCaseInsensitiveContains("http") && !$0.contains("www.") })
        }
    }

    /// Getting from the airport: guidance only. No booking or partner links unless JT approves them.
    @Test func airportTransferGuidanceCoversTheChoicesWithoutLinks() {
        #expect(LioArrivalTransferOption.allCases == [.preBooked, .taxi, .busOrMetro])
        for language in [LioLanguage.english, .chinese] {
            let texts = LioArrivalTransferOption.allCases.flatMap { [$0.title(language), $0.detail(language)] }
                + [LioArrivalTransferOption.footnote(language)]
            #expect(texts.allSatisfy { !$0.isEmpty })
            #expect(texts.allSatisfy { !$0.localizedCaseInsensitiveContains("http") && !$0.contains("www.") })
            #expect(Set(LioArrivalTransferOption.allCases.map { $0.title(language) }).count == 3)
        }
        #expect(Set(LioArrivalTransferOption.allCases.map(\.symbol)).count == 3)
    }

    @Test func progressFromBeforeTheTransferStepStillLoads() {
        let old = LioArrivalProgress(stored: "entry,payment,internet,taxi")
        #expect(old.doneCount == 4 && !old.isDone(.transfer))
        var next = old
        next.toggle(.transfer)
        #expect(next.stored == "entry,payment,internet,transfer,taxi")
    }

    /// The trip home page reads and writes the same ticks and nationality; the keys are stored on devices.
    @Test func sharedStorageKeysStayStable() {
        #expect(LioArrivalProgress.storageKey == "lio.arrival.progress.v1")
        #expect(LioArrivalTrip.nationalityStorageKey == "lio.local-support.nationality")
    }

    @Test func stayDaysFromATripAreKeptInTheFormsRange() {
        #expect(LioArrivalTrip.formStayDays(7) == 7)
        #expect(LioArrivalTrip.formStayDays(0) == 1)
        #expect(LioArrivalTrip.formStayDays(-3) == 1)
        #expect(LioArrivalTrip.formStayDays(120) == 90)
        #expect(LioArrivalTrip.formStayRange == 1...90)
    }
}
