import Foundation
import Testing
@testable import CJMessageClient

private enum Refused: Error, Equatable { case unavailable, unknown }
private enum HashOnly: LocalJournalCleanupPolicy {
    static var unavailable: Refused { .unavailable }
    static var outcomeUnknown: Refused { .unknown }
    static var recordExtension: String { "rec" }
}
private enum HashOrUUID: LocalJournalCleanupPolicy {
    static var unavailable: Refused { .unavailable }
    static var outcomeUnknown: Refused { .unknown }
    static var recordExtension: String { "rec" }
    static var acceptsUUIDStem: Bool { true }
}

@MainActor private final class JournalDirectory {
    let parent = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
    var root: URL { parent.appendingPathComponent("journal") }
    init() throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    }
    deinit { try? FileManager.default.removeItem(at: parent) }
    func write(_ name: String) throws { try Data("x".utf8).write(to: root.appendingPathComponent(name)) }
    func names() throws -> Set<String> { Set(try FileManager.default.contentsOfDirectory(atPath: root.path)) }
}

private let digest = String(repeating: "a1", count: 32)

@MainActor @Suite struct LocalJournalCleanupTests {
    @Test func clearsOnlyExactRecordNames() throws {
        let d = try JournalDirectory()
        try d.write(digest + ".rec"); try d.write(String(repeating: "0", count: 64) + ".rec")
        let cleanup = try LocalJournalCleanup<HashOnly>(root: d.root, suffixes: [])
        try cleanup.clear()
        #expect(try d.names().isEmpty)
        #expect(throws: Refused.unavailable) { try cleanup.checkReadable() }
    }

    @Test(arguments: [
        "notadigest.rec",                                    // right suffix, stem is not a digest
        String(repeating: "B2", count: 32) + ".rec",         // uppercase digest (distinct on case-insensitive volumes)
        String(repeating: "a", count: 63) + ".rec",          // short digest
        String(repeating: "a", count: 65) + ".rec",          // long digest
        digest + "xrec",                                     // extension without its dot
        digest + ".rec.bak",                                 // trailing extension
        digest + ".other",                                   // another family's record
        UUID().uuidString + ".rec",                          // UUID stem where only digests are allowed
    ])
    func foreignNameStopsTheWholeClearBeforeAnyUnlink(name: String) throws {
        let d = try JournalDirectory()
        try d.write(digest + ".rec"); try d.write(name)
        let before = try d.names()
        let cleanup = try LocalJournalCleanup<HashOnly>(root: d.root, suffixes: [])
        #expect(throws: Refused.unavailable) { try cleanup.clear() }
        #expect(try d.names() == before, "nothing may be erased once preflight refuses")
        try FileManager.default.removeItem(at: d.root.appendingPathComponent(name))
        try cleanup.clear()
        #expect(try d.names().isEmpty, "retry stays on the same held target")
    }

    @Test func uuidStemsOnlyWhenThePolicyAllowsThem() throws {
        let d = try JournalDirectory()
        try d.write(UUID().uuidString + ".rec"); try d.write(digest + ".rec")
        try LocalJournalCleanup<HashOrUUID>(root: d.root, suffixes: []).clear()
        #expect(try d.names().isEmpty)
        try d.write("not-a-uuid.rec")
        #expect(throws: Refused.unavailable) { try LocalJournalCleanup<HashOrUUID>(root: d.root, suffixes: []).clear() }
        #expect(try d.names() == ["not-a-uuid.rec"])
    }
}
