#if DEBUG && targetEnvironment(simulator)
import Foundation
import Darwin
import CJShell
import CJTripClient
import CJManualPreviewClient
import CJMessageHTTP
import CJMessageClient
import CJRunClient
import CJOfflineTrip
import CJMemoryClient
import CJNeedsClient
import CJFeedbackClient
import CJCleanupClient
import CJMessageKeyBridge
import CJMessageKeys
import CJSession
import CJAPI
import HTTPTypes
import OpenAPIRuntime
import Observation

@MainActor struct DevelopmentSessionLease {
    let session: SessionLifecycle
    let operation: SessionOperation
}

@MainActor private final class DevelopmentSessionPersistence: SessionPersistence {
    private var material: SessionMaterial?
    func load() throws -> SessionMaterial? { material }
    func save(_ material: SessionMaterial) throws { self.material = material }
    func clearAndBlock() throws { material = nil }
}

@MainActor private final class DevelopmentLifetime {
    var active = true
    let session: SessionLifecycle
    let operation: SessionOperation
    let trip: TripBinding
    let shell: ShellState
    let generation: ShellGeneration
    let ownsSession: Bool
    init(configuration: DevelopmentSessionConfiguration, shell: ShellState, lease: DevelopmentSessionLease?) throws {
        self.shell = shell; generation = shell.generation
        ownsSession = lease == nil
        if let lease {
            guard lease.session.isCurrent(lease.operation) else { throw SessionFailure.staleOperation }
            session = lease.session; operation = lease.operation
        } else {
            session = SessionLifecycle(persistence: DevelopmentSessionPersistence(), restorePolicy: .userInitiatedOnly)
            operation = try session.beginTrustedSDKSave()
            try session.save(SessionMaterial(trustedSDKBytes: Data(configuration.token.utf8)), for: operation)
        }
        trip = TripBinding(environment: configuration.environmentID, account: configuration.accountID,
                           generation: UUID(), selection: UUID())
    }
    var current: TripBinding? {
        active && session.isCurrent(operation) && shell.generation == generation ? trip : nil
    }
}

/// Only this explicitly configured DEBUG simulator root grants TripLiveWrites.
/// It uses the signed app_from_environment local fixture, never a production host.
@MainActor final class DevelopmentTripHost {
    let id = UUID()
    let trips: TripContainerHost
    let messages: DevelopmentMessageHost
    let memory: DevelopmentMemoryHost?
    let typedMemory: DevelopmentTypedMemoryHost?
    let needs: DevelopmentNeedsHost?
    let structuredTrips: StructuredTripHost?
    let feedback: DevelopmentFeedbackHost?
    let memoryHistory: DevelopmentMemoryHistoryHost?
    private let lifetime: DevelopmentLifetime
    private let keys: ScopedMessageKeyProvider

