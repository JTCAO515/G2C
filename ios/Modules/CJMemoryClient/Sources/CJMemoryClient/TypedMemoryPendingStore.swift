import Foundation
import CryptoKit
import CJMessageKeys

/// Separate V2 domain/directory; never reinterpret or overwrite an existing V1
/// manual/lifecycle journal. Reopen permits only original receipt queries.
@MainActor public final class TypedMemoryPendingStore {
    private let storage: MemoryEncryptedRecords<TypedMemoryPending>
    public init(directory: URL,maximumBytes: Int,maximumRecords: Int,binding: MemoryBinding,
                expectedKeyID: UUID,provider: any MessageEncryptionKeyProvider) throws {
        storage = try MemoryEncryptedRecords(directory:directory,maximumBytes:maximumBytes,maximumRecords:maximumRecords,
            binding:binding,expectedKeyID:expectedKeyID,provider:provider,domain:"CJMemoryTypedPendingV2")
    }
    init(directory: URL,maximumBytes: Int,maximumRecords: Int,namespace: MessageKeyNamespace,keyID: UUID,
         key: @escaping () throws -> SymmetricKey) throws {
        storage = try MemoryEncryptedRecords(directory:directory,maximumBytes:maximumBytes,maximumRecords:maximumRecords,
            namespace:namespace,keyID:keyID,domain:"CJMemoryTypedPendingV2",key:key)
    }
    func validate(_ binding: MemoryBinding) throws { try storage.validate(binding) }
    func validateDirectory() throws { try storage.validateDirectory() }
    func append(_ record: TypedMemoryPending,validateBinding: () throws -> Void) throws { try storage.append(record,validateBinding:validateBinding) }
    func requireOriginal(_ record: TypedMemoryPending) throws { try storage.requireOriginal(record) }
    func records() throws -> [TypedMemoryPending] { try storage.pending() }
    func rejection(for original: TypedMemoryPending) throws -> MemoryRejectedOperation<TypedMemoryPending>? {
        try storage.rejection(for:original,domain:"CJMemoryTypedRejectionsV2")
    }
    func recordRejection(_ original: TypedMemoryPending,status: Int,code: String,validateBinding: () throws -> Void) throws {
        try storage.recordRejection(original,status:status,code:code,domain:"CJMemoryTypedRejectionsV2",validateBinding:validateBinding)
    }
    func managementRecords(create: Bool) throws -> MemoryEncryptedRecords<TypedMemoryManagementPending>? {
        try storage.adjacentRecords(domain:"CJMemoryTypedManagementV2",create:create)
    }
    public func pending() throws -> [TypedMemoryCommand] {
        try storage.pending().map { try TypedMemoryCommand(originalUTF8:$0.originalUTF8) }
    }
}
