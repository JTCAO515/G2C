import Foundation
import CJAPI

func matches(_ value: String, _ pattern: String) -> Bool {
    value.range(of: pattern, options: .regularExpression) == value.startIndex..<value.endIndex
}
func localDate(_ value: String) -> Bool {
    guard matches(value, "[0-9]{4}-[0-9]{2}-[0-9]{2}") else { return false }
    let parts = value.split(separator: "-").compactMap { Int($0) }
    guard parts.count == 3, parts[0] > 0, (1...12).contains(parts[1]) else { return false }
    let y = parts[0]; let leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
    let days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return (1...days[parts[1] - 1]).contains(parts[2])
}
func localTime(_ value: String) -> Bool {
    matches(value, "(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?")
}
func money(_ value: String) -> Bool { matches(value, "(?:0|[1-9][0-9]{0,14})(?:\\.[0-9]{1,6})?") }
func require(_ valid: Bool) throws { guard valid else { throw NeedsFailure.invalidInput } }

func validateCommand(_ command: NeedsSchema.NeedsCommand) throws {
    try require(needsID(command.action_id) && needsID(command.needs_id) && command.expected_version >= 0 && command.expected_version < Int.max)
    try require(validText(command.source.text))
    let bytes = try encoded(command.changes)
    try require(bytes != Data("{}".utf8))
    // Official types share the same fields. No alternate wire representation or parser.
    let fields = try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: bytes)
    try validateFields(fields, complete: false)
}
func validateSnapshot(_ snapshot: NeedsSchema.NeedsSnapshot) throws {
    guard needsID(snapshot.needs_id), snapshot.version > 0 else { throw NeedsFailure.invalidResponse }
    try validateContent(snapshot.content_utf8_base64, fields: snapshot.fields)
}
func validateRevision(_ revision: NeedsSchema.NeedsRevision) throws {
    guard needsID(revision.needs_id), needsID(revision.action_id), revision.version > 0,
          let bytes = Data(base64Encoded: revision.original_input_utf8_base64), bytes.count <= 131_072,
          String(data: bytes, encoding: .utf8) != nil else { throw NeedsFailure.invalidResponse }
    let original = try JSONDecoder().decode(NeedsSchema.NeedsCommand.self, from: bytes)
    try validateCommand(original)
    guard same(original.action_id, revision.action_id), same(original.needs_id, revision.needs_id),
          original.expected_version == revision.version - 1 else { throw NeedsFailure.invalidResponse }
    try validateContent(revision.content_utf8_base64, fields: revision.fields)
}
private func validateContent(_ base64: String, fields: NeedsSchema.NeedsFields) throws {
    guard let content = Data(base64Encoded: base64), content.count <= 131_072,
          String(data: content, encoding: .utf8) != nil else { throw NeedsFailure.invalidResponse }
    let decoded = try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: content)
    try validateFields(decoded, complete: true)
    guard try encoded(decoded) == encoded(fields) else { throw NeedsFailure.invalidResponse }
}
func validateEvent(_ event: NeedsSchema.NeedsEvent) throws {
    try validate(event.date); try validate(event.time); try validate(event.timezone); try validate(event.place)
}
func validateFields(_ f: NeedsSchema.NeedsFields, complete: Bool) throws {
    if let v = f.party_size { try validate(v) }
    for v in [f.destination_timezone, f.overseas_timezone].compactMap({ $0 }) { try validate(v) }
    if let v = f.budget_currency { try validate(v) }
    for v in [f.budget_total, f.budget_per_person, f.budget_paid].compactMap({ $0 }) { try validate(v) }
    if let v = f.budget_basis { try validate(v) }
    if let v = f.budget_includes { try validate(v) }
    if let v = f.pace { try validate(v) }
    for v in [f.overseas_departure, f.arrival, f.departure].compactMap({ $0 }) { try validateEvent(v) }
    if let companions = f.companions?.additionalProperties {
        try require(companions.count <= 100 && companions.allSatisfy { needsID($0.key) && validText($0.value) })
    }
    func subjects(_ values: [String]) throws {
        try require((1...32).contains(values.count) && Set(values.map { Data($0.utf8) }).count == values.count)
        for value in values {
            if value == "self" || value == "party" { continue }
            try require(value.hasPrefix("companion:"))
            let id = String(value.dropFirst(10)); try require(needsID(id))
            if complete { try require(f.companions?.additionalProperties[id] != nil) }
        }
    }
    if let items = f.fixed_items {
        try require(items.count <= 100 && Set(items.map { Data($0.item_id.utf8) }).count == items.count)
        for item in items {
            try require(needsID(item.item_id) && validText(item.description)); try subjects(item.applies_to)
            try validate(item.locked); try validate(item.booking_status)
            try validateEvent(item.start); try validateEvent(item.end)
        }
    }
    if let items = f.temporary_conditions {
        try require(items.count <= 100 && Set(items.map { Data($0.condition_id.utf8) }).count == items.count)
        for item in items { try require(needsID(item.condition_id) && validText(item.description)); try subjects(item.applies_to) }
    }
}

func validate(_ value: NeedsSchema.NeedsPartySizeObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsPartySizeObservationKnown(let v): try require((1...100_000).contains(v.value))
    }
}

func validate(_ value: NeedsSchema.NeedsTimezoneObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsTimezoneObservationKnown(let v):
        // Fixed wire requires minLength 1; only the producer validates IANA membership.
        // Device tzdb/alias lists must not narrow accepted input or rewrite stored strings.
        try require(!v.value.isEmpty)
    }
}

func validate(_ value: NeedsSchema.NeedsCurrencyObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsCurrencyObservationKnown(let v): try require(matches(v.value, "[A-Z]{3}"))
    }
}

func validate(_ value: NeedsSchema.NeedsMoneyObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsMoneyObservationKnown(let v): try require(money(v.value))
    }
}

func validate(_ value: NeedsSchema.NeedsBudgetBasisObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsBudgetBasisObservationKnown(let v): _ = v
    }
}

func validate(_ value: NeedsSchema.NeedsCoverageObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsCoverageObservationKnown(let v): try require((1...32).contains(v.value.count) && v.value.allSatisfy(validText) && Set(v.value.map { Data($0.utf8) }).count == v.value.count)
    }
}

func validate(_ value: NeedsSchema.NeedsTextObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsTextObservationKnown(let v): try require(validText(v.value))
    }
}

func validate(_ value: NeedsSchema.NeedsLocalDateObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsLocalDateObservationKnown(let v): try require(localDate(v.value))
    }
}

func validate(_ value: NeedsSchema.NeedsLocalTimeObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsLocalTimeObservationKnown(let v): try require(localTime(v.value))
    }
}

func validate(_ value: NeedsSchema.NeedsLockedObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsLockedObservationKnown(let v): _ = v
    }
}

func validate(_ value: NeedsSchema.NeedsBookingObservation) throws {
    switch value {
    case .NeedsMissingObservation, .NeedsUnknownObservation: break
    case .NeedsUncertainObservation(let v): try require(validText(v.note))
    case .NeedsBookingObservationKnown(let v): _ = v
    }
}