    init(configuration: DevelopmentSessionConfiguration, shell: ShellState, lease: DevelopmentSessionLease? = nil, offline: OfflineTripController? = nil) throws {
        let environment = ProcessInfo.processInfo.environment
        let historyProfile = try DevelopmentMemoryHistoryProfile.read(environment)
        guard historyProfile == nil || lease != nil else { throw MemoryFailure.unconfigured }
        let feedbackProfile = try DevelopmentFeedbackProfile.read(environment)
        let messageProfile=try DevelopmentMessageProfile.read(environment)
        let typedMode = try DevelopmentTypedMode.read(environment,messageProfile:messageProfile)
        let needsProfile = try DevelopmentNeedsProfile.read(environment)
        let tripEditingProfile = try DevelopmentTripEditingProfile.read(environment)
        let tripDiscussions=messageProfile == .discussion,scopedEdits=messageProfile == .edit || messageProfile == .editResults
        let scopedResults=messageProfile == .editResults
        let needsPlanning=messageProfile == .planning
        let travelProfile=try needsPlanning ? DevelopmentTravelProfile.read(environment) : typedMode?.travel
        let answerProfile=try DevelopmentSessionConfiguration.toolAnswerProfile(environment)
        try messageProfile?.validate(typed:typedMode,needs:needsProfile,answer:answerProfile,
            travel:travelProfile,legacyProposal:configuration.proposalID != nil)
        let endpoint = try MessageEndpoint(url: configuration.endpoint, maximumRequestBytes: tripEditingProfile == nil ? 4096 : 1_000_000,
            maximumResponseBytes: 1_000_000, allowLoopbackHTTP: true)
        let lifetime = try DevelopmentLifetime(configuration: configuration, shell: shell, lease: lease)
        self.lifetime = lifetime
        let namespace = MessageKeyNamespace(environment: lifetime.trip.environment, account: lifetime.trip.account,
                                             purpose: .localTripPendingV1)
        guard let applicationID = Bundle.main.bundleIdentifier else { throw TripFailure.unconfigured }
        keys = try ScopedMessageKeyProvider(namespace: namespace, applicationIdentifier: applicationID,
                                             protection: .whenUnlockedThisDeviceOnly)
        let files = FileManager.default
        let support = try files.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                    appropriateFor: nil, create: true)
        let directory = support.appendingPathComponent("G2CDevelopmentTrip", isDirectory: true)
            .appendingPathComponent(namespace.environment.uuidString, isDirectory: true)
            .appendingPathComponent(namespace.account.uuidString, isDirectory: true)
        try files.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let root = directory.resolvingSymlinksInPath()
        let existing = try keys.existing(expectedID: nil, for: keys.begin(.lookup))
        let key: MessageEncryptionKey
        if let existing { key = existing }
        else {
            try TripPendingStore.requireEmptyNamespace(directory: root)
            let scopedDirectories = ["ScopedOriginals","ScopedReceipts","NeedsPlanningOriginals","NeedsPlanningReceipts"].map { root.appendingPathExtension($0) }
            for path in scopedDirectories where files.fileExists(atPath: path.path) {
                guard try files.contentsOfDirectory(atPath: path.path).isEmpty else { throw TripFailure.keyUnavailable }
            }
            key = try keys.create(storageState: .confirmedEmpty, for: keys.begin(.create))
        }
        let store = try TripPendingStore(directory: root, maximumBytes: 1_000_000, maximumRecords: 100,
            binding: lifetime.trip, expectedKeyID: key.id, provider: keys)
        let transport = try NoRedirectTransport(requestTimeout: 10, resourceTimeout: 20)
        let credentials: TripCredentialCallback = { binding in
            guard lifetime.current == binding else { return nil }
            return configuration.token
        }
        let client: TripClient
        if tripEditingProfile != nil {
            client = try TripClient(developmentManual: endpoint, credentials: credentials, currentBinding: { lifetime.current },
                session: lifetime.session, sessionOperation: lifetime.operation, pendingStore: store,
                requestTimeout: 10, resourceTimeout: 20, maximumJournalBytes: 4_000_000, maximumJournalRecords: 100)
        } else {
            client = TripClient(endpoint: endpoint, credentials: credentials, currentBinding: { lifetime.current },
                session: lifetime.session, sessionOperation: lifetime.operation, pendingStore: store, liveTransport: transport, liveWrites: TripLiveWrites())
        }
        trips = TripContainerHost(shell: shell)
        guard trips.bind(TripContainerBinding(client: client, trip: lifetime.trip, shellGeneration: shell.generation,
            session: lifetime.session, sessionOperation: lifetime.operation, pageSize: 20,
            proposalID: configuration.proposalID, synthetic: false, offline: offline, currentBinding: { lifetime.current })) else {
            throw TripFailure.staleBinding
        }
        let makeNeeds = { try needsProfile.map { profile in
            try DevelopmentNeedsHost(configuration:configuration,profile:profile,shell:shell,
                session:lifetime.session,operation:lifetime.operation,isCurrent:{lifetime.current != nil})
        } }
        let messageNeeds=scopedEdits || needsPlanning
        let preparedNeeds=try messageNeeds ? makeNeeds() : nil
        let currentNeeds:(@MainActor ()->MessageNeedsSelection?)?
        if let preparedNeeds {
            currentNeeds = { [weak preparedNeeds] in
                do { return try preparedNeeds?.host.currentMessageSelection() }
                catch { return nil } // unavailable saved source; never substitute a draft/default
            }
        } else { currentNeeds=nil }
        messages = try DevelopmentMessageHost(configuration: configuration, shell: shell,
            session: lifetime.session, operation: lifetime.operation,travelProfile:travelProfile,tripDiscussions:tripDiscussions,
            scopedEdits:scopedEdits,scopedResults:scopedResults,needsPlanning:needsPlanning,currentNeeds:currentNeeds,isCurrent: { lifetime.current != nil })
        if scopedEdits {
            let originals = root.appendingPathExtension("ScopedOriginals")
            let receipts = root.appendingPathExtension("ScopedReceipts")
            for path in [originals, receipts] {
                try files.createDirectory(at: path, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            }
            let scopedEndpoint = try MessageEndpoint(url: configuration.endpoint, maximumRequestBytes: 32768,
                maximumResponseBytes: 4_000_000, allowLoopbackHTTP: true)
            let scoped = try ScopedTripClient(endpoint: scopedEndpoint, binding: lifetime.trip, credentials: { binding in
                guard lifetime.current == binding else { return nil }; return configuration.token
            }, validate: { guard lifetime.current != nil else { throw TripFailure.staleBinding } },
                directory: originals, receiptDirectory: receipts, expectedKeyID: key.id, provider: keys)
            messages.messages.configureScopedCandidates(scoped)
            if scopedResults {
                let display=try ScopedDisplayClient(endpoint:scopedEndpoint,binding:lifetime.trip,credentials:{ binding in
                    guard lifetime.current == binding else { return nil };return configuration.token
                },validate:{ guard lifetime.current != nil else { throw TripFailure.staleBinding } })
                messages.messages.configureScopedDisplays(display,runs:messages.runs)
            }
        }
        if needsPlanning {
            let originals=root.appendingPathExtension("NeedsPlanningOriginals"),receipts=root.appendingPathExtension("NeedsPlanningReceipts")
            for path in [originals,receipts] {
                try files.createDirectory(at:path,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            }
            let planningEndpoint=try MessageEndpoint(url:configuration.endpoint,maximumRequestBytes:32768,maximumResponseBytes:4_000_000,allowLoopbackHTTP:true)
            let planning=try NeedsPlanningClient(endpoint:planningEndpoint,binding:lifetime.trip,credentials:{ binding in
                guard lifetime.current==binding else { return nil };return configuration.token
            },validate:{guard lifetime.current != nil else {throw TripFailure.staleBinding}},directory:originals,receiptDirectory:receipts,expectedKeyID:key.id,provider:keys)
            messages.messages.configurePlanningCandidates(planning)
        }
        needs=try messageNeeds ? preparedNeeds : makeNeeds()
        if let typedMode {
            guard let travel = messages.travelSelection else { throw MemoryFailure.unconfigured }
            typedMemory = try DevelopmentTypedMemoryHost(configuration:configuration,mode:typedMode,shell:shell,
                session:lifetime.session,operation:lifetime.operation,travel:travel,isCurrent:{lifetime.current != nil})
            memory = nil
        } else if let profile = try DevelopmentMemoryProfile.read(environment) {
            memory = try DevelopmentMemoryHost(configuration: configuration, profile: profile, shell: shell,
                session: lifetime.session, operation: lifetime.operation, isCurrent: { lifetime.current != nil })
            typedMemory = nil
        } else { memory = nil;typedMemory = nil }
        if tripEditingProfile != nil {
            let needsHost = needs?.host
            structuredTrips = StructuredTripHost(shell: shell, client: client, binding: lifetime.trip,
                session: lifetime.session, sessionOperation: lifetime.operation, currentBinding: { lifetime.current },
                needsSelection: {
                    guard let snapshot = needsHost?.presentation?.snapshot else { return nil }
                    return try TripNeedsReference(id: snapshot.needs_id, expectedVersion: snapshot.version)
                }, readNeeds: {
                    guard let needsHost, let context = needsHost.captureAction(), let work = needsHost.prepareDetail(context: context) else { return }
                    await needsHost.perform(work)
                }, offline: offline)
        } else { structuredTrips = nil }
        let historyMessages = messages.messages
        memoryHistory = try historyProfile.map { _ in
            try DevelopmentMemoryHistoryHost(configuration: configuration, shell: shell, messages: historyMessages,
                session: lifetime.session, operation: lifetime.operation, isCurrent: { lifetime.current != nil })
        }
        feedback = try feedbackProfile.map { _ in
            try DevelopmentFeedbackHost(configuration: configuration, shell: shell, session: lifetime.session,
                operation: lifetime.operation, isCurrent: { lifetime.current != nil })
        }
        shell.selectedTab = .trips
        // Disk restoration only selects an original action for GET reconciliation;
        // it never prepares or submits another action, even while the API is offline.
        trips.loadPending(context: trips.captureAction())
        if let original = trips.presentation?.pendingActions.first,
           trips.selectPending(original.actionID, context: trips.captureAction()) {
            shell.tripPath = [.originalAction]
        }
    }

    func invalidate() {
        lifetime.active = false
        memoryHistory?.invalidate()
        feedback?.invalidate()
        messages.invalidate()
        memory?.invalidate()
        typedMemory?.invalidate()
        needs?.invalidate()
        structuredTrips?.invalidate()
        trips.invalidate()
        keys.invalidate()
        if lifetime.ownsSession { _ = lifetime.session.clearWithSettlement() }
    }
}

/// Current account and real selected MESSAGE conversation, with a separate
/// history journal domain in the existing canonical Memory key namespace.
@MainActor final class DevelopmentMemoryHistoryHost {
    let host: MemoryHistoryContainerHost
    private let keys: ScopedMessageKeyProvider
    init(configuration: DevelopmentSessionConfiguration, shell: ShellState, messages: AssistantMessageHost,
         session: SessionLifecycle, operation: SessionOperation, isCurrent: @escaping @MainActor () -> Bool) throws {
        let binding = MemoryBinding(environment: configuration.environmentID, account: configuration.accountID,
                                    generation: UUID(), selection: UUID())
        let generation = shell.generation
        let namespace = MessageKeyNamespace(environment: binding.environment, account: binding.account, purpose: .localMemoryPendingV1)
        guard let applicationID = Bundle.main.bundleIdentifier else { throw MemoryFailure.unconfigured }
        let keys = try ScopedMessageKeyProvider(namespace: namespace, applicationIdentifier: applicationID,
                                                protection: .whenUnlockedThisDeviceOnly)
        let files = FileManager.default
        let support = try files.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let legacy = support.appendingPathComponent("G2CDevelopmentMemory", isDirectory: true)
            .appendingPathComponent(binding.environment.uuidString, isDirectory: true)
            .appendingPathComponent(binding.account.uuidString, isDirectory: true)
        try files.createDirectory(at: legacy, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let key: MessageEncryptionKey
        if let existing = try keys.existing(expectedID: nil, for: keys.begin(.lookup)) { key = existing }
        else {
            // This accepted helper checks every account-owned sibling journal,
            // including history-v1, before any new canonical key is created.
            guard try DevelopmentMemoryStorageNamespace.isEmpty(legacyRoot: legacy, files: files) else { throw MemoryFailure.keyUnavailable }
            key = try keys.create(storageState: .confirmedEmpty, for: keys.begin(.create))
        }
        let root = legacy.appendingPathExtension("history-v1")
        if !files.fileExists(atPath: root.path) {
            try files.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        }
        let store = try MemoryHistoryPendingStore(directory: root, maximumBytes: 100_000, maximumRecords: 100,
            binding: binding, expectedKeyID: key.id, provider: keys)
        let current: @MainActor () -> MemoryBinding? = {
            isCurrent() && session.isCurrent(operation) && shell.generation == generation && !shell.messageBindingBlocked ? binding : nil
        }
        let endpoint = try MemoryEndpoint(url: configuration.endpoint, maximumRequestBytes: 32768, maximumResponseBytes: 65536, allowLoopbackHTTP: true)
        let client = try MemoryHistoryClient(development: endpoint, credentials: { captured in
            guard current() == captured else { return nil }; return configuration.token
        }, currentBinding: current, currentConversation: { [weak messages] in
            guard current() != nil else { return nil }; return messages?.selectedConversation
        }, session: session, sessionOperation: operation, pendingStore: store, requestTimeout: 10, resourceTimeout: 20)
        host = MemoryHistoryContainerHost(shell: shell)
        guard host.bind(MemoryHistoryContainerBinding(client: client, memory: binding, shellGeneration: generation,
            messages: messages, session: session, sessionOperation: operation, currentBinding: current)) else { throw MemoryFailure.staleBinding }
        self.keys = keys
    }
    func invalidate() { host.invalidate(); keys.invalidate() }
}

/// Two independent feedback surfaces, sharing only the canonical account-scoped key.
/// These files are original feedback attempts, not a second MESSAGE journal.
@MainActor final class DevelopmentFeedbackHost {
    let answer: FeedbackContainerHost
    let general: FeedbackContainerHost
    private let keys: ScopedMessageKeyProvider
    init(configuration: DevelopmentSessionConfiguration, shell: ShellState, session: SessionLifecycle,
         operation: SessionOperation, isCurrent: @escaping @MainActor () -> Bool) throws {
        let namespace = MessageKeyNamespace(environment: configuration.environmentID, account: configuration.accountID,
                                             purpose: .localFeedbackPendingV1)
        guard let applicationID = Bundle.main.bundleIdentifier else { throw FeedbackFailure.unconfigured }
        let keys = try ScopedMessageKeyProvider(namespace: namespace, applicationIdentifier: applicationID,
                                                protection: .whenUnlockedThisDeviceOnly)
        let files = FileManager.default
        let support = try files.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let root = support.appendingPathComponent("G2CDevelopmentFeedback", isDirectory: true)
            .appendingPathComponent(namespace.environment.uuidString, isDirectory: true)
            .appendingPathComponent(namespace.account.uuidString, isDirectory: true)
        let answerDirectory = root.appendingPathComponent("Answer", isDirectory: true)
        let generalDirectory = root.appendingPathComponent("General", isDirectory: true)
        for directory in [answerDirectory, generalDirectory] {
            try files.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        }
        let key: MessageEncryptionKey
        if let existing = try keys.existing(expectedID: nil, for: keys.begin(.lookup)) { key = existing }
        else {
            // Neither surface can replace a missing key while any encrypted original remains.
            for directory in [answerDirectory, generalDirectory] {
                guard try files.contentsOfDirectory(atPath: directory.path).isEmpty else { throw FeedbackFailure.keyUnavailable }
            }
            key = try keys.create(storageState: .confirmedEmpty, for: keys.begin(.create))
        }
        let endpoint = try FeedbackEndpoint(url: configuration.endpoint, maximumRequestBytes: 16384,
                                             maximumResponseBytes: 1_000_000, allowLoopbackHTTP: true)
        let generation = shell.generation
        let makeBinding: @MainActor (FeedbackAnswerSource?) throws -> FeedbackContainerBinding = { source in
            let feedback = FeedbackBinding(environment: namespace.environment, account: namespace.account,
                                           generation: UUID(), selection: UUID())
            let current: @MainActor () -> FeedbackBinding? = {
                guard isCurrent(), session.isCurrent(operation), shell.generation == generation,
                      !shell.messageBindingBlocked else { return nil }
                if let source, !source.isCurrent(session: session, operation: operation, generation: generation) { return nil }
                guard isCurrent(), session.isCurrent(operation), shell.generation == generation,
                      !shell.messageBindingBlocked else { return nil }
                return feedback
            }
            let store = try FeedbackPendingStore(directory: source == nil ? generalDirectory : answerDirectory,
                maximumBytes: 32768, maximumRecords: 100, binding: feedback, expectedKeyID: key.id, provider: keys)
            let client = try FeedbackClient(development: endpoint, credentials: { binding in
                guard current() == binding else { return nil }; return configuration.token
            }, currentBinding: current, session: session, sessionOperation: operation, pendingStore: store,
                requestTimeout: 10, resourceTimeout: 20)
            return FeedbackContainerBinding(client: client, feedback: feedback, shellGeneration: generation,
                session: session, sessionOperation: operation, context: source?.context, runSource: source,
                synthetic: false, currentBinding: current)
        }
        answer = FeedbackContainerHost(shell: shell, surface: .answer, answerBinding: { try makeBinding($0) })
        general = FeedbackContainerHost(shell: shell, surface: .general)
        guard general.bind(try makeBinding(nil)) else { throw FeedbackFailure.staleBinding }
        self.keys = keys
    }
    func invalidate() { answer.invalidate(); general.invalidate(); keys.invalidate() }
}

/// Only an explicit DEBUG Simulator manual-v1 root activates these old HTTP
/// methods. A model preview neither constructs this capability nor selects IDs.
@MainActor final class DevelopmentNeedsHost {
    let host: NeedsContainerHost
    private let client: NeedsClient
    private let keys: ScopedMessageKeyProvider
    init(configuration: DevelopmentSessionConfiguration, profile: DevelopmentNeedsProfile, shell: ShellState,
         session: SessionLifecycle, operation: SessionOperation, isCurrent: @escaping @MainActor () -> Bool) throws {
        let binding = NeedsBinding(environment: configuration.environmentID, account: configuration.accountID,
                                   generation: UUID(), selection: UUID())
        let generation = shell.generation
        let namespace = MessageKeyNamespace(environment: binding.environment, account: binding.account, purpose: .localNeedsPendingV1)
        guard let applicationID = Bundle.main.bundleIdentifier else { throw NeedsFailure.unconfigured }
        keys = try ScopedMessageKeyProvider(namespace: namespace, applicationIdentifier: applicationID,
                                            protection: .whenUnlockedThisDeviceOnly)
        let files = FileManager.default
        let support = try files.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let directory = support.appendingPathComponent("G2CDevelopmentNeeds", isDirectory: true)
            .appendingPathComponent(binding.environment.uuidString, isDirectory: true)
            .appendingPathComponent(binding.account.uuidString, isDirectory: true)
        try files.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let root = directory.resolvingSymlinksInPath()
        let key: MessageEncryptionKey
        if let existing = try keys.existing(expectedID: nil, for: keys.begin(.lookup)) { key = existing }
        else {
            // Reuse the filesystem-only adjacent-journal check. No Memory key
            // or Memory client is involved; a missing Needs key is never reset.
            guard try DevelopmentMemoryStorageNamespace.isEmpty(legacyRoot: directory, files: files) else { throw NeedsFailure.keyUnavailable }
            key = try keys.create(storageState: .confirmedEmpty, for: keys.begin(.create))
        }
        let store = try NeedsPendingStore(directory: root, maximumBytes: 1048576, maximumRecords: 100,
                                         binding: binding, expectedKeyID: key.id, provider: keys)
        let endpoint = try NeedsEndpoint(url: configuration.endpoint, maximumRequestBytes: 131072,
                                         maximumResponseBytes: 1048576, allowLoopbackHTTP: true)
        let current: @MainActor () -> NeedsBinding? = {
            isCurrent() && session.isCurrent(operation) && shell.generation == generation ? binding : nil
        }
        client = try NeedsClient(localEndpoint: endpoint, credentials: { captured in
            guard current() == captured else { return nil }
            return configuration.token
        }, currentBinding: current, session: session, sessionOperation: operation, pendingStore: store,
            requestTimeout: 10, resourceTimeout: 20)
        host = NeedsContainerHost(shell: shell)
        guard host.bind(NeedsContainerBinding(client: client, needs: binding, selectedNeedsID: profile.needsID,
            shellGeneration: generation, session: session, sessionOperation: operation, synthetic: true,
            currentBinding: current)) else { throw NeedsFailure.staleBinding }
        host.loadPending(context: host.captureAction()) // Local encrypted records only; never an automatic POST.
    }
    func invalidate() { host.invalidate(); client.invalidate(); keys.invalidate() }
}

/// The server receives the existing manual command, with no caller source/owner flags.
@MainActor final class DevelopmentMemoryHost {
    let host: MemoryContainerHost
    private let keys: ScopedMessageKeyProvider

