#if os(iOS)
import AVFoundation
import SwiftUI
import Translation
import UIKit

struct LioToolsView: View {
    let language: LioLanguage
    let historyDirectory: URL?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    NavigationLink {
                        LioTextTranslationView(language: language, history: historyDirectory.map(LioTranslationHistory.init(directory:)))
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: "character.bubble")
                            Text(language.text("Translation", "翻译"))
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 8)
                            Image(systemName: "chevron.forward")
                                .accessibilityHidden(true)
                        }
                        .foregroundStyle(LioTheme.ink)
                        .padding(16)
                        .frame(minHeight: 56)
                        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: 16))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.tools.translation")
                }
                .padding(18)
            }
            .background(LioTheme.paper)
            .navigationTitle(language.text("Tools", "插件"))
        }
        .tint(LioTheme.vermilion)
    }
}

struct LioTranslationActionStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(LioTheme.ink)
            .padding(.horizontal, 10)
            .frame(minHeight: 44)
            .background(configuration.isPressed ? LioTheme.surfaceSunken : LioTheme.surface, in: Capsule())
    }
}

private struct LioTextTranslationView: View {
    let language: LioLanguage
    let history: LioTranslationHistory?
    @State private var source: LioTranslationLanguage = .english
    @State private var target: LioTranslationLanguage = .chinese
    @State private var input = ""
    @State private var attempt: Attempt?
    @State private var result: LioTranslationResult?
    @State private var imageLines: [LioImageTranslationLine] = []
    @State private var imageText: [String] = []
    @State private var spokenText: String?
    @State private var problem: LioTranslationFailure?
    @State private var speaker = AVSpeechSynthesizer()
    @State private var recent: [LioRecentTranslation] = []
    @State private var confirmsClearHistory = false
    @State private var historyError = false

