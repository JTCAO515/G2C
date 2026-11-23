#if os(iOS)
import AVFoundation
import Foundation
@preconcurrency import Speech

@MainActor
enum LioRecordedTranslationSpeech {
    static func text(from audio: LioTranslationRecording, language: LioTranslationLanguage,
                     isCurrent: @escaping @MainActor () -> Bool) async throws -> String {
        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: language.rawValue)),
              recognizer.supportsOnDeviceRecognition, recognizer.isAvailable else {
            throw LioTranslationFailure.speechUnavailable
        }
        let gate = LioMediaPermissionGate(isCurrent: isCurrent)
        let allowed = try await gate.request {
            await speechPermission()
        }
        guard isCurrent() else { throw CancellationError() }
        guard allowed else { throw LioTranslationFailure.speechDenied }
        let buffer = try audio.recognitionBuffer()
        let job = RecordedSpeechJob()
        return try await withTaskCancellationHandler {
            try await job.text(using: recognizer, buffer: buffer)
        } onCancel: {
            Task { @MainActor in job.complete(.failure(CancellationError())) }
        }
    }
    private nonisolated static func speechPermission() async -> Bool {
        await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0 == .authorized) }
        }
    }

}

@MainActor
private final class RecordedSpeechJob {
    private var continuation: CheckedContinuation<String, any Error>?
    private var recognition: SFSpeechRecognitionTask?
    private var timeout: Task<Void, Never>?

    func text(using recognizer: SFSpeechRecognizer, buffer: AVAudioPCMBuffer) async throws -> String {
        try Task.checkCancellation()
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = false
        return try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            recognition = recognizer.recognitionTask(with: request, resultHandler: Self.handler(for: self))
            request.append(buffer)
            request.endAudio()
            timeout = Task { @MainActor [weak self] in
                do { try await Task.sleep(for: .seconds(20)) }
                catch { return }
                self?.complete(.failure(LioTranslationFailure.noRecognizedText(.speech)))
            }
        }
    }

    private nonisolated static func handler(for job: RecordedSpeechJob)
        -> @Sendable (SFSpeechRecognitionResult?, (any Error)?) -> Void {
        { [weak job] result, error in
            let finalText = result?.isFinal == true ? result?.bestTranscription.formattedString : nil
            let failed = error != nil
            Task { @MainActor in
                if let finalText, !finalText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    job?.complete(.success(finalText))
                } else if failed || finalText != nil {
                    job?.complete(.failure(LioTranslationFailure.noRecognizedText(.speech)))
                }
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
