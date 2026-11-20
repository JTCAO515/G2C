import Testing
@testable import CJLioUser

@MainActor
struct LioTranslationMediaTests {
    @Test func mediaProgressOnlySwitchesAfterUploadCompletes() {
        #expect(LioMediaTranslationProgress(payloadPrepared: false, bodySent: false).label(.chinese)
                == "正在准备…")
        #expect(LioMediaTranslationProgress(payloadPrepared: true, bodySent: false).label(.chinese)
                == "正在上传…")
        let processing = LioMediaTranslationProgress(payloadPrepared: true, bodySent: true)
        #expect(processing.label(.chinese) == "正在识别并翻译…")
        #expect(processing.label(.english) == "Recognizing and translating…")
    }

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
