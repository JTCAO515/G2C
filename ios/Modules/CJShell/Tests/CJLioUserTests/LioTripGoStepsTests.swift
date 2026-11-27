import Foundation
import Testing
@testable import CJLioUser

/// #1979 (P0-5): no "get ready" page; the trip home opens on six steps in order, each one line and one "Go", and
/// each asks its own question when it is tapped. Views are not compiled on macOS, so the order, the words, the
/// "one Go" rule and where the answers are kept are tested here, in both languages.
@MainActor struct LioTripGoStepsTests {
    private static let shanghai = TimeZone(identifier: "Asia/Shanghai")!
    private let started = Date(timeIntervalSince1970: 1_795_000_000)

    private static func at(_ text: String) -> Date {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = shanghai
        formatter.dateFormat = "yyyy-MM-dd HH:mm"
        return formatter.date(from: text)!
    }

    /// Every tool on, and a router that can open the metro guide and the hotel search.
    private static func everything(profile: LioTripProfile? = nil) -> LioTripChecklist {
        LioTripChecklist(.init(now: at("2026-11-26 10:00"), timeZone: shanghai, profile: profile,
                               entry: .missingDetails, arrivalChecklist: .init(done: [], total: 6), hotelSaved: false,
                               showCards: true, attractionBooking: true, routableTools: [.metro, .hotels]))
    }

    private func folder() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("trip-go-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    // MARK: - Order and shape

    @Test func theSixStepsComeInOrderWithOrWithoutATrip() {
        let order = ["entry", "arrival", "hotel", "payment", "internet", "local"]
        #expect(LioTripTask.stepKeys == order)
        let noTrip = Self.everything()
        #expect(!noTrip.hasTrip)
        #expect(noTrip.tasks(in: .beforeTrip).prefix(6).map(\.key) == order)
        let trip = Self.everything(profile: LioTripProfile(arrival: LioTripDay("2026-12-08"), stayDays: 7, cityID: nil,
                                                           startedAt: started))
        #expect(trip.tasks(in: .beforeTrip).prefix(6).map(\.key) == order)
    }

    @Test func aStepWhoseToolIsMissingIsLeftOutRatherThanShownWithoutAWayToDoIt() {
        let list = LioTripChecklist(.init(now: Self.at("2026-11-26 10:00"), timeZone: Self.shanghai))
        // No Arrival Mode, no Back to Hotel, no router: arrival (it only asks) and payment remain.
        #expect(list.tasks.filter { LioTripTask.stepKeys.contains($0.key) }.map(\.key) == ["arrival", "payment"])
    }

    @Test func theHotelStepIsATickWhenOnlyTheHotelSearchCanOpenIt() {
        let list = LioTripChecklist(.init(now: Self.at("2026-11-26 10:00"), timeZone: Self.shanghai,
                                          routableTools: [.hotels]))
        let hotel = list.tasks.first { $0.key == "hotel" }
        #expect(hotel?.tick == .manual)
        #expect(hotel?.done == .open)
    }

    @Test(arguments: [LioLanguage.english, .chinese])
    func eachStepIsOneLineWithNoHeadingAndNoExplanation(language: LioLanguage) {
        let steps = Self.everything().tasks.filter { LioTripTask.stepKeys.contains($0.key) }
        #expect(steps.count == 6)
        for step in steps {
            let line = LioTripHomeCopy.title(step, language)
            #expect(!line.isEmpty && !line.contains("\n"), "\(step.key)")
            // The line is the whole row: nothing is shown under it.
            #expect(LioTripHomeCopy.detail(step, language).isEmpty, "\(step.key)")
        }
        #expect(Set(steps.map { LioTripHomeCopy.title($0, language) }).count == 6)
    }

    @Test func theOldHeadingsAreGoneFromBothLanguages() {
        let words = Self.everything().tasks.flatMap { task in
            [LioTripHomeCopy.title(task, .english), LioTripHomeCopy.title(task, .chinese)]
        }.joined(separator: "\n")
        for old in ["确认入境方式", "填入境卡", "准备上网", "保存酒店中文名和地址", "Check how you can enter China",
                    "Fill in the arrival card", "Sort out mobile data", "Just get ready", "先只做准备"] {
            #expect(!words.contains(old), "\(old)")
        }
    }

    @Test func eachStepHasExactlyOneGoButtonAndItIsCalledGo() {
        for step in Self.everything().tasks where LioTripTask.stepKeys.contains(step.key) {
            #expect(step.hasGo, "\(step.key)")
        }
        #expect(LioTripHomeCopy.go(.chinese) == "去办")
        #expect(LioTripHomeCopy.go(.english) == "Go")
    }

    @Test func theArrivalLineShowsWhatWasAnswered() {
        let day = LioTripDay("2026-12-08")!
        #expect(LioTripHomeCopy.arrival(day: nil, number: nil, .chinese) == "填到达日期和航班或车次")
        #expect(LioTripHomeCopy.arrival(day: nil, number: nil, .english) == "Add your arrival day and flight or train")
        #expect(LioTripHomeCopy.arrival(day: day, number: nil, .chinese) == "12月8日到达")
        #expect(LioTripHomeCopy.arrival(day: day, number: "CA1234", .chinese) == "12月8日到达 · CA1234")
        #expect(LioTripHomeCopy.arrival(day: day, number: "CA1234", .english) == "Arriving 8 Dec · CA1234")
    }

    @Test func theArrivalStepIsDoneByItsAnswerAndOnlyThen() {
        let open = Self.everything().tasks.first { $0.key == "arrival" }
        #expect(open?.done == .open)
        #expect(open?.tick == .manual)
        let profile = LioTripProfile(arrival: LioTripDay("2026-12-08"), stayDays: nil, cityID: nil, arrivalNumber: "mu5101",
                                     startedAt: started)
        let answered = Self.everything(profile: profile).tasks.first { $0.key == "arrival" }
        #expect(answered?.done == .automatic)
        #expect(answered?.kind == .arrival(day: LioTripDay("2026-12-08"), number: "MU5101"))
    }

    // MARK: - Where the answers are kept

    @Test func theArrivalDayAndNumberAreKeptWithTheTripAndTheFirstAnswerStartsIt() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        func make() -> LioTripHomeModel {
            LioTripHomeModel(store: LioTripHomeStore(directory: directory, isCurrent: { true }))
        }
        let model = make()
        #expect(model.profile == nil)
        // A tick made before any answer is not lost when the first answer starts the trip.
        model.setTick("payment", done: true)
        model.updateOrStart(at: started) { profile in
            profile.arrival = LioTripDay("2026-12-08")
            profile.arrivalNumber = LioTripProfile.cleanArrivalNumber("ca 1234")
        }
        let reloaded = make()
        #expect(reloaded.profile?.arrival == LioTripDay("2026-12-08"))
        #expect(reloaded.profile?.arrivalNumber == "CA1234")
        #expect(reloaded.profile?.startedAt == started)
        #expect(reloaded.ticks.isDone("payment"))
        // Changing the answer later keeps the rest.
        reloaded.updateOrStart { $0.stayStars = 4 }
        #expect(make().profile?.stayStars == 4)
        #expect(make().profile?.arrival == LioTripDay("2026-12-08"))
    }

