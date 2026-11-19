#if os(iOS)
import AVFoundation
import PhotosUI
import SwiftUI
import UIKit

struct LioTranslationImageInput: View {
    let language: LioLanguage
    let onImage: (Data) -> Void
    @Environment(\.openURL) private var openURL
    @State private var selection: PhotosPickerItem?
    @State private var cameraPresented = false
    @State private var input: Input?
    @State private var requestingCamera = false

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
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                PhotosPicker(selection: $selection, matching: .images) {
                    Label(language.text("Choose photo", "从相册选择"), systemImage: "photo")
                }
                .accessibilityIdentifier("lio.translation.photo")
                Button {
                    Task { await requestCamera() }
                } label: {
                    Label(language.text("Take photo", "拍照"), systemImage: "camera")
                }
                .disabled(requestingCamera)
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
        .sheet(isPresented: $cameraPresented) {
            LioTranslationCamera { data in
                cameraPresented = false
                if let data { input = Input(source: .camera(data)) }
            }
            .ignoresSafeArea()
        }
        .onChange(of: selection) {
            guard let selection else { return }
            input = Input(source: .library(selection))
            self.selection = nil
        }
        .task(id: input?.id) {
            guard let input else { return }
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
                guard self.input?.id == input.id else { return }
                onImage(data)
            } catch is CancellationError {
                return
            } catch {
                guard self.input?.id == input.id, !Task.isCancelled else { return }
                failure = error as? LioTranslationMediaFailure ?? .unreadableImage
            }
            if self.input?.id == input.id { self.input = nil }
        }
    }

    private func requestCamera() async {
        guard !requestingCamera else { return }
        requestingCamera = true
        defer { requestingCamera = false }
        guard UIImagePickerController.isSourceTypeAvailable(.camera) else {
            failure = .cameraUnavailable
            return
        }
        failure = nil
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: cameraPresented = true
        case .notDetermined:
            if await AVCaptureDevice.requestAccess(for: .video) { cameraPresented = true }
            else { failure = .cameraDenied }
        default: failure = .cameraDenied
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

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            onCapture((info[.originalImage] as? UIImage)?.jpegData(compressionQuality: 0.95))
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { onCapture(nil) }
    }
}
#endif
