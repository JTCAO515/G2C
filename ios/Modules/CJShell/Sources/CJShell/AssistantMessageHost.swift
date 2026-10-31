import Foundation
import Observation
import CJMessageClient
import CJMessageHTTP
import CJAPI

/// Trusted composition input, never constructed from view text or a session token.
/// queryOriginal must use the same recovery/scope/lease and a verified query adapter.
@MainActor public struct AssistantMessageBinding {
    let recovery: MessageRecovery
    let scope: StorageScope
    let lease: Lease
    let generation: ShellGeneration
    let conversationID: String?
    let messageID: String?
    let synthetic: Bool
    let isCurrent: @MainActor () -> Bool
    let invalidateResources: @MainActor () -> Void
    let queryOriginal: (@MainActor (String, Lease) async throws -> Void)?
    let sendClient: MessageHTTPClient?
    let travelSelection: TravelSelectionModel?
    let currentNeeds: (@MainActor () -> MessageNeedsSelection?)?
    let tripDiscussions: Bool
    let scopedEdits: Bool

    public init(recovery: MessageRecovery, scope: StorageScope, lease: Lease,
                generation: ShellGeneration, conversationID: String? = nil, messageID: String? = nil,
                synthetic: Bool, isCurrent: @escaping @MainActor () -> Bool,
                invalidateResources: @escaping @MainActor () -> Void,
                queryOriginal: (@MainActor (String, Lease) async throws -> Void)? = nil,
                sendClient: MessageHTTPClient? = nil,travelSelection: TravelSelectionModel? = nil,
                currentNeeds: (@MainActor () -> MessageNeedsSelection?)? = nil,tripDiscussions: Bool = false,scopedEdits:Bool = false) {
        self.recovery = recovery; self.scope = scope; self.lease = lease
        self.generation = generation; self.conversationID = conversationID; self.messageID = messageID
        self.synthetic = synthetic; self.isCurrent = isCurrent; self.queryOriginal = queryOriginal
        self.invalidateResources = invalidateResources
        self.sendClient = sendClient;self.travelSelection = travelSelection;self.currentNeeds = currentNeeds
        self.tripDiscussions=tripDiscussions
        self.scopedEdits=scopedEdits
    }
}

/// Captured only from the current transport-accepted canonical MESSAGE record.
/// No public initializer, credentials, or UI-derived message/run identifiers.
@MainActor public final class AcceptedMessageRunReceipt: CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    let receipt: Components.Schemas.MessageReceipt
    let travelReference: Components.Schemas.MessageTravelReference?
    let tripReference: MessageTripReference?
    let editReference: MessageEditReference?
    let originalTextUTF8: Data?
    let isCurrent: @MainActor () -> Bool
    let isStillOwned: @MainActor () -> Bool
    fileprivate init(receipt: Components.Schemas.MessageReceipt,travelReference: Components.Schemas.MessageTravelReference? = nil,tripReference:MessageTripReference? = nil,editReference:MessageEditReference? = nil, originalTextUTF8: Data?, isCurrent: @escaping @MainActor () -> Bool,
                     isStillOwned: @escaping @MainActor () -> Bool) {
        self.receipt = receipt;self.travelReference = travelReference;self.tripReference=tripReference;self.editReference=editReference;self.originalTextUTF8 = originalTextUTF8; self.isCurrent = isCurrent; self.isStillOwned = isStillOwned
    }
    public nonisolated var description: String { "<redacted accepted message receipt>" }
    public nonisolated var debugDescription: String { description }
    public nonisolated var customMirror: Mirror { Mirror(self, children: [:]) }
}

/// Current canonical recovery input only. The USAGE client, not the UI, must decode
/// and capture its own closed AcceptedUsageMessage. No public constructor or actor IDs.
@MainActor public final class AcceptedMessageUsageInput: CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    let recovery: MessageRecovery
    let scope: StorageScope
    let lease: Lease
    let record: ActionRecord
    let isCurrent: @MainActor () -> Bool
    let isStillOwned: @MainActor () -> Bool
    fileprivate init(binding: AssistantMessageBinding, record: ActionRecord,
                     isCurrent: @escaping @MainActor () -> Bool, isStillOwned: @escaping @MainActor () -> Bool) {
        recovery = binding.recovery; scope = binding.scope; lease = binding.lease; self.record = record
        self.isCurrent = isCurrent; self.isStillOwned = isStillOwned
    }
    public nonisolated var description: String { "<redacted accepted message usage input>" }
    public nonisolated var debugDescription: String { description }
    public nonisolated var customMirror: Mirror { Mirror(self, children: [:]) }
}

/// Activity only; canonical action phase/bytes/receipt stay in CJMessageClient.ActionRecord.
public enum MessageHostActivity: Equatable {
    case unavailable, ready, preparing, sending, querying, inputRejected, unknown, storageBlocked, invalidated
}
public enum TripDiscussionChoiceDisplay {
    case unselected,none,trip(title:String,selection:MessageTripSelection),unavailable
}
public struct MessageDiscussionRefusal {
    public let status:Int
    public let code:String
    public let definiteFailure:Bool
}
public struct ScopedMessagePresentation {
    public let title:String?
    public let trip:MessageEditTripSelection?
    public let needs:MessageNeedsSelection?
    public let intent:MessageModificationIntent
    fileprivate let owner:UUID
    fileprivate let generation:ShellGeneration
    fileprivate let revision:UUID
}
@MainActor public struct ScopedMessageChoiceCommand {
    fileprivate enum Kind { case intent(MessageModificationIntent), needs(MessageNeedsSelection) }
    fileprivate let kind:Kind
    fileprivate let owner:UUID
    fileprivate let generation:ShellGeneration
    fileprivate let revision:UUID
    public var needsSelection:MessageNeedsSelection? { if case .needs(let value)=kind { return value };return nil }
}
private struct ScopedMessageChoices {
    var revision=UUID()
    var entry:TripDiscussionEntry?
    var needs:MessageNeedsSelection?
    var intent:MessageModificationIntent = .none
}
public enum DiscussionConversationState {
    case idle,working(String),unknown(String),available(String),rejected(String,Int)
}
@MainActor public struct DiscussionConversationIntent {
    fileprivate enum Kind { case create,query(String),select(String) }
    fileprivate let kind:Kind
    fileprivate let owner:UUID
    fileprivate let generation:ShellGeneration
    fileprivate let choice:UUID
    fileprivate let selection:UUID
    fileprivate let draft:UUID
}

