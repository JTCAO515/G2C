import Foundation
import Testing
@testable import CJNeedsClient

@MainActor @Suite struct PendingDirectoryTests {
    @Test(arguments: [true, false], [2, 3])
    func callbackDirectoryReplacementFailsEvenForEmptyRead(initiallyEmpty: Bool, callbackNumber: Int) throws {
        let h = try Harness() // Intentionally retain both displaced and canonical directories.
        let initial = try h.store()
        if !initiallyEmpty { try initial.append(original("old-original")) }
        let incoming = h.root.appendingPathExtension("incoming")
        let retired = h.root.appendingPathExtension("retired")
        try FileManager.default.createDirectory(at: incoming, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let incomingStore = try NeedsPendingStore(directory: incoming, maximumBytes: 524_288, maximumRecords: 20,
                                                  namespace: h.namespace, keyID: h.keyID, key: { h.key })
        let action = try original("existing-original"); try incomingStore.append(action)
        let filename = try #require(FileManager.default.contentsOfDirectory(atPath: incoming.path).first)
        let originalCiphertext = try Data(contentsOf: incoming.appendingPathComponent(filename))
        var callbacks = 0; var swapped = false; var credentialCalls = 0
        let wire = Interceptor { _, _, _ in Issue.record("pending read must not dispatch"); throw NeedsFailure.exchangeUnknown }
        let client = try h.client(wire, store: initial, credentials: { _ in credentialCalls += 1; return "synthetic" }, bindingCallback: {
            callbacks += 1
            if callbacks == callbackNumber && !swapped {
                try! FileManager.default.moveItem(at: h.root, to: retired)
                try! FileManager.default.moveItem(at: incoming, to: h.root)
                swapped = true
            }
            return h.binding
        })
        let model = NeedsPresentation(client: client); model.replace(binding: h.binding); model.loadPending()
        #expect(swapped && model.pendingState == .failed)
        #expect(credentialCalls == 0)
        let fresh = try h.store().pending()
        #expect(fresh.count == 1 && fresh[0].originalUTF8 == action.originalUTF8)
        #expect(try Data(contentsOf: h.root.appendingPathComponent(filename)) == originalCiphertext)
        #expect(try FileManager.default.contentsOfDirectory(atPath: retired.path).count == (initiallyEmpty ? 0 : 1))
        print("PRESERVED initiallyEmpty=\(initiallyEmpty) callback=\(callbackNumber) state=\(model.pendingState) canonical=\(h.root.path) retired=\(retired.path)")
    }
    @Test func unchangedEmptyDirectoryStillLoads() throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in Issue.record("no dispatch"); throw NeedsFailure.exchangeUnknown }
        let model = NeedsPresentation(client: try h.client(wire)); model.replace(binding: h.binding); model.loadPending()
        #expect(model.pendingState == .loaded && model.pendingActions.isEmpty)
    }
}
