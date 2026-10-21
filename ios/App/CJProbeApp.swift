import SwiftUI
import CJProbeUI

@main
struct CJProbeApp: App {
    var body: some Scene {
        WindowGroup { ProbeView(environment: ProcessInfo.processInfo.environment) }
    }
}