@MainActor public struct MessageResubmissionContext: Identifiable {
    public let id = UUID()
    public let requiresConfirmation: Bool
    fileprivate let binding: AssistantMessageBinding
    fileprivate let messageID: String
    fileprivate let revision: UUID
    fileprivate let wire: MessageSendWireVersion
}

@MainActor @Observable public final class AssistantMessageHost {
    public private(set) var activity: MessageHostActivity = .unavailable
    private var storedDraftBytes: Data?
    public var draftStored: Bool { bindingIsCurrent && storedDraftBytes == Data(shell.draft.utf8) }
    @ObservationIgnored private let shell: ShellState
    @ObservationIgnored private var binding: AssistantMessageBinding?
    @ObservationIgnored private var usedGeneration: ShellGeneration?
    @ObservationIgnored private var task: Task<Void, Never>?
    private var record: ActionRecord?
    private var projection: LocalRecoveryProjection?
    private var selectedConversationID: String?
    private var selectedMessageID: String?
    private var runSelectionRevision = UUID()
    private var runSelectionAllowed = false
    private var discussionEntry:TripDiscussionEntry?
    private var discussionChoiceMade=false
    private var discussionRevision=UUID()
    private var storedDiscussionRefusal:MessageDiscussionRefusal?
    private let conversationIntentOwner=UUID()
    @ObservationIgnored private var scopedChoices=ScopedMessageChoices()
    private var conversationTask=UUID()
    private var storedConversationState:DiscussionConversationState = .idle
    public var creationIntent: MessageCreationIntent = .none
    public var isBusy: Bool { activity == .preparing || activity == .sending || activity == .querying }
    public var selectedConversation: String? { bindingIsCurrent ? selectedConversationID : nil }
    public var travelSelection: TravelSelectionModel? { bindingIsCurrent ? binding?.travelSelection : nil }
    public var supportsSending: Bool { bindingIsCurrent && binding?.sendClient != nil }
    public var supportsTripDiscussions:Bool { bindingIsCurrent && binding?.tripDiscussions == true }
    public var supportsScopedEdits:Bool { bindingIsCurrent && binding?.scopedEdits == true }
    public var supportsTripMessages:Bool { supportsTripDiscussions || supportsScopedEdits }
    public var discussionRefusal:MessageDiscussionRefusal? { bindingIsCurrent ? storedDiscussionRefusal : nil }
    public var conversationState:DiscussionConversationState { bindingIsCurrent ? storedConversationState : .idle }
    public var hasUnassignedDraft:Bool { bindingIsCurrent && selectedConversationID==nil && !shell.draft.isEmpty }
    public var conversationOpenings:[ConversationOpeningRecord] {
        guard bindingIsCurrent,let binding else { return [] }
        do { return try binding.recovery.conversationOpenings(lease:binding.lease) } catch { return [] }
    }
    public var scopedPresentation:ScopedMessagePresentation? {
        access(keyPath:\.scopedPresentation)
        let captured=scopedChoices
        guard supportsScopedEdits,let binding else { return nil }
        do {
            try captured.entry?.validate(scopeEnvironment:binding.scope.environment,scopeAccount:binding.scope.account,generation:binding.generation)
            let trip=try captured.entry.map(editSelection)
            guard isSameBinding(binding),bindingIsCurrent,isSameBinding(binding),scopedChoices.revision==captured.revision else { return nil }
            return .init(title:captured.entry?.title,trip:trip,needs:captured.needs,intent:captured.intent,
                owner:conversationIntentOwner,generation:binding.generation,revision:captured.revision)
        } catch { return nil }
    }
    private func editSelection(_ entry:TripDiscussionEntry) throws -> MessageEditTripSelection {
        let value=entry.selection
        return try .init(id:value.id,expectedVersion:value.expectedVersion,contentSHA256:entry.content.sha256,
            day:value.itemID == nil ? value.day : nil,itemIDs:value.itemID.map { [$0] } ?? [])
    }
    private func ownsScopedPresentation(_ value:ScopedMessagePresentation) -> Bool {
        value.owner==conversationIntentOwner && value.generation==shell.generation && value.revision==scopedChoices.revision
    }
    public func captureScopedIntent(_ intent:MessageModificationIntent,for presentation:ScopedMessagePresentation) -> ScopedMessageChoiceCommand? {
        guard supportsScopedEdits,!isBusy,ownsScopedPresentation(presentation) else { return nil }
        return .init(kind:.intent(intent),owner:conversationIntentOwner,generation:shell.generation,revision:scopedChoices.revision)
    }
    public func captureScopedNeedsChoice(for presentation:ScopedMessagePresentation) -> ScopedMessageChoiceCommand? {
        let token=scopedChoices.revision
        guard supportsScopedEdits,!isBusy,let binding,scopedChoices.entry != nil,ownsScopedPresentation(presentation),
              let needs=binding.currentNeeds?(),isSameBinding(binding),bindingIsCurrent,isSameBinding(binding),scopedChoices.revision==token,ownsScopedPresentation(presentation) else { return nil }
        return .init(kind:.needs(needs),owner:conversationIntentOwner,generation:binding.generation,revision:token)
    }
    @discardableResult public func performScopedChoice(_ command:ScopedMessageChoiceCommand) -> Bool {
        guard supportsScopedEdits,!isBusy,let binding,command.owner==conversationIntentOwner,
              command.generation==shell.generation,command.revision==scopedChoices.revision else { return false }
        var next=scopedChoices
        switch command.kind {
        case .intent(let intent):next.intent=intent
        case .needs(let needs):guard binding.currentNeeds?()==needs else { return false };next.needs=needs
        }
        next.revision=UUID()
        let changed=withMutation(keyPath:\.scopedPresentation) {
            guard isSameBinding(binding),bindingIsCurrent,isSameBinding(binding),!isBusy,
                  shell.generation==command.generation,scopedChoices.revision==command.revision else { return false }
            scopedChoices=next;return true
        }
        guard changed,isSameBinding(binding),scopedChoices.revision==next.revision else { return false }
        retireRunSelection();return true
    }
    private func selectScopedTrip(_ entry:TripDiscussionEntry) -> Bool {
        let token=scopedChoices.revision
        guard supportsScopedEdits,!isBusy,let binding else { return false }
        do { try entry.validate(scopeEnvironment:binding.scope.environment,scopeAccount:binding.scope.account,generation:binding.generation) }
        catch { return false }
        var next=ScopedMessageChoices();next.entry=entry
        let changed=withMutation(keyPath:\.scopedPresentation) {
            guard isSameBinding(binding),bindingIsCurrent,isSameBinding(binding),!isBusy,scopedChoices.revision==token else { return false }
            scopedChoices=next;return true
        }
        guard changed,isSameBinding(binding),scopedChoices.revision==next.revision else { return false }
        // A different formal Trip never silently inherits temporary memory or
        // the previous Trip's explicit NEEDS choice.
        binding.travelSelection?.invalidate()
        guard isSameBinding(binding),scopedChoices.revision==next.revision else { return false }
        retireRunSelection();return true
    }
    private func capturedScopedMessage() throws -> (entry:TripDiscussionEntry,trip:MessageEditTripSelection,namespace:MessageEditNamespace,needs:MessageNeedsSelection?,intent:MessageModificationIntent) {
        let captured=scopedChoices
        guard supportsScopedEdits,let binding,let entry=captured.entry,let travel=binding.travelSelection else { throw RecoveryError.queryOnly }
        let needs:MessageNeedsSelection?
        if captured.intent == .proposeScopedEdit {
            guard let selected=captured.needs,binding.currentNeeds?()==selected else { throw RecoveryError.queryOnly };needs=selected
        } else { needs=nil }
        try entry.validate(scopeEnvironment:binding.scope.environment,scopeAccount:binding.scope.account,generation:binding.generation)
        let original=try travel.capture()
        guard let namespace=original.context else { throw RecoveryError.queryOnly }
        let trip=try editSelection(entry)
        guard captured.intent != .proposeScopedEdit || ((trip.day != nil) != !trip.itemIDs.isEmpty) else { throw RecoveryError.queryOnly }
        try travel.validate(original)
        guard isSameBinding(binding),bindingIsCurrent,isSameBinding(binding),scopedChoices.revision==captured.revision else { throw RecoveryError.inactive }
        return try (entry,trip,MessageEditNamespace(id:namespace.value.id,expectedVersion:Int64(namespace.value.version)),needs,captured.intent)
    }
    private var currentChoiceRevision:UUID { binding?.scopedEdits == true ? scopedChoices.revision : discussionRevision }
    public func captureNewConversationIntent(for presentation:ScopedMessagePresentation) -> DiscussionConversationIntent? {
        guard ownsScopedPresentation(presentation) else { return nil }
        let result=captureNewConversationIntent()
        guard ownsScopedPresentation(presentation),result?.choice==presentation.revision,result?.generation==presentation.generation else { return nil }
        return result
    }
    public func captureNewConversationIntent() -> DiscussionConversationIntent? {
        guard supportsTripMessages,!isBusy,creationIntent == .none,
              selectedConversationID != nil || shell.draft.isEmpty,let binding else { return nil }
        do {
            if binding.scopedEdits { guard scopedPresentation?.trip != nil else { return nil } }
            else { _=try capturedDiscussion() }
            guard try !binding.recovery.conversationOpenings(lease:binding.lease).contains(where:{ $0.phase == .queryRequired }),
                  isSameBinding(binding),bindingIsCurrent,isSameBinding(binding) else { return nil }
            return conversationIntent(.create)
        } catch { return nil }
    }
    public func captureConversationQuery(id:String) -> DiscussionConversationIntent? {
        guard supportsTripMessages,!isBusy,conversationOpenings.contains(where:{ Data($0.conversationID.utf8)==Data(id.utf8) }) else { return nil }
        return conversationIntent(.query(id))
    }
    public func captureConversationSelection(id:String) -> DiscussionConversationIntent? {
        guard supportsTripMessages,!isBusy else { return nil }
        let known:Bool
        if case .available(let current)=storedConversationState,Data(current.utf8)==Data(id.utf8) { known=true }
        else { known=conversationOpenings.contains(where:{ $0.phase == .available && Data($0.conversationID.utf8)==Data(id.utf8) }) }
        return known ? conversationIntent(.select(id)) : nil
    }
    private func conversationIntent(_ kind:DiscussionConversationIntent.Kind) -> DiscussionConversationIntent {
        .init(kind:kind,owner:conversationIntentOwner,generation:shell.generation,choice:currentChoiceRevision,selection:runSelectionRevision,draft:shell.draftRevision)
    }
    private func currentConversationIntent(_ value:DiscussionConversationIntent) -> Bool {
        value.owner==conversationIntentOwner && value.generation==shell.generation && value.choice==currentChoiceRevision &&
        value.selection==runSelectionRevision && value.draft==shell.draftRevision
    }
    /// The rendered choice is pinned before a Task. New chats begin with an
    /// empty draft; text from an earlier conversation stays under its old ID.
    public func performConversationIntent(_ intent:DiscussionConversationIntent) {
        guard currentConversationIntent(intent),supportsTripMessages,!isBusy,currentConversationIntent(intent),let binding,let client=binding.sendClient else { return }
        if case .select(let id)=intent.kind { _=selectConversationForSending(id);return }
        do {
            let work:DiscussionConversationWork,creating:Bool
            switch intent.kind {
            case .create:
                guard captureNewConversationIntent() != nil,currentConversationIntent(intent) else { return }
                if let previous=selectedConversationID { try binding.recovery.saveDraft(Data(shell.draft.utf8),conversationID:previous,lease:binding.lease) }
                guard currentConversationIntent(intent),isSameBinding(binding),bindingIsCurrent,isSameBinding(binding) else { return }
                work=try binding.scopedEdits ? client.prepareNewTripEditConversation(lease:binding.lease) : client.prepareNewDiscussionConversation(lease:binding.lease);creating=true
            case .query(let id):work=try binding.scopedEdits ? client.prepareTripEditConversationQuery(id:id,lease:binding.lease) : client.prepareDiscussionConversationQuery(id:id,lease:binding.lease);creating=false
            case .select:return
            }
            guard currentConversationIntent(intent),isSameBinding(binding),bindingIsCurrent,isSameBinding(binding) else { return }
            if creating {
                retireRunSelection();selectedConversationID=work.conversationID;selectedMessageID=nil;record=nil
                shell.draft="";storedDraftBytes=Data()
            }
            projection=try binding.recovery.localProjection(scope:binding.scope,lease:binding.lease)
            let token=UUID();conversationTask=token;storedConversationState = .working(work.conversationID)
            activity=creating ? .preparing : .querying
            task=Task { [weak self] in
                do {
                    let outcome=try await client.performDiscussionConversation(work)
                    guard let self,self.conversationTask==token,self.isSameBinding(binding),self.bindingIsCurrent,self.isSameBinding(binding),self.conversationTask==token else { return }
                    switch outcome {
                    case .available(let id):
                        self.storedConversationState = .available(id)
                    case .unknown:self.storedConversationState = .unknown(work.conversationID)
                    case .rejected(let status,_):self.storedConversationState = .rejected(work.conversationID,status)
                    }
                    guard self.conversationTask==token,self.isSameBinding(binding) else { return }
                    self.task=nil;self.activity = .ready
                    guard self.conversationTask==token,self.isSameBinding(binding),self.bindingIsCurrent,self.isSameBinding(binding),self.conversationTask==token else { return }
                    if creating,case .available(let id)=outcome { _=self.selectConversationForSending(id) }
                } catch {
                    guard let self,self.conversationTask==token,self.isSameBinding(binding) else { return }
                    guard self.bindingIsCurrent else { self.blockStorage(for:binding);return }
                    guard self.isSameBinding(binding),self.conversationTask==token else { return }
                    self.storedConversationState = .unknown(work.conversationID)
                    guard self.isSameBinding(binding),self.conversationTask==token else { return }
                    self.task=nil;self.activity = .ready
                }
            }
        } catch { blockStorage(for:binding) }
    }
    public var tripDiscussionChoice:TripDiscussionChoiceDisplay {
        guard supportsTripDiscussions else { return .unavailable }
        guard discussionChoiceMade else { return .unselected }
        do {
            let choice=try capturedDiscussion()
            if let choice,let entry=discussionEntry { return .trip(title:entry.title,selection:choice) }
            return .none
        } catch { return .unavailable }
    }
    private func capturedDiscussion() throws -> MessageTripSelection? {
        let revision=discussionRevision
        guard bindingIsCurrent,let binding,binding.tripDiscussions,discussionChoiceMade else { throw RecoveryError.queryOnly }
        let entry=discussionEntry
        try entry?.validate(scopeEnvironment:binding.scope.environment,scopeAccount:binding.scope.account,generation:binding.generation)
        guard revision==discussionRevision,isSameBinding(binding),bindingIsCurrent,isSameBinding(binding),revision==discussionRevision else { throw RecoveryError.inactive }
        return entry?.selection
    }
    @discardableResult public func selectTripDiscussion(_ entry:TripDiscussionEntry) -> Bool {
        if binding?.scopedEdits == true { return selectScopedTrip(entry) }
        let revision=discussionRevision
        guard supportsTripDiscussions,!isBusy,let binding else { return false }
        do {
            try entry.validate(scopeEnvironment:binding.scope.environment,scopeAccount:binding.scope.account,generation:binding.generation)
            guard isSameBinding(binding),bindingIsCurrent,isSameBinding(binding),!isBusy,revision==discussionRevision else { return false }
            discussionEntry=entry;discussionChoiceMade=true;discussionRevision=UUID()
            retireRunSelection();return true
        } catch { return false }
    }
    @discardableResult public func selectUnboundDiscussion() -> Bool {
        let revision=discussionRevision
        guard supportsTripDiscussions,!isBusy,revision==discussionRevision else { return false }
        discussionEntry=nil;discussionChoiceMade=true;discussionRevision=UUID()
        retireRunSelection();return true
    }
    public var visibleOriginalText: String? {
        guard let record = visibleRecord,
              let value = try? JSONSerialization.jsonObject(with: record.originalUTF8) as? [String: Any] else { return nil }
        return value["text"] as? String
    }
    public var visibleProjection: LocalRecoveryProjection? {
        guard bindingIsCurrent, let binding, let projection,
              (try? binding.recovery.validateProjection(projection, scope: binding.scope, lease: binding.lease)) != nil else { return nil }
        return projection
    }
    public var canSelectLocalItem: Bool { bindingIsCurrent && !isBusy }