    init(configuration: DevelopmentSessionConfiguration, profile: DevelopmentMemoryProfile, shell: ShellState,
         session: SessionLifecycle, operation: SessionOperation, isCurrent: @escaping @MainActor () -> Bool) throws {
        let binding = MemoryBinding(environment: configuration.environmentID, account: configuration.accountID,
                                    generation: UUID(), selection: UUID())
        let generation = shell.generation
        let namespace = MessageKeyNamespace(environment: binding.environment, account: binding.account, purpose: .localMemoryPendingV1)
        guard let applicationID = Bundle.main.bundleIdentifier else { throw MemoryFailure.unconfigured }
        keys = try ScopedMessageKeyProvider(namespace: namespace, applicationIdentifier: applicationID,
                                            protection: .whenUnlockedThisDeviceOnly)
        let files = FileManager.default
        let support = try files.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let directory = support.appendingPathComponent("G2CDevelopmentMemory", isDirectory: true)
            .appendingPathComponent(binding.environment.uuidString, isDirectory: true)
            .appendingPathComponent(binding.account.uuidString, isDirectory: true)
        try files.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let root = directory.resolvingSymlinksInPath()
        let lifecycleRoot = root.appendingPathExtension("lifecycle")
        let managementURL = try DevelopmentMemoryProfile.managementEndpoint(ProcessInfo.processInfo.environment)
        let key: MessageEncryptionKey
        if let existing = try keys.existing(expectedID: nil, for: keys.begin(.lookup)) { key = existing }
        else {
            guard try DevelopmentMemoryStorageNamespace.isEmpty(legacyRoot:directory,files:files) else { throw MemoryFailure.keyUnavailable }
            key = try keys.create(storageState: .confirmedEmpty, for: keys.begin(.create))
        }
        let store = try MemoryPendingStore(directory: root, maximumBytes: 100_000, maximumRecords: 100,
                                           binding: binding, expectedKeyID: key.id, provider: keys)
        let endpoint = try MemoryEndpoint(url: configuration.endpoint, maximumRequestBytes: 32768,
                                         maximumResponseBytes: 1_000_000, allowLoopbackHTTP: true)
        // The lifetime is shared with account/Trip/MESSAGE; callbacks cannot revive an old identity.
        let current: @MainActor () -> MemoryBinding? = {
            isCurrent() && session.isCurrent(operation) && shell.generation == generation ? binding : nil
        }
        let legacyWritesAllowed: Bool
        do { legacyWritesAllowed = try DevelopmentMemoryStorageNamespace.legacyWritesAllowed(legacyRoot:root) }
        catch { legacyWritesAllowed = false } // Unreadable storage cannot authorize a writer.
        let transport = try NoRedirectTransport.developmentMemory(endpoint: endpoint, requestTimeout: 10,
            resourceTimeout: 20, validate: {
                guard current() == binding else { throw MemoryFailure.staleBinding }
                guard try DevelopmentMemoryStorageNamespace.legacyWritesAllowed(legacyRoot:root) else { throw MemoryFailure.pendingRequiresQuery }
            })
        let credentials: MemoryCredentialCallback = { requested in
            guard current() == requested else { return nil }
            return configuration.token
        }
        let managementEndpoint = try managementURL.map {
            try MemoryEndpoint(url:$0,maximumRequestBytes:32768,maximumResponseBytes:65536,allowLoopbackHTTP:true)
        }
        let lifecycle: MemoryManagementPendingStore?
        if managementURL != nil {
            if !files.fileExists(atPath: lifecycleRoot.path) {
                try files.createDirectory(at: lifecycleRoot, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
            }
            lifecycle = try MemoryManagementPendingStore(directory: lifecycleRoot, maximumBytes: 100_000,
                maximumRecords: 100, binding: binding, expectedKeyID: key.id, provider: keys)
        } else { lifecycle = nil }
        let client: MemoryClient
        if !legacyWritesAllowed {
            client = MemoryClient(endpoint:endpoint,credentials:credentials,currentBinding:current,pendingStore:store,
                liveReadTransport:try NoRedirectTransport(requestTimeout:10,resourceTimeout:20),
                managementPendingStore:lifecycle,managementReadEndpoint:managementEndpoint)
        } else if let managementEndpoint,let lifecycle {
            let managementTransport = try NoRedirectTransport.developmentMemoryManagement(endpoint: managementEndpoint,
                requestTimeout: 10, resourceTimeout: 20, validate: {
                    guard current() == binding else { throw MemoryFailure.staleBinding }
                    guard try DevelopmentMemoryStorageNamespace.legacyWritesAllowed(legacyRoot:root) else { throw MemoryFailure.pendingRequiresQuery }
                })
            client = try MemoryClient(localEndpoint: endpoint, credentials: credentials, currentBinding: current,
                pendingStore: store, localTransport: transport, managementEndpoint: managementEndpoint,
                managementTransport: managementTransport, managementPendingStore: lifecycle)
        } else {
            client = try MemoryClient(localEndpoint: endpoint, credentials: credentials, currentBinding: current,
                pendingStore: store, localTransport: transport)
        }
        var options: [MemoryManualOption] = []
        for subject in profile.subjects {
            for slot in profile.slots.keys.sorted() {
                let policy = profile.slots[slot]!
                guard policy.collection_allowed,
                      let kind = Components.Schemas.MemoryManualSaveCommand.kindPayload(rawValue: policy.kind) else { continue }
                for extent in profile.extents {
                    let contexts: [String?] = extent == "current" ? profile.context_ids.map(Optional.some) : [nil]
                    for context in contexts {
                        let scope: Components.Schemas.MemoryManualSaveCommand.extentPayload = extent == "current" ? .current : .long_term
                        let scopeLabel = context.map { "Current conversation / 当前会话: " + $0 } ?? "Long term / 长期"
                        options.append(MemoryManualOption(id: UUID(), label: subject + " · " + slot + " · " + scopeLabel,
                            disclosure: "Save only what you explicitly enter for this subject and scope. Inference stays unconfirmed. / 仅保存你为该对象及范围明确输入的内容；推断仍待确认。"
                                + (context.map { " Conversation / 会话: " + $0 } ?? ""),
                            subject: subject, slot: slot, kind: kind, extent: scope, contextID: context))
                    }
                }
            }
        }
        host = MemoryContainerHost(shell: shell)
        guard host.bind(MemoryContainerBinding(client: client, memory: binding, shellGeneration: generation,
            pageSize: 20, manualOptions: options, synthetic: false, currentBinding: current)) else {
            throw MemoryFailure.staleBinding
        }
    }
    func invalidate() { host.invalidate(); keys.invalidate() }
}

/// One account/key namespace across wire versions. V1 recovery is query-only;
/// V2 has its own encrypted domain and cannot bypass unresolved V1 originals.
@MainActor final class DevelopmentTypedMemoryHost {
    let host: TypedMemoryContainerHost
    private let keys: ScopedMessageKeyProvider
    init(configuration: DevelopmentSessionConfiguration,mode: DevelopmentTypedMode,shell: ShellState,
         session: SessionLifecycle,operation: SessionOperation,travel: TravelSelectionModel,
         isCurrent: @escaping @MainActor () -> Bool) throws {
        let binding = MemoryBinding(environment:configuration.environmentID,account:configuration.accountID,generation:UUID(),selection:UUID())
        let generation = shell.generation
        let namespace = MessageKeyNamespace(environment:binding.environment,account:binding.account,purpose:.localMemoryPendingV1)
        guard let applicationID = Bundle.main.bundleIdentifier else { throw MemoryFailure.unconfigured }
        keys = try ScopedMessageKeyProvider(namespace:namespace,applicationIdentifier:applicationID,protection:.whenUnlockedThisDeviceOnly)
        let files = FileManager.default
        let support = try files.url(for:.applicationSupportDirectory,in:.userDomainMask,appropriateFor:nil,create:true)
        let directory = support.appendingPathComponent("G2CDevelopmentMemory",isDirectory:true)
            .appendingPathComponent(binding.environment.uuidString,isDirectory:true).appendingPathComponent(binding.account.uuidString,isDirectory:true)
        try files.createDirectory(at:directory,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        let key: MessageEncryptionKey
        if let existing = try keys.existing(expectedID:nil,for:keys.begin(.lookup)) { key = existing }
        else {
            guard try DevelopmentMemoryStorageNamespace.isEmpty(legacyRoot:directory,files:files) else { throw MemoryFailure.keyUnavailable }
            key = try keys.create(storageState:.confirmedEmpty,for:keys.begin(.create))
        }
        let legacyRoot = directory.resolvingSymlinksInPath()
        let lifecycleRoot = legacyRoot.appendingPathExtension("lifecycle"),typedRoot = legacyRoot.appendingPathExtension("typed-v2")
        for root in [lifecycleRoot,typedRoot] where !files.fileExists(atPath:root.path) {
            try files.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        }
        let oldStore = try MemoryPendingStore(directory:legacyRoot,maximumBytes:100_000,maximumRecords:100,binding:binding,expectedKeyID:key.id,provider:keys)
        let oldManagement = try MemoryManagementPendingStore(directory:lifecycleRoot,maximumBytes:100_000,maximumRecords:100,binding:binding,expectedKeyID:key.id,provider:keys)
        let store = try TypedMemoryPendingStore(directory:typedRoot,maximumBytes:100_000,maximumRecords:100,binding:binding,expectedKeyID:key.id,provider:keys)
        let current: @MainActor () -> MemoryBinding? = {
            isCurrent() && session.isCurrent(operation) && shell.generation == generation ? binding : nil
        }
        let credentials: MemoryCredentialCallback = { requested in current() == requested ? configuration.token : nil }
        let oldEndpoint = try MemoryEndpoint(url:configuration.endpoint,maximumRequestBytes:32768,maximumResponseBytes:1_000_000,allowLoopbackHTTP:true)
        let oldManagementEndpoint = try DevelopmentMemoryProfile.managementEndpoint(ProcessInfo.processInfo.environment).map {
            try MemoryEndpoint(url:$0,maximumRequestBytes:32768,maximumResponseBytes:65536,allowLoopbackHTTP:true)
        }
        let reads = try NoRedirectTransport(requestTimeout:10,resourceTimeout:20)
        let legacy = MemoryClient(endpoint:oldEndpoint,credentials:credentials,currentBinding:current,pendingStore:oldStore,
            liveReadTransport:reads,managementPendingStore:oldManagement,managementReadEndpoint:oldManagementEndpoint)
        let endpoint = try MemoryEndpoint(url:mode.memoryEndpoint,maximumRequestBytes:32768,maximumResponseBytes:1_000_000,allowLoopbackHTTP:true)
        let transport = try NoRedirectTransport.developmentTypedMemory(endpoint:endpoint,requestTimeout:10,resourceTimeout:20,validate:{
            guard current() == binding else { throw MemoryFailure.staleBinding }
        })
        let client = try TypedMemoryClient(localEndpoint:endpoint,credentials:credentials,currentBinding:current,pendingStore:store,
            localTransport:transport,validatePriorOriginals:{
                if try legacy.requiresOriginalReconciliation(binding:binding) { throw MemoryFailure.pendingRequiresQuery }
            })
        var options: [TypedMemoryManualOption] = []
        for subject in mode.memory.subjects {
            for slot in mode.memory.slots.keys.sorted() {
                let policy = mode.memory.slots[slot]!
                guard policy.collection_allowed else { continue }
                let kind = Components.Schemas.MemoryManualSaveCommand.kindPayload(rawValue:policy.kind)!
                for extent in mode.memory.extents {
                    let scope: TypedMemoryScopeChoice = extent == "current" ? .selectedTravel : .longTerm
                    let label = extent == "current" ? "Selected travel / 所选旅行" : "Long term / 长期"
                    options.append(TypedMemoryManualOption(label:subject + " · " + slot + " · " + label,subject:subject,slot:slot,kind:kind,scope:scope))
                }
            }
        }
        host = try TypedMemoryContainerHost(shell:shell,client:client,binding:binding,pageSize:20,options:options,travel:travel,legacy:legacy,currentBinding:current)
    }
    func invalidate() { host.invalidate();keys.invalidate() }
}

@MainActor private final class DevelopmentMessageLifetime {
    var active = true
    let isCurrent: @MainActor () -> Bool
    init(isCurrent: @escaping @MainActor () -> Bool) { self.isCurrent = isCurrent }
    var current: Bool {
        guard active else { return false }
        let value = isCurrent();return value && active
    }
    func validate() throws {
        guard current else { throw RecoveryError.inactive }
    }
}

@MainActor private final class DevelopmentMessageCredentials: MessageCredentialsProvider {
    private let token: String
    private let scope: StorageScope
    private let lease: Lease
    private let lifetime: DevelopmentMessageLifetime
    init(token: String, scope: StorageScope, lease: Lease, lifetime: DevelopmentMessageLifetime) {
        self.token = token; self.scope = scope; self.lease = lease; self.lifetime = lifetime
    }
    func bearer(for requested: StorageScope, lease: Lease) async throws -> String? {
        try lifetime.validate()
        guard lease == self.lease, Data(requested.environment.utf8) == Data(scope.environment.utf8),
              Data(requested.account.utf8) == Data(scope.account.utf8) else { throw RecoveryError.inactive }
        return token
    }
}

/// Uses the same development account/session lifetime as the Trip host; no interceptor.
@MainActor final class DevelopmentMessageHost {
    let messages: AssistantMessageHost
    let history: ServerHistoryHost
    let runs: RunContainerHost
    let travelSelection: TravelSelectionModel?
    private let lifetime: DevelopmentMessageLifetime
    private let keyAdapter: ExistingMessageKeyAdapter

