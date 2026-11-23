#if os(iOS)
import AVFoundation
import CJRunClient
import SwiftUI
import Translation
import UIKit

struct LioToolsView: View {
    let language: LioLanguage
    let history: LioTranslationHistory?
    let relay: LioRelayTranslationClient?
    let draftStorage: LocalSupportDraftStorage?
    let enabled: Bool
    let sessionIsCurrent: @MainActor () -> Bool
    @Environment(\.lioTaxiEntry) private var taxiEntry

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    Text(language.text("Tools", "插件"))
                        .font(.largeTitle.bold())
                        .foregroundStyle(LioTheme.ink)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityAddTraits(.isHeader)
                    NavigationLink {
                        LioLocalSupportView(language: language, draftStorage: draftStorage)
                            .toolbar(.visible, for: .navigationBar)
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: "lifepreserver")
                            Text(language.text("Local Support", "本地协助"))
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
                    .accessibilityIdentifier("lio.tools.local-support")
                    if let taxiEntry {
                        taxi(taxiEntry)
                    }
                    #if DEBUG
                    if ProcessInfo.processInfo.arguments.contains("--lio-hotels-preview") {
                        previewHotels
                    }
                    #endif
                    NavigationLink {
                        LioTextTranslationView(language: language, history: history, enabled: enabled, isCurrent: {
                            UIApplication.shared.applicationState != .background && sessionIsCurrent()
                        }, relay: relay)
                            .toolbar(.visible, for: .navigationBar)
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
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(.hidden, for: .navigationBar)
        }
        .tint(LioTheme.vermilion)
    }

    private func taxi(_ entry: LioTaxiEntry) -> some View {
        NavigationLink {
            LioTaxiView(language: language, service: entry.service, tripPlaces: entry.tripPlaces,
                       recentStore: entry.recentStore)
                .toolbar(.visible, for: .navigationBar)
        } label: {
            Label(language.text("Taxi", "打车"), systemImage: "car")
                .foregroundStyle(LioTheme.ink)
                .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
                .padding(.horizontal, 16)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("lio.tools.taxi")
    }

    #if DEBUG
    private var previewHotels: some View {
        let partial = ProcessInfo.processInfo.arguments.contains("--lio-hotels-preview-partial")
        return NavigationLink {
            LioHotelsView(language: language, service: .preview(unapplied: partial ? [.guests] : []),
                          suggestedArea: LioHotelService.previewArea)
                .toolbar(.visible, for: .navigationBar)
        } label: {
            Label(language.text("Hotels", "酒店"), systemImage: "bed.double")
                .foregroundStyle(LioTheme.ink)
                .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
                .padding(.horizontal, 16)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("lio.tools.hotels")
    }
    #endif
}

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

private struct LioTextTranslationView: View {
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
    @State private var outputMode: Mode = .text
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

    private var translationTitle: String { language.text("Translation", "翻译") }
    private var historyTitle: String { language.text("Recent translations", "最近翻译") }
    private var mode: Mode { presentation.mode }
    private var historyPresented: Binding<Bool> {
        Binding(get: { presentation.isHistoryOpen }, set: { presentation.setHistoryOpen($0) })
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
        var usesOfflineEngine = false

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
                originalCard
                translationCard
                if #available(iOS 18.0, *), let attempt, attempt.usesOfflineEngine {
                    Color.clear.frame(height: 0).accessibilityHidden(true)
                        .translationTask(source: Locale.Language(identifier: attempt.request.source.rawValue),
                                         target: Locale.Language(identifier: attempt.request.target.rawValue)) { @Sendable session in
                            do {
                                let text = try await LioOfflineTranslation.translate(attempt.request, using: session)
                                try Task.checkCancellation()
                                await finish(attempt.id, result: .success(.init(text: text, offline: true)))
                            } catch is CancellationError {
                                await finish(attempt.id, result: nil)
                            } catch {
                                await finish(attempt.id, result: .failure(error as? LioTranslationFailure ?? .unavailableOffline))
                            }
                        }
                        .id(attempt.id)
                }
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
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if !editingText { modeBar }
        }
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
            guard let attempt, isCurrent() else { return }
            if let relay {
                await translateWithRelay(attempt, using: relay)
            } else {
                await prepareOffline(attempt)
            }
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

    private var originalCard: some View {
        let captureID = presentation.captureID
        let captureEnabled = enabled && !presentation.isHistoryOpen
        return VStack(alignment: .leading, spacing: 8) {
            cardHeading(language.text("Original text", "待译内容"))
            switch mode {
            case .text:
                textInput
            case .voice:
                LioRelayVoiceInput(language: language, source: source, enabled: captureEnabled,
                                   isCurrent: { captureIsCurrent(.voice, id: captureID) }) { recording in
                    guard captureIsCurrent(.voice, id: captureID) else { return }
                    begin(.recording(recording))
                }
                .id(captureID)
                if let spokenText {
                    Text(language.text("Recognized speech", "识别出的文字")).font(.subheadline)
                    Text(spokenText)
                        .textSelection(.enabled)
                        .accessibilityIdentifier("lio.translation.transcript")
                }
            case .photo:
                LioTranslationImageInput(language: language, source: source, enabled: captureEnabled,
                                         isCurrent: { captureIsCurrent(.photo, id: captureID) }) { data in
                    guard captureIsCurrent(.photo, id: captureID) else { return }
                    begin(.photo(data))
                }
                .id(captureID)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 110, alignment: .topLeading)
        .padding(16)
        .background { keyboardDismissArea }
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func captureIsCurrent(_ mode: Mode, id: UUID) -> Bool {
        enabled && isCurrent() && presentation.acceptsCapture(mode, id: id)
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

    private var textInput: some View {
        let actions = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
            : AnyLayout(HStackLayout(spacing: 10))
        return VStack(alignment: .leading, spacing: 8) {
            TextEditor(text: $input)
                .focused($editingText)
                .font(LioTheme.display(.title3))
                .foregroundStyle(LioTheme.ink)
                .scrollContentBackground(.hidden)
                .frame(minHeight: 100)
                .accessibilityLabel(language.text("Text to translate", "要翻译的文本"))
                .accessibilityIdentifier("lio.translation.input")
            actions { textInputActions }
        }
    }

    @ViewBuilder
    private var textInputActions: some View {
        PasteButton(payloadType: String.self) { values in
            if let text = values.first { input = text }
        }
        .frame(minHeight: 44)
        Button(language.text("Clear", "清空")) { input = ""; resetResult() }
            .frame(minHeight: 44)
        Button(action: start) {
            Label(language.text("Translate", "翻译"), systemImage: "arrow.forward")
                .font(.subheadline.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
        }
        .buttonStyle(LioTranslationActionStyle(prominent: true))
        .accessibilityIdentifier("lio.translation.submit")
        .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                  || attempt != nil || problem == .alreadyAccepted)
    }

    private var translationCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeading(language.text("Translation", "译文"))
            if mode == outputMode {
                if let attempt { ProgressView(progress(for: attempt)) }
                if let result { resultContent(result) }
                if let problem {
                    Text(message(for: problem))
                        .accessibilityIdentifier("lio.translation.problem")
                    if problem == .speechDenied, let settings = URL(string: UIApplication.openSettingsURLString) {
                        Button { UIApplication.shared.open(settings) } label: {
                            Text(language.text("Open Settings", "打开设置"))
                                .frame(minHeight: 44)
                                .contentShape(Rectangle())
                        }
                    }
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
            }
        }
        .frame(maxWidth: .infinity, minHeight: 110, alignment: .topLeading)
        .padding(16)
        .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
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

    private var modeBar: some View {
        HStack(spacing: 4) {
            ForEach(Mode.allCases, id: \.self) { choice in
                Button {
                    withAnimation(LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion)) {
                        presentation.select(choice)
                    }
                } label: {
                    VStack(spacing: 3) {
                        Image(systemName: choice.symbol)
                            .font(.body.weight(.semibold))
                            .accessibilityHidden(true)
                        Text(choice.title(language))
                            .font(.caption.weight(.semibold))
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .foregroundStyle(LioTheme.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(mode == choice ? LioTheme.surfaceSunken : LioTheme.surface, in: Capsule())
                    .overlay {
                        if mode == choice {
                            Capsule().strokeBorder(LioTheme.inkSecondary)
                                .allowsHitTesting(false)
                                .accessibilityHidden(true)
                        }
                    }
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(mode == choice ? [.isSelected] : [])
                .accessibilityIdentifier("lio.translation.mode.\(choice.rawValue)")
                .disabled(attempt != nil)
            }
        }
        .padding(5)
        .lioFloatingSurface(Capsule())
        .padding(.horizontal, 18)
        .padding(.vertical, 8)
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
            if value.offline {
                Text(language.text("Offline translation", "离线翻译"))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
            }
            if imageLines.isEmpty {
                Text(translated)
                    .foregroundStyle(LioTheme.ink)
                    .textSelection(.enabled)
                    .accessibilityIdentifier("lio.translation.result")
            } else {
                // This header is the home for a future photo/line display selector.
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
                    if entry.offline {
                        Text(language.text("Offline translation", "离线翻译")).font(.footnote)
                    }
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

    private func progress(for attempt: Attempt) -> String {
        guard attempt.hasMedia else { return language.text("Translating…", "正在翻译…") }
        return LioMediaTranslationProgress(payloadPrepared: attempt.preparedPayload != nil,
                                           bodySent: attempt.uploadSent).label(language)
    }

    private func begin(_ input: Attempt.Input, text: [String] = [],
                       preparedPayload: LioRelayTranslationRequest.Payload? = nil) {
        guard enabled, isCurrent(), mode == input.mode, !presentation.isHistoryOpen else { return }
        resetResult()
        outputMode = input.mode
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
            if #available(iOS 18.0, *), error.allowsOfflineFallback {
                await prepareOffline(attempt)
            } else {
                finish(attempt.id, result: .failure(error))
            }
        } catch LioTranslationMediaFailure.unreadableImage {
            finish(attempt.id, result: .failure(.unreadableImage))
        } catch {
            finish(attempt.id, result: .failure(.service))
        }
    }

    private func prepareOffline(_ attempt: Attempt) async {
        guard self.attempt?.id == attempt.id, isCurrent(), !Task.isCancelled else { return }
        guard #available(iOS 18.0, *) else {
            finish(attempt.id, result: .failure(.unsupportedOffline))
            return
        }
        do {
            let lines: [String]
            switch attempt.input {
            case .text:
                lines = attempt.request.text
            case .photo(let data):
                lines = try await LioOfflineTranslation.readPhoto(data, language: attempt.request.source)
            case .recording(let recording):
                lines = [try await LioRecordedTranslationSpeech.text(from: recording, language: attempt.request.source,
                    isCurrent: { self.attempt?.id == attempt.id && isCurrent() })]
            }
            try Task.checkCancellation()
            guard self.attempt?.id == attempt.id, isCurrent() else { return }
            if case .recording = attempt.input { spokenText = lines.first }
            self.attempt?.request = .init(source: attempt.request.source, target: attempt.request.target, text: lines)
            self.attempt?.usesOfflineEngine = true
        } catch is CancellationError {
            finish(attempt.id, result: nil)
        } catch let error as LioTranslationFailure {
            finish(attempt.id, result: .failure(error))
        } catch {
            finish(attempt.id, result: .failure(attempt.fromImage ? .unreadableImage : .speechUnavailable))
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
                                             output: value.text.joined(separator: "\n"), offline: value.offline)
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
            case .network, .quota, .service, .timedOut, .signInRequired, .accessDenied, .unavailableOffline:
                retryAttempt = attempt
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
        case .unsupportedOffline:
            language.text("Offline translation requires iOS 18 or later and a supported language pair.",
                          "离线翻译需要 iOS 18 或更新版本，并且语言组合须受支持。")
        case .unavailableOffline:
            language.text("Offline translation isn’t ready. Connect to download the language packs.",
                          "离线翻译暂不可用，请联网下载语言包。")
        case .speechDenied:
            language.text("Allow Speech Recognition in Settings for offline voice translation.",
                          "请在设置中允许语音识别，以使用离线语音翻译。")
        case .speechUnavailable:
            language.text("Offline speech recognition isn’t available for this language on this device.",
                          "此设备暂不支持该语言的离线语音识别。")
        }
    }
}

private extension LioTranslationPresentation.Mode {
    var symbol: String {
        switch self {
        case .text: "text.alignleft"
        case .voice: "mic"
        case .photo: "camera"
        }
    }

    func title(_ language: LioLanguage) -> String {
        switch self {
        case .text: language.text("Text", "文字")
        case .voice: language.text("Voice", "语音")
        case .photo: language.text("Photo", "拍照")
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
