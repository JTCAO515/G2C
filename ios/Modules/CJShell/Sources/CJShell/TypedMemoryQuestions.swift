import Foundation

struct TypedMemoryQuestion: Identifiable {
    let options: [TypedMemoryManualOption]
    var followUp = false
    var id: String { options[0].id.uuidString + (followUp ? ":additional" : ":first") }
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
        var result: [Self] = selected.prefix(3).map { .init(options: groups[$0]!) }
        if result.count == 1 { result.append(.init(options: result[0].options, followUp: true)) }
        return result
    }
}

extension TypedMemoryContainerHost {
    var collectionQuestions: [TypedMemoryQuestion] { TypedMemoryQuestion.choices(options) }
}
