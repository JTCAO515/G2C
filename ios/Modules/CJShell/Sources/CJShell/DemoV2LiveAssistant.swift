#if os(iOS)
import SwiftUI
import Observation
import CJMessageClient
import CJMessageHTTP

@MainActor struct DemoV2LiveServices {
    let submit: (Data) async throws -> DemoDialogueMessageOutcome
    let reconcile: (String) async throws -> DemoDialogueMessageOutcome
    let unresolved: () throws -> [String]
    let originalText: (String) throws -> String
    let read: (String, String?, @MainActor (Data) throws -> Void) async throws -> Void
}

/// Stage 1 of the signed Beta's zero-setup UI. This uses the existing approved
/// .1 question path and reads only the accepted original's server event feed.
@MainActor @Observable public final class DemoV2LiveAssistantModel {
    private let shell: ShellState
    private let generation: ShellGeneration
    private let services: DemoV2LiveServices
    private let isCurrentSession: @MainActor () -> Bool
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private var currentWork = UUID()
    @ObservationIgnored private var active = true

    private(set) var rows: [DemoV2Message] = []
    var draft = ""
    private(set) var notice: DemoV2DeliveryNotice?
    private(set) var busy = false
    private var originalToCheck: String?
    private var conversationID: String?
    private var openNewConversation = false
    private var answer: Answer?

    private struct Answer {
        let binding: DemoV2Dialogue.EventBinding
        let rowID: String
        var cursor: String?
        var projection = DemoV2RunProjection()
        var rereadFromStart = false
    }

    public convenience init(shell: ShellState, messages: DemoDialogueMessageClient, events: DemoDialogueEventsClient,
                            lease: Lease, isCurrentSession: @escaping @MainActor () -> Bool) {
        self.init(shell: shell, services: .init(
            submit: { try await messages.submit(originalUTF8: $0, lease: lease) },
            reconcile: { try await messages.reconcile(messageID: $0, lease: lease) },
            unresolved: { try messages.unresolvedMessages(lease: lease).map(\.messageID) },
            originalText: { try messages.originalText(messageID: $0, lease: lease) },
            read: { try await events.read(messageID: $0, after: $1, lease: lease, consume: $2) }),
            isCurrentSession: isCurrentSession)
    }

    init(shell: ShellState, services: DemoV2LiveServices, isCurrentSession: @escaping @MainActor () -> Bool) {
        self.shell = shell
        self.generation = shell.generation
        self.services = services
        self.isCurrentSession = isCurrentSession
    }

    func belongs(to state: ShellState) -> Bool { shell === state }

    private var current: Bool {
        active && shell.generation == generation && !shell.messageBindingBlocked && isCurrentSession()
    }

    var canStartNewChat: Bool { current && !busy && originalToCheck == nil }

