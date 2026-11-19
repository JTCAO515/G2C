#if os(iOS)
import AVFoundation
import Observation
import SwiftUI
import UIKit

struct LioRelayVoiceInput: View {
    let language: LioLanguage
    let enabled: Bool
    let isCurrent: @MainActor () -> Bool
    let onRecording: (Data) -> Void
    @State private var recorder = LioRelayVoiceRecorder()
    @Environment(\.openURL) private var openURL

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
        .onDisappear { recorder.cancel() }
    }
}

@MainActor @Observable
private final class LioRelayVoiceRecorder: NSObject, AVAudioRecorderDelegate {
    private var recorder: AVAudioRecorder?
    private var operation: UUID?
    private var completion: ((Data) -> Void)?
    private var sessionIsCurrent: (@MainActor () -> Bool)?
    private var settings: (AVAudioSession.Category, AVAudioSession.Mode, AVAudioSession.CategoryOptions)?
    private var ownsAudioSession = false
    private(set) var failure: LioTranslationMediaFailure?
    var isBusy: Bool { operation != nil }

    func start(isCurrent: @escaping @MainActor () -> Bool, onRecording: @escaping (Data) -> Void) {
        guard operation == nil, isCurrent() else { return }
        let id = UUID()
        operation = id
        failure = nil
        sessionIsCurrent = isCurrent
        Task { await authorize(id, isCurrent: isCurrent, onRecording: onRecording) }
    }

    private func authorize(_ id: UUID, isCurrent: @escaping @MainActor () -> Bool,
                           onRecording: @escaping (Data) -> Void) async {
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
            if !(error is CancellationError) { failure = error as? LioTranslationMediaFailure ?? .speechUnavailable }
        }
    }

    private func beginRecording(_ id: UUID, onRecording: @escaping (Data) -> Void) throws {
        let session = AVAudioSession.sharedInstance()
        settings = (session.category, session.mode, session.categoryOptions)
        try session.setCategory(.record, mode: .measurement)
        try session.setActive(true)
        ownsAudioSession = true
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(id.uuidString + ".wav")
        let recording = try AVAudioRecorder(url: url, settings: [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 16_000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsFloatKey: false,
        ])
        recorder = recording
        completion = onRecording
        recording.delegate = self
        guard recording.prepareToRecord() else { throw LioTranslationMediaFailure.speechUnavailable }
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: url.path)
        guard recording.record(forDuration: 60) else { throw LioTranslationMediaFailure.speechUnavailable }
    }

    func stop() {
        if let recorder { recorder.stop() }
        else { cancel() }
    }

    func cancel() {
        operation = nil
        completion = nil
        sessionIsCurrent = nil
        if let recording = recorder {
            recorder = nil
            recording.delegate = nil
            recording.stop()
            removeRecording(at: recording.url)
        }
        restoreAudioSettings()
    }

    nonisolated func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        let url = recorder.url
        Task { @MainActor in finish(url, success: flag) }
    }

    private func finish(_ url: URL, success: Bool) {
        guard recorder?.url == url else { return }
        guard sessionIsCurrent?() == true else { cancel(); return }
        let deliver = completion
        recorder = nil
        completion = nil
        operation = nil
        sessionIsCurrent = nil
        restoreAudioSettings()
        do {
            guard success else { throw LioTranslationMediaFailure.speechUnavailable }
            let data = try Data(contentsOf: url)
            try FileManager.default.removeItem(at: url)
            deliver?(data)
        } catch {
            removeRecording(at: url)
            failure = .speechUnavailable
        }
    }

    private func removeRecording(at url: URL) {
        do { try FileManager.default.removeItem(at: url) }
        catch let error as CocoaError where error.code == .fileNoSuchFile {}
        catch { failure = .speechUnavailable }
    }

    private func restoreAudioSettings() {
        let session = AVAudioSession.sharedInstance()
        if ownsAudioSession {
            ownsAudioSession = false
            do { try session.setActive(false, options: .notifyOthersOnDeactivation) }
            catch { failure = .speechUnavailable }
        }
        if let (category, mode, options) = settings {
            settings = nil
            do { try session.setCategory(category, mode: mode, options: options) }
            catch { failure = .speechUnavailable }
        }
    }
}
#endif