    private struct Attempt: Identifiable {
        let id = UUID()
        let request: LioTranslationRequest
        let fromImage: Bool
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    languagePicker(language.text("From", "源语言"), selection: $source, other: $target)
                    Button {
                        let previous = source
                        source = target
                        target = previous
                    } label: {
                        Image(systemName: "arrow.left.arrow.right")
                            .frame(minWidth: 44, minHeight: 44)
                    }
                    .accessibilityLabel(language.text("Swap languages", "互换语言"))
                    .accessibilityIdentifier("lio.translation.swap")
                    languagePicker(language.text("To", "目标语言"), selection: $target, other: $source)
                }
                TextEditor(text: $input)
                    .foregroundStyle(LioTheme.ink)
                    .scrollContentBackground(.hidden)
                    .frame(minHeight: 116)
                    .padding(8)
                    .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: 16))
                    .accessibilityLabel(language.text("Text to translate", "要翻译的文本"))
                    .accessibilityIdentifier("lio.translation.input")
                HStack {
                    PasteButton(payloadType: String.self) { values in
                        if let text = values.first { input = text }
                    }
                    .frame(minHeight: 44)
                    Button(language.text("Clear", "清空")) { input = ""; resetResult() }
                        .frame(minHeight: 44)
                    Spacer()
                    Button(action: start) {
                        Text(language.text("Translate", "翻译"))
                            .foregroundStyle(LioTheme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 16)
                            .frame(minHeight: 44)
                            .background(LioTheme.surface, in: Capsule())
                            .overlay { Capsule().strokeBorder(LioTheme.hairline) }
                    }
                    .buttonStyle(LioTranslationActionStyle())
                    .accessibilityIdentifier("lio.translation.submit")
                    .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || attempt != nil)
                }
                LioTranslationVoiceInput(language: language, source: source) { text in
                    start([text], fromImage: false)
                    spokenText = text
                }
                if let spokenText {
                    Text(spokenText)
                        .foregroundStyle(LioTheme.ink)
                        .textSelection(.enabled)
                        .accessibilityIdentifier("lio.translation.transcript")
                }
                LioTranslationImageInput(language: language) { lines in
                    start(lines, fromImage: true)
                    imageText = lines
                }
                if result == nil, !imageText.isEmpty {
                    Text(imageText.joined(separator: "\n"))
                        .foregroundStyle(LioTheme.ink)
                        .textSelection(.enabled)
                        .accessibilityIdentifier("lio.translation.image-text")
                }
                if attempt != nil { ProgressView(language.text("Translating…", "正在翻译…")) }
                if let result { resultCard(result) }
                if let problem {
                    Text(message(for: problem))
                        .foregroundStyle(LioTheme.ink)
                        .accessibilityIdentifier("lio.translation.problem")
                }
                if !recent.isEmpty { recentTranslations }
                if historyError {
                    Text(language.text("Translation history is temporarily unavailable.", "暂时无法访问翻译记录。"))
                        .foregroundStyle(LioTheme.ink)
                    if recent.isEmpty {
                        Button(language.text("Clear history", "清除记录")) { confirmsClearHistory = true }
                            .frame(minHeight: 44)
                    }
                }
                if #available(iOS 18.0, *), let attempt {
                    Color.clear.frame(height: 0).accessibilityHidden(true)
                        .translationTask(source: attempt.request.source.locale, target: attempt.request.target.locale) { @Sendable session in
                            do {
                                let text = try await Self.translateLocally(attempt.request, using: session)
                                try Task.checkCancellation()
                                await finish(attempt.id, result: .success(.init(text: text, offline: true)))
                            } catch is CancellationError {
                                await finish(attempt.id, result: nil)
                            } catch {
                                await finish(attempt.id, result: .failure(error as? LioTranslationFailure ?? .unavailableLocally))
                            }
                        }
                        .id(attempt.id)
                }
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Translation", "翻译"))
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: input) { resetResult() }
        .onChange(of: source) { resetResult() }
        .onChange(of: target) { resetResult() }
        .onDisappear { attempt = nil; speaker.stopSpeaking(at: .immediate) }
        .task { reloadHistory() }
        .confirmationDialog(language.text("Clear recent translations?", "清除最近翻译？"),
                            isPresented: $confirmsClearHistory, titleVisibility: .visible) {
            Button(language.text("Clear history", "清除记录"), role: .destructive, action: clearHistory)
        }
    }

    private func languagePicker(_ title: String, selection: Binding<LioTranslationLanguage>,
                                other: Binding<LioTranslationLanguage>) -> some View {
        Menu {
            ForEach(LioTranslationLanguage.allCases, id: \.self) { choice in
                Button(name(choice)) {
                    let previous = selection.wrappedValue
                    selection.wrappedValue = choice
                    if choice == other.wrappedValue { other.wrappedValue = previous }
                }
            }
        } label: {
            Text(name(selection.wrappedValue))
                .frame(maxWidth: .infinity, minHeight: 44)
        }
        .accessibilityLabel(title)
        .accessibilityValue(name(selection.wrappedValue))
    }

    private func name(_ value: LioTranslationLanguage) -> String {
        switch value {
        case .english: language.text("English", "英文")
        case .chinese: language.text("Chinese", "中文")
        }
    }

    private func resultCard(_ value: LioTranslationResult) -> some View {
        let translated = value.text.joined(separator: "\n")
        return VStack(alignment: .leading, spacing: 8) {
            if value.offline {
                Text(language.text("Offline translation", "离线翻译"))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.ink)
            }
            if imageLines.isEmpty {
                Text(translated)
                    .foregroundStyle(LioTheme.ink)
                    .textSelection(.enabled)
                    .accessibilityIdentifier("lio.translation.result")
            } else {
                ForEach(imageLines) { line in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(line.original)
                            .font(.subheadline)
                        Text(line.translated).font(.body.weight(.medium))
                    }
                    .foregroundStyle(LioTheme.ink)
                    .textSelection(.enabled)
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier("lio.translation.line.\(line.id)")
                }
            }
            HStack {
                Button(language.text("Copy", "复制")) { UIPasteboard.general.string = translated }
                Button(language.text("Listen", "朗读")) {
                    speaker.stopSpeaking(at: .immediate)
                    let utterance = AVSpeechUtterance(string: translated)
                    utterance.voice = AVSpeechSynthesisVoice(language: target.rawValue)
                    speaker.speak(utterance)
                }
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: 16))
    }

    private var recentTranslations: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(language.text("Recent translations", "最近翻译")).font(.headline)
                Spacer()
                Button(language.text("Clear history", "清除记录")) { confirmsClearHistory = true }
                    .frame(minHeight: 44)
            }
            ForEach(recent) { entry in
                VStack(alignment: .leading, spacing: 6) {
                    Text(entry.input)
                    Text(entry.output)
                    if entry.offline {
                        Text(language.text("Offline translation", "离线翻译")).font(.footnote)
                    }
                }
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: 12))
            }
        }
        .foregroundStyle(LioTheme.ink)
    }

    private func reloadHistory() {
        guard let history else { return }
        do {
            recent = try history.load()
            historyError = false
        } catch { historyError = true }
    }

    private func clearHistory() {
        guard let history else { return }
        do {
            try history.clear()
            recent = []
            historyError = false
        } catch { historyError = true }
    }

    private func resetResult() {
        attempt = nil
        result = nil
        imageLines = []
        imageText = []
        spokenText = nil
        problem = nil
        speaker.stopSpeaking(at: .immediate)
    }

    private func start() { start([input], fromImage: false) }

    private func start(_ lines: [String], fromImage: Bool) {
        resetResult()
        if #available(iOS 18.0, *) {
            attempt = Attempt(request: .init(source: source, target: target, text: lines), fromImage: fromImage)
        } else {
            problem = .unsupported
        }
    }

    @available(iOS 18.0, *)
    private nonisolated static func translateLocally(_ request: LioTranslationRequest,
                                                       using session: TranslationSession) async throws -> [String] {
        let availability = await LanguageAvailability().status(from: request.source.locale, to: request.target.locale)
        switch availability {
        case .unsupported: throw LioTranslationFailure.unsupported
        case .supported: try await session.prepareTranslation()
        case .installed: break
        @unknown default: throw LioTranslationFailure.unavailableLocally
        }
        var translated: [String] = []
        for text in request.text {
            try Task.checkCancellation()
            translated.append(try await session.translate(text).targetText)
        }
        return translated
    }

    private func finish(_ id: UUID, result outcome: Result<LioTranslationResult, LioTranslationFailure>?) {
        guard let attempt, attempt.id == id else { return }
        self.attempt = nil
        switch outcome {
        case .success(let value):
            if attempt.fromImage {
                do { imageLines = try LioImageTranslationLine.pair(attempt.request.text, with: value.text) }
                catch { problem = .unavailableLocally; return }
            }
            result = value
            if let history {
                let entry = LioRecentTranslation(source: attempt.request.source, target: attempt.request.target,
                                                 input: attempt.request.text.joined(separator: "\n"),
                                                 output: value.text.joined(separator: "\n"), offline: value.offline)
                do {
                    recent = try history.record(entry)
                    historyError = false
                } catch { historyError = true }
            }
        case .failure(let error): problem = error
        case nil: break
        }
    }

    private func message(for failure: LioTranslationFailure) -> String {
        switch failure {
        case .unsupported:
            language.text("Offline translation for these languages is unavailable on this device. It requires iOS 18 or later.",
                          "此设备暂不支持这两种语言的离线翻译。需使用 iOS 18 或更新版本。")
        default:
            language.text("Couldn’t translate offline. Connect to Wi-Fi to download the languages, then try again.",
                          "暂时无法离线翻译。请连接 Wi-Fi 下载语言包后重试。")
        }
    }
}
#endif
