#if os(iOS)
import AVFoundation
import PhotosUI
import SwiftUI
import UIKit

private struct LioMenuServiceKey: EnvironmentKey {
    static let defaultValue: LioMenuService? = nil
}

extension EnvironmentValues {
    /// Set by the host only when the build enables menu ordering (`G2CMenuOrderEnabled`, or Debug's
    /// `--lio-menu-preview`); the Tools card is hidden while it is `nil`.
    var lioMenuService: LioMenuService? {
        get { self[LioMenuServiceKey.self] }
        set { self[LioMenuServiceKey.self] = newValue }
    }
}

/// Menu ordering (点餐模式): photograph a menu, read each dish with dietary flags, then show staff a Chinese
/// order card. Behind `G2CMenuOrderEnabled`, hidden by default.
struct LioMenuOrderView: View {
    let language: LioLanguage
    let service: LioMenuService
    /// Saved food memory, or `nil` when memory is unavailable. Only `diet.spicy` is used, to pre-select
    /// "no spicy food"; it stays in this page's memory and is never stored or sent.
    let memoryNotes: [LioMenuDietNote]?
    @State private var needs: [LioDietaryNeed] = []
    @State private var appliedMemory = false
    @State private var photo: Data?
    @State private var reading: LioMenuReading?
    @State private var failure: LioMenuFailure?
    @State private var order = LioMenuOrder()
    @State private var showsCard = false
    @State private var pickerItem: PhotosPickerItem?
    @State private var showsCamera = false
    @State private var cameraProblem: String?

    private var spicyMemory: String? { memoryNotes.flatMap(LioMenuMemory.noSpicySource) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                if let reading {
                    LioMenuResults(language: language, reading: reading, restrictions: needs,
                                   order: $order)
                } else {
                    LioMenuIntro(language: language, needs: $needs, spicyMemory: spicyMemory) { inputs }
                    if photo != nil {
                        ProgressView(language.text("Reading the menu…", "正在识别菜单…"))
                            .frame(maxWidth: .infinity)
                            .accessibilityIdentifier("lio.menu.reading")
                    }
                    if let problem = cameraProblem ?? failure.map(message) {
                        Text(problem)
                            .foregroundStyle(LioTheme.danger)
                            .accessibilityIdentifier("lio.menu.failed")
                    }
                }
            }
            .padding(18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .tint(LioTheme.vermilion)
        .navigationTitle(language.text("Menu Helper", "点餐"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if reading != nil {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(language.text("New menu", "换一份")) {
                        reading = nil
                        order = LioMenuOrder()
                    }
                    .accessibilityIdentifier("lio.menu.restart")
                }
            }
        }
        .safeAreaInset(edge: .bottom) {
            if reading != nil, !order.isEmpty {
                Button {
                    for note in LioMenuNote.suggested(for: needs) where !order.has(note) { order.toggle(note) }
                    showsCard = true
                } label: {
                    Text(language.text("Show staff my order (\(order.count))", "给服务员看（\(order.count) 份）"))
                        .font(.headline)
                        .frame(maxWidth: .infinity, minHeight: 50)
                }
                .buttonStyle(.borderedProminent)
                .padding(.horizontal, 18)
                .padding(.bottom, LioTheme.Spacing.xs)
                .background(LioTheme.paper)
                .accessibilityIdentifier("lio.menu.show-card")
            }
        }
        .sheet(isPresented: $showsCard) {
            if let reading {
                LioMenuCardSheet(language: language, reading: reading, order: $order)
            }
        }
        .sheet(isPresented: $showsCamera) {
            LioMenuCamera { data in
                showsCamera = false
                if let data { photo = data }
            }
            .ignoresSafeArea()
        }
        .onAppear {
            guard !appliedMemory else { return }
            appliedMemory = true
            if spicyMemory != nil, !needs.contains(.noSpicy) { needs.insert(.noSpicy, at: 0) }
        }
        .onChange(of: pickerItem) { _, item in
            guard let item else { return }
            pickerItem = nil
            Task {
                if let data = try? await item.loadTransferable(type: Data.self) { photo = data } else {
                    failure = .unreadablePhoto
                }
            }
        }
        .task(id: photo) {
            guard let photo else { return }
            failure = nil
            cameraProblem = nil
            do {
                guard let jpeg = try? await LioTranslationImageEncoder.jpeg(from: photo) else {
                    throw LioMenuFailure.unreadablePhoto
                }
                let found = try await service.read(jpeg)
                guard !Task.isCancelled, self.photo == photo else { return }
                reading = found
            } catch is CancellationError {
                // A newer photo replaced this one, or the account changed: never keep this photo around.
                if self.photo == photo { self.photo = nil }
                return
            } catch {
                guard !Task.isCancelled, self.photo == photo else { return }
                failure = error as? LioMenuFailure ?? .unavailable
            }
            // The photo is not kept once it is read.
            self.photo = nil
        }
    }

