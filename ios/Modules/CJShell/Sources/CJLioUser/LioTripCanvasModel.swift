import Foundation
import Observation

/// #1995: `G2CTripCanvasEnabled` in the build's Info.plist; off unless it says YES. Off, the Trips tab is exactly what
/// it was. JT decides which build turns it on.
enum LioTripCanvasFeature {
    static let infoKey = "G2CTripCanvasEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool { enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) }
}

/// The trip canvases of the signed-in account, on this phone: one file next to the trip home's own, in the same
/// folder, so account cleanup removes it with the trip home (`LioTripHomeCleanup`). Another account can neither read
/// nor write it. One canvas per trip; the newest edited comes first.
@MainActor public struct LioTripCanvasStore {
    public static let fileName = "trip-canvas.json"
    static let maximumCount = 50
    static let currentVersion = 1

    let directory: URL
    /// Distinguishes stores made for different host sessions, even for the same folder.
    let id = UUID()
    private let isCurrent: @MainActor () -> Bool
    private var file: URL { directory.appendingPathComponent(Self.fileName) }

    public init(directory: URL, isCurrent: @escaping @MainActor () -> Bool) {
        self.directory = directory
        self.isCurrent = isCurrent
    }

    /// Beside the trip home's file; nil when the build has no account folder (previews keep nothing).
    init?(tripHome: LioTripHomeStore?) {
        guard let tripHome else { return nil }
        self.init(directory: tripHome.directory, isCurrent: { tripHome.current })
    }

    var current: Bool { isCurrent() }

    /// The file was written by a newer app: it is never rewritten, so its canvases stay on the phone.
    struct UnsupportedVersion: Error, Equatable { let version: Int }

    private struct Header: Codable { let version: Int }
    private struct Archive: Codable { let version: Int; let canvases: [LioTripCanvas] }
    private struct Lenient<Value: Decodable>: Decodable {
        let value: Value?
        init(from decoder: Decoder) throws { value = try? Value(from: decoder) }
    }
    private struct ArchiveRead: Decodable { let version: Int; let canvases: [Lenient<LioTripCanvas>] }

    /// A missing or damaged file reads as no canvases (the traveller starts again from the saved plan); a file this
    /// build cannot read (a newer app's, or one the phone cannot open now) throws, so nothing is written over it.
    func load() throws -> [LioTripCanvas] {
        guard isCurrent() else { throw CancellationError() }
        let data: Data
        do {
            data = try Data(contentsOf: file)
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return []
        }
        let decoder = JSONDecoder()
        guard let header = try? decoder.decode(Header.self, from: data) else { return [] }
        guard header.version == Self.currentVersion else { throw UnsupportedVersion(version: header.version) }
        guard let archive = try? decoder.decode(ArchiveRead.self, from: data) else { return [] }
        return archive.canvases.compactMap(\.value).filter(\.isValid)
    }

    func canvas(for tripID: String) throws -> LioTripCanvas? { try load().first { $0.tripID == tripID } }

    func save(_ canvas: LioTripCanvas) throws {
        let others = try load().filter { $0.tripID != canvas.tripID }
        try write(Array(([canvas] + others).prefix(Self.maximumCount)))
    }

    func remove(_ tripID: String) throws {
        let all = try load()
        guard all.contains(where: { $0.tripID == tripID }) else { return }
        try write(all.filter { $0.tripID != tripID })
    }

    private func write(_ canvases: [LioTripCanvas]) throws {
        guard isCurrent() else { throw CancellationError() }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var stored = directory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try stored.setResourceValues(attributes)
        let data = try JSONEncoder().encode(Archive(version: Self.currentVersion, canvases: canvases))
        #if os(iOS)
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file, options: .atomic)
        #endif
    }
}

/// One trip's canvas as the screen edits it. Every change is one step: it is written to the phone, and the step before
/// it is kept so the last change can be undone. A canvas that could not be read from the phone is shown from the saved
/// plan but not written, so an unreadable file is never overwritten.
@MainActor @Observable
final class LioTripCanvasModel {
    /// What the last change did, for the "· Undo" bar.
    struct Notice: Equatable {
        enum Kind: Equatable { case added, moved, edited, removed, dayAdded }
        let kind: Kind
        let nameZH: String
        let nameEN: String

