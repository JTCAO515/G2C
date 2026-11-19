#if os(iOS)
import AVFoundation
import Observation
@preconcurrency import Speech
import SwiftUI
import UIKit

struct LioTranslationVoiceInput: View {
    let language: LioLanguage
    let source: LioTranslationLanguage
    let enabled: Bool
    let isCurrent: @MainActor () -> Bool
    let onText: (String) -> Void
    @Environment(\.openURL) private var openURL
    @State private var capture = LioVoiceCapture()

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                guard enabled, isCurrent() else { return }
                if capture.isBusy { capture.stop() }
                else { capture.start(source, isCurrent: isCurrent, onText: onText) }
            } label: {
                Label(capture.isBusy
                      ? language.text("Stop recording", "停止录音")
                      : language.text("Speak", "语音输入"),
                      systemImage: capture.isBusy ? "stop.circle" : "mic")
                    .frame(minHeight: 44)
            }
            .buttonStyle(LioTranslationActionStyle())
            .accessibilityIdentifier("lio.translation.voice")
            if let failure = capture.failure {
                Text(message(failure)).foregroundStyle(LioTheme.ink)
                if failure == .microphoneDenied || failure == .speechDenied {
                    Button(language.text("Open Settings", "打开设置")) {
                        if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                    }
                    .frame(minHeight: 44)
                }
            }
        }
        .onChange(of: enabled) { _, available in
            if !available { capture.cancel() }
        }
        .onDisappear { capture.cancel() }
        .onChange(of: source) { capture.cancel() }
    }

    private func message(_ failure: LioTranslationMediaFailure) -> String {
        switch failure {
        case .microphoneDenied: language.text("Allow microphone access in Settings to use voice input.", "请在设置中允许使用麦克风。")
        case .speechDenied: language.text("Allow speech recognition in Settings to use voice input.", "请在设置中允许语音识别。")
        case .speechUnavailable: language.text("On-device speech recognition is unavailable. You can type instead.", "此设备暂不支持本机语音识别，可以输入文字。")
        default: language.text("Couldn’t recognize the speech. Try speaking again.", "暂时无法识别这段语音，请再说一次。")
        }
    }
}

@MainActor @Observable
private final class LioVoiceCapture {
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var recognition: SFSpeechRecognitionTask?
    private var completion: ((String) -> Void)?
    private var timeout: Task<Void, Never>?
    private var generation: UUID?
    private var hasTap = false
    private var ownsAudioSession = false
    private var previousAudioSettings: (AVAudioSession.Category, AVAudioSession.Mode, AVAudioSession.CategoryOptions)?
    private(set) var failure: LioTranslationMediaFailure?
    var isBusy: Bool { generation != nil }

    func start(_ language: LioTranslationLanguage, isCurrent: @escaping @MainActor () -> Bool,
               onText: @escaping (String) -> Void) {
        guard generation == nil, isCurrent() else { return }
        let id = UUID()
        generation = id
        failure = nil
        Task { await authorize(language, id: id, isCurrent: isCurrent, onText: onText) }
    }

    private func authorize(_ language: LioTranslationLanguage, id: UUID,
                           isCurrent: @escaping @MainActor () -> Bool,
                           onText: @escaping (String) -> Void) async {
        guard generation == id else { return }
        guard isCurrent() else { cancel(); return }
        do {
            guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: language.rawValue)) else {
                throw LioTranslationMediaFailure.speechUnavailable
            }
            switch SFSpeechRecognizer.authorizationStatus() {
            case .denied, .restricted: throw LioTranslationMediaFailure.speechDenied
            default: break
            }
            let authorization = LioVoiceAuthorization(
                onDeviceAvailable: recognizer.isAvailable && recognizer.supportsOnDeviceRecognition,
                microphone: { await AVAudioApplication.requestRecordPermission() },
                speech: {
                    await withCheckedContinuation { continuation in
                        SFSpeechRecognizer.requestAuthorization {
                            continuation.resume(returning: $0 == .authorized)
                        }
                    }
                },
                isCurrent: { [weak self] in self?.generation == id && isCurrent() }
            )
            try await authorization.check()
            guard generation == id else { return }
            guard isCurrent() else { cancel(); return }
            try beginAudio(recognizer, id: id) { text in
                guard isCurrent() else { return }
                onText(text)
            }
        } catch {
            guard generation == id else { return }
            cancel()
            if !(error is CancellationError) { failure = error as? LioTranslationMediaFailure ?? .speechUnavailable }
        }
    }

    private func beginAudio(_ recognizer: SFSpeechRecognizer, id: UUID, onText: @escaping (String) -> Void) throws {
        let audio = AVAudioSession.sharedInstance()
        previousAudioSettings = (audio.category, audio.mode, audio.categoryOptions)
        try audio.setCategory(.record, mode: .measurement)
        try audio.setActive(true)
        ownsAudioSession = true
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.channelCount > 0, format.sampleRate > 0 else { throw LioTranslationMediaFailure.speechUnavailable }
        let bufferRequest = SFSpeechAudioBufferRecognitionRequest()
        bufferRequest.requiresOnDeviceRecognition = true
        bufferRequest.shouldReportPartialResults = false
        request = bufferRequest
        completion = onText
        recognition = recognizer.recognitionTask(with: bufferRequest) { [weak self] result, error in
            let finalText = result?.isFinal == true ? result?.bestTranscription.formattedString : nil
            let failed = error != nil
            Task { @MainActor in
                self?.received(finalText, failed: failed, id: id)
            }
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            bufferRequest.append(buffer)
        }
        hasTap = true
        engine.prepare()
        try engine.start()
    }

    func stop() {
        guard let generation else { return }
        guard let request else { cancel(); return }
        guard timeout == nil else { return }
        endInput()
        request.endAudio()
        timeout = Task { @MainActor [weak self] in
            do { try await Task.sleep(for: .seconds(8)) }
            catch { return }
            guard self?.generation == generation else { return }
            self?.cancel()
            self?.failure = .unrecognizedSpeech
        }
    }

    func cancel() {
        generation = nil
        completion = nil
        timeout?.cancel()
        timeout = nil
        endInput()
        recognition?.cancel()
        recognition = nil
        request = nil
        let audio = AVAudioSession.sharedInstance()
        if ownsAudioSession {
            ownsAudioSession = false
            do { try audio.setActive(false, options: .notifyOthersOnDeactivation) }
            catch { failure = .speechUnavailable }
        }
        if let (category, mode, options) = previousAudioSettings {
            previousAudioSettings = nil
            do { try audio.setCategory(category, mode: mode, options: options) }
            catch { failure = .speechUnavailable }
        }
    }

    private func endInput() {
        engine.stop()
        if hasTap {
            engine.inputNode.removeTap(onBus: 0)
            hasTap = false
        }
    }

    private func received(_ text: String?, failed: Bool, id: UUID) {
        guard generation == id else { return }
        if let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            let action = completion
            cancel()
            action?(text)
        } else if failed || text != nil {
            cancel()
            failure = .unrecognizedSpeech
        }
    }
}
#endif
