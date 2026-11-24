#if os(iOS)
import CryptoKit
import Foundation
import Security

@MainActor public struct LocalMedicalCardVault {
    public struct Owner: Sendable, Equatable {
        let environment: UUID
        let account: UUID

        public init(environment: UUID, account: UUID) {
            self.environment = environment
            self.account = account
        }

        fileprivate var slot: String { environment.uuidString + "." + account.uuidString }
    }

    private let applicationIdentifier: String
    public init(applicationIdentifier: String) { self.applicationIdentifier = applicationIdentifier }

    public func storage(for owner: Owner, isCurrent: @escaping @MainActor () -> Bool) throws -> LocalMedicalCardStorage {
        try store(owner).storage(isCurrent: isCurrent)
    }

    public func clear(_ owner: Owner) throws { try store(owner).clear() }
    public func requireAbsent(_ owner: Owner) throws { try store(owner).requireAbsent() }

    private func store(_ owner: Owner) throws -> LocalMedicalCardFileStore {
        let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                  appropriateFor: nil, create: false)
        let directory = support.appending(path: "G2CLocalMedicalCard", directoryHint: .isDirectory)
            .appending(path: owner.slot, directoryHint: .isDirectory)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "G2C.LocalMedicalCard.encryption.v1",
            kSecAttrAccount as String: owner.slot,
            kSecAttrAccessGroup as String: applicationIdentifier,
            kSecAttrSynchronizable as String: false,
        ]
        return LocalMedicalCardFileStore(directory: directory, scope: Data(owner.slot.utf8),
            keys: .init(read: {
                var match = query
                match[kSecReturnData as String] = true
                match[kSecMatchLimit as String] = kSecMatchLimitOne
                var result: CFTypeRef?
                let status = SecItemCopyMatching(match as CFDictionary, &result)
                if status == errSecItemNotFound { return nil }
                guard status == errSecSuccess, let bytes = result as? Data, bytes.count == 32 else {
                    throw LocalMedicalCardFailure.unavailable
                }
                return SymmetricKey(data: bytes)
            }, create: {
                let key = SymmetricKey(size: .bits256)
                var item = query
                item[kSecValueData as String] = key.withUnsafeBytes { Data($0) }
                item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
                guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else {
                    throw LocalMedicalCardFailure.unavailable
                }
                return key
            }, remove: {
                let status = SecItemDelete(query as CFDictionary)
                guard status == errSecSuccess || status == errSecItemNotFound else {
                    throw LocalMedicalCardFailure.unavailable
                }
            }))
    }
}
#endif
