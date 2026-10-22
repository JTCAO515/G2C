import CJSession

// Also typechecked separately under a different package name, no @testable.
@MainActor func externalClearSettlementConsumer(_ lifecycle: SessionLifecycle) -> SessionClearSettlement {
    let result = lifecycle.clearWithSettlement()
    switch result {
    case .cleared, .replaced: return result
    case .failed(let failure): return .failed(failure)
    }
}
