#if os(iOS)
import AVFoundation
import CJRunClient
import SwiftUI
import UIKit

struct LioTranslationActionStyle: ButtonStyle {
    var prominent = false
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        let accented = prominent && isEnabled
        let subdued = prominent && !isEnabled
        return configuration.label
            .foregroundStyle(accented ? LioTheme.onVermilion : LioTheme.ink)
            .padding(.horizontal, 10)
            .frame(minHeight: 44)
            .background(
                accented ? LioTheme.vermilion : (subdued || configuration.isPressed ? LioTheme.surfaceSunken : LioTheme.surface),
                in: Capsule()
            )
    }
}

struct LioTextTranslationView: View {
    private typealias Mode = LioTranslationPresentation.Mode
    let language: LioLanguage
    let history: LioTranslationHistory?
    let enabled: Bool
    let isCurrent: @MainActor () -> Bool
    let relay: LioRelayTranslationClient?
    @State private var source: LioTranslationLanguage = .english
    @State private var target: LioTranslationLanguage = .chinese
    @State private var input = ""
    @FocusState private var editingText: Bool
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.self) private var environment
    @State private var presentation = LioTranslationPresentation()
    @State private var voicePrompt: LioVoicePrompt?
    @State private var inputNotice: LioTranslationInputNotice?
    @Environment(\.openURL) private var openURL
    @State private var attempt: Attempt?
    @State private var retryAttempt: Attempt?
    @State private var result: LioTranslationResult?
    @State private var imageLines: [LioImageTranslationLine] = []
    @State private var positionedPhoto: LioPositionedTranslation?
    @State private var photoDisplay = PhotoResultDisplay.translated
    @State private var spokenText: String?
    @State private var problem: LioTranslationFailure?
    @State private var speaker = AVSpeechSynthesizer()
    @State private var recent: [LioRecentTranslation] = []
    @State private var confirmsClearHistory = false
    @State private var historyError = false
    @State private var relayOriginals = LioRelayOriginalRequests()

    private var translationTitle: String { language.text("Translation", "翻译") }
    private var historyTitle: String { language.text("Recent translations", "最近翻译") }
    private var historyPresented: Binding<Bool> {
        Binding(get: { presentation.isHistoryOpen }, set: { presentation.setHistoryOpen($0) })
    }

    private enum PhotoResultDisplay: String {
        case translated, photo, lines
    }

    private struct Attempt: Identifiable {
        enum Input {
            case text, photo(Data), recording(LioTranslationRecording)

            var mode: Mode {
                switch self {
                case .text: .text
                case .photo: .photo
                case .recording: .voice
                }
            }
        }
        let id = UUID()
        var request: LioTranslationRequest
        let input: Input
        var preparedPayload: LioRelayTranslationRequest.Payload?
        var uploadSent = false

        var fromImage: Bool {
            if case .photo = input { return true }
            return false
        }

        var hasMedia: Bool {
            if case .text = input { return false }
            return true
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                languages
                resultArea
            }
            .padding(18)
            .background {
                ZStack {
                    keyboardDismissArea
                    LioKeyboardScrollObserver(enabled: editingText) { editingText = false }
                        .allowsHitTesting(false)
                }
                .accessibilityHidden(true)
            }
        }
        .accessibilityIdentifier("lio.translation.scroll")
        .scrollDismissesKeyboard(.interactively)
        .scrollBounceBehavior(editingText ? .always : .automatic, axes: .vertical)
        .background(LioTheme.paper)
        .navigationTitle(translationTitle)
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom, spacing: 0) { inputBar }
        .toolbar {
            ToolbarItem(placement: .principal) { toolbarTitle(translationTitle) }
            ToolbarItem(placement: .topBarTrailing) {
                if editingText {
                    Button(language.text("Done", "完成")) { editingText = false }
                        .accessibilityIdentifier("lio.translation.keyboard-done")
                } else {
                    Button { presentation.setHistoryOpen(true) } label: {
                        Image(systemName: "clock")
                            .frame(minWidth: 44, minHeight: 44)
                    }
                    .accessibilityLabel(historyTitle)
                    .accessibilityIdentifier("lio.translation.history")
                }
            }
        }
        .sheet(isPresented: historyPresented) { historySheet }
        .onChange(of: input) { resetResult() }
        .onChange(of: source) { resetResult() }
        .onChange(of: target) { resetResult() }
        .onChange(of: enabled) { _, available in
            guard !available else { return }
            // The root replaces this view on sign-out or owner change. A session
            // pause within the same owner must not discard captured input.
            let retainedInput = attempt ?? retryAttempt
            let retainedProblem = problem ?? .signInRequired
            resetResult()
            if let retainedInput {
                retryAttempt = retainedInput
                problem = retainedProblem
            }
        }
        .onDisappear { resetResult() }
        .task { reloadHistory() }
        .task(id: attempt?.id) {
            guard let attempt, let relay, isCurrent() else { return }
            await translateWithRelay(attempt, using: relay)
        }
    }

    private var languages: some View {
        HStack(spacing: 4) {
            languagePicker(language.text("From", "源语言"), selection: $source, other: $target)
            Button {
                withAnimation(LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion)) {
                    let previous = source
                    source = target
                    target = previous
                }
            } label: {
                Image(systemName: "arrow.left.arrow.right")
                    .foregroundStyle(LioTheme.vermilion)
                    .frame(width: 44, height: 44)
                    .background(LioTheme.surfaceSunken, in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(language.text("Swap languages", "互换语言"))
            .accessibilityIdentifier("lio.translation.swap")
            languagePicker(language.text("To", "目标语言"), selection: $target, other: $source)
        }
        .padding(5)
        .background(LioTheme.surface, in: Capsule())
    }

    /// Voice, photo and typed input share one bar, like a chat composer. Inputs pause
    /// while a translation is in flight or the history sheet is open, which retires any
    /// capture that was still being prepared.
    private var captureEnabled: Bool {
        enabled && !presentation.isHistoryOpen && attempt == nil
    }

    private func captureIsCurrent() -> Bool {
        enabled && isCurrent() && !presentation.isHistoryOpen
    }

    private var hasTypedText: Bool {
        !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var inputBar: some View {
        VStack(spacing: 8) {
            if let voicePrompt {
                HStack(spacing: 8) {
                    Image(systemName: voicePrompt.cancelling ? "xmark.circle.fill" : "waveform")
                        .foregroundStyle(voicePrompt.cancelling ? LioTheme.danger : LioTheme.vermilion)
                        .accessibilityHidden(true)
                    Text(voicePrompt.text)
                    Spacer(minLength: 8)
                    Text(timerInterval: voicePrompt.startedAt...voicePrompt.startedAt.addingTimeInterval(60),
                         countsDown: false)
                        .monospacedDigit()
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(LioTheme.ink)
                .padding(.horizontal, 16)
                .frame(minHeight: 44)
                .lioCard(Capsule())
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("lio.translation.recording")
            } else if let inputNotice {
                HStack(spacing: 8) {
                    Text(inputNotice.text)
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    if inputNotice.opensSettings {
                        Button(language.text("Open Settings", "打开设置")) {
                            if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                        }
                        .font(.subheadline.weight(.semibold))
                        .frame(minHeight: 44)
                    }
                }
                .foregroundStyle(LioTheme.ink)
                .padding(.horizontal, 16)
                .padding(.vertical, 6)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                .accessibilityIdentifier("lio.translation.input-notice")
            }
            HStack(alignment: .bottom, spacing: 8) {
                LioTranslationImageInput(language: language, source: source, enabled: captureEnabled,
                                         isCurrent: captureIsCurrent, onImage: { data in
                    guard captureIsCurrent() else { return }
                    begin(.photo(data))
                }, notice: $inputNotice)
                TextField(language.text("Type, or hold the mic to talk", "输入文字，或按住麦克风说话"),
                          text: $input, axis: .vertical)
                    .lineLimit(1...5)
                    .focused($editingText)
                    .font(.body)
                    .foregroundStyle(LioTheme.ink)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 11)
                    .frame(minHeight: 44)
                    .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                    .overlay {
                        RoundedRectangle(cornerRadius: LioTheme.Radius.card).stroke(LioTheme.hairline, lineWidth: LioTheme.outlineWidth)
                            .allowsHitTesting(false)
                    }
                    .accessibilityLabel(language.text("Text to translate", "要翻译的文本"))
                    .accessibilityIdentifier("lio.translation.input")
                if hasTypedText {
                    Button(action: start) {
                        Image(systemName: "arrow.up")
                            .font(.title3.weight(.bold))
                            .foregroundStyle(LioTheme.onVermilion)
                            .frame(width: 44, height: 44)
                            .background(LioTheme.vermilion, in: Circle())
                    }
                    .buttonStyle(.plain)
                    .disabled(attempt != nil || problem == .alreadyAccepted)
                    .opacity(attempt != nil || problem == .alreadyAccepted ? 0.5 : 1)
                    .accessibilityLabel(language.text("Translate", "翻译"))
                    .accessibilityIdentifier("lio.translation.submit")
                } else {
                    LioRelayVoiceInput(language: language, source: source, enabled: captureEnabled,
                                       isCurrent: captureIsCurrent, onRecording: { recording in
                        guard captureIsCurrent() else { return }
                        begin(.recording(recording))
                    }, prompt: $voicePrompt, notice: $inputNotice)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 8)
        .background(LioTheme.paper.opacity(0.96))
        .overlay(alignment: .top) {
            Rectangle().fill(LioTheme.hairline).frame(height: LioTheme.outlineWidth)
                .accessibilityHidden(true)
        }
        .onChange(of: input) { _, _ in inputNotice = nil }
    }

    @ViewBuilder
    private var keyboardDismissArea: some View {
        if editingText {
            Color.clear
                .contentShape(Rectangle())
                .onTapGesture { editingText = false }
                .accessibilityHidden(true)
        }
    }

    /// The latest translation, its original and any problem; an empty page explains the three inputs.
    private var resultArea: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let attempt {
                ProgressView(progress(for: attempt))
                    .foregroundStyle(LioTheme.inkSecondary)
            }
            if let result {
                if let original = originalText {
                    Text(original)
                        .font(.subheadline)
                        .foregroundStyle(LioTheme.inkSecondary)
                        .textSelection(.enabled)
                        .accessibilityLabel(language.text("You said: ", "你说的：") + original)
                        .accessibilityIdentifier("lio.translation.transcript")
                }
                resultContent(result)
            }
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
                    .disabled(!enabled)
                    .accessibilityIdentifier("lio.translation.retry")
                }
            }
            if attempt == nil, result == nil, problem == nil {
                emptyState
            }
        }
        .frame(maxWidth: .infinity, minHeight: 160, alignment: .topLeading)
        .padding(16)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    /// What was translated, when it isn't already on screen in the input field or as a photo.
    private var originalText: String? {
        if let spokenText { return spokenText }
        return nil
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(language.text("Translations appear here", "译文会显示在这里"))
                .font(LioTheme.display(.title3).weight(.semibold))
                .foregroundStyle(LioTheme.ink)
            emptyRow("keyboard", language.text("Type below and tap the arrow", "在下方输入文字，点箭头翻译"))
            emptyRow("mic.fill", language.text("Hold the mic, speak, then release", "按住麦克风说话，松开即翻译"))
            emptyRow("camera", language.text("Tap the camera to take or choose a photo", "点相机，拍照或从相册选图"))
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lio.translation.empty")
    }

    private func emptyRow(_ symbol: String, _ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: symbol)
                .foregroundStyle(LioTheme.vermilion)
                .frame(width: 22)
                .accessibilityHidden(true)
            Text(text)
                .font(.subheadline)
                .foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func cardHeading(_ label: String) -> some View {
        Text(label)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(LioTheme.inkSecondary)
            .accessibilityAddTraits(.isHeader)
    }

    private func toolbarTitle(_ title: String) -> some View {
        RunReadableText(text: title, style: .headline, color: Color(LioTheme.ink.resolve(in: environment)))
            .fixedSize()
            .accessibilityAddTraits(.isHeader)
    }

    private var historySheet: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if historyError {
                        Text(language.text("Translation history is temporarily unavailable.", "暂时无法访问翻译记录。"))
                        if recent.isEmpty { clearHistoryButton }
                    }
                    if !recent.isEmpty { recentTranslations }
                    if recent.isEmpty && !historyError { Text(language.text("No recent translations.", "暂无翻译记录。")) }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(18)
            }
            .background(LioTheme.paper)
            .navigationTitle(historyTitle)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) { toolbarTitle(historyTitle) }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { presentation.setHistoryOpen(false) } label: {
                        Image(systemName: "xmark")
                            .frame(minWidth: 44, minHeight: 44)
                    }
                    .accessibilityLabel(language.text("Close history", "关闭翻译记录"))
                    .accessibilityIdentifier("lio.translation.history-close")
                }
            }
            .confirmationDialog(language.text("Clear recent translations?", "清除最近翻译？"),
                                isPresented: $confirmsClearHistory, titleVisibility: .visible) {
                Button(language.text("Clear history", "清除记录"), role: .destructive, action: clearHistory)
            }
        }
        .tint(LioTheme.vermilion)
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
            HStack(spacing: 4) {
                Text(name(selection.wrappedValue))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                if !typeSize.isAccessibilitySize {
                    Image(systemName: "chevron.down").font(.caption2).accessibilityHidden(true)
                }
            }
            .font(.subheadline.weight(.semibold))
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

    private func resultContent(_ value: LioTranslationResult) -> some View {
        let translated = value.text.joined(separator: "\n")
        let actions = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading))
            : AnyLayout(HStackLayout())
        return VStack(alignment: .leading, spacing: 8) {
            if imageLines.isEmpty {
                Text(translated)
                    .font(LioTheme.display(.title2).weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                    .textSelection(.enabled)
                    .accessibilityIdentifier("lio.translation.result")
            } else {
                if let positionedPhoto {
                    HStack(spacing: 6) {
                        photoDisplayButton(.translated, title: language.text("Translated", "译图"))
                        photoDisplayButton(.photo, title: language.text("Photo", "照片"))
                        photoDisplayButton(.lines, title: language.text("Lines", "逐行"))
                    }
                    switch photoDisplay {
                    case .translated, .photo:
                        LioPositionedTranslationView(language: language, translation: positionedPhoto,
                                                     showsTranslation: photoDisplay == .translated)
                    case .lines:
                        lineComparison
                    }
                } else {
                    lineComparison
                }
            }
            actions {
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
    }

    private func photoDisplayButton(_ display: PhotoResultDisplay, title: String) -> some View {
        Button { photoDisplay = display } label: {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(LioTheme.ink)
                .frame(maxWidth: .infinity, minHeight: 44)
                .background(photoDisplay == display ? LioTheme.surfaceSunken : LioTheme.surface,
                            in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(photoDisplay == display ? .isSelected : [])
        .accessibilityIdentifier("lio.translation.photo-layout." + display.rawValue)
    }

    private var lineComparison: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(language.text("Line by line", "逐行对照"), systemImage: "list.bullet")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(LioTheme.inkSecondary)
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
    }

    private var clearHistoryButton: some View {
        Button(language.text("Clear history", "清除记录")) { confirmsClearHistory = true }
            .frame(minHeight: 44)
    }

    private var recentTranslations: some View {
        VStack(alignment: .leading, spacing: 12) {
            clearHistoryButton
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
        positionedPhoto = nil
        photoDisplay = .translated
        retryAttempt = nil
        spokenText = nil
        problem = nil
        speaker.stopSpeaking(at: .immediate)
    }

    private func start() { begin(.text, text: [input]) }

    private func progress(for attempt: Attempt) -> String {
        guard attempt.hasMedia else { return language.text("Translating…", "正在翻译…") }
        return LioMediaTranslationProgress(payloadPrepared: attempt.preparedPayload != nil,
                                           bodySent: attempt.uploadSent).label(language)
    }

    private func begin(_ input: Attempt.Input, text: [String] = [],
                       preparedPayload: LioRelayTranslationRequest.Payload? = nil) {
        guard enabled, isCurrent(), !presentation.isHistoryOpen else { return }
        presentation.select(input.mode)
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
                                                       payload: payload, storage: history,
                                                       prefersImageLayout: attempt.fromImage && relay.supportsImageLayout)
            let reply: LioRelayTranslationResponse
            do {
                let uploadFinished: LioRelayTranslationClient.UploadFinished = { [id = attempt.id] in
                    guard self.attempt?.id == id, isCurrent() else { return }
                    self.attempt?.uploadSent = true
                }
                reply = try await relay.translate(original, uploadFinished: attempt.hasMedia ? uploadFinished : nil)
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
                finish(attempt.id, result: .failure(.noRecognizedText(.init(kind: reply.kind))))
                return
            }
            if original.usesImageLayout, case .jpeg(let preparedImage) = payload {
                positionedPhoto = try LioPositionedTranslation(image: preparedImage, reply: reply)
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
            case .network, .quota, .service, .timedOut, .signInRequired, .accessDenied: retryAttempt = attempt
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
        case .noRecognizedText(let media):
            media.recoveryText(language)
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

/// Observe the existing scroll gesture without replacing it or reserving space.
private struct LioKeyboardScrollObserver: UIViewRepresentable {
    let enabled: Bool
    let onSwipeUp: () -> Void

    func makeUIView(context: Context) -> Marker {
        let marker = Marker()
        marker.isUserInteractionEnabled = false
        return marker
    }

    func updateUIView(_ marker: Marker, context: Context) {
        marker.onSwipeUp = enabled ? onSwipeUp : nil
        marker.attach()
    }

    static func dismantleUIView(_ marker: Marker, coordinator: ()) {
        marker.detach()
    }

    final class Marker: UIView {
        weak var scroll: UIScrollView?
        var onSwipeUp: (() -> Void)?

        override func didMoveToWindow() {
            super.didMoveToWindow()
            if window == nil { detach() } else { attach() }
        }

        func attach() {
            var ancestor = superview
            while let view = ancestor, !(view is UIScrollView) { ancestor = view.superview }
            let enclosing = ancestor as? UIScrollView
            guard enclosing !== scroll else { return }
            detach()
            scroll = enclosing
            enclosing?.panGestureRecognizer.addTarget(self, action: #selector(panEnded(_:)))
        }

        func detach() {
            scroll?.panGestureRecognizer.removeTarget(self, action: #selector(panEnded(_:)))
            scroll = nil
        }

        @objc private func panEnded(_ pan: UIPanGestureRecognizer) {
            let offset = pan.translation(in: scroll)
            guard pan.state == .ended, offset.y < -max(36, abs(offset.x)) else { return }
            onSwipeUp?()
        }
    }
}
#endif