        func text(_ language: LioLanguage) -> String {
            let name = language == .chinese ? nameZH : nameEN
            switch kind {
            case .added: return language.text("Added “\(name)”", "已加入「\(name)」")
            case .moved: return language.text("Moved “\(name)”", "已移动「\(name)」")
            case .edited: return language.text("Changed “\(name)”", "已修改「\(name)」")
            case .removed: return language.text("Removed “\(name)”", "已删除「\(name)」")
            case .dayAdded: return language.text("Added a day", "已加一天")
            }
        }
    }

    private let store: LioTripCanvasStore?
    private let makeID: @MainActor () -> String
    private(set) var canvas: LioTripCanvas
    private var before: LioTripCanvas?
    /// The file exists but could not be read: nothing is written until it can be.
    private var unread = false
    /// Set when the last write did not reach the phone; cleared by the next one that does.
    private(set) var saveFailed = false
    private(set) var notice: Notice?

    init(plan: LioPlanSummary?, store: LioTripCanvasStore?, makeID: @escaping @MainActor () -> String = { "p-" + UUID().uuidString }) {
        self.store = store
        self.makeID = makeID
        let tripID = plan?.tripID ?? LioTripCanvas.standaloneID
        var stored: LioTripCanvas?
        var unreadable = false
        if let store {
            do {
                stored = try store.canvas(for: tripID)
            } catch {
                unreadable = true
            }
        }
        unread = unreadable
        if let plan {
            canvas = LioTripCanvas.resolved(stored: stored, plan: plan)
        } else {
            canvas = stored ?? LioTripCanvas(emptyTripID: tripID)
        }
    }

    var storeID: UUID? { store?.id }
    /// The phone is keeping what the traveller changes.
    var persists: Bool { store?.current == true && !unread }
    var canUndo: Bool { before != nil }

    // MARK: - Changes

    func move(_ id: String, toDay dayID: String, at index: Int) {
        apply(.moved, point: id) { $0.move(id, toDay: dayID, at: index) }
    }

    func moveToEnd(_ id: String, ofDay dayID: String) {
        apply(.moved, point: id) { $0.moveToEnd(id, ofDay: dayID) }
    }

    func moveToWishlist(_ id: String) {
        apply(.moved, point: id) { $0.moveToWishlist(id) }
    }

    /// A point dropped on another takes its position.
    func drop(_ id: String, onto target: String) {
        apply(.moved, point: id) { $0.move(id, onto: target) }
    }

    func shift(_ id: String, by step: Int) {
        apply(.moved, point: id) { $0.shift(id, by: step) }
    }

    func remove(_ id: String) {
        apply(.removed, point: id) { $0.remove(id) != nil }
    }

    func addWish(_ name: String) {
        let id = makeID()
        apply(.added, point: id) { $0.addWish(id: id, name: name) }
    }

    func edit(_ id: String, name: String? = nil, in language: LioLanguage = .chinese, time: String?? = nil) {
        apply(.edited, point: id) { $0.edit(id, name: name, in: language, time: time) }
    }

    func addDay() {
        apply(.dayAdded, point: nil) { $0.addDay() != nil }
    }

    /// Goes back one change. Undoing is itself not undoable.
    func undo() {
        guard let before else { return }
        canvas = before
        self.before = nil
        notice = nil
        write()
    }

    func dismissNotice() { notice = nil }

    /// Runs one change on a copy; only a change that did something is kept, noticed and written.
    private func apply(_ kind: Notice.Kind, point id: String?, _ mutate: (inout LioTripCanvas) -> Bool) {
        var next = canvas
        let named = id.flatMap { canvas.point($0) }
        guard mutate(&next) else { return }
        let point = id.flatMap { next.point($0) } ?? named
        before = canvas
        canvas = next
        notice = Notice(kind: kind, nameZH: point?.nameZH ?? "", nameEN: point?.name(.english) ?? "")
        write()
    }

    private func write() {
        guard let store else { return }
        guard !unread else {
            saveFailed = true
            return
        }
        do {
            try store.save(canvas)
            saveFailed = false
        } catch {
            saveFailed = true
        }
    }
}