    init(configuration: DevelopmentSessionConfiguration, shell: ShellState,
         session: SessionLifecycle, operation: SessionOperation,travelProfile: DevelopmentTravelProfile? = nil,tripDiscussions:Bool = false,
         scopedEdits:Bool=false,scopedResults:Bool=false,needsPlanning:Bool=false,currentNeeds:(@MainActor ()->MessageNeedsSelection?)?=nil,isCurrent: @escaping @MainActor () -> Bool) throws {
        guard !tripDiscussions || travelProfile == nil else { throw DevelopmentDiscussionProfile.Failure.incompatibleProfiles }
        let answerFormat: RunAnswerFormat
        switch try DevelopmentSessionConfiguration.toolAnswerProfile(ProcessInfo.processInfo.environment) {
        case .plain:answerFormat = .plainText
        case .place:answerFormat = .placeToolV1
        case .fact:answerFormat = .factToolV1
        case .needs:answerFormat = .needsPreviewV1
        }
        let lifetime = DevelopmentMessageLifetime(isCurrent: isCurrent)
        let scope = try StorageScope(environment: configuration.environmentID.uuidString, account: configuration.accountID.uuidString)
        let namespace = MessageKeyNamespace(environment: configuration.environmentID, account: configuration.accountID,
                                             purpose: .localMessageStorageV1)
        guard let applicationID = Bundle.main.bundleIdentifier else { throw MessageHTTPFailure.invalidConfiguration }
        let keys = try ScopedMessageKeyProvider(namespace: namespace, applicationIdentifier: applicationID,
                                                 protection: .whenUnlockedThisDeviceOnly)
        let files = FileManager.default
        let support = try files.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let directory = support.appendingPathComponent("G2CDevelopmentMessages", isDirectory: true)
            .appendingPathComponent(namespace.environment.uuidString, isDirectory: true)
            .appendingPathComponent(namespace.account.uuidString, isDirectory: true)
        try files.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let root = directory.resolvingSymlinksInPath()
        if try keys.existing(expectedID: nil, for: keys.begin(.lookup)) == nil {
            guard try files.contentsOfDirectory(atPath: root.path).isEmpty else { throw RecoveryError.keyUnavailable }
            _ = try keys.create(storageState: .confirmedEmpty, for: keys.begin(.create))
        }
        let keyAdapter = try ExistingMessageKeyAdapter(provider: keys, scope: scope, namespace: namespace)
        let storage = try EncryptedFileStorage(directory: root, keys: keyAdapter)
        let recovery = MessageRecovery(storage: storage)
        let lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: configuration.endpoint, maximumRequestBytes: 16384,
                                           maximumResponseBytes: 1_000_000, allowLoopbackHTTP: true)
        let transport: NoRedirectTransport
        if scopedEdits {
            transport=try NoRedirectTransport.developmentTripEdits(endpoint:endpoint,requestTimeout:10,resourceTimeout:20,validate:{try lifetime.validate()})
        } else if tripDiscussions {
            transport=try NoRedirectTransport.developmentTripDiscussions(endpoint:endpoint,requestTimeout:10,resourceTimeout:20,validate:{try lifetime.validate()})
        } else if travelProfile != nil {
            transport = try NoRedirectTransport.developmentTravelMessages(endpoint:endpoint,requestTimeout:10,resourceTimeout:20,validate:{try lifetime.validate()})
        } else {
            transport = try NoRedirectTransport.developmentMessages(endpoint:endpoint,requestTimeout:10,resourceTimeout:20,validate:{try lifetime.validate()})
        }
        let credentials = DevelopmentMessageCredentials(token: configuration.token, scope: scope, lease: lease, lifetime: lifetime)
        let client = MessageHTTPClient(recovery: recovery, scope: scope, endpoint: endpoint,
                                        credentials: credentials, liveReadTransport: transport,readsScopedEditResults:scopedResults)
        let selectedTravel = try travelProfile.map { try TravelSelectionModel(ids:$0.travel_ids,client:client,lease:lease,isCurrent:{lifetime.current}) }
        let needsForBinding:(@MainActor ()->MessageNeedsSelection?)?
        if needsPlanning {
            needsForBinding = {
                guard lifetime.current,let selectedTravel else { return nil }
                do {
                    let travel=try selectedTravel.capture()
                    guard travel.context != nil else { return nil }
                    let needs=currentNeeds?()
                    try selectedTravel.validate(travel)
                    guard lifetime.current else { return nil }
                    return needs
                } catch { return nil } // No current explicit namespace; never substitute another journey.
            }
        } else { needsForBinding=currentNeeds }
        let messages = AssistantMessageHost(shell: shell), history = ServerHistoryHost(shell: shell)
        guard messages.bind(AssistantMessageBinding(recovery: recovery, scope: scope, lease: lease,
            generation: shell.generation, synthetic: false,
            isCurrent: { lifetime.current },
            invalidateResources: { lifetime.active = false;selectedTravel?.invalidate();keyAdapter.invalidate() },sendClient:client,travelSelection:selectedTravel,
            currentNeeds:needsForBinding,tripDiscussions:tripDiscussions,scopedEdits:scopedEdits)) else {
            throw RecoveryError.inactive
        }
        let limits = try MessageReadLimits(maximumPageItems: 20, maximumCursorBytes: 4096,
                                           maximumDecodedBytes: 1_000_000, maximumPages: 50)
        guard history.bind(ServerHistoryBinding(client: client, recovery: recovery, scope: scope, lease: lease,
            generation: shell.generation, limit: 20, limits: limits, synthetic: false,tripDiscussions:tripDiscussions,scopedEdits:scopedEdits,
            isCurrent: { lifetime.current },
            selectForSending: { [weak messages] cid in messages?.selectConversationForSending(cid) == true })) else {
            messages.invalidate(); throw RecoveryError.inactive
        }
        let runReads = try NoRedirectTransport(requestTimeout: 15, resourceTimeout: 150)
        let runStops = try scopedEdits ? RunCancellationTransport.developmentEditCompatible(endpoint:endpoint,validate:{try lifetime.validate()})
            : tripDiscussions ? RunCancellationTransport.developmentTripCompatible(endpoint:endpoint,validate:{try lifetime.validate()})
            : travelProfile == nil ? RunCancellationTransport.development(endpoint:endpoint,validate:{try lifetime.validate()})
            : RunCancellationTransport.developmentCompatible(endpoint:endpoint,validate:{try lifetime.validate()})
        let runModel = try RunDisplayModel(endpoint: endpoint, maximumMessageIDBytes:(tripDiscussions || scopedEdits) ? 16384 : 256, maximumTextBytes: 200000,
            credentials: { captured in
                try lifetime.validate()
                guard captured == operation, session.isCurrent(captured) else { throw RecoveryError.inactive }
                return configuration.token
            }, liveReadTransport: runReads, liveCancellationTransport: runStops, readsDraftStatus: true, draftStatusVersion: scopedResults ? .v6 : .v2)
        let runs = RunContainerHost(shell: shell)
        guard runs.configure(RunContainerConfiguration(model: runModel, session: session, operation: operation,
            generation: shell.generation, synthetic: false, followAcceptedMessages: true,
            answerFormat:answerFormat,
            isCurrent: { lifetime.current })) else { throw RecoveryError.inactive }
        self.lifetime = lifetime; self.keyAdapter = keyAdapter
        self.messages = messages; self.history = history; self.runs = runs
        travelSelection = selectedTravel
    }

