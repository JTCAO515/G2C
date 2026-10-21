import Foundation
import Security

public enum MessageKeyProtection: Sendable {
    case whenUnlockedThisDeviceOnly, afterFirstUnlockThisDeviceOnly
    var value: CFString {
        switch self {
        case .whenUnlockedThisDeviceOnly: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        case .afterFirstUnlockThisDeviceOnly: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        }
    }
}

@MainActor struct MessageKeychainOperations {
    var read: ([String: Any]) -> (OSStatus, [String: Any]?)
    var add: ([String: Any]) -> OSStatus
    var delete: ([String: Any]) -> OSStatus
    #if os(iOS)
    static var system: Self {
        Self(read: { query in
            var result: CFTypeRef?
            let status = SecItemCopyMatching(query as CFDictionary, &result)
            return (status, result as? [String: Any])
        }, add: { SecItemAdd($0 as CFDictionary, nil) }, delete: { SecItemDelete($0 as CFDictionary) })
    }
    #endif
}

@MainActor final class KeychainMessageKeys: MessageKeyPersistence {
    let namespace: MessageKeyNamespace
    let applicationIdentifier: String
    let protection: MessageKeyProtection
    let operations: MessageKeychainOperations
    private let prefix = Data("CJMKEY1".utf8)

    init(namespace: MessageKeyNamespace, applicationIdentifier: String,
         protection: MessageKeyProtection, operations: MessageKeychainOperations) throws {
        guard !applicationIdentifier.isEmpty, applicationIdentifier.contains("."),
              !applicationIdentifier.contains("*"), !applicationIdentifier.contains(where: \.isWhitespace) else {
            throw MessageKeyFailure.invalidConfiguration
        }
        self.namespace = namespace; self.applicationIdentifier = applicationIdentifier
        self.protection = protection; self.operations = operations
    }
    var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: namespace.service, kSecAttrAccount as String: namespace.slot,
         kSecAttrAccessGroup as String: applicationIdentifier, kSecAttrSynchronizable as String: false]
    }
    func read() throws -> MessageKeyRecord? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecReturnAttributes as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        let (status, result) = operations.read(request)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw MessageKeyFailure.keychain(status) }
        guard let data = result?[kSecValueData as String] as? Data,
              data.count == prefix.count + 36 + 32, data.starts(with: prefix),
              let idText = String(data: data.dropFirst(prefix.count).prefix(36), encoding: .utf8),
              let id = UUID(uuidString: idText),
              result?[kSecAttrGeneric as String] as? Data == Data(id.uuidString.utf8) else {
            throw MessageKeyFailure.malformedRecord
        }
        return MessageKeyRecord(id: id, bytes: Data(data.suffix(32)))
    }
    func add(_ record: MessageKeyRecord) throws {
        guard record.bytes.count == 32 else { throw MessageKeyFailure.malformedRecord }
        var request = query
        request[kSecAttrGeneric as String] = Data(record.id.uuidString.utf8)
        request[kSecAttrAccessible as String] = protection.value
        request[kSecValueData as String] = prefix + Data(record.id.uuidString.utf8) + record.bytes
        let status = operations.add(request)
        guard status == errSecSuccess else { throw MessageKeyFailure.keychain(status) }
    }
    func remove(expectedID: UUID) throws {
        var request = query
        // Exact version predicate: an old key ID cannot delete a replacement item.
        request[kSecAttrGeneric as String] = Data(expectedID.uuidString.utf8)
        let status = operations.delete(request)
        guard status == errSecSuccess else { throw MessageKeyFailure.keychain(status) }
    }
}

#if os(iOS)
extension ScopedMessageKeyProvider {
    public convenience init(namespace: MessageKeyNamespace, applicationIdentifier: String,
                            protection: MessageKeyProtection) throws {
        let store = try KeychainMessageKeys(namespace: namespace, applicationIdentifier: applicationIdentifier,
                                          protection: protection, operations: .system)
        self.init(namespace: namespace, persistence: store)
    }
}
#endif
