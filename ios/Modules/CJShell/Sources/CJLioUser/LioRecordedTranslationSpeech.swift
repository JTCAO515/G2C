#if os(iOS)
import Foundation
@preconcurrency import Speech

@MainActor
enum LioRecordedTranslationSpeech {
    static func text(from audio: Data, language: LioTranslationLanguage) async throws -> String {
        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: language.rawValue)),
              recognizer.supportsOnDeviceRecognition, recognizer.isAvailable else {
            throw LioTranslationMediaFailure.speechUnavailable
        }
        let allowed = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0 == .authorized) }
        }
        guard allowed else { throw LioTranslationMediaFailure.speechDenied }
        try Task.checkCancellation()

        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
        try audio.write(to: temporary, options: [.atomic, .completeFileProtection])
        let job = RecordedSpeechJob()
        let result: Result<String, any Error>
        do {
            let text = try await withTaskCancellationHandler {
                try await job.text(using: recognizer, file: temporary)
            } onCancel: {
                Task { @MainActor in job.complete(.failure(CancellationError())) }
            }
            result = .success(text)
        } catch { result = .failure(error) }
        try FileManager.default.removeItem(at: temporary)
        return try result.get()
    }
}

@MainActor
private final class RecordedSpeechJob {
    private var continuation: CheckedContinuation<String, any Error>?
    private var recognition: SFSpeechRecognitionTask?
    private var timeout: Task<Void, Never>?

    func text(using recognizer: SFSpeechRecognizer, file: URL) async throws -> String {
        try Task.checkCancellation()
        let request = SFSpeechURLRecognitionRequest(url: file)
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = false
        return try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            recognition = recognizer.recognitionTask(with: request) { [weak self] result, error in
                let finalText = result?.isFinal == true ? result?.bestTranscription.formattedString : nil
                let failed = error != nil
                Task { @MainActor in
                    if let finalText, !finalText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        self?.complete(.success(finalText))
                    } else if failed || finalText != nil {
                        self?.complete(.failure(LioTranslationMediaFailure.unrecognizedSpeech))
                    }
                }
            }
            timeout = Task { @MainActor [weak self] in
                do { try await Task.sleep(for: .seconds(20)) }
                catch { return }
                self?.complete(.failure(LioTranslationMediaFailure.unrecognizedSpeech))
            }
        }
    }

    func complete(_ result: Result<String, any Error>) {
        guard let continuation else { return }
        self.continuation = nil
        timeout?.cancel()
        timeout = nil
        recognition?.cancel()
        recognition = nil
        continuation.resume(with: result)
    }
}
#endif
