#if os(iOS)
import AVFoundation
import SwiftUI
import UIKit

struct LioToolsView: View {
    let language: LioLanguage
    let history: LioTranslationHistory?
    let relay: LioRelayTranslationClient?
    let enabled: Bool
    let sessionIsCurrent: @MainActor () -> Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    NavigationLink {
                        LioTextTranslationView(language: language, history: history, enabled: enabled, isCurrent: {
                            UIApplication.shared.applicationState != .background && sessionIsCurrent()
                        }, relay: relay)
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
                        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
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
    let enabled: Bool
    let isCurrent: @MainActor () -> Bool
    let relay: LioRelayTranslationClient?
    @State private var source: LioTranslationLanguage = .english
    @State private var target: LioTranslationLanguage = .chinese
    @State private var input = ""
    @State private var attempt: Attempt?
    @State private var retryAttempt: Attempt?
    @State private var result: LioTranslationResult?
    @State private var imageLines: [LioImageTranslationLine] = []
    @State private var spokenText: String?
    @State private var problem: LioTranslationFailure?
    @State private var speaker = AVSpeechSynthesizer()
    @State private var recent: [LioRecentTranslation] = []
    @State private var confirmsClearHistory = false
    @State private var historyError = false
    @State private var relayOriginals = LioRelayOriginalRequests()

    private struct Attempt: Identifiable {
        enum Input { case text, photo(Data), recording(LioTranslationRecording) }
        let id = UUID()
        var request: LioTranslationRequest
        let input: Input
        var preparedPayload: LioRelayTranslationRequest.Payload?

        var fromImage: Bool {
            if case .photo = input { return true }
            return false
        }
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
                    .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
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
                    .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                              || attempt != nil || problem == .alreadyAccepted)
                }
                LioRelayVoiceInput(language: language, source: source, enabled: enabled,
                                   isCurrent: isCurrent, onRecording: startRecording)
                if let spokenText {
                    Text(spokenText)
                        .foregroundStyle(LioTheme.ink)
                        .textSelection(.enabled)
                        .accessibilityIdentifier("lio.translation.transcript")
                }
                LioTranslationImageInput(language: language, source: source, enabled: enabled,
                                         isCurrent: isCurrent, onImage: startPhoto)
                if attempt != nil { ProgressView(language.text("Translating…", "正在翻译…")) }
                if let result { resultCard(result) }
                if let problem {
                    Text(message(for: problem))
                        .foregroundStyle(LioTheme.ink)
                        .accessibilityIdentifier("lio.translation.problem")
                    if let retryAttempt {
                        Button(language.text("Retry", "重试")) {
                            begin(retryAttempt.input, text: retryAttempt.request.text,
                                  preparedPayload: retryAttempt.preparedPayload)
                        }
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("lio.translation.retry")
                    }
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

            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Translation", "翻译"))
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: input) { resetResult() }
        .onChange(of: source) { resetResult() }
        .onChange(of: target) { resetResult() }
        .onChange(of: enabled) { _, available in
            if !available { resetResult() }
        }
        .onDisappear { resetResult() }
        .task { reloadHistory() }
        .task(id: attempt?.id) {
            guard let attempt, let relay, isCurrent() else { return }
            await translateWithRelay(attempt, using: relay)
        }
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
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
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
                }
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
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
        retryAttempt = nil
        spokenText = nil
        problem = nil
        speaker.stopSpeaking(at: .immediate)
    }

    private func start() { begin(.text, text: [input]) }

    private func startPhoto(_ data: Data) { begin(.photo(data)) }

    private func startRecording(_ data: LioTranslationRecording) { begin(.recording(data)) }

    private func begin(_ input: Attempt.Input, text: [String] = [],
                       preparedPayload: LioRelayTranslationRequest.Payload? = nil) {
        guard enabled, isCurrent() else { return }
        resetResult()
        guard relay != nil else {
            problem = .accessDenied
            return
        }
        attempt = Attempt(request: .init(source: source, target: target, text: text), input: input,
                          preparedPayload: preparedPayload)
    }

    private func translateWithRelay(_ attempt: Attempt, using relay: LioRelayTranslationClient) async {
        do {
            let payload: LioRelayTranslationRequest.Payload
            if let preparedPayload = attempt.preparedPayload {
                payload = preparedPayload
            } else {
                switch attempt.input {
                case .text: payload = .text(attempt.request.text.joined(separator: "\n"))
                case .photo(let data): payload = .jpeg(try await LioTranslationImageEncoder.jpeg(from: data))
                case .recording(let data): payload = .wav(try data.wireWAV())
                }
            }
            try Task.checkCancellation()
            guard self.attempt?.id == attempt.id, isCurrent() else { return }
            self.attempt?.preparedPayload = payload
            guard !relay.requiresOriginalStore || history != nil else { throw LioRelayTranslationFailure.originalUnavailable }
            let original = try relayOriginals.request(source: attempt.request.source, target: attempt.request.target,
                                                       payload: payload, storage: history)
            let reply: LioRelayTranslationResponse
            do {
                reply = try await relay.translate(original)
            } catch LioRelayTranslationFailure.alreadyAccepted {
                guard self.attempt?.id == attempt.id, isCurrent() else { return }
                try relayOriginals.accept(original, storage: history)
                throw LioRelayTranslationFailure.alreadyAccepted
            }
            if case .text(let source) = payload {
                guard let echoed = reply.items.first?.sourceText, echoed.utf8.elementsEqual(source.utf8) else {
                    throw LioTranslationFailure.service
                }
            }
            guard self.attempt?.id == attempt.id, isCurrent() else { return }
            guard !reply.items.isEmpty else {
                try relayOriginals.accept(original, storage: history)
                finish(attempt.id, result: .failure(.noRecognizedText))
                return
            }
            if case .recording = attempt.input { spokenText = reply.items.first?.sourceText }
            self.attempt?.request = .init(source: attempt.request.source, target: attempt.request.target,
                                          text: reply.items.map(\.sourceText))
            finish(attempt.id, result: .success(.init(text: reply.items.map(\.translatedText))),
                   relayOriginal: original)
        } catch is CancellationError {
            finish(attempt.id, result: nil)
        } catch LioRelayTranslationFailure.signInRequired {
            finish(attempt.id, result: .failure(.signInRequired))
        } catch LioRelayTranslationFailure.accessDenied {
            finish(attempt.id, result: .failure(.accessDenied))
        } catch LioRelayTranslationFailure.alreadyAccepted {
            finish(attempt.id, result: .failure(.alreadyAccepted))
        } catch LioRelayTranslationFailure.invalidInput {
            switch attempt.input {
            case .text: finish(attempt.id, result: .failure(.tooLong))
            case .photo: finish(attempt.id, result: .failure(.unreadableImage))
            case .recording: finish(attempt.id, result: .failure(.invalidRecording))
            }
        } catch let error as LioTranslationFailure {
            guard !Task.isCancelled else { return }
            finish(attempt.id, result: .failure(error))
        } catch LioTranslationMediaFailure.unreadableImage {
            finish(attempt.id, result: .failure(.unreadableImage))
        } catch {
            finish(attempt.id, result: .failure(.service))
        }
    }

    private func finish(_ id: UUID, result outcome: Result<LioTranslationResult, LioTranslationFailure>?,
                        relayOriginal: LioRelayTranslationRequest? = nil) {
        guard let attempt, attempt.id == id, isCurrent() else { return }
        self.attempt = nil
        switch outcome {
        case .success(let value):
            if attempt.fromImage {
                do { imageLines = try LioImageTranslationLine.pair(attempt.request.text, with: value.text) }
                catch { problem = .service; return }
            }
            let entry = LioRecentTranslation(source: attempt.request.source, target: attempt.request.target,
                                             input: attempt.request.text.joined(separator: "\n"),
                                             output: value.text.joined(separator: "\n"), offline: false)
            do {
                let saved: [LioRecentTranslation]?
                if let relayOriginal {
                    saved = try relayOriginals.deliver(relayOriginal, entry: entry, storage: history)
                } else {
                    saved = try history?.record(entry)
                }
                if let saved { recent = saved }
                historyError = false
            } catch { historyError = true }
            result = value
        case .failure(let error):
            problem = error
            switch error {
            case .network, .quota, .service, .timedOut: retryAttempt = attempt
            default: break
            }
        case nil: break
        }
    }

    private func message(for failure: LioTranslationFailure) -> String {
        switch failure {
        case .signInRequired:
            language.text("Sign in again to use online translation.", "请重新登录后使用在线翻译。")
        case .accessDenied:
            language.text("Online translation isn’t available for this account.", "此账号暂未开通在线翻译。")
        case .alreadyAccepted:
            language.text("This translation was already sent.", "这次翻译已发送。")
        case .noRecognizedText:
            language.text("No text was found to translate.", "没有识别到可翻译的文字。")
        case .invalidRecording:
            language.text("Couldn’t use this recording. Try recording again.", "无法使用这段录音，请重新录制。")
        case .unreadableImage:
            language.text("Couldn’t read this photo. Try another image.", "暂时无法识别这张图片，请换一张。")
        case .tooLong:
            language.text("Use up to 4,000 characters at a time.", "每次最多翻译 4000 字。")
        case .service:
            language.text("Translation is temporarily unavailable. Try again.", "翻译暂时不可用，请重试。")
        case .network:
            language.text("You're offline. Connect to the internet to translate.", "网络不可用，翻译需要联网。")
        case .quota:
            language.text("Translation limit reached. Try again later.", "翻译额度已用完，请稍后重试。")
        case .timedOut:
            language.text("Translation timed out. Try again.", "翻译超时，请重试。")
        }
    }
}
#endif
