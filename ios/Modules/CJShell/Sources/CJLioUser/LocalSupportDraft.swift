import Observation

@MainActor public struct LocalSupportDraftStorage {
    let load: () throws -> String?
    let save: (String) throws -> Void
    let clear: () throws -> Void

    public init(load: @escaping () throws -> String?, save: @escaping (String) throws -> Void,
                clear: @escaping () throws -> Void) {
        self.load = load
        self.save = save
        self.clear = clear
    }
}

@MainActor @Observable
final class LocalSupportDraft {
    enum Problem { case tooLong, cannotLoad, cannotSave, cannotClear }

    static let limit = 1000
    private let storage: LocalSupportDraftStorage
    private(set) var text = ""
    private(set) var canEdit = false
    private(set) var problem: Problem?
    private var clearFailed = false

    var canClear: Bool { canEdit && (!text.isEmpty || clearFailed) }

    init(storage: LocalSupportDraftStorage) { self.storage = storage }

    func load() {
        guard !canEdit else { return }
        do {
            let previous = try storage.load()
            guard previous?.count ?? 0 <= Self.limit else {
                problem = .cannotLoad
                return
            }
            text = previous ?? ""
            canEdit = true
            problem = nil
        } catch {
            problem = .cannotLoad
        }
    }

    func edit(_ value: String) {
        guard canEdit else { return }
        guard value.count <= Self.limit else {
            problem = .tooLong
            return
        }
        text = value
        if value.isEmpty {
            clear()
            return
        }
        do {
            try storage.save(value)
            clearFailed = false
            problem = nil
        } catch {
            problem = .cannotSave
        }
    }

    func clear() {
        guard canEdit else { return }
        do {
            try storage.clear()
            text = ""
            clearFailed = false
            problem = nil
        } catch {
            clearFailed = true
            problem = .cannotClear
        }
    }
}
