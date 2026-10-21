import Foundation
import UIKit
import Security

@main @MainActor final class SessionProbeApp: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        let controller = UIViewController()
        controller.view.backgroundColor = .systemBackground
        let label = UILabel(frame: controller.view.bounds.insetBy(dx: 24, dy: 100))
        label.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        label.numberOfLines = 0
        label.text = runProbe()
        controller.view.addSubview(label)
        window.rootViewController = controller
        window.makeKeyAndVisible()
        self.window = window
        return true
    }
    @MainActor private func runProbe() -> String {
        #if !targetEnvironment(simulator)
        return "SKIP: simulator only"
        #else
        let args = ProcessInfo.processInfo.arguments
        if args.contains("--message-key-phase") { return MessageKeyProbe.run(arguments: args) }
        guard let index = args.firstIndex(of: "--phase"), args.count > index+1 else { return "SKIP: explicit phase required" }
        let phase = args[index+1]
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let ownership = directory.appendingPathComponent("probe-ownership.plist")
        var cleanupQuery: [String: Any]?
        func require(_ condition: Bool) throws { if !condition { throw SessionFailure.storageUnavailable } }
        func base(_ namespace: SessionNamespace) -> [String: Any] {
            [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:namespace.service,
             kSecAttrAccount as String:namespace.slot, kSecAttrSynchronizable as String:false]
        }
        do {
            var report = ["phase=\(phase)"]
            let namespace: SessionNamespace
            let group: String
            if phase == "prepare" {
                // Never reuse a persisted ownership file, or read/delete an existing item.
                try require(!FileManager.default.fileExists(atPath: ownership.path))
                namespace = try SessionNamespace(environment: UUID(), slot: "synthetic-session-probe")
                var creation = base(namespace)
                creation[kSecValueData as String] = Data([0x43,0x4a,0x53,0x01,0])
                creation[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
                creation[kSecReturnAttributes as String] = true
                var attributes: CFTypeRef?
                let status = SecItemAdd(creation as CFDictionary, &attributes)
                guard status == errSecSuccess else { throw SessionFailure.keychain(status) }
                cleanupQuery = base(namespace) // only the item just created successfully
                guard let returned = attributes as? [String: Any],
                      let ownGroup = returned[kSecAttrAccessGroup as String] as? String else {
                    throw SessionFailure.invalidConfiguration
                }
                group = ownGroup
                cleanupQuery?[kSecAttrAccessGroup as String] = group
                let metadata = ["environment":namespace.environment.uuidString, "slot":namespace.slot, "group":group]
                try PropertyListSerialization.data(fromPropertyList: metadata, format: .binary, options: 0)
                    .write(to: ownership, options: .atomic)
                report += ["created_unique_item=true", "service=\(namespace.service)", "account=\(namespace.slot)", "group=\(group)"]
            } else {
                let data = try Data(contentsOf: ownership)
                guard let metadata = try PropertyListSerialization.propertyList(from: data, format: nil) as? [String:String],
                      let id = metadata["environment"].flatMap(UUID.init(uuidString:)),
                      let slot = metadata["slot"], slot == "synthetic-session-probe", let ownGroup = metadata["group"] else {
                    throw SessionFailure.invalidConfiguration
                }
                namespace = try SessionNamespace(environment: id, slot: slot); group = ownGroup
                cleanupQuery = base(namespace); cleanupQuery?[kSecAttrAccessGroup as String] = group
            }
            let scope = try KeychainSessionScope(namespace: namespace, applicationIdentifier: group)
            let store = KeychainSessionStore(scope: scope, protection: .whenUnlockedThisDeviceOnly)
            let lifecycle = SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly)
            switch phase {
            case "prepare":
                let material = try SessionMaterial(trustedSDKBytes: Data("SYNTHETIC-SESSION-NOT-A-TOKEN".utf8))
                try lifecycle.save(material, for: lifecycle.beginTrustedSDKSave())
                report.append("save=true")
            case "restore-clear":
                guard let loaded = try lifecycle.load(for: lifecycle.beginUserRestore()) else { throw SessionFailure.storageUnavailable }
                try require(loaded.withBytes { $0 == Data("SYNTHETIC-SESSION-NOT-A-TOKEN".utf8) })
                report.append("restore_after_process_restart=true")
                let beforeNetwork = try lifecycle.beginUserRestore()
                lifecycle.noteNetworkUnknown()
                try require(lifecycle.isCurrent(beforeNetwork))
                try require(try lifecycle.load(for: beforeNetwork) != nil)
                report.append("network_unknown_preserves=true")
                try lifecycle.clear()
                report.append("credential_overwritten_with_block_marker=true")
            case "blocked-clean":
                do { _ = try lifecycle.load(for: lifecycle.beginUserRestore()); throw SessionFailure.storageUnavailable }
                catch SessionFailure.restorationBlocked { report.append("block_marker_survives_process_restart=true") }
                guard let query = cleanupQuery else { throw SessionFailure.invalidConfiguration }
                let removed = SecItemDelete(query as CFDictionary)
                guard removed == errSecSuccess else { throw SessionFailure.keychain(removed) }
                let absent = SecItemCopyMatching(query as CFDictionary, nil)
                try require(absent == errSecItemNotFound)
                cleanupQuery = nil
                report.append("only_created_item_deleted_and_absent=true")
            default: throw SessionFailure.invalidConfiguration
            }
            report += ["business_permission=false", "PASS"]
            let text = report.joined(separator: "\n")+"\n"
            try text.write(to: directory.appendingPathComponent("\(phase).txt"), atomically: true, encoding: .utf8)
            print(text)
            return "PASS: \(phase) — synthetic data only"
        } catch {
            var message = "FAIL: \(phase) \(error as? SessionFailure ?? .storageUnavailable)"
            if let query = cleanupQuery {
                let status = SecItemDelete(query as CFDictionary)
                message += " owned_item_cleanup_status=\(status)"
            }
            try? message.write(to: directory.appendingPathComponent("\(phase).txt"), atomically: true, encoding: .utf8)
            print(message)
            return message
        }
        #endif
    }
}