    var canSend: Bool {
        canStartNewChat && answer == nil && notice != .dailyLimit && notice != .accessDenied &&
            !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    func restorePending() {
        guard current, !busy, originalToCheck == nil else { return }
        do {
            let unresolved = try services.unresolved()
            if unresolved.count == 1, let id = unresolved.first {
                originalToCheck = id
                draft = try services.originalText(id)
                notice = .unknown
            }
        } catch {
            if current { notice = .unknown }
        }
    }

    func newChat() {
        guard canStartNewChat else { return }
        rows.removeAll()
        draft = ""
        conversationID = nil
        answer = nil
        openNewConversation = true
        if notice != .dailyLimit && notice != .accessDenied { notice = nil }
    }

    func send() {
        guard canSend else { return }
        let text = draft
        let destination: DemoV2Dialogue.Destination = openNewConversation ? .newConversation
            : conversationID.map(DemoV2Dialogue.Destination.conversation) ?? .initial
        let original: DemoV2Dialogue.OriginalMessage
        do {
            original = try .init(.init(id: UUID(), text: text, language: shell.language, destination: destination))
        } catch {
            notice = .rejected
            return
        }
        start { model, work in
            do {
                let outcome = try await model.services.submit(original.bytes)
                try model.check(work)
                try await model.show(outcome, originalID: original.command.message_id, text: text, work: work)
            } catch RecoveryError.queryOnly {
                try model.check(work)
                model.busy = false
                model.restorePending()
            } catch MessageHTTPFailure.credentialsUnavailable {
                try model.check(work)
                model.notice = .accessDenied
            }
        }
    }

    func checkOriginal() {
        guard current, !busy else { return }
        if let id = originalToCheck {
            start { model, work in
                let text = try model.services.originalText(id)
                let outcome = try await model.services.reconcile(id)
                try model.check(work)
                try await model.show(outcome, originalID: id, text: text, work: work)
            }
        } else if answer != nil {
            start { model, work in try await model.readAnswer(work) }
        }
    }

    public func invalidate() {
        active = false
        currentWork = UUID()
        task?.cancel()
        task = nil
        rows.removeAll()
        draft = ""
        originalToCheck = nil
        conversationID = nil
        answer = nil
        notice = nil
        busy = false
    }

    private func start(_ operation: @escaping @MainActor (DemoV2LiveAssistantModel, UUID) async throws -> Void) {
        let work = UUID()
        currentWork = work
        busy = true
        task = Task { [weak self] in
            guard let self else { return }
            do { try await operation(self, work) }
            catch {
                if current && currentWork == work && !Task.isCancelled {
                    notice = originalToCheck == nil && answer != nil ? .answerInterrupted : .unknown
                }
            }
            if current && currentWork == work { busy = false; task = nil }
        }
    }

    private func check(_ work: UUID) throws {
        guard current, currentWork == work else { throw RecoveryError.inactive }
        try Task.checkCancellation()
    }

    private func show(_ outcome: DemoDialogueMessageOutcome, originalID: String, text: String, work: UUID) async throws {
        switch outcome {
        case .accepted(let receipt):
            originalToCheck = nil
            notice = nil
            conversationID = receipt.conversationID
            openNewConversation = false
            if Data(draft.utf8) == Data(text.utf8) { draft = "" }
            rows.append(.init(id: receipt.messageID, fromUser: true, text: text))
            let rowID = "reply-" + receipt.runID
            rows.append(.init(id: rowID, fromUser: false, text: ""))
            answer = Answer(binding: .init(verified: receipt), rowID: rowID)
            try await readAnswer(work)
        case .notObserved:
            originalToCheck = originalID
            notice = .notObserved
        case .unknown:
            originalToCheck = originalID
            notice = .unknown
        case .rejected(_, let code):
            originalToCheck = nil
            switch code {
            case "DEMO_DAILY_LIMIT": notice = .dailyLimit
            case "ACCESS_DENIED": notice = .accessDenied
            default: notice = .rejected
            }
        }
    }

    private func readAnswer(_ work: UUID) async throws {
        guard var reading = answer else { return }
        if reading.rereadFromStart {
            reading.projection = DemoV2RunProjection()
            reading.cursor = nil
            reading.rereadFromStart = false
        }
        var stream = try DemoV2EventStream(binding: reading.binding, maximumWireBytes: 1_000_000,
                                           resumingAfter: reading.cursor.flatMap(Int64.init))
        do {
            try await services.read(reading.binding.messageID, reading.cursor) { bytes in
                try check(work)
                let events = try stream.append(bytes)
                guard !events.isEmpty else { return }
                events.forEach { reading.projection.apply($0) }
                guard reading.projection.answer.utf8.count <= 200_000 else { throw MessageHTTPFailure.invalidResponse }
                reading.cursor = stream.lastEventID
                answer = reading
                updateRow(reading)
            }
            try check(work)
            try stream.finish()
            switch reading.projection.status?.stage {
            case .completed:
                notice = nil
                answer = nil
            case .failed, .cancelled, .contextInvalid:
                notice = .rejected
                answer = nil
            default:
                notice = .answerInterrupted
            }
        } catch DemoDialogueEventsFailure.resyncRequired {
            try check(work)
            answer?.rereadFromStart = true
            notice = .answerInterrupted
        }
    }

    private func updateRow(_ reading: Answer) {
        guard let index = rows.firstIndex(where: { $0.id == reading.rowID }) else { return }
        let language = shell.language
        let sources = reading.projection.sources.map { source in
            DemoV2Source(id: source.source_id, title: source.label,
                         details: source.openableURL?.absoluteString ??
                            language.text("No verified source available", "暂无可核实来源"),
                         link: source.openableURL)
        }
        rows[index] = DemoV2Message(id: reading.rowID, fromUser: false, text: reading.projection.answer,
                                    status: reading.projection.activity(language), sources: sources)
    }
}

struct DemoV2LiveAssistant: View {
    @Bindable var model: DemoV2LiveAssistantModel
    let language: ShellLanguage

    var body: some View {
        DemoV2ConversationView(language: language, messages: model.rows, activeCardID: nil,
                               draft: $model.draft, canSend: model.canSend,
                               onSend: model.send, onAction: { _, _ in },
                               deliveryNotice: model.notice, onCheckOriginal: model.checkOriginal)
            .navigationTitle(ShellTab.assistant.title(language))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Menu {
                        Button(language.text("New chat", "新对话"), systemImage: "square.and.pencil", action: model.newChat)
                            .disabled(!model.canStartNewChat)
                    } label: {
                        Label(language.text("Conversation", "对话"), systemImage: "ellipsis.circle")
                    }
                }
            }
            .task { model.restorePending() }
    }
}
#endif