    func invalidate() {
        lifetime.active = false
        travelSelection?.invalidate()
        runs.invalidate(); history.invalidate(); messages.invalidate(); keyAdapter.invalidate()
    }
}

/// Explicit DEBUG simulator account root; its volatile tokens are never UI state or preferences.
@MainActor @Observable final class DevelopmentAccountRoot {
    var trip: DevelopmentTripHost?
    let offline: OfflineTripController?
    private let shell: ShellState
    private let endpoint: URL
    private let proposalID: String?
    private let tokens: [String: String]
    private let persistence: KeychainSessionStore
    @ObservationIgnored lazy var accounts: DevelopmentAccountHost = {
        DevelopmentAccountHost(shell: shell,
            choices: tokens.keys.sorted().map { .init(id: $0, label: $0) }, persistence: persistence,
            material: { [weak self] choice in
                guard let token = self?.tokens[choice] else { throw SessionFailure.invalidConfiguration }
                return try SessionMaterial(trustedSDKBytes: Data(token.utf8))
            }, verify: { [weak self] material in
                guard let self else { return .networkUnknown }
                return await self.verify(material)
            }, activate: { [weak self] material, session, operation in
                guard let self, let configuration = self.configuration(material) else { throw SessionFailure.invalidConfiguration }
                try self.offline?.bindSynchronizationIdentity(material: material, account: configuration.accountID,
                    session: session, operation: operation)
                self.trip = try DevelopmentTripHost(configuration: configuration, shell: self.shell,
                    lease: DevelopmentSessionLease(session: session, operation: operation), offline: self.offline)
                self.shell.selectedTab = .memory
                self.shell.memoryPath = [.account]
            }, invalidate: { [weak self] in self?.trip?.invalidate(); self?.trip = nil },
            clearOffline: offline == nil ? nil : { [weak self] in try self?.offline?.clearLocally() },
            serverRejected: offline == nil ? nil : { [weak self] material in try self?.offline?.identityRejected(material: material) })
    }()

