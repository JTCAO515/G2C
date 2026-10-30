import Foundation
import Observation
import CJAPI
import CJMemoryClient
import CJMessageHTTP

public enum TypedMemoryScopeChoice: Sendable { case longTerm,selectedTravel }
public struct TypedMemoryManualOption: Identifiable {
    public let id = UUID()
    public let label: String
    let subject: String
    let slot: String
    let kind: Components.Schemas.MemoryManualSaveCommand.kindPayload
    let scope: TypedMemoryScopeChoice
    public init(label: String,subject: String,slot: String,kind: Components.Schemas.MemoryManualSaveCommand.kindPayload,scope: TypedMemoryScopeChoice) {
        self.label = label;self.subject = subject;self.slot = slot;self.kind = kind;self.scope = scope
    }
}
public struct TypedMemorySurface: Sendable {
    fileprivate let owner: UUID
    fileprivate let epoch: UUID
}
@MainActor public struct TypedMemorySaveWork {
    fileprivate let surface: TypedMemorySurface
    fileprivate let command: TypedMemoryCommand
    fileprivate let travel: CapturedTravelSelection?
    /// Exact reviewed command data; exposing it confers no construction or dispatch authority.
    public var original: TypedMemoryCommand { command }
}
@MainActor public struct TypedMemoryManagementWork {
    fileprivate let surface: TypedMemorySurface
    fileprivate let read: TypedMemoryRead
    fileprivate let operation: TypedMemoryOperation
    fileprivate let text: String?
    fileprivate let travel: CapturedTravelSelection?
    fileprivate let travelValue: MemoryTravelSelection?
}
public enum TypedMemoryManagementState {
    case ready,working,unknown,notObserved,rejected,needsOriginalQuery
    case historical(Components.Schemas.MemoryManagementReceiptV2)
}

/// One typed consumer, one canonical account binding and explicit travel model.
/// Surfaces retire read/dispatch authority; immutable original receipts remain
/// separate from current item state. A late surface exit cannot retire its successor.
@MainActor @Observable public final class TypedMemoryContainerHost {
    public let id = UUID()
    private let shell: ShellState
    private let generation: ShellGeneration
    private let client: TypedMemoryClient
    private let binding: MemoryBinding
    private let currentBinding: @MainActor () -> MemoryBinding?
    private let configuredOptions: [TypedMemoryManualOption]
    private let travel: TravelSelectionModel
    private let pageSize: Int
    private var active = true
    @ObservationIgnored private var invalidating = false
    @ObservationIgnored private var publishing = false
    @ObservationIgnored private var epoch = UUID()
    @ObservationIgnored private var working = false
    @ObservationIgnored private var page: TypedMemoryCursor?
    @ObservationIgnored private var itemValues: MemoryLoad<[TypedMemoryRead]> = .unconfigured
    @ObservationIgnored private var detailValue: MemoryLoad<TypedMemoryRead?> = .unconfigured
    @ObservationIgnored private var originalValues: MemoryLoad<[TypedMemoryCommand]> = .unconfigured
    @ObservationIgnored private var managementOriginalValues: MemoryLoad<[TypedMemoryManagementPending]> = .unconfigured
    @ObservationIgnored private var saveValue: MemorySaveState = .ready
    @ObservationIgnored private var managementValue: TypedMemoryManagementState = .ready
    private var visibleEpoch: UUID?

