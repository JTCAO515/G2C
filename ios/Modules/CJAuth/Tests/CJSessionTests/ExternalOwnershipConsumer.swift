import CJSession

// Also typechecked separately with a different package name, not @testable.
@MainActor func externalOwnershipConsumer(_ lifecycle: SessionLifecycle, _ original: SessionOperation) -> Bool {
    lifecycle.ownsOperation(original)
}
