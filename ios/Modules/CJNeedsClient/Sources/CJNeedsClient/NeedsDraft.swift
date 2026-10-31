import Foundation
import CJAPI

public enum NeedsLanguage: Sendable { case zh, en
    func text(_ zh: String, _ en: String) -> String { self == .zh ? zh : en }
}
public enum NeedsObservationState: String, CaseIterable, Sendable {
    case absent, missing, unknown, uncertain, known
    public func label(_ language: NeedsLanguage) -> String {
        switch self {
        case .absent: language.text("未记录", "Not recorded")
        case .missing: language.text("明确未提供", "Explicitly missing")
        case .unknown: language.text("尚未确定", "Unknown")
        case .uncertain: language.text("不确定", "Uncertain")
        case .known: language.text("用户提供", "User provided")
        }
    }
}
/// Presentation state only. Conversion constructs the official generated observation types.
public struct NeedsObservationInput: Equatable, Sendable {
    public var state: NeedsObservationState = .absent
    public var value = ""
    public var note = ""
    public var items: [String]?
    public init(state: NeedsObservationState = .absent, value: String = "", note: String = "", items: [String]? = nil) {
        self.state = state; self.value = value; self.note = note; self.items = items
    }
}
public enum NeedsField: String, CaseIterable, Sendable {
    case partySize, destinationTimezone, overseasTimezone, currency, total, perPerson, paid, basis, includes, pace
    public func label(_ l: NeedsLanguage) -> String {
        switch self {
        case .partySize: l.text("人数（独立于同伴列表）", "Party size (separate from companions)")
        case .destinationTimezone: l.text("目的地时区（IANA）", "Destination timezone (IANA)")
        case .overseasTimezone: l.text("海外时区（IANA）", "Overseas timezone (IANA)")
        case .currency: l.text("币种（三位大写）", "Currency (three uppercase letters)")
        case .total: l.text("预算总计", "Total budget")
        case .perPerson: l.text("每人预算", "Budget per person")
        case .paid: l.text("已支付金额", "Amount already paid")
        case .basis: l.text("预算口径", "Budget basis")
        case .includes: l.text("包含／不包含范围", "Included / excluded costs")
        case .pace: l.text("本次节奏", "Pace for this journey")
        }
    }
}
public enum NeedsEventField: String, CaseIterable, Sendable {
    case overseasDeparture, arrival, departure
    public func label(_ l: NeedsLanguage) -> String {
        switch self {
        case .overseasDeparture: l.text("海外出发", "Overseas departure")
        case .arrival: l.text("抵达", "Arrival")
        case .departure: l.text("离开", "Departure")
        }
    }
}
public struct NeedsEventInput: Equatable, Sendable {
    public var date = NeedsObservationInput()
    public var time = NeedsObservationInput()
    public var timezone = NeedsObservationInput()
    public var place = NeedsObservationInput()
    public init() {}
    init(_ event: NeedsSchema.NeedsEvent) {
        date = .init(event.date); time = .init(event.time); timezone = .init(event.timezone); place = .init(event.place)
    }
    public mutating func markUnrecordedMissing() {
        if date.state == .absent { date.state = .missing }
        if time.state == .absent { time.state = .missing }
        if timezone.state == .absent { timezone.state = .missing }
        if place.state == .absent { place.state = .missing }
    }
    func event() throws -> NeedsSchema.NeedsEvent {
        let event = try NeedsSchema.NeedsEvent(date: date.localDate(), time: time.localTime(), timezone: timezone.timezone(), place: place.text())
        try validateEvent(event); return event
    }
}
public struct NeedsCompanionInput: Identifiable, Equatable, Sendable {
    public let id: String
    public var label: String
    public init(id: String = UUID().uuidString, label: String = "") { self.id = id; self.label = label }
}
public struct NeedsFixedInput: Identifiable, Sendable {
    public let id: String
    public var kind: NeedsSchema.NeedsFixedItem.kindPayload?
    public var description = ""
    public var appliesTo: [String] = []
    public var locked = NeedsObservationInput()
    public var booking = NeedsObservationInput()
    public var start = NeedsEventInput()
    public var end = NeedsEventInput()
    public init(id: String = UUID().uuidString) { self.id = id }
    init(_ item: NeedsSchema.NeedsFixedItem) {
        id = item.item_id; kind = item.kind; description = item.description; appliesTo = item.applies_to
        locked = .init(item.locked); booking = .init(item.booking_status); start = .init(item.start); end = .init(item.end)
    }
    func item() throws -> NeedsSchema.NeedsFixedItem {
        guard let kind else { throw NeedsFailure.invalidInput }
        return try .init(item_id: id, kind: kind, description: description, applies_to: appliesTo,
                         locked: locked.locked(), start: start.event(), end: end.event(), booking_status: booking.booking())
    }
}
public struct NeedsConditionInput: Identifiable, Sendable {
    public let id: String
    public var description = ""
    public var appliesTo: [String] = []
    public init(id: String = UUID().uuidString) { self.id = id }
    init(_ condition: NeedsSchema.NeedsTemporaryCondition) {
        id = condition.condition_id; description = condition.description; appliesTo = condition.applies_to
    }
}

