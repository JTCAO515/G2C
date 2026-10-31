import Foundation
import Observation
import CJAPI

public enum NeedsViewState: Equatable, Sendable {
    case unavailable, idle, loading, loaded, missing, cancelled, failed, saveRejected, invalidInput, unknown, conflict, confirmed
    public func message(_ l: NeedsLanguage) -> String {
        switch self {
        case .unavailable: l.text("真实保存尚未启用。", "Live saving is not enabled.")
        case .idle: l.text("可只修改已经明确的条件。", "Change only the details you know.")
        case .loading: l.text("正在读取或核对…", "Reading or reconciling…")
        case .loaded: l.text("已读取用户提供的条件。", "User-provided details loaded.")
        case .missing: l.text("本次读取未找到记录。", "No record observed in this read.")
        case .cancelled: l.text("已停止读取。", "Read cancelled.")
        case .failed: l.text("暂时无法读取；没有更改条件。", "Unable to read; details were not changed.")
        case .saveRejected: l.text("原保存明确失败；原动作仍保留，请明确审阅新的修改。", "The original save was rejected. Its bytes are preserved; explicitly review any new correction.")
        case .invalidInput: l.text("请检查已修改字段的格式、状态和输入说明；无需补齐其它条件。", "Check the format, state and source statement of edited fields. Other details may remain incomplete.")
        case .unknown: l.text("结果尚未核定。仅核对原动作，不重新发送。", "Result unknown. Reconcile the original action; do not resend.")
        case .conflict: l.text("版本或原输入冲突。保留你的编辑，请对照最新版本重新审阅。", "Version or original-input conflict. Your edits are preserved; review against the latest version.")
        case .confirmed: l.text("原动作与历史版本已核对。", "Original action verified against its historical revision.")
        }
    }
}
public struct NeedsPresentationWork: Sendable {
    let lifetime: UUID
    let request: UUID
    let owner: UUID
    let work: NeedsWork
    let keepsEditor: Bool
}

