import Foundation
import Observation
import SwiftUI

/// The passport nationality Local Support, Arrival Mode and the trip home share, kept per account (#1741).
/// It sits in UserDefaults under a key scoped to the signed-in account, so a second account on the same phone does
/// not read the first one's nationality. Account deletion (`account_cleanup`) removes it; switching accounts or a
/// session found invalid keeps it, as JT approved on 2026-11-25.
@MainActor @Observable public final class LioNationalityStore {
    /// The device-wide key used before #1741. Read once per account to migrate, then removed.
    nonisolated public static let legacyKey = "lio.local-support.nationality"

    /// The account's own key. Only an account id is in it: the nationality itself is the value.
    nonisolated public static func key(account: String) -> String { legacyKey + ".account." + account }

    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored public let key: String

    public var value: String {
        didSet {
            guard value != oldValue else { return }
            if value.isEmpty { defaults.removeObject(forKey: key) } else { defaults.set(value, forKey: key) }
        }
    }

    /// `account` is the signed-in account's id; nil (signed out, previews) keeps the device-wide key and neither
    /// migrates nor removes it.
    public init(account: String?, defaults: UserDefaults = .standard) {
        self.defaults = defaults
        if let account, !account.isEmpty {
            Self.migrateLegacyValue(toAccount: account, in: defaults)
            key = Self.key(account: account)
        } else {
            key = Self.legacyKey
        }
        value = defaults.string(forKey: key) ?? ""
    }

    /// Moves the device-wide value into this account once, then removes the device-wide key. An account that
    /// already has its own value keeps it; the old key is still removed so no later account picks it up.
    nonisolated public static func migrateLegacyValue(toAccount account: String, in defaults: UserDefaults = .standard) {
        guard !account.isEmpty, let legacy = defaults.object(forKey: legacyKey) else { return }
        let scoped = key(account: account)
        if defaults.object(forKey: scoped) == nil, let text = legacy as? String, !text.isEmpty {
            defaults.set(text, forKey: scoped)
        }
        defaults.removeObject(forKey: legacyKey)
    }

    /// Account deletion only: removes this account's nationality and nothing else.
    nonisolated public static func erase(account: String, in defaults: UserDefaults = .standard) {
        defaults.removeObject(forKey: key(account: account))
    }

    nonisolated public static func isAbsent(account: String, in defaults: UserDefaults = .standard) -> Bool {
        defaults.object(forKey: key(account: account)) == nil
    }
}

private struct LioNationalityKey: EnvironmentKey { static let defaultValue: LioNationalityStore? = nil }

extension EnvironmentValues {
    /// The signed-in account's nationality; nil outside a signed-in host (previews, demo without an account).
    var lioNationality: LioNationalityStore? {
        get { self[LioNationalityKey.self] }
        set { self[LioNationalityKey.self] = newValue }
    }
}

public extension View {
    /// The signed-in account's nationality for every Lio page below (#1741).
    func lioNationality(_ store: LioNationalityStore?) -> some View { environment(\.lioNationality, store) }
}

/// Reads the account's nationality from the environment, or a device-wide store when there is no account.
@MainActor @propertyWrapper struct LioNationalityBinding: DynamicProperty {
    @Environment(\.lioNationality) private var injected
    /// Signed out or in previews: the device-wide key, read through the same store.
    @State private var fallback = LioNationalityStore(account: nil)

    var store: LioNationalityStore { injected ?? fallback }

    var wrappedValue: String {
        get { store.value }
        nonmutating set { store.value = newValue }
    }

    var projectedValue: Binding<String> {
        let store = store
        return Binding(get: { store.value }, set: { store.value = $0 })
    }
}
