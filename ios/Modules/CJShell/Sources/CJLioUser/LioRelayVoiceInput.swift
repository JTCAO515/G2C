#if os(iOS)
import AVFoundation
import Observation
import SwiftUI
import UIKit

/// Hold to talk: recording starts on press and is translated on release.
/// Sliding up before release cancels; a tap shows how to use it. VoiceOver users
/// activate once to start and again to translate.
struct LioRelayVoiceInput: View {
    let language: LioLanguage
    let source: LioTranslationLanguage
    let enabled: Bool
    let isCurrent: @MainActor () -> Bool
    let onRecording: (LioTranslationRecording) -> Void
    /// Recording prompt shown above the input bar while the button is held.
    @Binding var prompt: LioVoicePrompt?
    @Binding var notice: LioTranslationInputNotice?
    @State private var recorder = LioRelayVoiceRecorder()
    @State private var pressed = false
    @State private var dragHeight: CGFloat = 0
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var cancelling: Bool { LioHoldToTalk.isCancelling(dragHeight: dragHeight) }

    var body: some View {
        Image(systemName: recorder.isBusy ? "waveform" : "mic.fill")
            .font(.title3.weight(.semibold))
            .foregroundStyle(pressed || recorder.isBusy ? LioTheme.onVermilion : LioTheme.vermilion)
            .frame(width: 44, height: 44)
            .background(pressed || recorder.isBusy ? LioTheme.vermilion : LioTheme.surfaceSunken, in: Circle())
            .scaleEffect(pressed && !reduceMotion ? 1.15 : 1)
            .animation(LioTheme.Motion.animation(LioTheme.Motion.micro, reduceMotion: reduceMotion), value: pressed)
            .opacity(enabled ? 1 : 0.5)
            .contentShape(Circle())
            .gesture(holdGesture, including: enabled ? .all : .none)
            .accessibilityElement()
            .accessibilityLabel(recorder.isBusy ? language.text("Stop and translate", "停止并翻译")
                                                : language.text("Hold to talk", "按住说话"))
            .accessibilityHint(language.text("Release to translate.", "松开即翻译。"))
            .accessibilityAddTraits(.isButton)
            .accessibilityAction { toggleForAccessibility() }
            .accessibilityIdentifier("lio.translation.voice")
            .onChange(of: recorder.startedAt) { updatePrompt() }
            .onChange(of: dragHeight) { updatePrompt() }
            .onChange(of: recorder.failure) { _, failure in
                guard let failure else { return }
                notice = failure == .microphoneDenied
                    ? deniedNotice
                    : .init(text: language.text("Couldn’t record speech. Try again.", "暂时无法录音，请再试一次。"))
            }
            .onChange(of: enabled) { _, available in
                if !available { retire() }
            }
            .onChange(of: source) { retire() }
            .onChange(of: scenePhase) { _, phase in
                if phase == .background { retire() }
            }
            .onDisappear { retire() }
    }

    private var holdGesture: some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                dragHeight = value.translation.height
                guard !pressed else { return }
                pressed = true
                notice = nil
                guard enabled, isCurrent() else { return }
                if AVAudioApplication.shared.recordPermission == .denied {
                    notice = deniedNotice
                    return
                }
                recorder.start(isCurrent: isCurrent, onRecording: onRecording)
            }
            .onEnded { _ in
                let decision = LioHoldToTalk.release(recordingStartedAt: recorder.startedAt, at: Date(),
                                                     dragHeight: dragHeight)
                pressed = false
                dragHeight = 0
                switch decision {
                case .translate: recorder.stop()
                case .cancel, .tooShort: recorder.cancel()
                }
                if recorder.failure == nil, notice?.opensSettings != true,
                   let hint = LioHoldToTalk.hint(decision, language: language) {
                    notice = .init(text: hint)
                }
                prompt = nil
            }
    }

    private var deniedNotice: LioTranslationInputNotice {
        .init(text: language.text("Allow microphone access in Settings to use voice input.", "请在设置中允许使用麦克风。"),
              opensSettings: true)
    }

    private func toggleForAccessibility() {
        guard enabled, isCurrent() else { return }
        if AVAudioApplication.shared.recordPermission == .denied {
            notice = deniedNotice
            return
        }
        if recorder.isBusy { recorder.stop() }
        else {
            notice = nil
            recorder.start(isCurrent: isCurrent, onRecording: onRecording)
        }
    }

    private func updatePrompt() {
        guard let startedAt = recorder.startedAt else { prompt = nil; return }
        prompt = LioVoicePrompt(startedAt: startedAt,
                                text: LioHoldToTalk.recordingPrompt(cancelling: cancelling, language: language),
                                cancelling: cancelling)
    }

    private func retire() {
        recorder.cancel()
        pressed = false
        dragHeight = 0
        prompt = nil
    }
}

struct LioVoicePrompt: Equatable {
    let startedAt: Date
    let text: String
    let cancelling: Bool
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
        // Asking for the microphone without a usage description terminates the app;
        // builds without one (such as plain Debug) report that recording is unavailable.
        guard Bundle.main.object(forInfoDictionaryKey: "NSMicrophoneUsageDescription") != nil else {
            failure = .recordingUnavailable
            return
        }
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