    private func message(_ failure: LioMenuFailure) -> String {
        switch failure {
        case .signInRequired: language.text("Sign in to read menus.", "登录后才能识别菜单。")
        case .notEnabled: language.text("Menu reading isn't available for this account yet.", "这个账号暂时还不能识别菜单。")
        case .quota: language.text("Menu reading has reached its limit for now. Try again later.",
                                    "菜单识别暂时达到上限，请稍后再试。")
        case .timedOut: language.text("That took too long. Try again.", "识别超时了，请再试一次。")
        case .offline: language.text("No connection. Check your network and try again.", "没有网络，请检查网络后再试。")
        case .unreadablePhoto: language.text("Couldn't open this photo. Try another one.", "这张照片打不开，请换一张。")
        case .alreadyUsed, .unavailable:
            language.text("Couldn't read this menu right now. Try again, or take a clearer, flatter photo.",
                          "暂时无法识别这份菜单。请再试一次，或换一张更清楚、更平整的照片。")
        }
    }

    private var inputs: some View {
        HStack(spacing: LioTheme.Spacing.sm) {
            Button {
                Task { await openCamera() }
            } label: {
                Label(language.text("Photograph menu", "拍菜单"), systemImage: "camera")
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
            .buttonStyle(.borderedProminent)
            .accessibilityIdentifier("lio.menu.camera")
            PhotosPicker(selection: $pickerItem, matching: .images) {
                Label(language.text("Choose photo", "从相册选"), systemImage: "photo.on.rectangle")
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier("lio.menu.photo")
        }
        .disabled(photo != nil)
    }

    private func openCamera() async {
        cameraProblem = nil
        guard UIImagePickerController.isSourceTypeAvailable(.camera),
              Bundle.main.object(forInfoDictionaryKey: "NSCameraUsageDescription") != nil else {
            cameraProblem = language.text("This device can't take photos here. Choose a photo instead.",
                                          "此设备暂时无法拍照，可以从相册选图。")
            return
        }
        let granted: Bool
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: granted = true
        case .notDetermined: granted = await AVCaptureDevice.requestAccess(for: .video)
        default: granted = false
        }
        if granted { showsCamera = true } else {
            cameraProblem = language.text("Allow camera access in Settings to take a photo.", "如需拍照，请在设置中允许使用相机。")
        }
    }
}

// MARK: - Intro

struct LioMenuIntro<Actions: View>: View {
    let language: LioLanguage
    @Binding var needs: [LioDietaryNeed]
    /// The memory words behind a pre-selected "no spicy food", if any.
    let spicyMemory: String?
    @ViewBuilder let actions: Actions

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                Text(language.text("Photograph a Chinese menu", "拍一张中文菜单"))
                    .font(.title2.weight(.bold))
                Text(language.text("Lio explains each dish, marks ones that may not suit you, and makes a card in Chinese to show staff.",
                                   "Lio 会解释每道菜，标出可能不适合你的菜，再生成一张给服务员看的中文点单卡。"))
                    .foregroundStyle(LioTheme.inkSecondary)
            }
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                Text(language.text("What do you avoid?", "你有哪些忌口？"))
                    .font(.headline)
                group(language.text("Diet", "饮食"), LioDietaryNeed.preferences)
                if let spicyMemory, needs.contains(.noSpicy) {
                    Text(language.text("No spicy food is ticked from your memory: \(spicyMemory)",
                                       "「不吃辣」来自「我的记忆」：\(spicyMemory)"))
                        .font(.caption)
                        .foregroundStyle(LioTheme.inkSecondary)
                        .accessibilityIdentifier("lio.menu.memory")
                }
                group(language.text("Allergies", "过敏"), LioDietaryNeed.allergies)
            }
            .padding(LioTheme.Spacing.md)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            actions
            Text(language.text("The menu photo is sent only to our authorised model service to read it, and is not kept. What you tick here stays on this phone.",
                               "菜单照片只发给已授权的模型服务识别，不保存；你勾选的忌口只在本机比对，不上传。"))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.menu.privacy")
        }
    }

    private func group(_ title: String, _ options: [LioDietaryNeed]) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: LioTheme.Spacing.xs, alignment: .leading)],
                      alignment: .leading, spacing: LioTheme.Spacing.xs) {
                ForEach(options, id: \.self) { need in chip(need) }
            }
        }
    }

    private func chip(_ need: LioDietaryNeed) -> some View {
        let on = needs.contains(need)
        return Button {
            if on { needs.removeAll { $0 == need } } else { needs.append(need) }
        } label: {
            Label(need.text(language), systemImage: on ? "checkmark.circle.fill" : "circle")
                .font(.subheadline)
                .foregroundStyle(on ? LioTheme.onVermilion : LioTheme.ink)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .padding(.horizontal, LioTheme.Spacing.sm)
                .background(on ? LioTheme.vermilion : LioTheme.surfaceSunken,
                            in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
        .accessibilityIdentifier("lio.menu.need.\(need.rawValue)")
    }
}

// MARK: - Results

struct LioMenuResults: View {
    let language: LioLanguage
    let reading: LioMenuReading
    let restrictions: [LioDietaryNeed]
    @Binding var order: LioMenuOrder

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
            if reading.isSample {
                Text(language.text("Sample menu for testing — not your photo.", "示例菜单，仅供测试，不是你拍的照片。"))
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(LioTheme.vermilion)
                    .accessibilityIdentifier("lio.menu.sample")
            }
            if reading.truncated {
                Text(language.text("This menu is long: only the first part was read. Photograph the rest separately.",
                                   "菜单较长，只识别了前一部分，其余可以分开再拍。"))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.menu.truncated")
            }
            Text(language.text("\(reading.dishes.count) dishes. Tap + to add to your order.",
                               "识别到 \(reading.dishes.count) 道菜，点「+」加入点单。"))
                .font(.subheadline)
                .foregroundStyle(LioTheme.inkSecondary)
            ForEach(reading.dishes) { dish in
                LioMenuDishCard(language: language, dish: dish,
                                flags: LioMenuFlag.flags(for: dish, restrictions: restrictions),
                                quantity: order.quantity(of: dish),
                                add: { order.add(dish) }, remove: { order.remove(dish) })
            }
            Text(language.text("Explanations describe how the dish is usually made. Kitchens differ: for allergies, always confirm with staff.",
                               "解释按常见做法写，各店做法不同；有过敏请务必向服务员确认。"))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityIdentifier("lio.menu.footer")
        }
    }
}

