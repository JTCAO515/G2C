import CryptoKit
import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LocalMedicalCardTests {
    @Test func consentAndOptionalFieldsRoundTripWithoutPlaintextAndClearTogether() throws {
        let fixture = Fixture()
        defer { fixture.removeDirectory() }
        let store = fixture.store()

        #expect(try store.load() == nil)
        try store.save(LocalMedicalCard())
        #expect(try store.load()?.isEmpty == true)

        var card = LocalMedicalCard()
        card[.contactName] = "Synthetic Name"
        card[.foodAllergies] = "Example only"
        try store.save(card)
        #expect(try store.load() == card)
        let savedBytes = try Data(contentsOf: fixture.file)
        #expect(savedBytes.range(of: Data("Synthetic Name".utf8)) == nil)
        #expect(fixture.created == 1)
        try store.clear()
        try store.requireAbsent()
        #expect(try store.load() == nil)
        #expect(fixture.key == nil)
    }

    @Test func aNewInstallationWithoutTheFileNeverReusesAnExistingKey() throws {
        let fixture = Fixture()
        defer { fixture.removeDirectory() }
        let store = fixture.store()
        try store.save(LocalMedicalCard())
        let oldBytes = try Data(contentsOf: fixture.file)
        fixture.removeDirectory()
        #expect(fixture.key != nil)
        #expect(try store.load() == nil)

        try store.save(LocalMedicalCard())
        #expect(fixture.created == 2)
        try oldBytes.write(to: fixture.file)
        #expect(throws: (any Error).self) { try store.load() }
    }

    @Test func keychainFailureDoesNotLeaveTheEncryptedCardBehind() throws {
        let fixture = Fixture()
        defer { fixture.removeDirectory() }
        let store = fixture.store()
        try store.save(LocalMedicalCard())
        fixture.failsKeyRemoval = true
        #expect(throws: LocalMedicalCardFailure.unavailable) { try store.clear() }
        #expect(try store.load() == nil)
        #expect(fixture.key != nil)

        fixture.failsKeyRemoval = false
        try store.clear()
        try store.requireAbsent()
    }

    @Test func theEncryptedCardCannotBeOpenedUnderAnotherAccount() throws {
        let fixture = Fixture()
        defer { fixture.removeDirectory() }
        try fixture.store().save(LocalMedicalCard())
        #expect(throws: (any Error).self) { try fixture.store(scope: "other owner").load() }
    }

    @Test func inactiveHandlesCannotSeeOrChangeTheCard() throws {
        let fixture = Fixture()
        defer { fixture.removeDirectory() }
        let store = fixture.store()
        try store.save(LocalMedicalCard())
        let retired = store.storage(isCurrent: { false })
        #expect(throws: LocalMedicalCardFailure.inactive) { try retired.load() }
        #expect(throws: LocalMedicalCardFailure.inactive) { try retired.save(LocalMedicalCard()) }
        #expect(throws: LocalMedicalCardFailure.inactive) { try retired.clear() }
        #expect(try store.load()?.isEmpty == true)
    }

    @Test func validatesInputBeforeCreatingAKeyOrFile() throws {
        let fixture = Fixture()
        defer { fixture.removeDirectory() }
        var card = LocalMedicalCard()
        card[.bloodType] = String(repeating: "x", count: LocalMedicalCard.Field.bloodType.limit + 1)
        #expect(throws: LocalMedicalCardFailure.invalidCard) { try fixture.store().save(card) }
        #expect(fixture.key == nil)
        #expect(!FileManager.default.fileExists(atPath: fixture.file.path))
    }

    @MainActor private final class Fixture {
        let directory = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString, directoryHint: .isDirectory)
        var key: SymmetricKey?
        var created = 0
        var failsKeyRemoval = false
        var file: URL { directory.appending(path: "card.aesgcm") }

        func store(scope: String = "selected owner") -> LocalMedicalCardFileStore {
            LocalMedicalCardFileStore(directory: directory, scope: Data(scope.utf8), keys: .init(
                read: { self.key },
                create: {
                    let value = SymmetricKey(size: .bits256)
                    self.key = value
                    self.created += 1
                    return value
                },
                remove: {
                    guard !self.failsKeyRemoval else { throw LocalMedicalCardFailure.unavailable }
                    self.key = nil
                }
            ))
        }

        func removeDirectory() {
            if FileManager.default.fileExists(atPath: directory.path) {
                do { try FileManager.default.removeItem(at: directory) }
                catch { Issue.record("Could not remove the test directory.") }
            }
        }
    }
}
