import Foundation
import Security

public enum SessionProtection: Sendable {
    case whenUnlockedThisDeviceOnly, afterFirstUnlockThisDeviceOnly
    var value: CFString {
        switch self {
        case .whenUnlockedThisDeviceOnly: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        case .afterFirstUnlockThisDeviceOnly: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        }
    }
}

public struct KeychainSessionScope: Sendable {
    public let namespace: SessionNamespace
    public let applicationIdentifier: String
    /// Trusted host supplies its own application-identifier, never a shared access group.
    /// No default access-group query is allowed. Host entitlement validation remains required.
    public init(namespace: SessionNamespace, applicationIdentifier: String) throws {
        guard !applicationIdentifier.isEmpty, applicationIdentifier.contains("."),
              !applicationIdentifier.contains("*"), !applicationIdentifier.contains(where: \.isWhitespace) else {
            throw SessionFailure.invalidConfiguration
        }
        self.namespace = namespace; self.applicationIdentifier = applicationIdentifier
    }
}

/// Internal test injection. No macOS live implementation is exposed.
@MainActor struct KeychainOperations {
    var copy: ([String: Any]) -> (OSStatus, Data?)
    var add: ([String: Any]) -> OSStatus
    var update: ([String: Any], [String: Any]) -> OSStatus
    #if os(iOS)
    static var system: Self {
        Self(copy: { query in
            var result: CFTypeRef?
            let status = SecItemCopyMatching(query as CFDictionary, &result)
            return (status, result as? Data)
        }, add: { SecItemAdd($0 as CFDictionary, nil) },
             update: { SecItemUpdate($0 as CFDictionary, $1 as CFDictionary) })
    }
    #endif
}

@MainActor public final class KeychainSessionStore: SessionPersistence {
    private let scope: KeychainSessionScope
    private let protection: SessionProtection
    private let operations: KeychainOperations
    private let prefix = Data([0x43, 0x4a, 0x53, 0x01]) // local envelope version, not provider format

    #if os(iOS)
    public convenience init(scope: KeychainSessionScope, protection: SessionProtection) {
        self.init(scope: scope, protection: protection, operations: .system)
    }
    #endif
    init(scope: KeychainSessionScope, protection: SessionProtection, operations: KeychainOperations) {
        self.scope = scope; self.protection = protection; self.operations = operations
    }
    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: scope.namespace.service,
         kSecAttrAccount as String: scope.namespace.slot,
         kSecAttrAccessGroup as String: scope.applicationIdentifier,
         kSecAttrSynchronizable as String: false]
    }
    public func load() throws -> SessionMaterial? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        let (status, data) = operations.copy(request)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw SessionFailure.keychain(status) }
        guard let data, data.count >= prefix.count+1, data.starts(with: prefix) else { throw SessionFailure.malformedRecord }
        let tag = data[data.startIndex+prefix.count]
        if tag == 0 && data.count == prefix.count+1 { throw SessionFailure.restorationBlocked }
        guard tag == 1, data.count > prefix.count+1 else { throw SessionFailure.malformedRecord }
        return try SessionMaterial(trustedSDKBytes: Data(data.dropFirst(prefix.count+1)))
    }
    public func save(_ material: SessionMaterial) throws {
        try material.withBytes { try write(prefix + Data([1]) + $0) }
    }
    public func clearAndBlock() throws {
        // Replaces all secret data with a durable non-secret marker, including after restart.
        // A failed write is reported; lifecycle stays blocked. No broad delete is performed.
        try write(prefix + Data([0]))
    }
    private func write(_ data: Data) throws {
        let values: [String: Any] = [kSecValueData as String: data, kSecAttrAccessible as String: protection.value]
        let status = operations.update(query, values)
        if status == errSecSuccess { return }
        guard status == errSecItemNotFound else { throw SessionFailure.keychain(status) }
        let added = operations.add(query.merging(values) { _, new in new })
        guard added == errSecSuccess else { throw SessionFailure.keychain(added) }
        // Duplicate/unknown writes are not retried with another key or a broader query.
    }
}
