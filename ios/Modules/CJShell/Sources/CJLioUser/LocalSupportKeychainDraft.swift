#if os(iOS)
import Foundation
import Security

@MainActor public struct LocalSupportKeychainDraft {
    public enum Scope: Hashable, Sendable {
        case guest
        case account(environment: UUID, account: UUID)

        fileprivate var slot: String {
            switch self {
            case .guest: "guest"
            case .account(let environment, let account):
                "account.\(environment.uuidString).\(account.uuidString)"
            }
        }
    }

    public enum Failure: Error {
        case invalidRecord, inactiveScope, keychain(OSStatus)
    }

    private let applicationIdentifier: String

    /// The App supplies the application identifier read from its signed entitlement.
    public init(applicationIdentifier: String) { self.applicationIdentifier = applicationIdentifier }

    public func storage(for scope: Scope, isCurrent: @escaping @MainActor () -> Bool) -> LocalSupportDraftStorage {
        LocalSupportDraftStorage(load: {
            guard isCurrent() else { throw Failure.inactiveScope }
            return try load(scope)
        }, save: { value in
            guard isCurrent() else { throw Failure.inactiveScope }
            try save(value, in: scope)
        }, clear: {
            guard isCurrent() else { throw Failure.inactiveScope }
            try clear(scope)
        })
    }

    /// Used by the App after fencing the scope's UI and before reporting cleanup complete.
    public func clear(_ scope: Scope) throws {
        let status = SecItemDelete(query(scope) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw Failure.keychain(status) }
        try requireAbsent(scope)
    }

    public func requireAbsent(_ scope: Scope) throws {
        let status = SecItemCopyMatching(query(scope) as CFDictionary, nil)
        guard status == errSecItemNotFound else { throw Failure.keychain(status) }
    }

    private func query(_ scope: Scope) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "G2C.LocalSupport.draft.v1",
            kSecAttrAccount as String: scope.slot,
            kSecAttrAccessGroup as String: applicationIdentifier,
            kSecAttrSynchronizable as String: false,
        ]
    }

    private func load(_ scope: Scope) throws -> String? {
        var request = query(scope)
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw Failure.keychain(status) }
        guard let data = result as? Data, let text = String(data: data, encoding: .utf8) else {
            throw Failure.invalidRecord
        }
        return text
    }

    private func save(_ value: String, in scope: Scope) throws {
        let item = query(scope)
        let data: [String: Any] = [
            kSecValueData as String: Data(value.utf8),
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        ]
        let status = SecItemUpdate(item as CFDictionary, data as CFDictionary)
        if status == errSecSuccess { return }
        guard status == errSecItemNotFound else { throw Failure.keychain(status) }
        let added = SecItemAdd(item.merging(data) { _, replacement in replacement } as CFDictionary, nil)
        guard added == errSecSuccess else { throw Failure.keychain(added) }
    }
}
#endif
