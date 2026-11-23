#if os(iOS)
import AVFoundation
import SwiftUI

private enum LioSpokenClipKey: EnvironmentKey {
    static let defaultValue: LioSpokenClip? = nil
}

extension EnvironmentValues {
    var lioSpokenClip: LioSpokenClip? {
        get { self[LioSpokenClipKey.self] }
        set { self[LioSpokenClipKey.self] = newValue }
    }
}

struct LioSpokenPlaybackControls: View {
    struct Choice: Identifiable, Equatable {
        let id: String
        let title: String
        let phrase: LioSpokenClip.Phrase
    }

    private struct Request {
        let id = UUID()
        let choice: Choice
    }

    let language: LioLanguage
    let clip: LioSpokenClip
    let choices: [Choice]
    @Environment(\.scenePhase) private var phase
    @State private var request: Request?
    @State private var player: AVAudioPlayer?
    @State private var problem: LioSpokenRelayFailure?

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            ForEach(choices) { item in
                let active = request?.choice.id == item.id
                Button {
                    stop()
                    problem = nil
                    if !active { request = Request(choice: item) }
                } label: {
                    Label(active ? language.text("Stop audio", "停止播放") : item.title,
                          systemImage: active ? "stop.circle" : "speaker.wave.2")
                        .foregroundStyle(LioTheme.ink)
                        .frame(minWidth: 44, minHeight: 46)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(item.id)
            }
            if request != nil, player == nil {
                ProgressView(language.text("Preparing audio…", "正在准备朗读…"))
            }
            if let problem {
                Text(message(for: problem))
                    .accessibilityIdentifier("lio.tts.problem")
            }
        }
        .task(id: request?.id) {
            guard let pending = request else { return }
            do {
                let bytes = try await clip.audio(for: pending.choice.phrase)
                guard request?.id == pending.id, phase == .active else { return }
                let sound = try AVAudioPlayer(data: bytes, fileTypeHint: AVFileType.wav.rawValue)
                guard sound.play() else { throw LioSpokenRelayFailure.unavailable }
                player = sound
                try await Task.sleep(for: .seconds(sound.duration))
                if request?.id == pending.id { stop() }
            } catch is CancellationError {
                if request?.id == pending.id { stop() }
            } catch {
                guard !Task.isCancelled, request?.id == pending.id else { return }
                stop()
                problem = error as? LioSpokenRelayFailure ?? .unavailable
            }
        }
        .onChange(of: choices) { _, _ in
            stop()
            problem = nil
        }
        .onChange(of: phase) { _, current in
            if current != .active { stop() }
        }
        .onDisappear { stop() }
    }

    private func stop() {
        request = nil
        player?.stop()
        player = nil
    }

    private func message(for failure: LioSpokenRelayFailure) -> String {
        switch failure {
        case .invalidText:
            language.text("Read up to 280 characters at a time.", "一次最多朗读 280 个字符。")
        case .signInRequired:
            language.text("Sign in again to use audio.", "请重新登录后使用朗读。")
        case .quota:
            language.text("Your daily reading limit is reached.", "今天的朗读次数已用完。")
        case .offline:
            language.text("Connect to the internet to listen.", "请联网后朗读。")
        case .timedOut:
            language.text("Audio took too long. Try again.", "朗读准备超时，请重试。")
        case .unavailable:
            language.text("Audio couldn’t be played. Try again.", "无法播放音频，请重试。")
        }
    }
}
#endif
