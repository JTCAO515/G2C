import Foundation
import CryptoKit
import Darwin
import CJAPI
import enum CJMessageClient.LocalJournalFile
import CJMessageKeys

public enum MemoryFailure: Error, Equatable, Sendable {
    case unconfigured, staleBinding, invalidInput, invalidResponse, storageUnavailable
    case keyUnavailable, pendingRequiresQuery, liveWriteUnavailable, exchangeUnknown
    case rejected(Int, String)
}
public struct MemoryBinding: Hashable, Sendable {
    public let environment: UUID
    public let account: UUID
    public let generation: UUID
    public let selection: UUID
    public init(environment: UUID, account: UUID, generation: UUID, selection: UUID) {
        self.environment = environment; self.account = account; self.generation = generation; self.selection = selection
    }
}
public struct MemoryPending: Codable, Sendable {
    public let operationID: String
    public let itemID: String
    public let originalUTF8: Data
    public let expectedSHA256: String
    let inference: Bool
    init(_ command: Components.Schemas.MemoryManualSaveCommand) throws {
        try validateManual(command)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        originalUTF8 = try encoder.encode(command)
        operationID = command.operation_id; itemID = command.item_id
        expectedSHA256 = digest(originalUTF8); inference = command.kind == .inference
    }
    func validate() throws {
        let command = try JSONDecoder().decode(Components.Schemas.MemoryManualSaveCommand.self, from: originalUTF8)
        guard same(command.operation_id, operationID), same(command.item_id, itemID),
              memoryText(operationID), memoryText(itemID),
              digest(originalUTF8) == expectedSHA256, inference == (command.kind == .inference) else { throw MemoryFailure.invalidResponse }
    }
}
// Wire bounds are Unicode scalar counts, preserving the original UTF-8 representation.
func memoryText(_ value: String) -> Bool {
    (1...4096).contains(value.unicodeScalars.count) && !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
}
func validateManual(_ command: Components.Schemas.MemoryManualSaveCommand) throws {
    guard [command.operation_id, command.item_id, command.subject, command.slot, command.text, command.occurred_at].allSatisfy(memoryText) else { throw MemoryFailure.invalidInput }
    switch command.context_id {
    case .case1(let id): guard command.extent == .current, memoryText(id) else { throw MemoryFailure.invalidInput }
    case .case2(let null): guard command.extent == .long_term, null.value == nil else { throw MemoryFailure.invalidInput }
    }
}
func same(_ a: String, _ b: String) -> Bool { Data(a.utf8) == Data(b.utf8) }
func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }

protocol MemoryJournalRecord: Codable {
    var journalID: String { get }
    var originalUTF8: Data { get }
    var expectedSHA256: String { get }
    func validate() throws
}
extension MemoryPending: MemoryJournalRecord { var journalID: String { operationID } }

// A separate encrypted record preserves the immutable manual journal and old readers.
struct MemoryRejectedOperation<Original: MemoryJournalRecord>: MemoryJournalRecord {
    let original: Original
    let status: Int
    let code: String
    var journalID: String { original.journalID }
    var originalUTF8: Data { original.originalUTF8 }
    var expectedSHA256: String { original.expectedSHA256 }
    func validate() throws {
        try original.validate()
        guard (400...599).contains(status), memoryText(code) else { throw MemoryFailure.invalidResponse }
    }
}