    init(environment: [String: String], shell: ShellState) throws {
        _ = try DevelopmentTripEditingProfile.read(environment)
        guard environment["G2C_DEV_ACCOUNT_MODE"] == "1",
              let endpoint = DevelopmentSessionConfiguration.readEndpoint(environment),
              let raw = (environment["G2C_DEV_ACCOUNTS"] ?? "{}").data(using: .utf8), raw.count <= 131072,
              let tokens = try JSONSerialization.jsonObject(with: raw) as? [String: String], tokens.count <= 8,
              tokens.keys.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }),
              let applicationID = Bundle.main.bundleIdentifier else { throw SessionFailure.invalidConfiguration }
        self.shell = shell; self.endpoint = endpoint; self.tokens = tokens
        proposalID = environment["G2C_DEV_PROPOSAL_ID"]
        let scope = try KeychainSessionScope(namespace: SessionNamespace(
            environment: DevelopmentSessionConfiguration.environmentNamespace(endpoint), slot: "M1.Development.Active"),
            applicationIdentifier: applicationID)
        let sdkStore = KeychainSessionStore(scope: scope, protection: .whenUnlockedThisDeviceOnly)
        persistence = sdkStore
        if let profile = try DevelopmentOfflineProfile.read(environment) {
            let files = FileManager.default
            let support = try files.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            let directory = support.appendingPathComponent("G2COfflineTrip", isDirectory: true)
                .appendingPathComponent(DevelopmentSessionConfiguration.environmentNamespace(endpoint).uuidString, isDirectory: true)
            try files.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            offline = try OfflineTripController(environment: DevelopmentSessionConfiguration.environmentNamespace(endpoint),
                applicationIdentifier: applicationID, directory: directory.resolvingSymlinksInPath(),
                sdkMaterial: sdkStore.load, policy: .acceptedTrip, clock: {
                    guard let value = OfflineDeviceClock.read(), let wall = value.trustedWallSeconds else { return nil }
                    let (shifted, overflow) = wall.addingReportingOverflow(profile.wallOffset)
                    guard !overflow else { return nil }
                    return .init(trustedWallSeconds: profile.trusted ? shifted : nil,
                        boot: value.boot, uptime: value.uptime + Double(profile.uptimeOffset))
                })
        } else { offline = nil }
    }

