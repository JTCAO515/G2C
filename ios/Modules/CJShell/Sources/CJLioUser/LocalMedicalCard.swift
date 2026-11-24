import CryptoKit
import Foundation

struct LocalMedicalCard: Codable, Equatable {
    enum Field: String, CaseIterable, Identifiable {
        case bloodType, drugAllergies, foodAllergies, otherAllergies, medications, medicalHistory
        case contactName, contactRelationship, contactPhone, insurer, policyNumber

        var id: Self { self }

        var limit: Int {
            switch self {
            case .bloodType, .contactPhone: 40
            case .contactName, .contactRelationship, .insurer, .policyNumber: 100
            case .drugAllergies, .foodAllergies, .otherAllergies: 160
            case .medications, .medicalHistory: 280
            }
        }
    }

    private var fields: [String: String] = [:]
    var isEmpty: Bool { fields.isEmpty }

    subscript(field: Field) -> String {
        get { fields[field.rawValue] ?? "" }
        set {
            if newValue.isEmpty { fields.removeValue(forKey: field.rawValue) }
            else { fields[field.rawValue] = newValue }
        }
    }

    func validate() throws {
        guard fields.allSatisfy({ name, value in
            guard let field = Field(rawValue: name) else { return false }
            return !value.isEmpty && value.count <= field.limit && value.utf8.count <= field.limit * 4
        }) else { throw LocalMedicalCardFailure.invalidCard }
    }
}

enum LocalMedicalCardFailure: Error, Equatable {
    case inactive, invalidCard, unavailable
}

@MainActor public final class LocalMedicalCardStorage {
    let isCurrent: @MainActor () -> Bool
    let load: @MainActor () throws -> LocalMedicalCard?
    let save: @MainActor (LocalMedicalCard) throws -> Void
    let clear: @MainActor () throws -> Void

    init(isCurrent: @escaping @MainActor () -> Bool, load: @escaping @MainActor () throws -> LocalMedicalCard?,
         save: @escaping @MainActor (LocalMedicalCard) throws -> Void, clear: @escaping @MainActor () throws -> Void) {
        self.isCurrent = isCurrent
        self.load = load
        self.save = save
        self.clear = clear
    }
}

/// The encrypted card stays in the App's excluded-from-backup container. Its
/// device-bound Keychain key alone cannot reveal a card after App removal.
@MainActor struct LocalMedicalCardFileStore {
    struct Keys {
        let read: @MainActor () throws -> SymmetricKey?
        let create: @MainActor () throws -> SymmetricKey
        let remove: @MainActor () throws -> Void
    }

    private struct Record: Codable {
        let version: Int
        let card: LocalMedicalCard
    }

    let directory: URL
    let scope: Data
    let keys: Keys
    private var file: URL { directory.appending(path: "card.aesgcm") }

    func storage(isCurrent: @escaping @MainActor () -> Bool) -> LocalMedicalCardStorage {
        LocalMedicalCardStorage(isCurrent: isCurrent, load: {
            guard isCurrent() else { throw LocalMedicalCardFailure.inactive }
            return try load()
        }, save: { value in
            guard isCurrent() else { throw LocalMedicalCardFailure.inactive }
            try save(value)
        }, clear: {
            guard isCurrent() else { throw LocalMedicalCardFailure.inactive }
            try clear()
        })
    }

    func load() throws -> LocalMedicalCard? {
        guard let size = try existingFileSize() else { return nil }
        guard size <= 32_768, let key = try keys.read() else { throw LocalMedicalCardFailure.unavailable }
        let bytes = try Data(contentsOf: file)
        let plaintext = try AES.GCM.open(AES.GCM.SealedBox(combined: bytes), using: key, authenticating: scope)
        let record = try JSONDecoder().decode(Record.self, from: plaintext)
        guard record.version == 1 else { throw LocalMedicalCardFailure.invalidCard }
        try record.card.validate()
        return record.card
    }

    func save(_ card: LocalMedicalCard) throws {
        try card.validate()
        let existing = try existingFileSize()
        let key: SymmetricKey
        if existing != nil {
            guard let stored = try keys.read() else { throw LocalMedicalCardFailure.unavailable }
            key = stored
        } else {
            // An old Keychain item may outlive App removal. Never reuse it
            // when there is no encrypted card in this installation.
            try keys.remove()
            key = try keys.create()
        }
        let data = try JSONEncoder().encode(Record(version: 1, card: card))
        let box = try AES.GCM.seal(data, using: key, authenticating: scope)
        guard let bytes = box.combined else { throw LocalMedicalCardFailure.unavailable }

        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        try excludeFromBackup(directory)
        #if os(iOS)
        try bytes.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try bytes.write(to: file, options: .atomic)
        #endif
        try excludeFromBackup(file)
    }

    func clear() throws {
        try keys.remove()
        if try existingFileSize() != nil {
            try FileManager.default.removeItem(at: file)
        }
        try requireAbsent()
    }

    func requireAbsent() throws {
        guard try existingFileSize() == nil, try keys.read() == nil else {
            throw LocalMedicalCardFailure.unavailable
        }
    }

    private func existingFileSize() throws -> Int? {
        do {
            let metadata = try file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard metadata.isRegularFile == true, metadata.isSymbolicLink == false, let size = metadata.fileSize else {
                throw LocalMedicalCardFailure.unavailable
            }
            return size
        } catch let error as CocoaError where Self.isMissing(error) {
            return nil
        }
    }

    private func excludeFromBackup(_ url: URL) throws {
        var stored = url
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try stored.setResourceValues(values)
    }

    private static func isMissing(_ error: CocoaError) -> Bool {
        error.code == .fileNoSuchFile || error.code == .fileReadNoSuchFile
    }
}
