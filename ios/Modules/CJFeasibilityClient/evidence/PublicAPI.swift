import CJFeasibilityClient
import CJSession
import SwiftUI
@MainActor func host(session: SessionLifecycle, current: @escaping @MainActor () -> FeasibilityBinding?) -> FeasibilityView {
    let closed = FeasibilityModel(session: session, currentBinding: current)
    return FeasibilityView(model: closed, binding: current(), language: .english)
}