struct LioMenuDishCard: View {
    let language: LioLanguage
    let dish: LioMenuDish
    let flags: [LioMenuFlag]
    let quantity: Int
    let add: () -> Void
    let remove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(dish.nameZH ?? language.text("Unreadable dish", "看不清的菜"))
                        .font(.title3.weight(.bold))
                        .foregroundStyle(dish.isLegible ? LioTheme.ink : LioTheme.inkSecondary)
                    if dish.isLegible {
                        Text(dish.nameEN).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    }
                }
                Spacer(minLength: LioTheme.Spacing.xs)
                if let price = dish.priceText {
                    Text(price).font(.subheadline.monospacedDigit()).foregroundStyle(LioTheme.inkSecondary)
                }
            }
            ForEach(flags, id: \.self) { flag in
                LioMenuFlagBadge(language: language, flag: flag)
            }
            if dish.isLegible {
                Text(language.text(dish.summaryEN, dish.summaryZH))
                detail(language.text("Main ingredients", "主要食材"), language.text(dish.ingredientsEN, dish.ingredientsZH))
                HStack(spacing: LioTheme.Spacing.md) {
                    spice
                    detail(language.text("Method", "做法"), language.text(dish.methodEN, dish.methodZH))
                }
                detail(language.text("Portion", "分量"), language.text(dish.portionEN, dish.portionZH))
                stepper
            }
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityIdentifier("lio.menu.dish.\(dish.id)")
    }

    private func detail(_ title: String, _ value: String) -> some View {
        (Text(title + language.text(": ", "：")).foregroundStyle(LioTheme.inkSecondary) + Text(value))
            .font(.subheadline)
    }

    @ViewBuilder private var spice: some View {
        if let level = dish.spice {
            HStack(spacing: 2) {
                ForEach(0..<max(level.rawValue, 1), id: \.self) { _ in
                    Image(systemName: level == .notSpicy ? "leaf" : "flame.fill")
                }
                Text(level.text(language))
            }
            .font(.subheadline)
            .foregroundStyle(level == .notSpicy ? LioTheme.jade : LioTheme.vermilion)
        } else {
            Text(language.text("Spice level not clear", "辣度不确定")).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
        }
    }

    private var stepper: some View {
        HStack(spacing: LioTheme.Spacing.sm) {
            Spacer()
            if quantity > 0 {
                Button(action: remove) {
                    Image(systemName: "minus").font(.headline).foregroundStyle(LioTheme.vermilion)
                        .frame(width: 44, height: 44)
                        .background(LioTheme.surfaceSunken, in: Circle())
                }
                    .accessibilityLabel(language.text("Remove one", "减一份"))
                    .accessibilityIdentifier("lio.menu.remove.\(dish.id)")
                Text("\(quantity)").font(.headline.monospacedDigit()).frame(minWidth: 24)
            }
            Button(action: add) {
                Image(systemName: "plus").font(.headline).foregroundStyle(LioTheme.onVermilion)
                    .frame(width: 44, height: 44)
                    .background(LioTheme.vermilion, in: Circle())
            }
            .disabled(quantity >= LioMenuOrder.maximumQuantity)
            .accessibilityLabel(language.text("Add one", "加一份"))
            .accessibilityIdentifier("lio.menu.add.\(dish.id)")
        }
    }
}