    @Test func theNumberAndTheHotelLevelAreReadBackThroughTheirLimits() {
        #expect(LioTripProfile.cleanArrivalNumber(" mu 5101 ") == "MU5101")
        #expect(LioTripProfile.cleanArrivalNumber("<b>G1234</b>") == "BG1234B")
        #expect(LioTripProfile.cleanArrivalNumber(String(repeating: "A1", count: 20))?.count == LioTripProfile.maximumArrivalNumberLength)
        #expect(LioTripProfile.cleanArrivalNumber("航班") == nil)
        #expect(LioTripProfile.cleanArrivalNumber("   ") == nil)
        #expect(LioTripProfile(arrival: nil, stayDays: nil, cityID: nil, stayStars: 2, startedAt: started).stayStars == nil)
        #expect(LioTripProfile(arrival: nil, stayDays: nil, cityID: nil, stayStars: 6, startedAt: started).stayStars == nil)
        #expect(LioTripProfile(arrival: nil, stayDays: nil, cityID: nil, stayStars: 5, startedAt: started).stayStars == 5)
    }

    @Test func aFileWrittenBeforeTheNewAnswersExistedStillReads() throws {
        let json = #"{"arrival":"2026-12-08","stayDays":7,"cityID":"beijing","startedAt":0}"#
        let profile = try JSONDecoder().decode(LioTripProfile.self, from: Data(json.utf8))
        #expect(profile.arrival == LioTripDay("2026-12-08"))
        #expect(profile.arrivalNumber == nil)
        #expect(profile.stayStars == nil)
        // A wrong type for a new field reads as "not given", not as a damaged trip.
        let odd = #"{"arrival":"2026-12-08","arrivalNumber":5,"stayStars":"four","startedAt":0}"#
        let readOdd = try JSONDecoder().decode(LioTripProfile.self, from: Data(odd.utf8))
        #expect(readOdd.arrivalNumber == nil && readOdd.stayStars == nil)
    }

    @Test func thePassportIsNotInTheTripFileButInTheSharedNationalitySetting() throws {
        let suite = "trip-go-" + UUID().uuidString
        let defaults = try #require(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        // Signed out: the answer goes to the device-wide key, as before.
        let signedOut = LioNationalityStore(account: nil, defaults: defaults)
        signedOut.value = "DE"
        #expect(defaults.string(forKey: LioNationalityStore.legacyKey) == "DE")
        // The next sign-in moves it to that account.
        let account = LioNationalityStore(account: "A", defaults: defaults)
        #expect(account.value == "DE")
        #expect(defaults.object(forKey: LioNationalityStore.legacyKey) == nil)
        // The trip file never carries it.
        let profile = LioTripProfile(arrival: LioTripDay("2026-12-08"), stayDays: 7, cityID: nil, startedAt: started)
        let text = String(decoding: try JSONEncoder().encode(profile), as: UTF8.self).lowercased()
        #expect(!text.contains("nationality") && !text.contains("passport") && !text.contains("\"de\""))
    }
}