@MainActor @Observable public final class NeedsPresentation {
    public private(set) var binding: NeedsBinding?
    public private(set) var selectedNeedsID: String?
    public private(set) var selectedActionID: String?
    public private(set) var snapshot: NeedsSchema.NeedsSnapshot?
    public private(set) var revision: NeedsSchema.NeedsRevision?
    public private(set) var receipt: NeedsSchema.NeedsReceipt?
    public private(set) var state: NeedsViewState = .unavailable
    public private(set) var pendingState: NeedsViewState = .unavailable
    public private(set) var pendingActions: [NeedsPending] = []
    public private(set) var verifiedActionIDs: Set<String> = []
    public var draft: NeedsDraft?
    public var canSave: Bool { client?.acceptsUserActions == true }
    private let client: NeedsClient?
    private let owner = UUID()
    private var lifetime = UUID()
    private var request = UUID()
    private var started: UUID?
    private var pendingRequest = UUID()
    public init(client: NeedsClient?) { self.client = client }
    public func replace(binding: NeedsBinding?) {
        client?.invalidate(); lifetime = UUID(); request = UUID(); started = nil
        self.binding = binding; selectedNeedsID = nil; selectedActionID = nil
        snapshot = nil; revision = nil; receipt = nil; draft = nil
        pendingActions = []; pendingState = .unavailable
        state = binding != nil && client?.acceptsUserActions == true ? .idle : .unavailable
        verifiedActionIDs = []
    }
    /// Explicit host selection; a new record uses version zero only when the user chooses to create it.
    public func beginNew(id: String) {
        if client?.acceptsUserActions == true { client?.retireWork() } else { client?.invalidate() }
        request = UUID(); started = nil
        selectedNeedsID = id; selectedActionID = nil; snapshot = nil; revision = nil; receipt = nil
        draft = NeedsDraft(needsID: id, expectedVersion: 0); state = .idle
    }
    /// Explicit user replacement of the local editor, never an automatic CAS retry.
    public func beginCorrectionFromSnapshot() -> Bool {
        guard let client, let snapshot, binding != nil else { return false }
        client.retireWork(); request = UUID(); started = nil
        selectedNeedsID = snapshot.needs_id; selectedActionID = nil
        draft = NeedsDraft(needsID: snapshot.needs_id, expectedVersion: snapshot.version, fields: snapshot.fields)
        receipt = nil; revision = nil; state = .idle
        return true
    }
    private func wrap(_ work: NeedsWork, keepsEditor: Bool = false) -> NeedsPresentationWork {
        request = UUID(); started = nil; state = .loading
        return .init(lifetime: lifetime, request: request, owner: owner, work: work, keepsEditor: keepsEditor)
    }
    public func prepareDetail(id: String) -> NeedsPresentationWork? {
        guard let client, let binding else { state = .unavailable; return nil }
        if selectedNeedsID.map({ same($0, id) }) != true { draft = nil }
        selectedNeedsID = id; selectedActionID = nil; snapshot = nil; revision = nil; receipt = nil
        return wrap(client.prepareDetail(id: id, binding: binding))
    }
    public func prepareRevision(id: String, version: Int) -> NeedsPresentationWork? {
        guard let client, let binding else { state = .unavailable; return nil }
        if selectedNeedsID.map({ same($0, id) }) != true { draft = nil }
        selectedNeedsID = id; selectedActionID = nil; snapshot = nil; revision = nil; receipt = nil
        return wrap(client.prepareRevision(id: id, version: version, binding: binding))
    }
    public func prepareQuery(actionID: String, preservingEditor: Bool = false) -> NeedsPresentationWork? {
        guard let client, let binding else { state = .unavailable; return nil }
        if !preservingEditor, let original = pendingActions.first(where: { same($0.actionID, actionID) }) {
            if selectedNeedsID.map({ same($0, original.needsID) }) != true { draft = nil }
            selectedNeedsID = original.needsID
        }
        selectedActionID = actionID; receipt = nil; revision = nil
        if !preservingEditor { snapshot = nil }
        return wrap(client.prepareQuery(actionID: actionID, binding: binding), keepsEditor: preservingEditor)
    }
    public func prepareReplay(actionID: String, preservingEditor: Bool = false) -> NeedsPresentationWork? {
        guard let client, client.acceptsUserActions, let binding,
              verifiedActionIDs.contains(actionID) else { return nil }
        selectedActionID = actionID; receipt = nil
        verifiedActionIDs.remove(actionID)
        return wrap(client.prepareReplay(actionID: actionID, binding: binding), keepsEditor: preservingEditor)
    }
    /// Keep a frozen original across errors. No automatic new ID or version update.
    public func prepareSave(actionID: String) -> NeedsPresentationWork? {
        guard let client, let binding, let draft else { state = .unavailable; return nil }
        do {
            let pending = try draft.freeze(actionID: actionID)
            selectedActionID = pending.actionID; receipt = nil
            return wrap(client.prepareManualAction(pending, binding: binding))
        } catch { state = .invalidInput; return nil }
    }
    private func matches(_ work: NeedsPresentationWork) -> Bool {
        owner == work.owner && lifetime == work.lifetime && request == work.request && binding == work.work.binding
    }
    private func current(_ work: NeedsPresentationWork) -> Bool {
        // The trusted binding callback may synchronously replace selection/identity.
        matches(work) && client?.owns(work.work) == true && matches(work)
    }
    public func perform(_ work: NeedsPresentationWork) async {
        guard current(work), started != work.request, let client else { return }
        started = work.request
        do {
            let result = try await client.perform(work.work)
            guard current(work) else { return }
            switch result {
            case .detail(let value):
                snapshot = value; state = value == nil ? .missing : .loaded
                // Never overwrite a correction when loading latest data after a conflict.
                if draft == nil, let value { draft = .init(needsID: value.needs_id, expectedVersion: value.version, fields: value.fields) }
            case .revision(let value): revision = value; state = value == nil ? .missing : .loaded
            case .confirmed(let receipt, let revision):
                if !work.keepsEditor {
                    if selectedNeedsID.map({ same($0, revision.needs_id) }) != true { draft = nil }
                    selectedNeedsID = revision.needs_id
                }
                self.receipt = receipt; self.revision = revision; state = .confirmed
                verifiedActionIDs.insert(receipt.action_id)
            case .rejectedOriginal(let original, let status, _):
                selectedActionID = original.actionID; receipt = nil; revision = nil
                verifiedActionIDs.remove(original.actionID)
                state = status == 409 ? .conflict : .saveRejected
            case .notObserved: state = .unknown
            }
        } catch {
            guard current(work) else { return }
            if let failure = error as? NeedsFailure, case .rejected(409, _) = failure { state = .conflict; return }
            if error as? NeedsFailure == .liveWriteUnavailable { state = .unavailable; return }
            switch work.work.kind {
            case .query, .submit, .replay: state = .unknown
            case .detail, .revision: state = error is CancellationError ? .cancelled : .failed
            }
        }
    }
    public func loadPending() {
        guard let client, let binding else { pendingState = .unavailable; return }
        let lifetime = lifetime; let request = request; let pendingRequest = UUID(); self.pendingRequest = pendingRequest
        pendingState = .loading
        do {
            let records = try client.pending(binding: binding)
            guard self.lifetime == lifetime, self.request == request, self.binding == binding, self.pendingRequest == pendingRequest else { return }
            pendingActions = records; pendingState = .loaded
        } catch {
            guard self.lifetime == lifetime, self.request == request, self.binding == binding, self.pendingRequest == pendingRequest else { return }
            pendingState = .failed
        }
    }
}
