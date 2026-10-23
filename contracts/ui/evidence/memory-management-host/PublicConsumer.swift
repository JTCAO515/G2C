// Public APIs only. Caller supplies the real Shell and trusted client/binding.
// Typechecks against localized harness; does not prove canonical App composition.
import Foundation
import CJShell
import CJMemoryClient
@MainActor func mountMemory(shell: ShellState, client: MemoryClient, binding: MemoryBinding,
    current: @escaping @MainActor () -> MemoryBinding?) async {
    let host = MemoryContainerHost(shell: shell)
    _ = host.bind(MemoryContainerBinding(client: client, memory: binding, shellGeneration: shell.generation,
        pageSize: 20, synthetic: false, currentBinding: current))
    let lifetime = host.beginManagementPresentation()
    await host.loadGroups(context: host.captureAction())
    _ = host.managementSelection
    host.loadManagementPending(context: host.captureAction())
    _ = host.managementPending
    host.leaveManagementPresentation(lifetime)
}
#if os(iOS)
import SwiftUI
@MainActor func managementUI(client: MemoryClient, selection: MemoryManagementSelection,
    record: MemoryManagementPending, binding: MemoryBinding) -> some View {
    VStack {
        MemoryManagementControls(client: client, selection: selection, binding: binding, language: .english)
        MemoryManagementRecoveryView(client: client, pending: record, binding: binding, language: .chinese)
    }
}
#endif
