import Foundation
import CryptoKit
import Darwin
import CJAPI
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

/// Immutable, exclusive encrypted records. Reopening grants query only; no resend/delete API.
@MainActor public final class MemoryPendingStore {
    private let root: URL
    private let directory: Int32
    private let maximumBytes: Int
    private let maximumRecords: Int
    private let namespace: MessageKeyNamespace
    private let keyID: UUID
    private let key: () throws -> SymmetricKey
    private var ad: Data { Data("CJMemoryPending|1|\(namespace.environment.uuidString)|\(namespace.account.uuidString)|\(namespace.purpose.rawValue)|\(keyID.uuidString)".utf8) }
    public convenience init(directory: URL, maximumBytes: Int, maximumRecords: Int, binding: MemoryBinding,
                            expectedKeyID: UUID, provider: any MessageEncryptionKeyProvider) throws {
        let namespace = MessageKeyNamespace(environment: binding.environment, account: binding.account, purpose: .localMemoryPendingV1)
        guard provider.namespace == namespace else { throw MemoryFailure.keyUnavailable }
        try self.init(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords, namespace: namespace, keyID: expectedKeyID) {
            guard provider.namespace == namespace else { throw MemoryFailure.keyUnavailable }
            let op = try provider.begin(.lookup)
            guard let key = try provider.existing(expectedID: expectedKeyID, for: op), provider.isCurrent(op),
                  key.namespace == namespace, key.id == expectedKeyID else { throw MemoryFailure.keyUnavailable }
            return key.withSymmetricKey { $0 }
        }
    }
    // Package-only test seam; no public raw key initializer and no platform key calls in tests.
    init(directory: URL, maximumBytes: Int, maximumRecords: Int, namespace: MessageKeyNamespace, keyID: UUID,
         key: @escaping () throws -> SymmetricKey) throws {
        guard maximumBytes > 0, maximumBytes <= Int.max - 28, maximumRecords > 0, directory.isFileURL,
              directory.standardizedFileURL.path == directory.resolvingSymlinksInPath().path else { throw MemoryFailure.storageUnavailable }
        let fd = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw MemoryFailure.storageUnavailable }
        var st = stat()
        guard fstat(fd, &st) == 0, st.st_uid == getuid(), st.st_mode & 0o077 == 0 else { close(fd); throw MemoryFailure.storageUnavailable }
        root = directory; self.directory = fd; self.maximumBytes = maximumBytes; self.maximumRecords = maximumRecords
        self.namespace = namespace; self.keyID = keyID; self.key = key
    }
    deinit { close(directory) }
    func validate(_ binding: MemoryBinding) throws {
        guard namespace.environment == binding.environment, namespace.account == binding.account,
              namespace.purpose == .localMemoryPendingV1 else { throw MemoryFailure.staleBinding }
    }
    private func name(_ id: String) throws -> String {
        guard memoryText(id) else { throw MemoryFailure.invalidInput }
        return digest(Data(id.utf8)) + ".memory"
    }
    func append(_ pending: MemoryPending, validateBinding: () throws -> Void = {}) throws {
        let existing = try self.pending()
        guard existing.count < maximumRecords, !existing.contains(where: { same($0.operationID, pending.operationID) }) else { throw MemoryFailure.storageUnavailable }
        try pending.validate()
        let plain = try JSONEncoder().encode(pending)
        guard plain.count <= maximumBytes else { throw MemoryFailure.invalidInput }
        let encrypted = try AES.GCM.seal(plain, using: key(), authenticating: ad)
        guard let bytes = encrypted.combined else { throw MemoryFailure.storageUnavailable }
        try validateDirectory()
        try validateBinding()
        try validateDirectory()
        let fd = openat(directory, try name(pending.operationID), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw MemoryFailure.storageUnavailable }
        defer { close(fd) }
        let count = bytes.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
        guard count == bytes.count, fsync(fd) == 0, fsync(directory) == 0 else { throw MemoryFailure.storageUnavailable }
        try validateDirectory()
    }
    func validateDirectory() throws {
        // Callback/await boundary checks, not a claim of protection against arbitrary same-UID races.
        var current = stat(); var original = stat()
        guard lstat(root.path, &current) == 0, fstat(directory, &original) == 0,
              current.st_ino == original.st_ino, current.st_dev == original.st_dev,
              current.st_mode & S_IFMT == S_IFDIR, current.st_uid == getuid(), current.st_mode & 0o077 == 0,
              root.path == root.resolvingSymlinksInPath().path else { throw MemoryFailure.storageUnavailable }
    }
    func requireOriginal(_ expected: MemoryPending) throws {
        guard let observed = try pending().first(where: { same($0.operationID, expected.operationID) }),
              observed.originalUTF8 == expected.originalUTF8, same(observed.expectedSHA256, expected.expectedSHA256) else { throw MemoryFailure.storageUnavailable }
        try validateDirectory()
    }
    public func pending() throws -> [MemoryPending] {
        try validateDirectory()
        let names = try FileManager.default.contentsOfDirectory(atPath: root.path)
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
            let pending = try JSONDecoder().decode(MemoryPending.self, from: plain)
            try pending.validate()
            let legacyName = UUID(uuidString: pending.operationID).map { $0.uuidString + ".memory" }
            guard try name(pending.operationID) == filename || legacyName == filename else { throw MemoryFailure.storageUnavailable }
            return pending
        }
        try validateDirectory()
        guard Set(result.map { Data($0.operationID.utf8) }).count == result.count else { throw MemoryFailure.storageUnavailable }
        return result
    }
}