    private func configuration(_ material: SessionMaterial) -> DevelopmentSessionConfiguration? {
        material.withBytes { bytes in
            guard let token = String(data: bytes, encoding: .utf8) else { return nil }
            var environment = ["G2C_DEV_API_BASE_URL": endpoint.absoluteString, "G2C_DEV_TOKEN": token]
            if let proposalID { environment["G2C_DEV_PROPOSAL_ID"] = proposalID }
            return DevelopmentSessionConfiguration.read(environment)
        }
    }

    private func verify(_ material: SessionMaterial) async -> DevelopmentSessionCheck {
        guard let configuration = configuration(material) else { return .rejected }
        // Untrusted token metadata can deny an expired attempt, never authorize one.
        if let expiry = configuration.expiresAt, expiry <= Date().timeIntervalSince1970 { return .expired }
        do {
            let transport = try DevelopmentVerificationTransport(endpoint: endpoint, token: configuration.token)
            let client = Client(serverURL: endpoint, transport: transport)
            let result = try await client.queryMessageReceipt(.init(query: .init(message_id: "session-" + UUID().uuidString)))
            try Task.checkCancellation()
            switch result {
            case .ok(let response):
                let body = try response.body.json
                guard UUID(uuidString: body.request_id) != nil,
                      body.request_id == response.headers.X_hyphen_Request_hyphen_ID else { return .networkUnknown }
                return .accepted(account: configuration.subject)
            case .default(let status, _): return status == 401 || status == 403 ? .serverRejected : .networkUnknown
            }
        } catch { return .networkUnknown }
    }
}

private struct DevelopmentVerificationTransport: ClientTransport {
    let endpoint: URL
    private let token: String
    private let transport: NoRedirectTransport
    init(endpoint: URL, token: String) throws {
        self.endpoint = endpoint; self.token = token
        transport = try NoRedirectTransport(requestTimeout: 5, resourceTimeout: 10)
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard baseURL == endpoint, request.method == .get, request.scheme == nil, request.authority == nil,
              operationID == Operations.queryMessageReceipt.id,
              request.path?.hasPrefix("/v1/message-receipts?") == true, body == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }) else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        var request = request; request.headerFields[.authorization] = "Bearer " + token
        try Task.checkCancellation()
        let (response, body) = try await transport.send(request, body: nil, baseURL: baseURL, operationID: operationID)
        guard !(300..<400).contains(response.status.code), let body else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: 16384)
        try Task.checkCancellation()
        return (response, HTTPBody(bytes))
    }
}

/// Fixed App-owned locations, captured only after normal writers are quiesced.
/// Neither an HTTP field nor a target string is ever concatenated into a path.
@MainActor private final class DevelopmentDeviceNativeLayout {
    let scope: AccountCleanupScope
    private let support: DeviceCleanupDirectory
    private let roots: [DeviceCleanupTarget: [DeviceCleanupDirectory]]
    init(scope: AccountCleanupScope) throws {
        self.scope = scope
        let supplied = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
            appropriateFor: nil, create: false)
        guard let physical = realpath(supplied.path, nil) else { throw CleanupFailure.unavailable }
        defer { free(physical) }
        let base = try DeviceCleanupDirectory(existingOwnedAncestor: URL(fileURLWithPath: String(cString: physical)))
        support = base
        let environment = scope.environment.uuidString, account = scope.account.uuidString
        func capture(_ folder: String, _ child: String, _ nested: String? = nil) throws -> DeviceCleanupDirectory {
            let root = try base.child(folder).child(environment).child(child)
            return try nested.map { try root.child($0) } ?? root
        }
        let trip = try capture("G2CDevelopmentTrip", account)
        let manual = try capture("G2CDevelopmentTrip", account + ".CJTripManual")
        let manualRejected = try capture("G2CDevelopmentTrip", account + ".CJTripManual.CJTripManualRejections")
        let scoped = try [".ScopedOriginals", ".ScopedReceipts"].map { try capture("G2CDevelopmentTrip", account + $0) }
        let planning = try [".NeedsPlanningOriginals", ".NeedsPlanningReceipts"].map { try capture("G2CDevelopmentTrip", account + $0) }
        let memory = try ["", ".CJMemoryRejections"].map { try capture("G2CDevelopmentMemory", account + $0) }
        let lifecycle = try [".lifecycle", ".lifecycle.CJMemoryManagementRejections"].map { try capture("G2CDevelopmentMemory", account + $0) }
        let typed = try [".typed-v2", ".typed-v2.CJMemoryTypedRejectionsV2", ".typed-v2.CJMemoryTypedManagementV2", ".typed-v2.CJMemoryTypedManagementV2.CJMemoryTypedManagementRejectionsV2"].map { try capture("G2CDevelopmentMemory", account + $0) }
        let history = try [".history-v1", ".history-v1.CJMemoryHistoryRejectionsV1"].map { try capture("G2CDevelopmentMemory", account + $0) }
        let needs = try ["", ".CJNeedsRejections"].map { try capture("G2CDevelopmentNeeds", account + $0) }
        let feedback = try ["Answer", "General"].map { try capture("G2CDevelopmentFeedback", account, $0) }
        let offline = try capture("G2COfflineTrip", account)
        roots = [
            .encryptedMessage: [try capture("G2CDevelopmentMessages", account)],
            .tripPending: [trip, manual, manualRejected], .tripScoped: scoped, .needsPlanning: planning,
            .memoryManual: memory, .memoryLifecycle: lifecycle, .memoryTyped: typed, .memoryHistory: history,
            .needsPending: needs, .feedbackPending: feedback, .offlineTrip: [offline], .offlineWriteResidue: [offline],
            .tripKey: [trip, manual, manualRejected] + scoped + planning,
            .memoryKey: memory + lifecycle + typed + history, .needsKey: needs, .feedbackKey: feedback,
            .offlineKey: [offline], .messageKey: [try capture("G2CDevelopmentMessages", account)]
        ]
    }
    func directories(for target: DeviceCleanupTarget) throws -> [DeviceCleanupDirectory] {
        try support.validateIdentity()
        guard let result = roots[target] else { throw CleanupFailure.unavailable }
        for directory in result { try directory.validateIdentity() }
        return result
    }
    func requireEmpty(for target: DeviceCleanupTarget) throws {
        for directory in try directories(for: target) { try directory.requireEmpty() }
    }
    func primaryURL(for target: DeviceCleanupTarget) throws -> URL? {
        guard let first = try directories(for: target).first else { throw CleanupFailure.unavailable }
        return try first.existingURLForTrustedHost()
    }
    func manifestReferences() throws -> [String: [String]] {
        var result: [String: [String]] = [:]
        for target in DeviceCleanupTarget.allCases where target != .sdkSession {
            result[target.rawValue] = try directories(for: target).map { try $0.identityReference() }
        }
        return result
    }
}