/// A partial correction. Editing a value explicitly marks only that top-level field.
public struct NeedsDraft: Sendable {
    public let editorID = UUID()
    public let needsID: String
    public let expectedVersion: Int
    public var sourceText = ""
    public private(set) var observations: [NeedsField: NeedsObservationInput] = [:]
    public private(set) var changedFields: Set<NeedsField> = []
    public private(set) var events: [NeedsEventField: NeedsEventInput] = [:]
    public private(set) var changedEvents: Set<NeedsEventField> = []
    public var companions: [NeedsCompanionInput] { didSet { companionsChanged = true } }
    public var fixedItems: [NeedsFixedInput] { didSet { fixedItemsChanged = true } }
    public var conditions: [NeedsConditionInput] { didSet { conditionsChanged = true } }
    public private(set) var companionsChanged = false
    public private(set) var fixedItemsChanged = false
    public private(set) var conditionsChanged = false
    private static let amounts: Set<NeedsField> = [.total, .perPerson, .paid]
    // An amount retains its source currency until the user re-enters it.
    // Missing source currency is not silently replaced by a later selection.
    private var amountCurrencies: [NeedsField: NeedsObservationInput] = [:]
    private var manuallyEnteredWithoutCurrency: Set<NeedsField> = []
    public var currencyReviewRequired: Set<NeedsField> {
        let currency = observations[.currency]!
        guard currency.state == .known else { return [] }
        return Set(Self.amounts.filter { field in
            guard observations[field]!.state == .known else { return false }
            let original = amountCurrencies[field]!
            return original.state != .known || !same(original.value, currency.value)
        })
    }
    public init(needsID: String, expectedVersion: Int, fields: NeedsSchema.NeedsFields = .init()) {
        self.needsID = needsID; self.expectedVersion = expectedVersion
        observations = [.partySize: .init(fields.party_size), .destinationTimezone: .init(fields.destination_timezone),
                        .overseasTimezone: .init(fields.overseas_timezone), .currency: .init(fields.budget_currency),
                        .total: .init(fields.budget_total), .perPerson: .init(fields.budget_per_person), .paid: .init(fields.budget_paid),
                        .basis: .init(fields.budget_basis), .includes: .init(fields.budget_includes), .pace: .init(fields.pace)]
        if let e = fields.overseas_departure { events[.overseasDeparture] = .init(e) }
        if let e = fields.arrival { events[.arrival] = .init(e) }
        if let e = fields.departure { events[.departure] = .init(e) }
        companions = (fields.companions?.additionalProperties ?? [:]).map { .init(id: $0.key, label: $0.value) }.sorted { $0.id < $1.id }
        fixedItems = (fields.fixed_items ?? []).map(NeedsFixedInput.init)
        conditions = (fields.temporary_conditions ?? []).map(NeedsConditionInput.init)
        for field in Self.amounts where observations[field]!.state == .known {
            amountCurrencies[field] = observations[.currency]!
        }
    }
    public mutating func set(_ field: NeedsField, _ value: NeedsObservationInput) {
        observations[field] = value
        if value.state == .absent { changedFields.remove(field) } else { changedFields.insert(field) }
        if Self.amounts.contains(field) {
            if value.state == .known {
                amountCurrencies[field] = observations[.currency]!
                if observations[.currency]!.state != .known { manuallyEnteredWithoutCurrency.insert(field) }
                else { manuallyEnteredWithoutCurrency.remove(field) }
            } else {
                amountCurrencies.removeValue(forKey: field); manuallyEnteredWithoutCurrency.remove(field)
            }
        } else if field == .currency, value.state == .known {
            // Both entries are explicit edits in this editor. This never binds
            // an untouched historical or copied extraction amount.
            for amount in manuallyEnteredWithoutCurrency { amountCurrencies[amount] = value }
            manuallyEnteredWithoutCurrency = []
        }
    }
    /// Explicit user copy only; no command/ID/persistence is produced. Absent
    /// extraction fields retain prior input and the original expected version.
    public mutating func applyUnconfirmedPreview(_ preview: NeedsPreviewV1) {
        let incoming = NeedsDraft(needsID: needsID, expectedVersion: expectedVersion, fields: preview.fields)
        for (field, value) in incoming.observations where value.state != .absent {
            observations[field] = value; changedFields.insert(field)
            if Self.amounts.contains(field) {
                if value.state == .known { amountCurrencies[field] = incoming.observations[.currency]! }
                else { amountCurrencies.removeValue(forKey: field) }
                manuallyEnteredWithoutCurrency.remove(field)
            }
        }
        for (field, value) in incoming.events { events[field] = value; changedEvents.insert(field) }
        if preview.fields.companions != nil { companions = incoming.companions }
        if preview.fields.fixed_items != nil { fixedItems = incoming.fixedItems }
        if preview.fields.temporary_conditions != nil { conditions = incoming.conditions }
        sourceText = preview.sourceText
        // deferredMemoryRequests remain separate. No inferred lifetime change.
    }
    public mutating func set(_ field: NeedsEventField, _ value: NeedsEventInput) { events[field] = value; changedEvents.insert(field) }
    public mutating func leaveEventUnchanged(_ field: NeedsEventField) { changedEvents.remove(field) }
    public func freeze(actionID: String) throws -> NeedsPending {
        guard currencyReviewRequired.isEmpty else { throw NeedsFailure.invalidInput }
        var changes = NeedsSchema.NeedsChanges()
        for field in changedFields {
            guard let input = observations[field] else { throw NeedsFailure.invalidInput }
            switch field {
            case .partySize: changes.party_size = try input.partySize()
            case .destinationTimezone: changes.destination_timezone = try input.timezone()
            case .overseasTimezone: changes.overseas_timezone = try input.timezone()
            case .currency: changes.budget_currency = try input.currency()
            case .total: changes.budget_total = try input.money()
            case .perPerson: changes.budget_per_person = try input.money()
            case .paid: changes.budget_paid = try input.money()
            case .basis: changes.budget_basis = try input.budgetBasis()
            case .includes: changes.budget_includes = try input.coverage()
            case .pace: changes.pace = try input.text()
            }
        }
        for field in changedEvents {
            guard let input = events[field] else { throw NeedsFailure.invalidInput }
            switch field {
            case .overseasDeparture: changes.overseas_departure = try input.event()
            case .arrival: changes.arrival = try input.event()
            case .departure: changes.departure = try input.event()
            }
        }
        if companionsChanged {
            var labels: [String: String] = [:]
            for companion in companions {
                guard labels[companion.id] == nil else { throw NeedsFailure.invalidInput }
                labels[companion.id] = companion.label
            }
            changes.companions = .init(additionalProperties: labels)
        }
        if fixedItemsChanged { changes.fixed_items = try fixedItems.map { try $0.item() } }
        if conditionsChanged { changes.temporary_conditions = conditions.map { .init(condition_id: $0.id, applies_to: $0.appliesTo, description: $0.description) } }
        return try NeedsPending(command: .init(action_id: actionID, needs_id: needsID, expected_version: expectedVersion,
                                               source: .init(kind: .manual, text: sourceText), changes: changes))
    }
}

