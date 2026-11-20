#if os(iOS)
import AVFoundation
import Observation
import SwiftUI
import UIKit

struct LioRelayVoiceInput: View {
    let language: LioLanguage
    let source: LioTranslationLanguage
    let enabled: Bool
    let isCurrent: @MainActor () -> Bool
    let onRecording: (LioTranslationRecording) -> Void
    @State private var recorder = LioRelayVoiceRecorder()
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                guard enabled, isCurrent() else { return }
                if recorder.isBusy { recorder.stop() }
                else { recorder.start(isCurrent: isCurrent, onRecording: onRecording) }
            } label: {
                Label(recorder.isBusy
                      ? language.text("Stop recording", "停止录音")
                      : language.text("Speak", "语音输入"),
                      systemImage: recorder.isBusy ? "stop.circle" : "mic")
            }
            .buttonStyle(LioTranslationActionStyle())
            .accessibilityIdentifier("lio.translation.voice")
            if let startedAt = recorder.startedAt {
                HStack {
                    Text(language.text("Recording", "录音中"))
                    Text(timerInterval: startedAt...startedAt.addingTimeInterval(60), countsDown: false)
                        .monospacedDigit()
                }
                .accessibilityElement(children: .combine)
            }
            if let failure = recorder.failure {
                if failure == .microphoneDenied {
                    Text(language.text("Allow microphone access in Settings to use voice input.", "请在设置中允许使用麦克风。"))
                    Button(language.text("Open Settings", "打开设置")) {
                        if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                    }
                    .frame(minHeight: 44)
                } else {
                    Text(language.text("Couldn’t record speech. Try again.", "暂时无法录音，请再试一次。"))
                }
            }
        }
        .foregroundStyle(LioTheme.ink)
        .onChange(of: enabled) { _, available in
            if !available { recorder.cancel() }
        }
        .onChange(of: source) { recorder.cancel() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { recorder.cancel() }
        }
        .onDisappear { recorder.cancel() }
    }
}

@MainActor @Observable
private final class LioRelayVoiceRecorder {
    private let engine = AVAudioEngine()
    private var collector: LioTranslationPCMCollector?
    private var timeout: Task<Void, Never>?
    private var operation: UUID?
    private var completion: ((LioTranslationRecording) -> Void)?
    private var sessionIsCurrent: (@MainActor () -> Bool)?
    private var settings: (AVAudioSession.Category, AVAudioSession.Mode, AVAudioSession.CategoryOptions)?
    private var ownsAudioSession = false
    private(set) var failure: LioTranslationMediaFailure?
    private(set) var startedAt: Date?
    var isBusy: Bool { operation != nil }

    func start(isCurrent: @escaping @MainActor () -> Bool, onRecording: @escaping (LioTranslationRecording) -> Void) {
        guard operation == nil, isCurrent() else { return }
        let id = UUID()
        operation = id
        failure = nil
        sessionIsCurrent = isCurrent
        Task { await authorize(id, isCurrent: isCurrent, onRecording: onRecording) }
    }

    private func authorize(_ id: UUID, isCurrent: @escaping @MainActor () -> Bool,
                           onRecording: @escaping (LioTranslationRecording) -> Void) async {
        do {
            let gate = LioMediaPermissionGate(isCurrent: { [weak self] in self?.operation == id && isCurrent() })
            let allowed = try await gate.request { await AVAudioApplication.requestRecordPermission() }
            guard operation == id else { return }
            guard isCurrent() else { cancel(); return }
            guard allowed else { throw LioTranslationMediaFailure.microphoneDenied }
            try beginRecording(id, onRecording: onRecording)
        } catch {
            guard operation == id else { return }
            cancel()
            if !(error is CancellationError) { failure = error as? LioTranslationMediaFailure ?? .recordingUnavailable }
        }
    }

    private func beginRecording(_ id: UUID, onRecording: @escaping (LioTranslationRecording) -> Void) throws {
        let session = AVAudioSession.sharedInstance()
        settings = (session.category, session.mode, session.categoryOptions)
        try session.setCategory(.record, mode: .measurement)
        try session.setActive(true)
        ownsAudioSession = true
        let microphone = engine.inputNode
        let format = microphone.outputFormat(forBus: 0)
        let collector = try LioTranslationPCMCollector(inputFormat: format)
        microphone.installTap(onBus: 0, bufferSize: 1024, format: format,
                              block: LioTranslationPCMCollector.tap(for: collector))
        self.collector = collector
        self.completion = onRecording
        engine.prepare()
        try engine.start()
        startedAt = Date()
        timeout = Task { @MainActor [weak self] in
            do { try await Task.sleep(for: .seconds(60)) }
            catch { return }
            if self?.operation == id { self?.stop() }
        }
    }

    func stop() {
        guard let collector, sessionIsCurrent?() == true else { cancel(); return }
        let deliver = completion
        cancel()
        do {
            try deliver?(collector.finish())
        } catch {
            failure = .recordingUnavailable
        }
    }

    func cancel() {
        operation = nil
        startedAt = nil
        completion = nil
        sessionIsCurrent = nil
        timeout?.cancel()
        timeout = nil
        if collector != nil {
            engine.stop()
            engine.inputNode.removeTap(onBus: 0)
            collector = nil
        }
        restoreAudioSettings()
    }

    private func restoreAudioSettings() {
        let session = AVAudioSession.sharedInstance()
        if ownsAudioSession {
            ownsAudioSession = false
            do { try session.setActive(false, options: .notifyOthersOnDeactivation) }
            catch { failure = .recordingUnavailable }
        }
        if let (category, mode, options) = settings {
            settings = nil
            do { try session.setCategory(category, mode: mode, options: options) }
            catch { failure = .recordingUnavailable }
        }
    }
}
#endif
