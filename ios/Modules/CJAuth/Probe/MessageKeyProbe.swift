import Foundation
import CryptoKit

/// Prepared only. Requires explicit launch phase after Main approves signing proposal.
@MainActor enum MessageKeyProbe {
    static func run(arguments: [String]) -> String {
        #if !targetEnvironment(simulator)
        return "SKIP: simulator only"
        #else
        guard let index = arguments.firstIndex(of: "--message-key-phase"), arguments.count > index+1 else {
            return "SKIP: explicit message-key phase required"
        }
        let phase = arguments[index+1]
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let idFile = directory.appendingPathComponent("message-key-id.txt")
        let ciphertextFile = directory.appendingPathComponent("synthetic-message.sealed")
        do {
            guard let configURL = Bundle.main.url(forResource: "MessageKeyProbeScope", withExtension: "plist"),
                  let config = try PropertyListSerialization.propertyList(from: Data(contentsOf: configURL), format: nil) as? [String:String],
                  config["bundleID"] == Bundle.main.bundleIdentifier,
                  let environment = config["environment"].flatMap(UUID.init(uuidString:)),
                  let account = config["account"].flatMap(UUID.init(uuidString:)),
                  let group = config["applicationIdentifier"] else { throw MessageKeyFailure.invalidConfiguration }
            let namespace = MessageKeyNamespace(environment: environment, account: account, purpose: .localMessageStorageV1)
            let provider = try ScopedMessageKeyProvider(namespace: namespace, applicationIdentifier: group,
                                                        protection: .whenUnlockedThisDeviceOnly)
            switch phase {
            case "create":
                guard !FileManager.default.fileExists(atPath: idFile.path),
                      !FileManager.default.fileExists(atPath: ciphertextFile.path) else { throw MessageKeyFailure.alreadyExists }
                let key = try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create))
                // Non-secret receipt before test ciphertext, never raw key bytes.
                try key.id.uuidString.write(to: idFile, atomically: true, encoding: .utf8)
                let sealed = try key.withSymmetricKey { try AES.GCM.seal(Data("synthetic-message-only".utf8), using: $0) }
                guard let bytes = sealed.combined else { throw MessageKeyFailure.storageUnavailable }
                try bytes.write(to: ciphertextFile, options: .atomic)
            case "restore":
                guard let id = UUID(uuidString: try String(contentsOf: idFile, encoding: .utf8)),
                      let key = try provider.existing(expectedID: id, for: provider.begin(.lookup)) else { throw MessageKeyFailure.keyMismatch }
                let sealed = try AES.GCM.SealedBox(combined: Data(contentsOf: ciphertextFile))
                let plaintext = try key.withSymmetricKey { try AES.GCM.open(sealed, using: $0) }
                guard plaintext == Data("synthetic-message-only".utf8) else { throw MessageKeyFailure.keyMismatch }
            case "clear":
                guard let id = UUID(uuidString: try String(contentsOf: idFile, encoding: .utf8)) else { throw MessageKeyFailure.keyMismatch }
                // Only this harness-created file; no key deletion while test ciphertext remains.
                try FileManager.default.removeItem(at: ciphertextFile)
                try provider.clear(expectedID: id, storageState: .confirmedEmpty, for: provider.begin(.clear))
                guard try provider.existing(expectedID: nil, for: provider.begin(.lookup)) == nil else { throw MessageKeyFailure.clearUnconfirmed }
                try FileManager.default.removeItem(at: idFile)
            default: throw MessageKeyFailure.invalidConfiguration
            }
            let report = "PASS message-key phase=\(phase); synthetic-only; no business grant\n"
            try report.write(to: directory.appendingPathComponent("message-key-\(phase).txt"), atomically: true, encoding: .utf8)
            return report
        } catch {
            // Unknown writes preserve original item/receipt, never retry under a new namespace.
            let report = "FAIL message-key phase=\(phase) \(error as? MessageKeyFailure ?? .storageUnavailable)\n"
            try? report.write(to: directory.appendingPathComponent("message-key-\(phase).txt"), atomically: true, encoding: .utf8)
            return report
        }
        #endif
    }
}
