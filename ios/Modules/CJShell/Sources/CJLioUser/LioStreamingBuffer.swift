import Foundation

/// Presentation blocks supplied by the existing Markdown renderer. A heading or list
/// line is atomic; an unfinished final block can wait for its closing boundary.
struct LioStreamingBlock: Equatable {
    let text: String
    var atomic = false
    var sealed = true
}

/// Display pacing only. This value never changes a message, sends a request or stores text.
struct LioStreamingBuffer {
    static let normalInterval = LioTheme.Motion.streamingStep
    static let reducedInterval = LioTheme.Motion.reducedStreamingStep
    private var ready = ""
    private var boundaries: [Int] = []
    private var shown = 0
    private var readyCount = 0
    private var credit = Duration.zero

    var text: String { String(ready.prefix(shown)) }
    var visibleCharacterCount: Int { shown }
    var hasPending: Bool { shown < readyCount }

    /// Returning to an existing view reveals the admitted prefix without replaying it.
    /// Unsealed words and atomic blocks remain withheld until they are ready.
    mutating func revealReady() { shown = readyCount; credit = .zero }

    /// Reconcile a cumulative presentation. Corrections replace the old display;
    /// a completed response is available immediately, within the 300ms finish limit.
    mutating func receive(_ blocks: [LioStreamingBlock], completed: Bool) {
        let previous = text
        let wasPending = hasPending
        var units: [String] = []
        for block in blocks {
            if block.atomic {
                if !block.sealed && !completed { break }
                if !block.text.isEmpty { units.append(block.text) }
            } else {
                units += Self.units(block.text, sealed: block.sealed || completed)
            }
        }
        ready = units.joined()
        var bytes = 0
        let byteEnds = units.map { unit in bytes += unit.utf8.count; return bytes }
        boundaries = []
        var unit = 0
        var offset = 0
        var characters = 0
        // Adjacent presentation blocks can join into one extended grapheme.
        // Round release boundaries to the complete grapheme in the joined value.
        for character in ready {
            characters += 1
            offset += String(character).utf8.count
            while unit < byteEnds.count && byteEnds[unit] <= offset {
                boundaries.append(characters)
                unit += 1
            }
        }
        readyCount = characters
        if !ready.hasPrefix(previous) { shown = 0 }
        if !wasPending { credit = .zero }
        if completed {
            shown = readyCount
            credit = .zero
        }
    }

    @discardableResult
    mutating func advance(by elapsed: Duration, reduceMotion: Bool) -> Bool {
        guard hasPending else { credit = .zero; return false }
        credit += elapsed
        let interval = reduceMotion ? Self.reducedInterval : Self.normalInterval
        guard credit >= interval else { return false }
        let steps = Int(credit / interval)
        credit -= interval * steps
        var first = 0
        while boundaries[first] <= shown { first += 1 }
        let remaining = boundaries.count - first
        let acceleration = reduceMotion ? remaining : max(1, (remaining + 39) / 40)
        let count = min(remaining, steps * acceleration)
        shown = boundaries[first + count - 1]
        return true
    }

    private static func units(_ text: String, sealed: Bool) -> [String] {
        var result: [String] = []
        var word = ""
        for character in text {
            if character.isWhitespace {
                if !word.isEmpty {
                    word.append(character)
                    result.append(word)
                    word = ""
                } else if !result.isEmpty {
                    result[result.count - 1].append(character)
                } else {
                    word.append(character)
                }
            } else if isHan(character) {
                if !word.isEmpty { result.append(word); word = "" }
                result.append(String(character))
            } else {
                word.append(character)
            }
        }
        if sealed && !word.isEmpty { result.append(word) }
        return result
    }

    private static func isHan(_ character: Character) -> Bool {
        character.unicodeScalars.contains { scalar in
            switch scalar.value {
            case 0x3400...0x4DBF, 0x4E00...0x9FFF, 0xF900...0xFAFF,
                 0x20000...0x2FA1F, 0x30000...0x323AF: true
            default: false
            }
        }
    }
}
