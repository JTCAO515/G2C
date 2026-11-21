#if os(iOS)
import AVFoundation
import PhotosUI
import SwiftUI
import UIKit

struct LioTranslationImageInput: View {
    let language: LioLanguage
    let source: LioTranslationLanguage
    let enabled: Bool
    let isCurrent: @MainActor () -> Bool
    let onImage: (Data) -> Void
    @Environment(\.openURL) private var openURL
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var photoPickerPresented = false
    @State private var photoRequest: UUID?
    @State private var cameraRequest: UUID?
    @State private var camera: Camera?
    @State private var input: Input?

    private struct Camera: Identifiable { let id: UUID }

    private struct Input: Identifiable {
        enum Source {
            case library(PhotosPickerItem)
            case camera(Data)
        }
        let id = UUID()
        let source: Source
    }
    @State private var failure: LioTranslationMediaFailure?

    var body: some View {
        let actions = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading))
            : AnyLayout(HStackLayout())
        VStack(alignment: .leading, spacing: 8) {
            actions {
                Button {
                    guard enabled, isCurrent() else { return }
                    photoRequest = UUID()
                    photoPickerPresented = true
                } label: {
                    Label(language.text("Choose photo", "从相册选择"), systemImage: "photo")
                }
                .accessibilityIdentifier("lio.translation.photo")
                Button {
                    requestCamera()
                } label: {
                    Label(language.text("Take photo", "拍照"), systemImage: "camera")
                }
                .disabled(cameraRequest != nil)
                .accessibilityIdentifier("lio.translation.camera")
            }
            .controlSize(.large)
            .buttonStyle(LioTranslationActionStyle())
            if let failure {
                Text(message(failure)).foregroundStyle(LioTheme.ink)
                    .accessibilityIdentifier("lio.translation.image-problem")
                if failure == .cameraDenied {
                    Button(language.text("Open Settings", "打开设置")) {
                        if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                    }
                    .frame(minHeight: 44)
                }
            }
        }
        .photosPicker(isPresented: $photoPickerPresented, selection: selection(for: photoRequest), matching: .images)
        .sheet(item: $camera) { presented in
            LioTranslationCamera(isCurrent: { camera?.id == presented.id && isCurrent() }) { data in
                guard camera?.id == presented.id, isCurrent() else { return }
                camera = nil
                if let data { input = Input(source: .camera(data)) }
            }
            .ignoresSafeArea()
        }
        .onChange(of: enabled) { _, available in
            if !available { retireInput() }
        }
        .onChange(of: source) { retireInput() }
        .onDisappear { retireInput() }
        .task(id: input?.id) {
            guard let input, isCurrent() else { return }
            do {
                failure = nil
                let data: Data
                switch input.source {
                case .library(let item):
                    guard let selected = try await item.loadTransferable(type: Data.self) else {
                        throw LioTranslationMediaFailure.unreadableImage
                    }
                    data = selected
                case .camera(let captured): data = captured
                }
                try Task.checkCancellation()
                guard self.input?.id == input.id, isCurrent() else { return }
                onImage(data)
            } catch is CancellationError {
                return
            } catch {
                guard self.input?.id == input.id, isCurrent(), !Task.isCancelled else { return }
                failure = error as? LioTranslationMediaFailure ?? .unreadableImage
            }
            if self.input?.id == input.id { self.input = nil }
        }
    }

    private func selection(for request: UUID?) -> Binding<PhotosPickerItem?> {
        Binding(get: { nil }, set: { item in
            guard let request, request == photoRequest, let item, isCurrent() else { return }
            photoRequest = nil
            input = Input(source: .library(item))
        })
    }

    private func retireInput() {
        cameraRequest = nil
        camera = nil
        photoRequest = nil
        photoPickerPresented = false
        input = nil
        failure = nil
    }

    private func requestCamera() {
        guard cameraRequest == nil, enabled, isCurrent() else { return }
        let request = UUID()
        cameraRequest = request
        Task { await authorizeCamera(request) }
    }

    private func authorizeCamera(_ request: UUID) async {
        guard cameraRequest == request else { return }
        defer { if cameraRequest == request { cameraRequest = nil } }
        guard isCurrent() else { return }
        guard UIImagePickerController.isSourceTypeAvailable(.camera) else {
            failure = .cameraUnavailable
            return
        }
        failure = nil
        let gate = LioMediaPermissionGate(isCurrent: { cameraRequest == request && isCurrent() })
        do {
            let granted = try await gate.request {
                switch AVCaptureDevice.authorizationStatus(for: .video) {
                case .authorized: return true
                case .notDetermined: return await AVCaptureDevice.requestAccess(for: .video)
                default: return false
                }
            }
            guard cameraRequest == request, isCurrent() else { return }
            if granted { camera = Camera(id: request) }
            else { failure = .cameraDenied }
        } catch is CancellationError {
            return
        } catch {
            failure = .cameraUnavailable
        }
    }

    private func message(_ failure: LioTranslationMediaFailure) -> String {
        switch failure {
        case .noText: language.text("No text was found in this photo.", "这张图片里没有识别到文字。")
        case .cameraDenied: language.text("Allow camera access in Settings to take a photo.", "如需拍照，请在设置中允许使用相机。")
        case .cameraUnavailable: language.text("This device can’t take photos here. Choose a photo instead.", "此设备暂时无法拍照，可以从相册选图。")
        default: language.text("Couldn’t read this photo. Try another image.", "暂时无法识别这张图片，请换一张。")
        }
    }
}

private struct LioTranslationCamera: UIViewControllerRepresentable {
    let isCurrent: @MainActor () -> Bool
    let onCapture: (Data?) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(isCurrent: isCurrent, onCapture: onCapture) }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    @MainActor final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        let isCurrent: @MainActor () -> Bool
        let onCapture: (Data?) -> Void

        init(isCurrent: @escaping @MainActor () -> Bool, onCapture: @escaping (Data?) -> Void) {
            self.isCurrent = isCurrent
            self.onCapture = onCapture
        }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            guard isCurrent() else { return }
            onCapture((info[.originalImage] as? UIImage)?.jpegData(compressionQuality: 0.95))
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            if isCurrent() { onCapture(nil) }
        }
    }
}
#endif
