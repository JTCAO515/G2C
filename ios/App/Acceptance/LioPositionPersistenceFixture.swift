// Generated simulator target only. Fixed synthetic keys/server data, no Keychain or network.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
@testable import CJMessageKeys
import Observation

@MainActor private final class PositionAcceptanceKeys: MessageKeyPersistence {
    let record = MessageKeyRecord(id: UUID(uuidString: "B35744FC-F460-4ED1-B21B-A64D5D34896C")!, bytes: Data(repeating: 57, count: 32))
    func read() throws -> MessageKeyRecord? { record }
    func add(_ value: MessageKeyRecord) throws { throw MessageKeyFailure.alreadyExists }
    func remove(expectedID: UUID) throws { throw MessageKeyFailure.clearUnconfirmed }
}
@MainActor @Observable private final class PositionAcceptanceFault {
    var writes = 0
    func reject(_ bytes: Data) throws { writes += 1; throw RecoveryError.persistenceUnknown }
}
@MainActor private struct PositionAcceptanceClients {
    let chats: ChatHistoryClients
    let fault = PositionAcceptanceFault()
    init(shell: ShellState) throws {
        let environment = UUID(uuidString: "C35744FC-F460-4ED1-B21B-A64D5D34896C")!
        let retainedCase = ProcessInfo.processInfo.arguments.contains("--lio-position-retained-unsent")
        let account = UUID(uuidString: retainedCase
            ? (shell.language == .chinese ? "F35744FC-F460-4ED1-B21B-A64D5D34896C" : "A35744FC-F460-4ED1-B21B-A64D5D34896C")
            : (shell.language == .chinese ? "D35744FC-F460-4ED1-B21B-A64D5D34896C" : "E35744FC-F460-4ED1-B21B-A64D5D34896C"))!
        let namespace = MessageKeyNamespace(environment: environment, account: account, purpose: .localMessageStorageV1)
        let keys = ScopedMessageKeyProvider(namespace: namespace, persistence: PositionAcceptanceKeys(),
                                            randomBytes: { throw MessageKeyFailure.storageUnavailable })
        let base = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let directory = base.appendingPathComponent("SyntheticPositionAcceptance").appendingPathComponent(account.uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let store = try LioChatPositionStore(directory: directory, namespace: namespace, keys: keys, validate: {})
        let continuity = LioChatContinuity()
        try restoreLioChatPosition(continuity, store: store)
        if retainedCase && continuity.selectedID == nil {
            let local = Data("synthetic-unsent-local".utf8)
            continuity.withPositionChange {
                continuity.selectedID = local
                continuity.blankIDs.insert(local)
                continuity.firstQuestions[local] = LioQuestion(messageID: "synthetic-original-A",
                    text: "Original A", language: shell.language.lio)
                continuity.updateDraft("Different draft B", for: local)
            }
        }
        if ProcessInfo.processInfo.arguments.contains("--lio-position-write-failure") {
            continuity.bindPositionWriter { [fault] in try fault.reject($0) }
        }
        chats = try ChatHistoryClients(positionShell: shell, continuity: continuity, account: account.uuidString)
    }
}
private extension ChatHistoryClients {
    init(positionShell shell: ShellState, continuity: LioChatContinuity, account: String) throws {
        try self.init(shell: shell, source: ChatHistorySource(shell: shell, account: account), continuity: continuity)
    }
}
@MainActor private struct LioPositionPersistenceFixture: View {
    let shell: ShellState
    @State private var clients: Result<PositionAcceptanceClients, any Error>?
    var body: some View {
        Group {
            if let clients {
                switch clients {
                case .success(let value):
                    LioHome(language: shell.language.lio, service: value.chats.original, isDemo: false,
                            chatLibrary: value.chats.library) { LioMenuSettings(shell: shell) }

                case .failure:
                    Text("Synthetic position setup failed").accessibilityIdentifier("fixture.position.setup-failure")
                }
            } else { ProgressView() }
        }
        .task { if clients == nil { clients = Result { try PositionAcceptanceClients(shell: shell) } } }
    }
}
#endif
