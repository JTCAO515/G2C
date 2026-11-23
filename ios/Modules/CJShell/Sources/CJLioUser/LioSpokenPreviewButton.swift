#if os(iOS) && DEBUG
import AVFoundation
import SwiftUI

struct LioSpokenPreviewButton: View {
    let language: LioLanguage
    let phrase: LioSpokenClip.Phrase
    @State private var clip = LioSpokenClip { _, _ in
        // A short local audio sample exercises playback without a model call.
        var pcm = Data()
        for sample in 0..<12_800 {
            let volume = sin(Double(sample) * 2 * .pi * 440 / Double(LioTranslationWAV.sampleRate))
            var value = Int16(volume * 1400).littleEndian
            withUnsafeBytes(of: &value) { pcm.append(contentsOf: $0) }
        }
        return try LioTranslationWAV.encode(pcm: pcm)
    }
    @State private var player: AVAudioPlayer?
    @State private var playing = false
    @State private var request: UUID?
    @State private var failed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Button {
                if request != nil {
                    stop()
                } else {
                    failed = false
                    request = UUID()
                }
            } label: {
                Label(
                    request == nil
                       ? language.text("Play sample audio", "播放示例音频")
                       : language.text("Stop audio", "停止播放"),
                    systemImage: request == nil ? "speaker.wave.2" : "stop.circle"
                )
                .foregroundStyle(LioTheme.ink)
                .frame(minHeight: 44)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.tts.sample")
            if request != nil, !playing {
                ProgressView(language.text("Getting audio…", "正在获取音频…"))
            }
            if failed {
                Text(language.text("Audio couldn’t be played. Try again.", "无法播放音频，请重试。"))
            }
        }
        .task(id: request) {
            guard let current = request else { return }
            do {
                let data = try await clip.audio(for: phrase)
                guard request == current else { return }
                let audio = try AVAudioPlayer(data: data, fileTypeHint: AVFileType.wav.rawValue)
                guard audio.play() else { throw CocoaError(.fileReadCorruptFile) }
                player = audio
                playing = true
                try await Task.sleep(for: .seconds(audio.duration))
                if request == current { stop() }
            } catch {
                guard !Task.isCancelled, request == current else { return }
                stop()
                failed = true
            }
        }
        .onChange(of: phrase) { stop() }
        .onDisappear { stop() }
    }

    private func stop() {
        request = nil
        player?.stop()
        player = nil
        playing = false
    }
}
#endif
