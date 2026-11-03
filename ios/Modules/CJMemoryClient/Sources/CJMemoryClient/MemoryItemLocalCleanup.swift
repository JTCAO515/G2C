import Foundation

/// Item-specific encrypted manual/edit originals only. Other memories, history
/// consent, erasure recovery metadata and shared keys remain intact. The Root
/// retires its content writers before requesting this operation.
@MainActor public final class MemoryItemLocalCleanup {
    private let manual: MemoryPendingStore
    private let management: MemoryManagementPendingStore
    private let typed: TypedMemoryPendingStore
    public init(manual: MemoryPendingStore, management: MemoryManagementPendingStore, typed: TypedMemoryPendingStore) {
        self.manual = manual; self.management = management; self.typed = typed
    }
    private struct Step {
        let validate: () throws -> Void
        let perform: () throws -> Void
    }
    private func step<Record>(_ store: MemoryEncryptedRecords<Record>, matches: (Record) throws -> Bool) throws -> Step {
        let plan = try store.prepareRemoval(where: matches)
        return Step(validate: { try store.validateRemoval(plan) }, perform: { try store.performRemoval(plan) })
    }
    private func rejectionStep<Record>(_ store: MemoryEncryptedRecords<Record>, domain: String,
        matches: (Record) throws -> Bool) throws -> Step? {
        let rejected: MemoryEncryptedRecords<MemoryRejectedOperation<Record>>? = try store.adjacentRecords(domain: domain, create: false)
        guard let rejected else { return nil }
        return try step(rejected) { try matches($0.original) }
    }
    public func clear(_ authorization: MemoryErasureLocalAuthorization, validateCurrent: () throws -> Void) throws {
        try authorization.validate()
        try validateCurrent()
        try manual.validate(authorization.binding); try management.validate(authorization.binding); try typed.validate(authorization.binding)
        let itemID = authorization.itemID
        var steps: [Step] = []
        steps.append(try step(manual.storage) { same($0.itemID, itemID) })
        if let step = try rejectionStep(manual.storage, domain: "CJMemoryRejections", matches: { same($0.itemID, itemID) }) { steps.append(step) }
        steps.append(try step(management.storage) { same(try $0.action.header.item, itemID) })
        if let step = try rejectionStep(management.storage, domain: "CJMemoryManagementRejections", matches: { same(try $0.action.header.item, itemID) }) { steps.append(step) }
        steps.append(try step(typed.storage) { same($0.itemID, itemID) })
        if let step = try rejectionStep(typed.storage, domain: "CJMemoryTypedRejectionsV2", matches: { same($0.itemID, itemID) }) { steps.append(step) }
        if let management = try typed.managementRecords(create: false) {
            steps.append(try step(management) { same(try $0.action.header.item, itemID) })
            if let step = try rejectionStep(management, domain: "CJMemoryTypedManagementRejectionsV2", matches: { same(try $0.action.header.item, itemID) }) { steps.append(step) }
        }
        // Key/authorization callbacks may reenter. Finish every such callback
        // before validating every physical plan, then unlink without callbacks.
        try authorization.validate()
        try validateCurrent()
        for step in steps { try step.validate() }
        for step in steps { try step.perform() }
    }
}