/// Immutable, exclusive encrypted records. Reopening grants query only; no resend API. Explicit account cleanup is separate.
@MainActor final class MemoryEncryptedRecords<Record: MemoryJournalRecord> {
    private let cleanup: MemoryLocalJournalCleanup
    private let root: URL
    private let directory: Int32
    private let maximumBytes: Int
    private let maximumRecords: Int
    private let namespace: MessageKeyNamespace
    private let domain: String
    private let keyID: UUID
    private let key: () throws -> SymmetricKey
    private var ad: Data { Data("\(domain)|1|\(namespace.environment.uuidString)|\(namespace.account.uuidString)|\(namespace.purpose.rawValue)|\(keyID.uuidString)".utf8) }
    convenience init(directory: URL, maximumBytes: Int, maximumRecords: Int, binding: MemoryBinding,
                            expectedKeyID: UUID, provider: any MessageEncryptionKeyProvider, domain: String) throws {
        let namespace = MessageKeyNamespace(environment: binding.environment, account: binding.account, purpose: .localMemoryPendingV1)
        guard provider.namespace == namespace else { throw MemoryFailure.keyUnavailable }
        try self.init(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords, namespace: namespace, keyID: expectedKeyID, domain: domain) {
            guard provider.namespace == namespace else { throw MemoryFailure.keyUnavailable }
            let op = try provider.begin(.lookup)
            guard let key = try provider.existing(expectedID: expectedKeyID, for: op), provider.isCurrent(op),
                  key.namespace == namespace, key.id == expectedKeyID else { throw MemoryFailure.keyUnavailable }
            return key.withSymmetricKey { $0 }
        }
    }
    // Package-only test seam; no public raw key initializer and no platform key calls in tests.
    init(directory: URL, maximumBytes: Int, maximumRecords: Int, namespace: MessageKeyNamespace, keyID: UUID, domain: String,
         cleanup: MemoryLocalJournalCleanup? = nil, key: @escaping () throws -> SymmetricKey) throws {
        guard maximumBytes > 0, maximumBytes <= Int.max - 28, maximumRecords > 0, directory.isFileURL,
              directory.standardizedFileURL.path == directory.resolvingSymlinksInPath().path else { throw MemoryFailure.storageUnavailable }
        let fd = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw MemoryFailure.storageUnavailable }
        var st = stat()
        guard fstat(fd, &st) == 0, st.st_uid == getuid(), st.st_mode & 0o077 == 0 else { close(fd); throw MemoryFailure.storageUnavailable }
        do {
            let owner = try cleanup ?? MemoryLocalJournalCleanup(root: directory, suffixes: Self.cleanupSuffixes(domain))
            try owner.validateRegistered(directory)
            self.cleanup = owner
        } catch { close(fd); throw error }
        root = directory; self.directory = fd; self.maximumBytes = maximumBytes; self.maximumRecords = maximumRecords
        self.namespace = namespace; self.keyID = keyID; self.key = key; self.domain = domain
    }
    deinit { close(directory) }
    func adjacentRecords<Other: MemoryJournalRecord>(domain: String, create: Bool) throws -> MemoryEncryptedRecords<Other>? {
        try validateDirectory()
        let target = root.appendingPathExtension(domain)
        guard try cleanup.openAdjacent(target, create: create) else { return nil }
        return try MemoryEncryptedRecords<Other>(directory: target, maximumBytes: maximumBytes,
            maximumRecords: maximumRecords, namespace: namespace, keyID: keyID, domain: domain, cleanup: cleanup, key: key)
    }
    private static func cleanupSuffixes(_ domain: String) -> [String] {
        switch domain {
        case "CJMemoryPending": ["CJMemoryRejections"]
        case "CJMemoryManagementPending": ["CJMemoryManagementRejections"]
        case "CJMemoryTypedPendingV2": ["CJMemoryTypedRejectionsV2", "CJMemoryTypedManagementV2",
            "CJMemoryTypedManagementV2.CJMemoryTypedManagementRejectionsV2"]
        case "CJMemoryHistoryPendingV1": ["CJMemoryHistoryRejectionsV1"]
        case "CJMemoryCandidatePendingV1": ["CJMemoryCandidateRejectionsV1"]
        case "CJMemoryErasurePendingV1": ["CJMemoryErasureObservationsV1"]
        default: []
        }
    }
    func clearLocalFiles() throws { try cleanup.clear() }

    func rejection(for original: Record, domain: String) throws -> MemoryRejectedOperation<Record>? {
        let records: MemoryEncryptedRecords<MemoryRejectedOperation<Record>>? = try adjacentRecords(domain: domain, create: false)
        guard let record = try records?.pending().first(where: { same($0.journalID, original.journalID) }) else { return nil }
        guard record.originalUTF8 == original.originalUTF8, record.expectedSHA256 == original.expectedSHA256 else {
            throw MemoryFailure.storageUnavailable
        }
        return record
    }
    func recordRejection(_ original: Record, status: Int, code: String, domain: String, validateBinding: () throws -> Void) throws {
        try requireOriginal(original)
        guard let records: MemoryEncryptedRecords<MemoryRejectedOperation<Record>> = try adjacentRecords(domain: domain, create: true) else {
            throw MemoryFailure.storageUnavailable
        }
        try records.append(MemoryRejectedOperation(original: original, status: status, code: code), validateBinding: validateBinding)
    }
    func validate(_ binding: MemoryBinding) throws {
        guard namespace.environment == binding.environment, namespace.account == binding.account,
              namespace.purpose == .localMemoryPendingV1 else { throw MemoryFailure.staleBinding }
    }
    private func name(_ id: String) throws -> String {
        guard memoryText(id) else { throw MemoryFailure.invalidInput }
        return digest(Data(id.utf8)) + ".memory"
    }
    func append(_ pending: Record, validateBinding: () throws -> Void = {}) throws {
        let existing = try self.pending()
        guard existing.count < maximumRecords, !existing.contains(where: { same($0.journalID, pending.journalID) }) else { throw MemoryFailure.storageUnavailable }
        try pending.validate()
        let plain = try JSONEncoder().encode(pending)
        guard plain.count <= maximumBytes else { throw MemoryFailure.invalidInput }
        let encrypted = try AES.GCM.seal(plain, using: key(), authenticating: ad)
        guard let bytes = encrypted.combined else { throw MemoryFailure.storageUnavailable }
        try validateDirectory()
        try validateBinding()
        try validateDirectory()
        guard LocalJournalFile.createExclusive(try name(pending.journalID), in: directory, bytes: bytes) else { throw MemoryFailure.storageUnavailable }
        try validateDirectory()
    }
    func validateDirectory() throws {
        try cleanup.checkReadable()
        // Callback/await boundary checks, not a claim of protection against arbitrary same-UID races.
        var current = stat(); var original = stat()
        guard lstat(root.path, &current) == 0, fstat(directory, &original) == 0,
              current.st_ino == original.st_ino, current.st_dev == original.st_dev,
              current.st_mode & S_IFMT == S_IFDIR, current.st_uid == getuid(), current.st_mode & 0o077 == 0,
              root.path == root.resolvingSymlinksInPath().path else { throw MemoryFailure.storageUnavailable }
    }
    func requireOriginal(_ expected: Record) throws {
        guard let observed = try pending().first(where: { same($0.journalID, expected.journalID) }),
              observed.originalUTF8 == expected.originalUTF8, same(observed.expectedSHA256, expected.expectedSHA256) else { throw MemoryFailure.storageUnavailable }
        try validateDirectory()
    }
    /// Additive proof for the history consumer's final callback-free outflow fence.
    /// Existing journal formats and pending()/rejection behavior stay unchanged.
    struct Durability: Sendable {
        fileprivate let filename: String
        fileprivate let ciphertext: Data
    }
    private func readProofCiphertext(_ filename: String) throws -> Data {
        let fd = openat(directory, filename, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw MemoryFailure.storageUnavailable }
        defer { close(fd) }
        var st = stat()
        guard fstat(fd, &st) == 0, st.st_mode & S_IFMT == S_IFREG, st.st_nlink == 1,
              st.st_uid == getuid(), st.st_mode & 0o077 == 0, st.st_size > 28,
              st.st_size <= maximumBytes + 28 else { throw MemoryFailure.storageUnavailable }
        var bytes = Data(count: Int(st.st_size))
        let count = bytes.withUnsafeMutableBytes { read(fd, $0.baseAddress, $0.count) }
        guard count == bytes.count else { throw MemoryFailure.storageUnavailable }
        return bytes
    }
    func proveOriginal(_ expected: Record) throws -> Durability {
        try validateDirectory()
        let filename = try name(expected.journalID)
        let bytes = try readProofCiphertext(filename)
        let material = try key()
        try validateDirectory()
        let plain = try AES.GCM.open(AES.GCM.SealedBox(combined: bytes), using: material, authenticating: ad)
        let observed = try JSONDecoder().decode(Record.self, from: plain)
        try observed.validate()
        guard same(observed.journalID, expected.journalID), observed.originalUTF8 == expected.originalUTF8,
              same(observed.expectedSHA256, expected.expectedSHA256) else { throw MemoryFailure.storageUnavailable }
        return Durability(filename: filename, ciphertext: bytes)
    }
    func validateDurability(_ proof: Durability) throws {
        try validateDirectory()
        guard try readProofCiphertext(proof.filename) == proof.ciphertext else { throw MemoryFailure.storageUnavailable }
    }
    func validateInventory(_ records: [Record]) throws {
        try validateDirectory()
        let expected = try Set(records.map { try name($0.journalID) })
        let actual = try Set(LocalJournalFile.recordNames(atPath: root.path))
        guard expected == actual else { throw MemoryFailure.storageUnavailable }
    }
    /// Exact per-record plan for item erasure. Building it decrypts/validates the
    /// whole bounded journal before any deletion; execution invokes no key or
    /// caller callback and never follows a supplied path or a replaced file.
    /// It also erases every writer temporary entry: one left by a crash before its
    /// rename may hold this item's complete or truncated ciphertext, and an
    /// uncommitted entry cannot be attributed to an item without the key.
    struct Removal {
        fileprivate let owner: MemoryEncryptedRecords<Record>
        fileprivate let inventory: [Durability]
        fileprivate let selected: Set<String>
        fileprivate let identities: [String: (dev_t, ino_t)]
        fileprivate let temporaries: [String: (dev_t, ino_t)]
    }
    /// Same preflight as LocalJournalCleanup.clear: no symlink follow, a regular
    /// file with a single link, owned by this UID.
    private func temporaryIdentity(_ name: String) throws -> (dev_t, ino_t) {
        var entry = stat()
        guard LocalJournalFile.isTemporary(name), fstatat(directory, name, &entry, AT_SYMLINK_NOFOLLOW) == 0,
              entry.st_mode & S_IFMT == S_IFREG, entry.st_nlink == 1, entry.st_uid == getuid() else { throw MemoryFailure.storageUnavailable }
        return (entry.st_dev, entry.st_ino)
    }
    private func temporaryNames() throws -> Set<String> {
        Set(try FileManager.default.contentsOfDirectory(atPath: root.path).filter(LocalJournalFile.isTemporary))
    }
    func prepareRemoval(where matches: (Record) throws -> Bool) throws -> Removal {
        let records = try pending()
        let names = try LocalJournalFile.recordNames(atPath: root.path)
        var inventory: [Durability] = [], selected = Set<String>()
        var identities: [String: (dev_t, ino_t)] = [:]
        for record in records {
            let canonical = try name(record.journalID)
            let legacy = UUID(uuidString: record.journalID).map { $0.uuidString + ".memory" }
            let candidates = names.filter { $0 == canonical || $0 == legacy }
            guard candidates.count == 1, let filename = candidates.first else { throw MemoryFailure.storageUnavailable }
            var entry = stat()
            guard fstatat(directory, filename, &entry, AT_SYMLINK_NOFOLLOW) == 0 else { throw MemoryFailure.storageUnavailable }
            identities[filename] = (entry.st_dev, entry.st_ino)
            let proof = Durability(filename: filename, ciphertext: try readProofCiphertext(filename))
            let material = try key()
            try validateDirectory()
            let plain = try AES.GCM.open(AES.GCM.SealedBox(combined: proof.ciphertext), using: material, authenticating: ad)
            let observed = try JSONDecoder().decode(Record.self, from: plain)
            try observed.validate()
            guard same(observed.journalID, record.journalID), observed.originalUTF8 == record.originalUTF8,
                  same(observed.expectedSHA256, record.expectedSHA256) else { throw MemoryFailure.storageUnavailable }
            inventory.append(proof)
            if try matches(record) { selected.insert(filename) }
        }
        var temporaries: [String: (dev_t, ino_t)] = [:]
        for name in try temporaryNames() { temporaries[name] = try temporaryIdentity(name) }
        let plan = Removal(owner: self, inventory: inventory, selected: selected, identities: identities, temporaries: temporaries)
        try validateRemoval(plan)
        return plan
    }
    func validateRemoval(_ plan: Removal) throws {
        guard plan.owner === self else { throw MemoryFailure.storageUnavailable }
        try validateDirectory()
        guard try Set(LocalJournalFile.recordNames(atPath: root.path)) == Set(plan.inventory.map(\.filename)) else {
            throw MemoryFailure.storageUnavailable
        }
        for proof in plan.inventory { try validateRemovalEntry(proof, plan: plan) }
        guard try temporaryNames() == Set(plan.temporaries.keys) else { throw MemoryFailure.storageUnavailable }
        for (name, identity) in plan.temporaries {
            guard try temporaryIdentity(name) == identity else { throw MemoryFailure.storageUnavailable }
        }
    }
    private func validateRemovalEntry(_ proof: Durability, plan: Removal) throws {
        var entry = stat()
        guard let identity = plan.identities[proof.filename],
              fstatat(directory, proof.filename, &entry, AT_SYMLINK_NOFOLLOW) == 0,
              entry.st_dev == identity.0, entry.st_ino == identity.1 else { throw MemoryFailure.storageUnavailable }
        try validateDurability(proof)
    }
    func performRemoval(_ plan: Removal) throws {
        try validateRemoval(plan)
        for proof in plan.inventory where plan.selected.contains(proof.filename) {
            // Final callback-free byte/metadata comparison immediately before unlink.
            try validateRemovalEntry(proof, plan: plan)
            guard unlinkat(directory, proof.filename, 0) == 0 else { throw MemoryFailure.exchangeUnknown }
        }
        for (name, identity) in plan.temporaries {
            // Same name, inode and file checks immediately before unlink; earlier unlinks may have happened.
            guard (try? temporaryIdentity(name)).map({ $0 == identity }) == true,
                  unlinkat(directory, name, 0) == 0 else { throw MemoryFailure.exchangeUnknown }
        }
        guard fsync(directory) == 0 else { throw MemoryFailure.exchangeUnknown }
        try validateDirectory()
        guard try Set(LocalJournalFile.recordNames(atPath: root.path)) == Set(plan.inventory.map(\.filename)).subtracting(plan.selected),
              try temporaryNames().isEmpty else {
            throw MemoryFailure.exchangeUnknown
        }
        for proof in plan.inventory where !plan.selected.contains(proof.filename) { try validateDurability(proof) }
    }
    func pending() throws -> [Record] {
        try validateDirectory()
        let names = try LocalJournalFile.recordNames(atPath: root.path)
        guard names.count <= maximumRecords else { throw MemoryFailure.storageUnavailable }
        let result = try names.sorted().map { filename in
            let stem = String(filename.dropLast(7))
            guard filename.hasSuffix(".memory"), UUID(uuidString: stem) != nil || (stem.count == 64 && stem.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) })) else { throw MemoryFailure.storageUnavailable }
            let fd = openat(directory, filename, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
            guard fd >= 0 else { throw MemoryFailure.storageUnavailable }
            defer { close(fd) }
            var st = stat()
            guard fstat(fd, &st) == 0, st.st_mode & S_IFMT == S_IFREG, st.st_nlink == 1,
                  st.st_uid == getuid(), st.st_mode & 0o077 == 0, st.st_size > 28,
                  st.st_size <= maximumBytes + 28 else { throw MemoryFailure.storageUnavailable }
            var bytes = Data(count: Int(st.st_size))
            let count = bytes.withUnsafeMutableBytes { read(fd, $0.baseAddress, $0.count) }
            guard count == bytes.count else { throw MemoryFailure.storageUnavailable }
            let material = try key()
            try validateDirectory()
            let plain = try AES.GCM.open(AES.GCM.SealedBox(combined: bytes), using: material, authenticating: ad)
            let pending = try JSONDecoder().decode(Record.self, from: plain)
            try pending.validate()
            let legacyName = UUID(uuidString: pending.journalID).map { $0.uuidString + ".memory" }
            guard try name(pending.journalID) == filename || legacyName == filename else { throw MemoryFailure.storageUnavailable }
            return pending
        }
        try validateDirectory()
        guard Set(result.map { Data($0.journalID.utf8) }).count == result.count else { throw MemoryFailure.storageUnavailable }
        return result
    }
}

