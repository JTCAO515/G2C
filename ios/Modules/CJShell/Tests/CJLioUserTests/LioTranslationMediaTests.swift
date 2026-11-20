import Testing
@testable import CJLioUser

@MainActor
struct LioTranslationMediaTests {
    @Test func retiringDuringCameraPermissionRejectsTheLateGrant() async {
        var current = true
        let gate = LioMediaPermissionGate(isCurrent: { current })
        await #expect(throws: CancellationError.self) {
            try await gate.request {
                current = false
                return true
            }
        }
    }

    @Test func preservesDuplicateImageLinesAndTheirOrder() throws {
        let rows = try LioImageTranslationLine.pair(["茶", "茶", "咖啡"], with: ["Tea", "Tea", "Coffee"])
        #expect(rows.map(\.id) == [0, 1, 2])
        #expect(rows.map(\.original) == ["茶", "茶", "咖啡"])
        #expect(rows.map(\.translated) == ["Tea", "Tea", "Coffee"])
    }

    @Test func refusesMissingOrMismatchedImageText() {
        #expect(throws: LioTranslationMediaFailure.noText) {
            try LioImageTranslationLine.pair([], with: [])
        }
        #expect(throws: LioTranslationMediaFailure.mismatchedLines) {
            try LioImageTranslationLine.pair(["茶", "咖啡"], with: ["Tea"])
        }
    }
}