struct LioMenuFlagBadge: View {
    let language: LioLanguage
    let flag: LioMenuFlag

    var body: some View {
        Label(flag.text(language), systemImage: symbol)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(flag.isWarning ? LioTheme.onVermilion : LioTheme.ink)
            .padding(.horizontal, LioTheme.Spacing.sm)
            .padding(.vertical, LioTheme.Spacing.xxs)
            .background(background, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
            .fixedSize(horizontal: false, vertical: true)
    }

    private var symbol: String {
        switch flag {
        case .unsuitable: "xmark.circle.fill"
        case .check, .mayContain: "exclamationmark.triangle.fill"
        case .unreadable: "questionmark.circle"
        }
    }

    private var background: Color {
        switch flag {
        case .unsuitable: LioTheme.vermilion
        case .check, .mayContain: LioTheme.gold.opacity(0.35)
        case .unreadable: LioTheme.surfaceSunken
        }
    }
}

// MARK: - Card for staff

struct LioMenuCardSheet: View {
    let language: LioLanguage
    let reading: LioMenuReading
    @Binding var order: LioMenuOrder
    @Environment(\.dismiss) private var dismiss
    @State private var priorIdleTimer: Bool?

    var body: some View {
        NavigationStack {
            ScrollView {
                LioMenuCardContent(language: language, card: order.card(in: reading), order: $order)
                    .padding(24)
            }
            .background(LioTheme.paper)
            .foregroundStyle(LioTheme.ink)
            .navigationTitle(language.text("Show staff", "给服务员看"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(language.text("Close", "关闭")) { dismiss() }
                        .accessibilityIdentifier("lio.menu.card.done")
                }
            }
        }
        .tint(LioTheme.vermilion)
        .onAppear {
            guard priorIdleTimer == nil else { return }
            priorIdleTimer = UIApplication.shared.isIdleTimerDisabled
            UIApplication.shared.isIdleTimerDisabled = true
        }
        .onDisappear {
            if let priorIdleTimer {
                UIApplication.shared.isIdleTimerDisabled = priorIdleTimer
                self.priorIdleTimer = nil
            }
        }
    }
}

struct LioMenuCardContent: View {
    let language: LioLanguage
    let card: LioMenuOrder.Card
    @Binding var order: LioMenuOrder

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                Text(card.greeting).font(.title3.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary)
                ForEach(card.lines, id: \.self) { line in
                    Text(line).font(LioTheme.display(.largeTitle).weight(.bold))
                }
                if !card.notes.isEmpty {
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                        Text("备注：").font(.title3.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary)
                        ForEach(card.notes, id: \.self) { note in
                            Text(note).font(.title2.weight(.semibold))
                        }
                    }
                    .accessibilityIdentifier("lio.menu.card.notes")
                }
                Text(card.closing).font(.title3.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary)
            }
            .textSelection(.enabled)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(LioTheme.Spacing.md)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .accessibilityIdentifier("lio.menu.card")
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                Text(language.text("Add a note for staff", "加备注")).font(.headline)
                ForEach(notes, id: \.id) { note in
                    Button { order.toggle(note) } label: {
                        HStack {
                            Image(systemName: order.has(note) ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(order.has(note) ? LioTheme.vermilion : LioTheme.inkSecondary)
                            VStack(alignment: .leading, spacing: 0) {
                                Text(note.chinese)
                                if language == .english {
                                    Text(note.english).font(.caption).foregroundStyle(LioTheme.inkSecondary)
                                }
                            }
                            Spacer()
                        }
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.menu.note.\(note.id)")
                }
            }
        }
    }

    /// Notes already on the card first, then the everyday ones.
    private var notes: [LioMenuNote] {
        order.notes + LioMenuNote.common.filter { !order.notes.contains($0) }
    }
}

// MARK: - Camera

private struct LioMenuCamera: UIViewControllerRepresentable {
    let onCapture: (Data?) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onCapture: onCapture) }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    @MainActor final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        let onCapture: (Data?) -> Void

        init(onCapture: @escaping (Data?) -> Void) { self.onCapture = onCapture }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            onCapture((info[.originalImage] as? UIImage)?.jpegData(compressionQuality: 0.9))
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { onCapture(nil) }
    }
}
#endif
