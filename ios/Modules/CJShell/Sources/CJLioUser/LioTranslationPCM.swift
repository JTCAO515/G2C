@preconcurrency import AVFoundation
import Foundation

struct LioTranslationRecording: Sendable {
    fileprivate let pcm: Data

    func wireWAV() throws -> Data {
        try LioTranslationWAV.encode(pcm: pcm)
    }

    fileprivate static func format() -> AVAudioFormat? {
        AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: Double(LioTranslationWAV.sampleRate),
                      channels: 1, interleaved: true)
    }
}

/// The audio tap and the main actor share this bounded buffer. Conversion and
/// draining use the same lock; no recording content is written to disk.
final class LioTranslationPCMCollector: @unchecked Sendable {
    private let lock = NSLock()
    private let converter: AVAudioConverter
    private var pcm = Data()
    private var failed = false

    init(inputFormat: AVAudioFormat) throws {
        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0,
              let output = LioTranslationRecording.format(),
              let converter = AVAudioConverter(from: inputFormat, to: output) else {
            throw LioTranslationMediaFailure.recordingUnavailable
        }
        self.converter = converter
    }

    func append(_ input: AVAudioPCMBuffer) {
        lock.withLock {
            let remaining = LioTranslationWAV.maximumPCMBytes - pcm.count
            guard !failed, remaining > 0, input.frameLength > 0 else { return }
            let ratio = converter.outputFormat.sampleRate / converter.inputFormat.sampleRate
            let needed = ceil(Double(input.frameLength) * ratio) + 16
            let frames = AVAudioFrameCount(min(needed, Double(remaining / MemoryLayout<Int16>.size)))
            guard let output = AVAudioPCMBuffer(pcmFormat: converter.outputFormat, frameCapacity: frames) else {
                failed = true
                return
            }
            var supplied = false
            var error: NSError?
            let status = converter.convert(to: output, error: &error) { _, state in
                if supplied {
                    state.pointee = .noDataNow
                    return nil
                }
                supplied = true
                state.pointee = .haveData
                return input
            }
            guard status != .error, let samples = output.int16ChannelData?.pointee else {
                failed = true
                return
            }
            pcm.append(UnsafeRawPointer(samples).assumingMemoryBound(to: UInt8.self),
                       count: Int(output.frameLength) * MemoryLayout<Int16>.size)
        }
    }

    func finish() throws -> LioTranslationRecording {
        try lock.withLock {
            guard !failed, !pcm.isEmpty else { throw LioTranslationMediaFailure.emptyRecording }
            return LioTranslationRecording(pcm: pcm)
        }
    }
}
