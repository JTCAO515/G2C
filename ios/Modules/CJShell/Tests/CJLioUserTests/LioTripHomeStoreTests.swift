import Foundation
import Testing
@testable import CJLioUser

/// Trip home phase 1 (T1): the trip profile and ticks stay on this device, in the account's message folder.
@MainActor struct LioTripHomeStoreTests {
    private let started = Date(timeIntervalSince1970: 1_795_000_000)

    private func folder() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("trip-home-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    private func profile(stayDays: Int? = 7) -> LioTripProfile {
        LioTripProfile(arrival: LioTripDay("2026-12-08"), stayDays: stayDays, cityID: "beijing", startedAt: started)
    }

    @Test func profileAndTicksComeBackFromTheAccountFolder() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripHomeStore(directory: LioTripHomeStore.storageDirectory(inMessageDirectory: directory),
                                     isCurrent: { true })
        #expect(try store.load() == .init())
        var ticks = LioTripTicks()
        ticks.set("payment", done: true, at: started)
        try store.save(.init(profile: profile(), ticks: ticks))
        let loaded = try store.load()
        #expect(loaded.profile == profile())
        #expect(loaded.ticks.isDone("payment"))
        #expect(!loaded.ticks.isDone("medical-card"))
        let folder = directory.appendingPathComponent(LioTripHomeStore.directoryName, isDirectory: true)
        #expect(try FileManager.default.contentsOfDirectory(atPath: folder.path) == [LioTripHomeStore.fileName])
        #expect(try folder.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup == true)
        try store.clear()
        #expect(try store.load() == .init())
        try store.clear()
    }

    @Test func anotherAccountCannotReadOrWriteTheTrip() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        var current = true
        let store = LioTripHomeStore(directory: directory, isCurrent: { current })
        try store.save(.init(profile: profile()))
        current = false
        #expect(throws: CancellationError.self) { try store.load() }
        #expect(throws: CancellationError.self) { try store.save(.init()) }
        #expect(throws: CancellationError.self) { try store.clear() }
        current = true
        #expect(try store.load().profile == profile())
    }

    @Test func aDamagedOrNewerFileReadsAsAnEmptyTrip() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripHomeStore(directory: directory, isCurrent: { true })
        let file = directory.appendingPathComponent(LioTripHomeStore.fileName)
        for bytes in ["not json", #"{"version":2,"snapshot":null}"#, #"{"version":1,"snapshot":{"profile":{"arrival":"2026-02-30","startedAt":0}}}"#] {
            try Data(bytes.utf8).write(to: file)
            #expect(try store.load() == .init(), "\(bytes)")
        }
    }

    @Test func aProfileReadBackKeepsTheSameLimits() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripHomeStore(directory: directory, isCurrent: { true })
        let longKey = String(repeating: "k", count: LioTripTicks.maximumKeyLength + 1)
        let json = #"{"version":1,"snapshot":{"profile":{"arrival":"2026-12-08","stayDays":99999,"cityID":"","planID":"p","startedAt":0},"ticks":{"done":{"payment":0,"\#(longKey)":0,"":0}}}}"#
        try Data(json.utf8).write(to: directory.appendingPathComponent(LioTripHomeStore.fileName))
        let loaded = try store.load()
        #expect(loaded.profile?.stayDays == LioTripProfile.maximumStayDays)
        #expect(loaded.profile?.cityID == nil)
        #expect(loaded.profile?.planID == "p")
        #expect(loaded.ticks.done.keys.sorted() == ["payment"])
    }

    @Test func ticksKeepTheNewestWithinTheCap() {
        var ticks = LioTripTicks()
        for index in 0..<(LioTripTicks.maximumCount + 5) {
            ticks.set("task-\(index)", done: true, at: started.addingTimeInterval(TimeInterval(index)))
        }
        #expect(ticks.done.count == LioTripTicks.maximumCount)
        #expect(!ticks.isDone("task-0"))
        #expect(ticks.isDone("task-\(LioTripTicks.maximumCount + 4)"))
        ticks.set("task-\(LioTripTicks.maximumCount + 4)", done: false, at: started)
        #expect(!ticks.isDone("task-\(LioTripTicks.maximumCount + 4)"))
        ticks.set(String(repeating: "x", count: LioTripTicks.maximumKeyLength + 1), done: true, at: started)
        #expect(ticks.done.count == LioTripTicks.maximumCount - 1)
    }

    @Test func aNewTripStartsWithoutTheLastTripsTicks() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let model = LioTripHomeModel(store: LioTripHomeStore(directory: directory, isCurrent: { true }))
        model.start(profile())
        model.setTick("payment", done: true)
        #expect(model.ticks.isDone("payment"))
        model.start(profile(stayDays: 3))
        #expect(!model.ticks.isDone("payment"))
        #expect(model.profile?.stayDays == 3)
        model.update { $0.cityID = "shanghai" }
        #expect(LioTripHomeModel(store: LioTripHomeStore(directory: directory, isCurrent: { true })).profile?.cityID == "shanghai")
        model.clear()
        #expect(model.profile == nil)
        #expect(try LioTripHomeStore(directory: directory, isCurrent: { true }).load() == .init())
    }

    @Test func aFailedSaveKeepsWhatWasShownAndSaysSo() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        // A file where the folder should be: every save fails.
        let blocked = directory.appendingPathComponent("blocked")
        try Data().write(to: blocked)
        let model = LioTripHomeModel(store: LioTripHomeStore(directory: blocked, isCurrent: { true }))
        model.start(profile())
        #expect(model.profile == nil)
        #expect(model.saveFailed)
    }

    @Test func anotherAccountSeesNothingAndChangesNothing() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        var current = true
        let model = LioTripHomeModel(store: LioTripHomeStore(directory: directory, isCurrent: { current }))
        model.start(profile())
        current = false
        #expect(model.profile == nil)
        #expect(!model.persists)
        model.setTick("payment", done: true)
        model.clear()
        current = true
        #expect(model.profile == profile())
        #expect(!model.ticks.isDone("payment"))
    }

    @Test func withoutAnAccountFolderTheTripLastsOnlyThisSession() {
        let model = LioTripHomeModel(store: nil)
        #expect(!model.persists)
        model.start(profile())
        model.setTick("payment", done: true)
        #expect(model.profile == profile())
        #expect(model.ticks.isDone("payment"))
    }

    @Test func theSwitchIsOnOnlyForTheStringYes() {
        #expect(LioTripHomeFeature.infoKey == "G2CTripHomeEnabled")
        #expect(LioTripHomeFeature.enabled(infoValue: "YES"))
        for value: Any? in [nil, "", "NO", "yes", "1", true, 1, "$(G2C_TRIP_HOME_ENABLED)"] {
            #expect(!LioTripHomeFeature.enabled(infoValue: value), "\(String(describing: value))")
        }
    }

    @Test func tripDaysParseCompareAndCount() throws {
        let day = try #require(LioTripDay("2026-12-31"))
        #expect(day.adding(days: 1).description == "2027-01-01")
        #expect(day.adding(days: -365).description == "2025-12-31")
        #expect(day.days(until: try #require(LioTripDay("2027-01-10"))) == 10)
        #expect(try #require(LioTripDay("2027-01-10")).days(until: day) == -10)
        #expect(LioTripDay("2026-12-08")! < day)
        for bad in ["2026-2-1", "2026-02-30", "26-12-01", "2026/12/01", "", "2026-12-01T00:00"] {
            #expect(LioTripDay(bad) == nil, "\(bad)")
        }
        #expect(day.adding(days: .max) == day.adding(days: 36_600))
        // The same instant is a different day in Los Angeles and Shanghai.
        let instant = Date(timeIntervalSince1970: 1_796_342_400) // 2026-12-04 00:00 UTC
        #expect(LioTripDay(date: instant, timeZone: TimeZone(identifier: "America/Los_Angeles")!).description == "2026-12-03")
        #expect(LioTripDay(date: instant, timeZone: TimeZone(identifier: "Asia/Shanghai")!).description == "2026-12-04")
        let encoded = try JSONEncoder().encode(day)
        #expect(String(decoding: encoded, as: UTF8.self) == "\"2026-12-31\"")
        #expect(try JSONDecoder().decode(LioTripDay.self, from: encoded) == day)
    }

    // MARK: - #1649 review, P3 follow-ups

    @Test func anUnreadableFileIsNeverOverwrittenByAnEmptyScreen() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        // A folder where the file should be: reading fails with something other than "no such file".
        let file = directory.appendingPathComponent(LioTripHomeStore.fileName)
        try FileManager.default.createDirectory(at: file, withIntermediateDirectories: false)
        let model = LioTripHomeModel(store: LioTripHomeStore(directory: directory, isCurrent: { true }))
        #expect(model.profile == nil)
        model.start(profile())
        model.setTick("payment", done: true)
        model.clear()
        #expect(model.saveFailed)
        #expect(model.profile == nil)
        var isFolder: ObjCBool = false
        #expect(FileManager.default.fileExists(atPath: file.path, isDirectory: &isFolder) && isFolder.boolValue)
        // Once the file reads again, writes go through.
        try FileManager.default.removeItem(at: file)
        try LioTripHomeStore(directory: directory, isCurrent: { true }).save(.init(profile: profile()))
        model.reload()
        #expect(model.profile == profile())
        #expect(!model.saveFailed)
        model.setTick("payment", done: true)
        #expect(!model.saveFailed)
        #expect(try LioTripHomeStore(directory: directory, isCurrent: { true }).load().ticks.isDone("payment"))
    }

    @Test func theTripFolderIsPrivateToTheApp() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let folder = LioTripHomeStore.storageDirectory(inMessageDirectory: directory)
        try LioTripHomeStore(directory: folder, isCurrent: { true }).save(.init(profile: profile()))
        let permissions = try FileManager.default.attributesOfItem(atPath: folder.path)[.posixPermissions] as? NSNumber
        #expect(permissions?.int16Value == 0o700)
    }
}