extension NeedsObservationInput {
    init(_ value: NeedsSchema.NeedsPartySizeObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsPartySizeObservationKnown(let v): state = .known; self.value = String(v.value)
        }
    }
    func partySize() throws -> NeedsSchema.NeedsPartySizeObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:
            guard matches(value, "[0-9]+"), let known = Int(value) else { throw NeedsFailure.invalidInput }
            return .NeedsPartySizeObservationKnown(.init(state: .known, value: known))
        }
    }
    init(_ value: NeedsSchema.NeedsTimezoneObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsTimezoneObservationKnown(let v): state = .known; self.value = v.value
        }
    }
    func timezone() throws -> NeedsSchema.NeedsTimezoneObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:

            return .NeedsTimezoneObservationKnown(.init(state: .known, value: value))
        }
    }
    init(_ value: NeedsSchema.NeedsCurrencyObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsCurrencyObservationKnown(let v): state = .known; self.value = v.value
        }
    }
    func currency() throws -> NeedsSchema.NeedsCurrencyObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:

            return .NeedsCurrencyObservationKnown(.init(state: .known, value: value))
        }
    }
    init(_ value: NeedsSchema.NeedsMoneyObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsMoneyObservationKnown(let v): state = .known; self.value = v.value
        }
    }
    func money() throws -> NeedsSchema.NeedsMoneyObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:

            return .NeedsMoneyObservationKnown(.init(state: .known, value: value))
        }
    }
    init(_ value: NeedsSchema.NeedsBudgetBasisObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsBudgetBasisObservationKnown(let v): state = .known; self.value = v.value.rawValue
        }
    }
    func budgetBasis() throws -> NeedsSchema.NeedsBudgetBasisObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:
            guard let known = NeedsSchema.NeedsBudgetBasisObservationKnown.valuePayload(rawValue: value) else { throw NeedsFailure.invalidInput }
            return .NeedsBudgetBasisObservationKnown(.init(state: .known, value: known))
        }
    }
    init(_ value: NeedsSchema.NeedsCoverageObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsCoverageObservationKnown(let v): state = .known; self.items = v.value; self.value = v.value.joined(separator: "\n")
        }
    }
    func coverage() throws -> NeedsSchema.NeedsCoverageObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:

            return .NeedsCoverageObservationKnown(.init(state: .known, value: items ?? value.components(separatedBy: "\n")))
        }
    }
    init(_ value: NeedsSchema.NeedsTextObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsTextObservationKnown(let v): state = .known; self.value = v.value
        }
    }
    func text() throws -> NeedsSchema.NeedsTextObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:

            return .NeedsTextObservationKnown(.init(state: .known, value: value))
        }
    }
    init(_ value: NeedsSchema.NeedsLocalDateObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsLocalDateObservationKnown(let v): state = .known; self.value = v.value
        }
    }
    func localDate() throws -> NeedsSchema.NeedsLocalDateObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:

            return .NeedsLocalDateObservationKnown(.init(state: .known, value: value))
        }
    }
    init(_ value: NeedsSchema.NeedsLocalTimeObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsLocalTimeObservationKnown(let v): state = .known; self.value = v.value
        }
    }
    func localTime() throws -> NeedsSchema.NeedsLocalTimeObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:

            return .NeedsLocalTimeObservationKnown(.init(state: .known, value: value))
        }
    }
    init(_ value: NeedsSchema.NeedsLockedObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsLockedObservationKnown(let v): state = .known; self.value = v.value ? "true" : "false"
        }
    }
    func locked() throws -> NeedsSchema.NeedsLockedObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:
            guard value == "true" || value == "false" else { throw NeedsFailure.invalidInput }
            return .NeedsLockedObservationKnown(.init(state: .known, value: value == "true"))
        }
    }
    init(_ value: NeedsSchema.NeedsBookingObservation?) {
        self.init()
        guard let value else { return }
        switch value {
        case .NeedsMissingObservation: state = .missing
        case .NeedsUnknownObservation: state = .unknown
        case .NeedsUncertainObservation(let v): state = .uncertain; note = v.note
        case .NeedsBookingObservationKnown(let v): state = .known; self.value = v.value.rawValue
        }
    }
    func booking() throws -> NeedsSchema.NeedsBookingObservation {
        switch state {
        case .absent: throw NeedsFailure.invalidInput
        case .missing: return .NeedsMissingObservation(.init(state: .missing))
        case .unknown: return .NeedsUnknownObservation(.init(state: .unknown))
        case .uncertain: return .NeedsUncertainObservation(.init(state: .uncertain, note: note))
        case .known:
            guard let known = NeedsSchema.NeedsBookingObservationKnown.valuePayload(rawValue: value) else { throw NeedsFailure.invalidInput }
            return .NeedsBookingObservationKnown(.init(state: .known, value: known))
        }
    }
}
