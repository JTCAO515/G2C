import Foundation
import Testing
@testable import CJLioUser

/// #1572 (JT, 2026-11-25): details the traveller typed are remembered on this device only, in the account's
/// folder, and can be cleared. Situational details (symptoms, amounts, places) are not kept.
@MainActor struct LioShowCardDetailsTests {
    private func folder() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("show-card-details-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    private func typed() -> LioShowCardInput {
        var input = LioShowCardInput(hotel: .init(nameZH: "北京饭店", addressZH: "长安街33号"), nights: 4, destinationZH: "机场")
        input.bookingName = "SMITH JOHN"
        input.roomNumber = "1208"
        input.medicineName = "Ibuprofen"
        input.drugAllergies = [.penicillin]
        input.foodAllergies = [.peanut, .sesame]
        input.spice = .mild
        input.conditions = [.pregnant]
        input.childAge = "6"
        input.currency = .eur
        input.symptoms = [.fever]
        input.symptomDays = .today
        input.amount = "500"
        input.placeZH = "天安门"
        input.atmLocation = "王府井"
        input.pickUpTime = "18:00"
        return input
    }

    @Test func rememberedDetailsComeBackButSituationalOnesDoNot() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioShowCardDetailsStore(directory: LioShowCardDetailsStore.storageDirectory(inMessageDirectory: directory),
                                            isCurrent: { true })
        #expect(try store.load() == LioShowCardDetails())
        try store.save(LioShowCardDetails(typed()))
        var restored = LioShowCardInput()
        try store.load().apply(to: &restored)
        #expect(restored.bookingName == "SMITH JOHN" && restored.medicineName == "Ibuprofen")
        #expect(restored.drugAllergies == [.penicillin] && restored.foodAllergies == [.peanut, .sesame])
        #expect(restored.spice == .mild && restored.conditions == [.pregnant] && restored.childAge == "6")
        #expect(restored.currency == .eur)
        #expect(restored.symptoms.isEmpty && restored.symptomDays == nil && restored.amount == nil)
        #expect(restored.placeZH == nil && restored.atmLocation == nil && restored.pickUpTime == nil)
        #expect(restored.destinationZH == nil && restored.nights == 1)
        #expect(restored.hotel == nil && restored.roomNumber == nil, "the hotel and room belong to Back to Hotel")
        let text = try String(contentsOf: directory.appendingPathComponent(LioShowCardDetailsStore.directoryName)
            .appendingPathComponent(LioShowCardDetailsStore.fileName), encoding: .utf8)
        for situational in ["fever", "500", "天安门", "王府井", "18:00", "机场", "北京饭店", "1208"] {
            #expect(!text.contains(situational), "\(situational) must not be written")
        }
    }

    @Test func clearingRemovesEverythingTyped() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioShowCardDetailsStore(directory: directory, isCurrent: { true })
        try store.save(LioShowCardDetails(typed()))
        try store.clear()
        #expect(try store.load() == LioShowCardDetails())
        #expect(!FileManager.default.fileExists(atPath: directory.appendingPathComponent(LioShowCardDetailsStore.fileName).path))
        try store.clear()
        var input = typed()
        LioShowCardDetails().apply(to: &input)
        #expect(input.bookingName == nil && input.drugAllergies.isEmpty && input.foodAllergies.isEmpty)
        #expect(input.medicineName == nil && input.conditions.isEmpty && input.childAge == nil && input.spice == .none)
    }

    @Test func anotherAccountCannotReadWriteOrClear() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        var current = true
        let store = LioShowCardDetailsStore(directory: directory, isCurrent: { current })
        try store.save(LioShowCardDetails(typed()))
        current = false
        #expect(throws: CancellationError.self) { try store.load() }
        #expect(throws: CancellationError.self) { try store.save(LioShowCardDetails()) }
        #expect(throws: CancellationError.self) { try store.clear() }
    }

    @Test func aFileWrittenBeforeTheWalletWasAddedStillReads() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioShowCardDetailsStore(directory: directory, isCurrent: { true })
        let older = #"{"version":1,"details":{"bookingName":"SMITH JOHN","drugAllergies":["penicillin"],"foodAllergies":[],"conditions":[],"spice":"none","currency":"usd"}}"#
        try Data(older.utf8).write(to: directory.appendingPathComponent(LioShowCardDetailsStore.fileName))
        let details = try store.load()
        #expect(details.bookingName == "SMITH JOHN" && details.drugAllergies == [.penicillin] && details.wallet == nil)
    }

    @Test func aDamagedOrNewerFileReadsAsNothingRemembered() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioShowCardDetailsStore(directory: directory, isCurrent: { true })
        try Data("{".utf8).write(to: directory.appendingPathComponent(LioShowCardDetailsStore.fileName))
        #expect(try store.load() == LioShowCardDetails())
        try Data(#"{"version":2}"#.utf8).write(to: directory.appendingPathComponent(LioShowCardDetailsStore.fileName))
        #expect(try store.load() == LioShowCardDetails())
    }

    @Test func folderIsListedWithTheAccountFolders() {
        #expect(LioAccountFolders.showCardDetailsDirectoryName == LioShowCardDetailsStore.directoryName)
        #expect(LioShowCardDetailsStore.directoryName != LioReturnHotelStore.directoryName)
    }
}
