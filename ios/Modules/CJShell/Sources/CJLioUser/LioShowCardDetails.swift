import Foundation

/// Details the traveller typed once and needs again (JT, 2026-11-25): the booking name, allergies, the usual
/// medicine, pharmacy conditions, spice and the usual currency. Kept on this device in the account's folder only,
/// never uploaded or logged, cleared from the cards page or when the account is removed.
/// Situational details (symptoms, amounts, places, times) and the hotel (Back to Hotel keeps it) are not kept.
struct LioShowCardDetails: Codable, Equatable, Sendable {
    var bookingName: String?
    var medicineName: String?
    var drugAllergies: [LioDrugAllergen] = []
    var foodAllergies: [LioFoodAllergen] = []
    var conditions: [LioPharmacyCondition] = []
    var childAge: String?
    var spice = LioSpiceLevel.none
    var currency = LioExchangeCurrency.usd

    init() {}

    init(_ input: LioShowCardInput) {
        bookingName = input.cleanBookingName
        medicineName = input.cleanMedicineName
        drugAllergies = LioDrugAllergen.allCases.filter(input.drugAllergies.contains)
        foodAllergies = LioFoodAllergen.allCases.filter(input.foodAllergies.contains)
        conditions = LioPharmacyCondition.allCases.filter(input.conditions.contains)
        childAge = input.cleanChildAge
        spice = input.spice
        currency = input.currency
    }

    /// Replaces the remembered fields; everything else on the input stays as it is.
    func apply(to input: inout LioShowCardInput) {
        input.bookingName = LioShowCardInput.clean(bookingName)
        input.medicineName = LioShowCardInput.clean(medicineName)
        input.drugAllergies = Set(drugAllergies)
        input.foodAllergies = Set(foodAllergies)
        input.conditions = Set(conditions)
        input.childAge = LioShowCardInput.clean(childAge)
        input.spice = spice
        input.currency = currency
    }
}

@MainActor public struct LioShowCardDetailsStore {
    nonisolated public static let directoryName = "show-card-details"
    nonisolated public static let fileName = "show-card-details.json"

    nonisolated public static func storageDirectory(inMessageDirectory directory: URL) -> URL {
        directory.appendingPathComponent(directoryName, isDirectory: true)
    }

    let directory: URL
    private let isCurrent: @MainActor () -> Bool
    private var file: URL { directory.appendingPathComponent(Self.fileName) }

    init(directory: URL, isCurrent: @escaping @MainActor () -> Bool) {
        self.directory = directory
        self.isCurrent = isCurrent
    }

    private struct Archive: Codable {
        let version: Int
        let details: LioShowCardDetails?
    }

    /// Nothing saved, a damaged file or a newer file all read as nothing remembered.
    func load() throws -> LioShowCardDetails {
        guard isCurrent() else { throw CancellationError() }
        let data: Data
        do {
            data = try Data(contentsOf: file)
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return LioShowCardDetails()
        }
        guard let archive = try? JSONDecoder().decode(Archive.self, from: data), archive.version == 1,
              let details = archive.details else { return LioShowCardDetails() }
        return details
    }

    func save(_ details: LioShowCardDetails) throws {
        guard isCurrent() else { throw CancellationError() }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var storedDirectory = directory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try storedDirectory.setResourceValues(attributes)
        let data = try JSONEncoder().encode(Archive(version: 1, details: details))
        #if os(iOS)
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file, options: .atomic)
        #endif
    }

    func clear() throws {
        guard isCurrent() else { throw CancellationError() }
        do {
            try FileManager.default.removeItem(at: file)
        } catch let error as CocoaError where error.code == .fileNoSuchFile {
            return
        }
    }
}