/// Manual-save journal. Its existing ciphertext format and public API remain unchanged.
@MainActor public final class MemoryPendingStore {
    let storage: MemoryEncryptedRecords<MemoryPending>
    public init(directory: URL, maximumBytes: Int, maximumRecords: Int, binding: MemoryBinding,
                expectedKeyID: UUID, provider: any MessageEncryptionKeyProvider) throws {
        storage = try MemoryEncryptedRecords(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords,
            binding: binding, expectedKeyID: expectedKeyID, provider: provider, domain: "CJMemoryPending")
    }
    init(directory: URL, maximumBytes: Int, maximumRecords: Int, namespace: MessageKeyNamespace, keyID: UUID,
         key: @escaping () throws -> SymmetricKey) throws {
        storage = try MemoryEncryptedRecords(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords,
            namespace: namespace, keyID: keyID, domain: "CJMemoryPending", key: key)
    }
    func validate(_ binding: MemoryBinding) throws { try storage.validate(binding) }
    func validateDirectory() throws { try storage.validateDirectory() }
    func append(_ pending: MemoryPending, validateBinding: () throws -> Void = {}) throws { try storage.append(pending, validateBinding: validateBinding) }
    func requireOriginal(_ expected: MemoryPending) throws { try storage.requireOriginal(expected) }
    func rejection(for original: MemoryPending) throws -> MemoryRejectedOperation<MemoryPending>? {
        try storage.rejection(for: original, domain: "CJMemoryRejections")
    }
    func recordRejection(_ original: MemoryPending, status: Int, code: String, validateBinding: () throws -> Void) throws {
        try storage.recordRejection(original, status: status, code: code, domain: "CJMemoryRejections", validateBinding: validateBinding)
    }
    /// Exact manual journal and its known rejection sidecar; no key access.
    public func clearLocalFiles() throws { try storage.clearLocalFiles() }
    public func pending() throws -> [MemoryPending] { try storage.pending() }
}
