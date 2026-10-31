import Foundation
import Testing
@testable import CJNeedsClient

struct CurrencyReviewTests {
    func draft() -> NeedsDraft {
        var value = NeedsDraft(needsID: "needs-local", expectedVersion: 1, fields: .init(
            budget_currency: .NeedsCurrencyObservationKnown(.init(state: .known, value: "USD")),
            budget_total: .NeedsMoneyObservationKnown(.init(state: .known, value: "1000.00")),
            budget_paid: .NeedsMoneyObservationKnown(.init(state: .known, value: "100.00"))))
        value.sourceText = "Explicit correction; no conversion"
        return value
    }
    @Test func currencyCannotRelabelUntouchedAmounts() throws {
        var value = draft()
        value.set(.currency, .init(state: .known, value: "CNY"))
        #expect(value.currencyReviewRequired == [.total, .paid])
        #expect(value.observations[.total]?.value == "1000.00")
        #expect(throws: NeedsFailure.invalidInput) { try value.freeze(actionID: "blocked") }
        value.set(.total, .init(state: .known, value: "7000.00"))
        #expect(value.currencyReviewRequired == [.paid])
        value.set(.paid, .init(state: .unknown))
        #expect(value.currencyReviewRequired.isEmpty)
        let original = try value.freeze(actionID: "explicit-correction")
        #expect(NeedsObservationInput(original.command.changes.budget_total).value == "7000.00")
        #expect(NeedsObservationInput(original.command.changes.budget_paid).state == .unknown)
        #expect(value.expectedVersion == 1)
    }
    @Test func revertingCurrencyDoesNotRequireInventedConversion() throws {
        var value = draft()
        value.set(.currency, .init(state: .known, value: "CNY"))
        value.set(.currency, .init(state: .known, value: "USD"))
        #expect(value.currencyReviewRequired.isEmpty)
        #expect(try value.freeze(actionID: "unchanged-unit").command.changes.budget_total == nil)
    }
    @Test func newlyTypedAmountAndExplicitCurrencyAreOneManualClaim() throws {
        var value = NeedsDraft(needsID: "new-needs", expectedVersion: 0)
        value.sourceText = "I explicitly enter these values"
        value.set(.total, .init(state: .known, value: "1000.00"))
        value.set(.currency, .init(state: .known, value: "USD"))
        #expect(value.currencyReviewRequired.isEmpty)
        _ = try value.freeze(actionID: "first")
        value.set(.currency, .init(state: .known, value: "CNY"))
        #expect(value.currencyReviewRequired == [.total])
    }
    @Test func copiedAmountsKeepTheirDeclaredCurrencyAndOriginalBasis() throws {
        let f = try #require(PreviewV1Tests().fixtures().first(where: { $0.name == "en" }))
        var value = NeedsDraft(needsID: "existing", expectedVersion: 7)
        let editor = value.editorID
        value.applyUnconfirmedPreview(try f.decode())
        #expect(value.expectedVersion == 7 && value.editorID == editor)
        #expect(value.currencyReviewRequired.isEmpty && value.sourceText == f.source_text)
        #expect(value.companions.count == 1 && value.fixedItems.count == 2 && value.conditions.count == 1)
        value.set(.currency, .init(state: .known, value: "CNY"))
        #expect(value.currencyReviewRequired == [.total, .paid])
        #expect(throws: NeedsFailure.invalidInput) { try value.freeze(actionID: "not-a-conversion") }
        #expect(value.conditions.allSatisfy { !$0.description.hasPrefix("remember") })
    }
    @Test func absentPreviewAmountRetainsPriorCurrencyAndVersion() throws {
        let f = try #require(PreviewV1Tests().fixtures().first(where: { $0.name == "questions" }))
        var value = draft()
        let preview = try f.decode()
        #expect(preview.fields.budget_total == nil) // Missing basis does not invent total/per-person.
        value.applyUnconfirmedPreview(preview)
        #expect(value.expectedVersion == 1 && value.observations[.paid]?.state == .uncertain)
        #expect(value.observations[.total]?.value == "1000.00")
        #expect(value.currencyReviewRequired.isEmpty)
    }
}
