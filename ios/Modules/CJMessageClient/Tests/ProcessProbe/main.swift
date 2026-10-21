// Test-only process probe. Synthetic temporary key file; NOT a production key provider.
import Foundation
import CryptoKit
import CJMessageClient

@MainActor final class SyntheticKeys: MessageEncryptionKeyProvider {
    let secret: SymmetricKey
    init(file: URL) throws { secret = SymmetricKey(data: try Data(contentsOf: file)) }
    func key(for scope: StorageScope) throws -> SymmetricKey? { secret }
}

@main struct Probe {
    @MainActor static func main() throws {
        let args = CommandLine.arguments
        guard args.count == 4, ["write", "read"].contains(args[1]) else { throw RecoveryError.invalidInput }
        let directory = URL(fileURLWithPath: args[2]).resolvingSymlinksInPath()
        let keys = try SyntheticKeys(file: URL(fileURLWithPath: args[3]))
        let store = try EncryptedFileStorage(directory: directory, keys: keys)
        let recovery = MessageRecovery(storage: store)
        let scope = try StorageScope(environment: "synthetic-process-local", account: "synthetic-process-user")
        let lease = try recovery.activate(scope)
        let raw = Data(" {\"message_id\":\"process-original\",\"text\":\"fixture 中文\"} \n".utf8)
        if args[1] == "write" {
            guard try recovery.action(messageID: "process-original", lease: lease) == nil else { throw RecoveryError.invalidInput }
            try recovery.saveDraft(Data("synthetic unsent".utf8), conversationID: "chat", lease: lease)
            try recovery.stage(messageID: "process-original", originalUTF8: raw, lease: lease)
            let submission = try recovery.beginSubmission(messageID: "process-original", lease: lease)
            guard submission.originalUTF8 == raw else { throw RecoveryError.invalidSnapshot }
            print("PASS writer process: durable original bytes + draft + queryRequired, no network")
        } else {
            guard let action = try recovery.action(messageID: "process-original", lease: lease),
                  action.originalUTF8 == raw, action.phase == .queryRequired,
                  try recovery.draft(conversationID: "chat", lease: lease) == Data("synthetic unsent".utf8) else {
                throw RecoveryError.invalidSnapshot
            }
            let query = try recovery.beginQuery(messageID: "process-original", lease: lease)
            try recovery.observeNotObserved(query)
            do {
                _ = try recovery.beginSubmission(messageID: "process-original", lease: lease)
                throw RecoveryError.invalidSnapshot
            } catch RecoveryError.queryOnly { }
            print("PASS new reader process: same ID/bytes/draft; null remains query-only")
        }
    }
}