/// Actual keyless domain erasure, using each domain's accepted primitive. Key IDs
/// are captured from existing canonical Keychain records; missing keys are never
/// replaced or fabricated to construct a readable store.
@MainActor private final class DevelopmentDeviceNativeStores {
    let scope: AccountCleanupScope
    let layout: DevelopmentDeviceNativeLayout
    private let applicationID: String
    private let keys: [MessageKeyPurpose: ScopedMessageKeyProvider]
    let keyIDs: [MessageKeyPurpose: UUID]
    init(scope: AccountCleanupScope, layout: DevelopmentDeviceNativeLayout) throws {
        guard let applicationID = Bundle.main.bundleIdentifier else { throw CleanupFailure.unavailable }
        self.scope = scope; self.layout = layout; self.applicationID = applicationID
        var keys: [MessageKeyPurpose: ScopedMessageKeyProvider] = [:], ids: [MessageKeyPurpose: UUID] = [:]
        for purpose in [MessageKeyPurpose.localMessageStorageV1, .localTripPendingV1, .localMemoryPendingV1,
                        .localNeedsPendingV1, .localFeedbackPendingV1, .localOfflineTripSnapshotV1] {
            let provider = try ScopedMessageKeyProvider(namespace: .init(environment: scope.environment, account: scope.account, purpose: purpose),
                applicationIdentifier: applicationID, protection: .whenUnlockedThisDeviceOnly)
            if let key = try provider.existing(expectedID: nil, for: provider.begin(.lookup)) { ids[purpose] = key.id }
            keys[purpose] = provider
        }
        self.keys = keys; keyIDs = ids
    }
    private func provider(_ purpose: MessageKeyPurpose) throws -> (ScopedMessageKeyProvider, UUID) {
        guard let provider = keys[purpose], let id = keyIDs[purpose] else { throw CleanupFailure.unavailable }
        return (provider, id)
    }
    private var memoryBinding: MemoryBinding { .init(environment: scope.environment, account: scope.account, generation: scope.generation, selection: scope.generation) }
    private var tripBinding: TripBinding { .init(environment: scope.environment, account: scope.account, generation: scope.generation, selection: scope.generation) }
    func eraseFiles(for target: DeviceCleanupTarget) throws {
        let captured = try layout.directories(for: target)
        let firstPhysical = try layout.primaryURL(for: target)
        if firstPhysical == nil && target != .feedbackPending { try layout.requireEmpty(for: target); return }
        let url = firstPhysical?.resolvingSymlinksInPath() // Domain ctors retain their original root checks.
        switch target {
        case .encryptedMessage:
            guard let url else { throw CleanupFailure.unavailable }
            let (provider, _) = try provider(.localMessageStorageV1)
            let scope = try StorageScope(environment: self.scope.environment.uuidString, account: self.scope.account.uuidString)
            let adapter = try ExistingMessageKeyAdapter(provider: provider, scope: scope, namespace: provider.namespace)
            let store = try EncryptedFileStorage(directory: url, keys: adapter)
            for directory in captured { try directory.validateIdentity() }
            try store.clearLocalSnapshot(scope: scope)
        case .tripPending:
            guard let url else { throw CleanupFailure.unavailable }
            let (provider, id) = try provider(.localTripPendingV1)
            let store = try TripPendingStore(directory: url, maximumBytes: 1_000_000, maximumRecords: 100,
                binding: tripBinding, expectedKeyID: id, provider: provider)
            for directory in captured { try directory.validateIdentity() }
            try store.clearLocalFiles()
        case .memoryManual:
            guard let url else { throw CleanupFailure.unavailable }
            let (provider, id) = try provider(.localMemoryPendingV1)
            let store = try MemoryPendingStore(directory: url, maximumBytes: 100_000, maximumRecords: 100,
                binding: memoryBinding, expectedKeyID: id, provider: provider)
            for directory in captured { try directory.validateIdentity() }
            try store.clearLocalFiles()
        case .memoryLifecycle:
            guard let url else { throw CleanupFailure.unavailable }
            let (provider, id) = try provider(.localMemoryPendingV1)
            let store = try MemoryManagementPendingStore(directory: url, maximumBytes: 100_000, maximumRecords: 100,
                binding: memoryBinding, expectedKeyID: id, provider: provider)
            for directory in captured { try directory.validateIdentity() }
            try store.clearLocalFiles()
        case .memoryTyped:
            guard let url else { throw CleanupFailure.unavailable }
            let (provider, id) = try provider(.localMemoryPendingV1)
            let store = try TypedMemoryPendingStore(directory: url, maximumBytes: 100_000, maximumRecords: 100,
                binding: memoryBinding, expectedKeyID: id, provider: provider)
            for directory in captured { try directory.validateIdentity() }
            try store.clearLocalFiles()
        case .memoryHistory:
            guard let url else { throw CleanupFailure.unavailable }
            let (provider, id) = try provider(.localMemoryPendingV1)
            let store = try MemoryHistoryPendingStore(directory: url, maximumBytes: 100_000, maximumRecords: 100,
                binding: memoryBinding, expectedKeyID: id, provider: provider)
            for directory in captured { try directory.validateIdentity() }
            try store.clearLocalFiles()
        case .needsPending:
            guard let url else { throw CleanupFailure.unavailable }
            let (provider, id) = try provider(.localNeedsPendingV1)
            let binding = NeedsBinding(environment: scope.environment, account: scope.account, generation: scope.generation, selection: scope.generation)
            let store = try NeedsPendingStore(directory: url, maximumBytes: 1_048_576, maximumRecords: 100,
                binding: binding, expectedKeyID: id, provider: provider)
            for directory in captured { try directory.validateIdentity() }
            try store.clearLocalFiles()
        case .feedbackPending:
            let (provider, id) = try provider(.localFeedbackPendingV1)
            let binding = FeedbackBinding(environment: scope.environment, account: scope.account, generation: scope.generation, selection: scope.generation)
            for directory in captured {
                guard let physical = try directory.existingURLForTrustedHost() else { continue }
                let store = try FeedbackPendingStore(directory: physical.resolvingSymlinksInPath(), maximumBytes: 100_000,
                    maximumRecords: 100, binding: binding, expectedKeyID: id, provider: provider)
                try directory.validateIdentity(); try store.clearLocalFiles()
            }
        default: throw CleanupFailure.unavailable // SDK/offline/paired handlers are explicitly supplied separately.
        }
        try layout.requireEmpty(for: target)
    }
    private func purpose(for target: DeviceCleanupTarget) throws -> MessageKeyPurpose {
        let purpose: MessageKeyPurpose
        switch target {
        case .messageKey: purpose = .localMessageStorageV1
        case .tripKey: purpose = .localTripPendingV1
        case .memoryKey: purpose = .localMemoryPendingV1
        case .needsKey: purpose = .localNeedsPendingV1
        case .feedbackKey: purpose = .localFeedbackPendingV1
        case .offlineKey: purpose = .localOfflineTripSnapshotV1
        default: throw CleanupFailure.unavailable
        }
        return purpose
    }
    func eraseKey(for target: DeviceCleanupTarget) throws {
        let purpose = try purpose(for: target)
        try layout.requireEmpty(for: target) // Every shared sibling, not only the base journal.
        guard let provider = keys[purpose] else { throw CleanupFailure.unavailable }
        guard let id = keyIDs[purpose] else {
            guard try provider.existing(expectedID: nil, for: provider.begin(.lookup)) == nil else { throw CleanupFailure.stale }
            return
        }
        try provider.clear(expectedID: id, storageState: .confirmedEmpty, for: provider.begin(.clear))
        guard try provider.existing(expectedID: nil, for: provider.begin(.lookup)) == nil else { throw CleanupFailure.exchangeUnknown }
        try layout.requireEmpty(for: target)
    }
    func verifyKeyAbsent(for target: DeviceCleanupTarget) throws {
        let purpose = try purpose(for: target)
        try layout.requireEmpty(for: target)
        guard let provider = keys[purpose], try provider.existing(expectedID: nil, for: provider.begin(.lookup)) == nil else { throw CleanupFailure.unavailable }
    }
}

#endif
