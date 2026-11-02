import Foundation

struct TypedMemoryQuestion: Identifiable {
    let options: [TypedMemoryManualOption]
    var id: UUID { options[0].id }
    var kind: String { options[0].kind.rawValue }
    var optionIDs: Set<UUID> { Set(options.map(\.id)) }

    private struct Key: Hashable { let subject, slot, kind: String }
    static func choices(_ options: [TypedMemoryManualOption]) -> [Self] {
        var groups: [Key: [TypedMemoryManualOption]] = [:]
        var order: [Key] = []
        for option in options where option.kind.rawValue != "inference" {
            let key = Key(subject: option.subject, slot: option.slot, kind: option.kind.rawValue)
            if groups[key] == nil { order.append(key) }
            groups[key, default: []].append(option)
        }
        var selected: [Key] = [], kinds = Set<String>()
        for key in order where kinds.insert(key.kind).inserted { selected.append(key) }
        for key in order where !selected.contains(key) { selected.append(key) }
        return selected.prefix(3).map { .init(options: groups[$0]!) }
    }
}

extension TypedMemoryContainerHost {
    var collectionQuestions: [TypedMemoryQuestion] { TypedMemoryQuestion.choices(options) }
}
