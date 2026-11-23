#if os(iOS) && DEBUG
import SwiftUI

struct LioSpokenPreviewButton: View {
    let language: LioLanguage
    let phrase: LioSpokenClip.Phrase
    @State private var clip = LioSpokenClip { _, _ in
        var pcm = Data()
        for sample in 0..<48_000 {
            let volume = sin(Double(sample) * 2 * .pi * 440 / Double(LioTranslationWAV.sampleRate))
            var value = Int16(volume * 1400).littleEndian
            withUnsafeBytes(of: &value) { pcm.append(contentsOf: $0) }
        }
        return try LioTranslationWAV.encode(pcm: pcm)
    }

    var body: some View {
        LioSpokenPlaybackControls(
            language: language, clip: clip,
            choices: [.init(id: "lio.tts.sample", title: language.text("Play sample audio", "播放示例音频"),
                            phrase: phrase)]
        )
    }
}

#Preview {
    LioSpokenPreviewButton(language: .english, phrase: .init(language: .english, text: "Tea"))
        .padding()
}
#endif