    public init(shell: ShellState,client: TypedMemoryClient,binding: MemoryBinding,pageSize: Int,
                options: [TypedMemoryManualOption],travel: TravelSelectionModel,
                currentBinding: @escaping @MainActor () -> MemoryBinding?) throws {
        self.shell = shell;generation = shell.generation;self.client = client;self.binding = binding
        self.pageSize = pageSize;configuredOptions = options;self.travel = travel;self.currentBinding = currentBinding
        let predecessor = shell.typedMemoryContainerHost
        guard (1...100).contains(pageSize),current,shell.typedMemoryContainerHost === predecessor else { throw MemoryFailure.staleBinding }
        predecessor?.invalidate()
        guard current,shell.typedMemoryContainerHost === predecessor else { throw MemoryFailure.staleBinding }
        shell.typedMemoryContainerHost = self
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    private var current: Bool {
        guard active,!invalidating,shell.generation == generation,!shell.messageBindingBlocked else { return false }
        let observed = currentBinding()
        return observed == binding && active && !invalidating && shell.generation == generation && !shell.messageBindingBlocked
    }
    private var presented: Bool {
        let token = epoch
        return visibleEpoch == token && current && epoch == token && visibleEpoch == token
    }
    public var isConfigured: Bool { current }
    public var busy: Bool { presented && working }
    public var options: [TypedMemoryManualOption] { current ? configuredOptions : [] }
    public var items: MemoryLoad<[TypedMemoryRead]> { presented ? itemValues : .unconfigured }
    public var detail: MemoryLoad<TypedMemoryRead?> { presented ? detailValue : .unconfigured }
    public var originals: MemoryLoad<[TypedMemoryCommand]> { presented ? originalValues : .unconfigured }
    public var managementOriginals: MemoryLoad<[TypedMemoryManagementPending]> { presented ? managementOriginalValues : .unconfigured }
    public var saveState: MemorySaveState { presented ? saveValue : .unconfigured }
    public var managementState: TypedMemoryManagementState { presented ? managementValue : .unknown }
    public var hasMore: Bool { presented && !working && page != nil }

    public func enterSurface() -> TypedMemorySurface? {
        let original = epoch
        guard current,epoch == original else { return nil }
        epoch = UUID();client.retirePresentation()
        let surface = TypedMemorySurface(owner:id,epoch:epoch)
        guard present(surface,{ clearValues();working = false }) else { return nil }
        return surface
    }
    public func leaveSurface(_ surface: TypedMemorySurface?) {
        guard let surface,owns(surface) else { return }
        epoch = UUID();client.retirePresentation()
        _ = present(TypedMemorySurface(owner:id,epoch:epoch),{ clearValues();working = false })
    }
    private func clearValues() {
        page = nil;itemValues = .unconfigured;detailValue = .unconfigured
        originalValues = .unconfigured;managementOriginalValues = .unconfigured
        saveValue = .ready;managementValue = .ready
    }
    public func invalidate() {
        guard !invalidating else { return }
        invalidating = true // fence before observable writes can reenter this method
        active = false;epoch = UUID();working = false;visibleEpoch = nil;clearValues();client.invalidate()
    }
    public func suspendForBackground() { invalidate() }
    private func owns(_ surface: TypedMemorySurface) -> Bool {
        guard surface.owner == id,surface.epoch == epoch,current else { return false }
        return active && surface.epoch == epoch
    }
    private func begin(_ surface: TypedMemorySurface?) -> TypedMemorySurface? {
        guard let surface,owns(surface),!working else { return nil }
        working = true;return surface
    }
    /// Observation can synchronously enter a newer surface. Hide values before
    /// mutating them; publish only the original surface stamp afterward. If an
    /// observer supersedes this stamp, getters withhold all older values.
    @discardableResult private func present(_ surface: TypedMemorySurface,_ change: () -> Void) -> Bool {
        guard owns(surface) else { return false }
        // willSet observers run before the old value changes. A nested surface
        // may retire/clear private values immediately, but must not recursively
        // notify the same still-running observer. Its next action publishes its
        // own stamp; the older outer publication remains withheld.
        if publishing { change();return owns(surface) }
        publishing = true
        defer { publishing = false }
        visibleEpoch = nil
        guard owns(surface) else { return false }
        change()
        guard owns(surface) else { return false }
        visibleEpoch = surface.epoch
        return owns(surface) && visibleEpoch == surface.epoch
    }

    public func loadItems(surface: TypedMemorySurface?,more: Bool = false) async {
        guard let surface = begin(surface) else { return }
        let cursor: TypedMemoryCursor?
        let previous: [TypedMemoryRead]
        if more {
            guard let next = page,case .loaded(let values) = itemValues else { working = false;return }
            cursor = next;previous = values
        } else { cursor = nil;previous = [] }
        guard present(surface,{ itemValues = .loading }) else { return }
        do {
            let result = try await client.list(limit:pageSize,after:cursor,binding:binding)
            guard owns(surface) else { return }
            present(surface,{ page = result.next;itemValues = .loaded(previous + result.items);working = false })
        } catch {
            present(surface,{ page = nil;itemValues = .failed;working = false })
        }
    }
    public func loadDetail(itemID: String,surface: TypedMemorySurface?) async {
        guard let surface = begin(surface) else { return }
        guard present(surface,{ detailValue = .loading;managementValue = .ready }) else { return }
        do {
            let value = try await client.detail(itemID:itemID,binding:binding)
            guard owns(surface) else { return }
            present(surface,{ detailValue = .loaded(value);working = false })
        } catch { present(surface,{ detailValue = .failed;working = false }) }
    }
    public func loadOriginals(surface: TypedMemorySurface?) {
        guard let surface = begin(surface) else { return }
        do {
            let saves = try client.pending(binding:binding)
            guard owns(surface) else { return }
            let management = try client.managementPending(binding:binding)
            guard owns(surface) else { return }
            present(surface,{ originalValues = .loaded(saves);managementOriginalValues = .loaded(management);working = false })
        } catch {
            present(surface,{ originalValues = .failed;managementOriginalValues = .failed;working = false })
        }
    }
    private func selectedTravel() throws -> (CapturedTravelSelection,MemoryTravelSelection) {
        let capture = try travel.capture()
        guard let value = capture.context?.value else { throw MemoryFailure.invalidInput }
        try travel.validate(capture)
        return (capture,try MemoryTravelSelection(id:value.id,expectedVersion:Int64(value.version)))
    }
    public func prepareSave(optionID: UUID,text: String,occurredAt: String,surface: TypedMemorySurface?) throws -> TypedMemorySaveWork {
        guard let surface,owns(surface),!working,let option = configuredOptions.first(where:{ $0.id == optionID }) else { throw MemoryFailure.staleBinding }
        let capture: CapturedTravelSelection?,context: MemoryTravelSelection?
        switch option.scope {
        case .longTerm:capture = nil;context = nil
        case .selectedTravel:let selected = try selectedTravel();capture = selected.0;context = selected.1
        }
        let command = try TypedMemoryCommand(operationID:UUID().uuidString,itemID:UUID().uuidString,subject:option.subject,
            slot:option.slot,text:text,occurredAt:occurredAt,kind:option.kind,travelContext:context)
        guard owns(surface),!working else { throw MemoryFailure.staleBinding }
        return TypedMemorySaveWork(surface:surface,command:command,travel:capture)
    }
    public func performSave(_ work: TypedMemorySaveWork) async {
        guard let surface = begin(work.surface) else { return }
        guard present(surface,{ saveValue = .saving }) else { return }
        do {
            if let captured = work.travel { try travel.validate(captured) }
            guard owns(surface) else { return }
            let result = try await client.save(work.command,binding:binding)
            guard owns(surface) else { return }
            present(surface,{ publish(result);working = false })
        } catch { present(surface,{ saveValue = saveFailure(error);working = false }) }
    }
    private func publish(_ result: MemorySaveResult) {
        switch result {
        case .saved:saveValue = .saved
        case .candidate:saveValue = .candidate
        case .notObserved:saveValue = .notObserved
        case .rejected:saveValue = .rejected
        }
    }
    private func saveFailure(_ error: any Error) -> MemorySaveState {
        if let error = error as? MemoryFailure {
            switch error {
            case .rejected:return .rejected
            case .invalidInput:return .failed
            case .pendingRequiresQuery:return .needsOriginalQuery
            default:return .unknown
            }
        }
        return .unknown
    }
    public func querySave(operationID: String,surface: TypedMemorySurface?) async {
        guard let surface = begin(surface) else { return }
        guard present(surface,{ saveValue = .saving }) else { return }
        do {
            let result = try await client.query(operationID:operationID,binding:binding)
            guard owns(surface) else { return }
            present(surface,{ publish(result);working = false })
        } catch { present(surface,{ saveValue = .unknown;working = false }) }
    }
    public func prepareManagement(_ operation: TypedMemoryOperation,text: String? = nil,surface: TypedMemorySurface?) throws -> TypedMemoryManagementWork {
        guard let surface,owns(surface),!working,presented,case .loaded(let value) = detailValue,let read = value else { throw MemoryFailure.staleBinding }
        try client.validateRead(read,binding:binding)
        let capture: CapturedTravelSelection?,context: MemoryTravelSelection?
        if operation == .edit,case .travel(let original) = read.item.scope {
            let selected = try selectedTravel()
            guard Data(selected.1.id.utf8) == Data(original.id.utf8) else { throw MemoryFailure.invalidInput }
            capture = selected.0;context = selected.1
        } else { capture = nil;context = nil }
        guard owns(surface),!working else { throw MemoryFailure.staleBinding }
        return TypedMemoryManagementWork(surface:surface,read:read,operation:operation,text:text,travel:capture,travelValue:context)
    }
    public func performManagement(_ work: TypedMemoryManagementWork) async {
        guard let surface = begin(work.surface) else { return }
        guard present(surface,{ managementValue = .working }) else { return }
        do {
            if let captured = work.travel { try travel.validate(captured) }
            guard owns(surface) else { return }
            let result = try await client.manage(work.operation,read:work.read,text:work.text,travelContext:work.travelValue,binding:binding)
            guard owns(surface) else { return }
            present(surface,{ detailValue = .unconfigured;publish(result);working = false })
        } catch { present(surface,{
            detailValue = .unconfigured
            if let failure = error as? MemoryFailure,failure == .pendingRequiresQuery { managementValue = .needsOriginalQuery }
            else { managementValue = .unknown }
            working = false
        }) }
    }
    private func publish(_ result: TypedMemoryManagementResult) {
        switch result {
        case .historicalReceipt(let receipt):managementValue = .historical(receipt)
        case .notObserved:managementValue = .notObserved
        case .rejected:managementValue = .rejected
        }
    }
    public func queryManagement(actionID: String,surface: TypedMemorySurface?) async {
        guard let surface = begin(surface) else { return }
        guard present(surface,{ managementValue = .working }) else { return }
        do {
            let result = try await client.queryManagement(actionID:actionID,binding:binding)
            guard owns(surface) else { return }
            present(surface,{ publish(result);working = false })
        } catch { present(surface,{ managementValue = .unknown;working = false }) }
    }
}