    public var visibleRecord: ActionRecord? { bindingIsCurrent ? record : nil }
    public var isSynthetic: Bool { bindingIsCurrent && binding?.synthetic == true }
    public var isConfigured: Bool { bindingIsCurrent }
    public var canSaveDraft: Bool { bindingIsCurrent && selectedConversationID != nil && !isBusy && activity != .storageBlocked }
    public var canQuery: Bool {
        guard bindingIsCurrent, binding?.queryOriginal != nil || binding?.sendClient != nil, !isBusy,
              let record else { return false }
        return record.phase == .queryRequired || record.phase == .notObserved
    }
    public var canStartMessage: Bool {
        guard bindingIsCurrent, !isBusy, let binding, let client = binding.sendClient,
              let conversation = selectedConversationID else { return false }
        if binding.scopedEdits {
            do {
                _=try capturedScopedMessage()
                guard creationIntent == .none else { return false }
                return try client.canStartTripEdit(conversationID:conversation,lease:binding.lease)
            } catch { return false }
        }
        if binding.tripDiscussions {
            do { _=try capturedDiscussion();guard creationIntent == .none else { return false }
                return try client.canStartTripDiscussion(conversationID:conversation,lease:binding.lease)
            } catch { return false }
        }
        if let travel = binding.travelSelection {
            guard (try? travel.capture()) != nil,creationIntent == .none || binding.currentNeeds?() != nil else { return false }
            return (try? client.canStartTravelSend(conversationID:conversation,lease:binding.lease)) == true
        }
        return (try? client.canStartSend(conversationID: conversation, lease: binding.lease)) == true
    }
    public var canSend: Bool { canStartMessage && !shell.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    public var canResubmit: Bool {
        guard bindingIsCurrent, !isBusy, let binding, let client = binding.sendClient,
              let record, record.phase == .notObserved,
              let cid = try? originalConversation(record), selectedConversationID.map({ Data($0.utf8) == Data(cid.utf8) }) == true else { return false }
        switch try? client.originalSendVersion(messageID:record.messageID,lease:binding.lease) {
        case .scopedEdit:
            return binding.scopedEdits && (try? client.tripEditDecision(messageID:record.messageID,lease:binding.lease)) == .resubmitOriginal
        case .tripDiscussion:
            return binding.tripDiscussions && (try? client.tripDiscussionDecision(messageID:record.messageID,lease:binding.lease)) == .resubmitOriginal
        case .travel:
            return !binding.scopedEdits && binding.travelSelection != nil && (try? client.travelSendDecision(messageID:record.messageID,lease:binding.lease)) == .resubmitOriginal
        case .legacy:
            return !binding.tripDiscussions && binding.travelSelection == nil && (try? client.sendDecision(messageID:record.messageID,lease:binding.lease)) == .resubmitOriginal
        case .historicalDraft,nil:return false
        }
    }

    public init(shell: ShellState) {
        self.shell = shell
        shell.messageHost?.invalidate()
        shell.messageHost = self
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }

    /// Once per UI generation. Rebinding cannot erase ambiguity within an identity lifetime.
    @discardableResult public func bind(_ value: AssistantMessageBinding) -> Bool {
        guard !shell.messageBindingBlocked, value.generation == shell.generation, usedGeneration != value.generation,
              !value.tripDiscussions || (value.travelSelection == nil && value.currentNeeds == nil),
              !value.scopedEdits || (!value.tripDiscussions && value.travelSelection != nil && value.currentNeeds != nil),
              value.isCurrent(), value.conversationID?.isEmpty != true else { return false }
        // isCurrent is injected and may synchronously reenter with a newer account.
        guard !shell.messageBindingBlocked, value.generation == shell.generation,
              usedGeneration != value.generation else { return false }
        usedGeneration = value.generation
        do {
            try value.recovery.validateScope(value.scope, lease: value.lease)
            let draft = try value.conversationID.flatMap { try value.recovery.draft(conversationID: $0, lease: value.lease) }
            let restored = try value.messageID.flatMap { try value.recovery.action(messageID: $0, lease: value.lease) }
            retireRunSelection()
            binding = value
            projection = try value.recovery.localProjection(scope: value.scope, lease: value.lease)
            selectedConversationID = value.conversationID
            selectedMessageID = value.messageID
            runSelectionAllowed = value.messageID != nil
            if let draft {
                guard let text = String(data: draft, encoding: .utf8) else { throw RecoveryError.invalidInput }
                shell.draft = text
            }
            record = restored
            activity = .ready
            return true
        } catch {
            guard value.generation == shell.generation, usedGeneration == value.generation,
                  binding == nil || isSameBinding(value) else { return false }
            // A rejected/unacquired lease cannot authorize invalidating that resource.
            binding = nil; record = nil; projection = nil; activity = .storageBlocked
            return false
        }
    }

    @discardableResult public func selectAction(_ reference: LocalActionReference, from captured: LocalRecoveryProjection) -> Bool {
        guard canSelectLocalItem, let binding else { return false }
        do {
            try binding.recovery.validateProjection(captured, scope: binding.scope, lease: binding.lease)
            guard captured.actions.contains(where: { Data($0.messageID.utf8) == Data(reference.messageID.utf8) }),
                  let action = try binding.recovery.action(messageID: reference.messageID, lease: binding.lease) else { return false }
            retireRunSelection()
            selectedMessageID = reference.messageID
            runSelectionAllowed = true
            record = action
            projection = try binding.recovery.localProjection(scope: binding.scope, lease: binding.lease)
            activity = .ready
            return true
        } catch { return false } // stale selection is rejected without invalidating a newer binding
    }

    /// Explicit replacement confirmed by the view; no preview/body appears in the list.
    @discardableResult public func selectDraft(_ reference: LocalDraftReference, from captured: LocalRecoveryProjection) -> Bool {
        guard canSelectLocalItem, let binding else { return false }
        do {
            try binding.recovery.validateProjection(captured, scope: binding.scope, lease: binding.lease)
            guard captured.drafts.contains(where: { Data($0.conversationID.utf8) == Data(reference.conversationID.utf8) }),
                  let bytes = try binding.recovery.draft(conversationID: reference.conversationID, lease: binding.lease),
                  let text = String(data: bytes, encoding: .utf8) else { return false }
            retireRunSelection()
            selectedConversationID = reference.conversationID
            shell.draft = text
            storedDraftBytes = bytes
            return true
        } catch { return false }
    }

    private func retireRunSelection() {
        conversationTask=UUID()
        runSelectionRevision = UUID(); runSelectionAllowed = false
        shell.runContainerHost?.retireSelection()
        shell.originalUsageContainerHost?.retireSelection()
    }
    public func captureAcceptedUsageInput() -> AcceptedMessageUsageInput? {
        let revision = runSelectionRevision
        guard let originalBinding = binding, runSelectionAllowed, let id = selectedMessageID,
              bindingIsCurrent, isSameBinding(originalBinding), revision == runSelectionRevision,
              let record = try? originalBinding.recovery.action(messageID: id, lease: originalBinding.lease),
              record.phase == .accepted, record.receipt != nil,
              ownsRunReceipt(record, binding: originalBinding, revision: revision) else { return nil }
        return AcceptedMessageUsageInput(binding: originalBinding, record: record, isCurrent: { [weak self] in
            self?.ownsRunReceipt(record, binding: originalBinding, revision: revision) == true
        }, isStillOwned: { [weak self] in
            self?.ownsRunReceiptWithoutCallbacks(record, binding: originalBinding, revision: revision) == true
        })
    }
    /// Decode the exact typed payload encoded by MessageHTTPClient only after its
    /// accepted recovery state, original bytes/hash, lease and current selection agree.
    public func captureAcceptedRunReceipt() -> AcceptedMessageRunReceipt? {
        let revision = runSelectionRevision
        guard let originalBinding = binding,runSelectionAllowed,let id = selectedMessageID,
              bindingIsCurrent,isSameBinding(originalBinding),revision == runSelectionRevision,
              let record = try? originalBinding.recovery.action(messageID:id,lease:originalBinding.lease),record.phase == .accepted,
              let bytes = record.receipt,ownsRunReceipt(record,binding:originalBinding,revision:revision) else { return nil }
        let receipt: Components.Schemas.MessageReceipt
        let reference: Components.Schemas.MessageTravelReference?
        let tripReference:MessageTripReference?
        let editReference:MessageEditReference?
        do {
            if let client=originalBinding.sendClient,try client.originalSendVersion(messageID:id,lease:originalBinding.lease) == .scopedEdit {
                let accepted=try client.acceptedTripEdit(messageID:id,lease:originalBinding.lease)
                receipt=accepted.receipt;reference=nil;tripReference=nil;editReference=accepted.reference
            } else if let client=originalBinding.sendClient,try client.originalSendVersion(messageID:id,lease:originalBinding.lease) == .tripDiscussion {
                let accepted=try client.acceptedTripDiscussion(messageID:id,lease:originalBinding.lease)
                receipt=accepted.receipt;reference=nil;tripReference=accepted.reference;editReference=nil
            } else if let client = originalBinding.sendClient,try client.originalSendVersion(messageID:id,lease:originalBinding.lease) == .travel {
                let accepted = try client.acceptedTravelMessage(messageID:id,lease:originalBinding.lease)
                try client.validateRead(accepted,lease:originalBinding.lease)
                receipt = accepted.value.receipt;reference = accepted.value.reference;tripReference=nil;editReference=nil
            } else {
                receipt = try JSONDecoder().decode(Components.Schemas.MessageReceipt.self,from:bytes);reference = nil;tripReference=nil;editReference=nil
            }
            guard Data(receipt.message_id.utf8) == Data(record.messageID.utf8),receipt.input_sha256 == record.inputSHA256,
                  ownsRunReceipt(record,binding:originalBinding,revision:revision) else { return nil }
        } catch { return nil }
        // Legacy receipt readers remain available when text is absent. New
        // extraction consumers require these original decoded text bytes; they
        // never take source text from a mutable composer or later message.
        let originalText = (try? JSONSerialization.jsonObject(with: record.originalUTF8) as? [String: Any])?["text"] as? String
        return AcceptedMessageRunReceipt(receipt: receipt,travelReference:reference,tripReference:tripReference,editReference:editReference,
            originalTextUTF8:originalText.map { Data($0.utf8) }, isCurrent: { [weak self] in
            self?.ownsRunReceipt(record, binding: originalBinding, revision: revision) == true
        }, isStillOwned: { [weak self] in
            self?.ownsRunReceiptWithoutCallbacks(record, binding: originalBinding, revision: revision) == true
        })
    }
    private func ownsRunReceipt(_ original: ActionRecord, binding: AssistantMessageBinding, revision: UUID) -> Bool {
        guard ownsRunReceiptWithoutCallbacks(original, binding: binding, revision: revision),
              bindingIsCurrent else { return false }
        return ownsRunReceiptWithoutCallbacks(original, binding: binding, revision: revision)
    }
    /// Canonical in-memory lease/record reads only: safe after the last trusted callback.
    /// This establishes original ownership, not admission or server authorization.
    private func ownsRunReceiptWithoutCallbacks(_ original: ActionRecord, binding: AssistantMessageBinding, revision: UUID) -> Bool {
        guard !shell.messageBindingBlocked, isSameBinding(binding), revision == runSelectionRevision, runSelectionAllowed,
              selectedMessageID.map({ Data($0.utf8) == Data(original.messageID.utf8) }) == true,
              (try? binding.recovery.validateScope(binding.scope, lease: binding.lease)) != nil,
              let current = try? binding.recovery.action(messageID: original.messageID, lease: binding.lease) else { return false }
        return current == original && current.phase == .accepted
    }

    private func isSameBinding(_ original: AssistantMessageBinding) -> Bool {
        guard let current = binding else { return false }
        return current.recovery === original.recovery && current.lease == original.lease
            && current.generation == original.generation && shell.generation == original.generation
    }

    private var bindingIsCurrent: Bool {
        guard !shell.messageBindingBlocked, let binding, binding.generation == shell.generation, binding.isCurrent() else { return false }
        return (try? binding.recovery.validateScope(binding.scope, lease: binding.lease)) != nil
            && isSameBinding(binding) && !shell.messageBindingBlocked
    }

    public func saveDraft() {
        guard canSaveDraft, let binding, let selectedConversationID else { return }
        let originalBytes = Data(shell.draft.utf8)
        do {
            try binding.recovery.saveDraft(originalBytes, conversationID: selectedConversationID, lease: binding.lease)
            guard isSameBinding(binding) else { return }
            guard bindingIsCurrent else { blockStorage(for: binding); return }
            guard isSameBinding(binding) else { return }
            storedDraftBytes = originalBytes
            projection = try binding.recovery.localProjection(scope: binding.scope, lease: binding.lease)
        } catch { blockStorage(for: binding) }
    }

    public func queryOriginal() {
        guard canQuery, let binding, let messageID = selectedMessageID else { return }
        retireRunSelection()
        activity = .querying
        task = Task { [weak self] in
            do {
                if let client = binding.sendClient {
                    switch try client.originalSendVersion(messageID:messageID,lease:binding.lease) {
                    case .scopedEdit:_ = try await client.reconcileTripEdit(messageID:messageID,lease:binding.lease)
                    case .tripDiscussion:_ = try await client.reconcileTripDiscussion(messageID:messageID,lease:binding.lease)
                    case .legacy:_ = try await client.reconcileSend(messageID:messageID,lease:binding.lease)
                    case .travel:_ = try await client.reconcileTravelSend(messageID:messageID,lease:binding.lease)
                    case .historicalDraft:throw RecoveryError.queryOnly
                    }
                }
                else if let query = binding.queryOriginal { try await query(messageID, binding.lease) }
                guard let self, self.isSameBinding(binding) else { return }
                guard self.bindingIsCurrent else { self.blockStorage(for: binding); return }
                guard self.isSameBinding(binding) else { return }
                self.record = try binding.recovery.action(messageID: messageID, lease: binding.lease)
                self.runSelectionAllowed = true
                self.projection = try binding.recovery.localProjection(scope: binding.scope, lease: binding.lease)
                self.activity = .ready
                self.task = nil
            } catch {
                guard let self, self.isSameBinding(binding) else { return }
                let current = self.bindingIsCurrent
                guard self.isSameBinding(binding) else { return }
                if current { self.activity = .unknown; self.task = nil }
                else { self.blockStorage(for: binding) }
            }
        }
    }

    @discardableResult public func selectConversationForSending(_ conversationID: String) -> Bool {
        guard bindingIsCurrent, !isBusy, let binding, let client = binding.sendClient,
              !conversationID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              conversationID.utf8.count <= 256, !conversationID.utf8.contains(0) else { return false }
        do {
            let previous = selectedConversationID
            if let previous {
                try binding.recovery.saveDraft(Data(shell.draft.utf8), conversationID: previous, lease: binding.lease)
            }
            guard isSameBinding(binding), bindingIsCurrent, isSameBinding(binding) else { return false }
            retireRunSelection()
            selectedConversationID = conversationID; selectedMessageID = nil; record = nil
            let draft = try binding.recovery.draft(conversationID: conversationID, lease: binding.lease)
            if previous != nil || shell.draft.isEmpty {
                guard let text = String(data: draft ?? Data(), encoding: .utf8) else { throw RecoveryError.invalidSnapshot }
                shell.draft = text
            }
            storedDraftBytes = draft
            let currentProjection = try binding.recovery.localProjection(scope: binding.scope, lease: binding.lease)
            projection = currentProjection
            for reference in currentProjection.actions.sorted(by: { Data($0.messageID.utf8).lexicographicallyPrecedes(Data($1.messageID.utf8)) })
                where reference.phase != .accepted && reference.phase != .notAccepted {
                guard let pending = try binding.recovery.action(messageID: reference.messageID, lease: binding.lease) else { throw RecoveryError.staleOperation }
                if Data(try originalConversation(pending).utf8) == Data(conversationID.utf8) {
                    selectedMessageID = pending.messageID; record = pending; break
                }
            }
            let revision = runSelectionRevision
            let needsHead = record == nil
            activity = .preparing
            task = Task { [weak self] in
                do {
                    if needsHead {
                        if binding.scopedEdits { _ = try await client.readTripEditHead(conversationID:conversationID,lease:binding.lease) }
                        else if binding.tripDiscussions { _ = try await client.readTripDiscussionHead(conversationID:conversationID,lease:binding.lease) }
                        else if binding.travelSelection != nil { _ = try await client.readTravelSendHead(conversationID:conversationID,lease:binding.lease) }
                        else { _ = try await client.readSendHead(conversationID:conversationID,lease:binding.lease) }
                    }
                    guard let self, self.isSameBinding(binding), self.runSelectionRevision == revision else { return }
                    guard self.bindingIsCurrent else { self.blockStorage(for: binding); return }
                    if (binding.tripDiscussions || binding.scopedEdits) && needsHead { self.storedDiscussionRefusal=nil }
                    self.activity = .ready; self.task = nil
                    self.saveDraft()
                } catch {
                    if binding.tripDiscussions || binding.scopedEdits,case MessageReadFailure.rejected(let status,let error)=error {
                        self?.recordDiscussionRefusal(status:status,code:error.error.code,binding:binding,revision:revision)
                    }
                    self?.sendFailed(binding, revision: revision)
                }
            }
            return true
        } catch { blockStorage(for: binding); return false }
    }

    public func sendNew() {
        guard canSend, let binding, let client = binding.sendClient, let conversation = selectedConversationID else { return }
        let text = shell.draft, editorRevision = shell.draftRevision
        retireRunSelection()
        let revision = runSelectionRevision
        activity = .sending
        do {
            let original: ActionRecord
            let travelWire = binding.travelSelection != nil
            if binding.scopedEdits {
                let selected=try capturedScopedMessage()
                guard isSameBinding(binding),bindingIsCurrent,isSameBinding(binding),creationIntent == .none else { return }
                original=try client.stageTripEdit(messageID:UUID().uuidString,conversationID:conversation,text:text,
                    intent:selected.intent,trip:selected.trip,namespace:selected.namespace,needs:selected.needs,content:selected.entry.content,lease:binding.lease)
            } else if binding.tripDiscussions {
                let choice=try capturedDiscussion()
                guard isSameBinding(binding),bindingIsCurrent,isSameBinding(binding),creationIntent == .none else { return }
                original=try client.stageTripDiscussion(messageID:UUID().uuidString,conversationID:conversation,text:text,trip:choice,content:discussionEntry?.content,lease:binding.lease)
            } else if let travel = binding.travelSelection {
                let selection = try travel.capture()
                let needs = creationIntent == .none ? nil : binding.currentNeeds?()
                try travel.validate(selection)
                guard isSameBinding(binding),bindingIsCurrent,isSameBinding(binding) else { return }
                original = try client.stageTravelSend(messageID:UUID().uuidString,conversationID:conversation,text:text,
                    creationIntent:creationIntent,travelContext:selection.context,needsReference:needs,lease:binding.lease)
            } else {
                original = try client.stageSend(messageID:UUID().uuidString,conversationID:conversation,text:text,creationIntent:creationIntent,lease:binding.lease)
            }
            guard isSameBinding(binding), bindingIsCurrent, isSameBinding(binding) else { return }
            record = original; selectedMessageID = original.messageID
            projection = try binding.recovery.localProjection(scope: binding.scope, lease: binding.lease)
            task = Task { [weak self] in
                do {
                    if binding.scopedEdits {
                        let outcome=try await client.submitPreparedTripEdit(messageID:original.messageID,lease:binding.lease)
                        if case .rejected(let status,let error)=outcome {
                            self?.recordDiscussionRefusal(status:status,code:error.error.code,binding:binding,revision:revision,
                                definiteFailure:error.error.outcome == .failed && error.error.recovery == .do_not_retry && error.error.code != "INPUT_CONFLICT")
                        }
                    } else if binding.tripDiscussions {
                        let outcome=try await client.submitPreparedTripDiscussion(messageID:original.messageID,lease:binding.lease)
                        if case .rejected(let status,let error)=outcome { self?.recordDiscussionRefusal(status:status,code:error.error.code,binding:binding,revision:revision) }
                    } else if travelWire { _ = try await client.submitPreparedTravelSend(messageID:original.messageID,lease:binding.lease) }
                    else { _ = try await client.submitPrepared(messageID:original.messageID,lease:binding.lease) }
                    try self?.sendFinished(binding, messageID: original.messageID, revision: revision,
                                          clearEditorRevision: editorRevision)
                } catch { self?.sendFailed(binding, revision: revision) }
            }
        } catch RecoveryError.invalidInput {
            guard isSameBinding(binding), runSelectionRevision == revision else { return }
            guard bindingIsCurrent else { blockStorage(for: binding); return }
            guard isSameBinding(binding), runSelectionRevision == revision else { return }
            activity = .inputRejected; task = nil; saveDraft()
        } catch { sendFailed(binding, revision: revision) }
    }

    public func captureResubmission() -> MessageResubmissionContext? {
        guard canResubmit,let binding,let client = binding.sendClient,let record else { return nil }
        do {
            let wire = try client.originalSendVersion(messageID:record.messageID,lease:binding.lease)
            let confirmation = try wire == .scopedEdit ? client.requiresTripEditResubmissionConfirmation(messageID:record.messageID,lease:binding.lease)
                : wire == .tripDiscussion ? client.requiresTripDiscussionResubmissionConfirmation(messageID:record.messageID,lease:binding.lease)
                : wire == .travel ? client.requiresTravelResubmissionConfirmation(messageID:record.messageID,lease:binding.lease)
                : client.requiresResubmissionConfirmation(messageID:record.messageID,lease:binding.lease)
            return MessageResubmissionContext(requiresConfirmation:confirmation,binding:binding,messageID:record.messageID,revision:runSelectionRevision,wire:wire)
        } catch { return nil }
    }

    public func resubmitOriginal(_ context: MessageResubmissionContext, confirmed: Bool) {
        guard canResubmit, isSameBinding(context.binding), runSelectionRevision == context.revision,
              selectedMessageID.map({ Data($0.utf8) == Data(context.messageID.utf8) }) == true,
              !context.requiresConfirmation || confirmed, let client = context.binding.sendClient else { return }
        let binding = context.binding
        retireRunSelection(); let revision = runSelectionRevision
        activity = .sending
        task = Task { [weak self] in
            do {
                switch context.wire {
                case .scopedEdit:_ = try await client.submitPreparedTripEdit(messageID:context.messageID,lease:binding.lease,confirmRestored:confirmed)
                case .tripDiscussion:_ = try await client.submitPreparedTripDiscussion(messageID:context.messageID,lease:binding.lease,confirmRestored:confirmed)
                case .legacy:_ = try await client.submitPrepared(messageID:context.messageID,lease:binding.lease,confirmRestored:confirmed)
                case .travel:_ = try await client.submitPreparedTravelSend(messageID:context.messageID,lease:binding.lease,confirmRestored:confirmed)
                case .historicalDraft:throw RecoveryError.queryOnly
                }
                try self?.sendFinished(binding, messageID: context.messageID, revision: revision)
            } catch { self?.sendFailed(binding, revision: revision) }
        }
    }

    private func sendFinished(_ original: AssistantMessageBinding, messageID: String, revision: UUID,
                              clearEditorRevision: UUID? = nil) throws {
        guard isSameBinding(original), runSelectionRevision == revision else { return }
        guard bindingIsCurrent else { blockStorage(for: original); return }
        guard isSameBinding(original), runSelectionRevision == revision else { return }
        record = try original.recovery.action(messageID: messageID, lease: original.lease)
        if original.tripDiscussions || original.scopedEdits,record?.phase == .accepted { storedDiscussionRefusal=nil }
        if record?.phase == .accepted, let clearEditorRevision, shell.draftRevision == clearEditorRevision,
           let conversation = selectedConversationID {
            try original.recovery.saveDraft(Data(), conversationID: conversation, lease: original.lease)
            guard isSameBinding(original), bindingIsCurrent, isSameBinding(original), runSelectionRevision == revision else { return }
            if shell.draftRevision == clearEditorRevision { shell.draft = ""; storedDraftBytes = Data() }
        }
        projection = try original.recovery.localProjection(scope: original.scope, lease: original.lease)
        runSelectionAllowed = record?.phase == .accepted
        activity = record?.phase == .queryRequired ? .unknown : .ready; task = nil
        saveDraft()
    }

    private func sendFailed(_ original: AssistantMessageBinding, revision: UUID) {
        guard isSameBinding(original), runSelectionRevision == revision else { return }
        let current = bindingIsCurrent
        guard isSameBinding(original), runSelectionRevision == revision else { return }
        guard current else { blockStorage(for: original); return }
        if let selectedMessageID { record = try? original.recovery.action(messageID: selectedMessageID, lease: original.lease) }
        activity = .unknown; task = nil
        saveDraft()
    }
    private func recordDiscussionRefusal(status:Int,code:String,binding:AssistantMessageBinding,revision:UUID,definiteFailure:Bool=false) {
        guard isSameBinding(binding),runSelectionRevision==revision,bindingIsCurrent,isSameBinding(binding),runSelectionRevision==revision else { return }
        storedDiscussionRefusal=MessageDiscussionRefusal(status:status,code:code,definiteFailure:definiteFailure)
    }

    private func originalConversation(_ record: ActionRecord) throws -> String {
        guard let value = try JSONSerialization.jsonObject(with: record.originalUTF8) as? [String: Any],
              let cid = value["conversation_id"] as? String, !cid.isEmpty else { throw RecoveryError.invalidSnapshot }
        return cid
    }

    /// Called synchronously by ShellState BEFORE its identity generation/clear changes.
    public func invalidate() { retire(as: .invalidated) }

    private func retire(as nextActivity: MessageHostActivity) {
        let previous = binding
        binding = nil; record = nil; projection = nil; storedDraftBytes = nil
        selectedConversationID = nil; selectedMessageID = nil
        discussionEntry=nil;discussionChoiceMade=false;discussionRevision=UUID();storedDiscussionRefusal=nil
        scopedChoices=ScopedMessageChoices()
        conversationTask=UUID();storedConversationState = .idle
        creationIntent = .none
        retireRunSelection()
        task?.cancel(); task = nil
        activity = nextActivity
        // Detach before invoking an external callback; never mutate a replacement afterward.
        previous?.recovery.invalidate()
        previous?.invalidateResources()
    }
    private func blockStorage(for original: AssistantMessageBinding) {
        guard isSameBinding(original) else { return }
        retire(as: .storageBlocked)
    }
}
