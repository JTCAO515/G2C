import CJMessageHTTP
import Foundation

/// #1991 (58.1 D-3): `G2CAnswerRichEnabled` in the build's Info.plist; off unless it says YES. Off, the App never
/// declares `LIO-answer-rich.1`, never reads `rich` and nothing on screen changes. The server's own list
/// (`CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON`, switch `CJ_LIO_ANSWER_RICH`) still decides which accounts get it.
/// JT decides which build turns it on.
enum LioAnswerRichFeature {
    static let infoKey = "G2CAnswerRichEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-answer-rich-preview")
        #else
        return false
        #endif
    }
}

/// A place named in an answer, as a range of the answer's Unicode scalar values (`[start, end)`), checked against the
/// text and known to the App's place library.
struct LioPlaceSpan: Equatable, Sendable {
    let start: Int
    let end: Int
    let placeID: String
}

/// Turns the server's entities into the spans the App will draw as tappable words (LIO-answer-rich.1, App
/// behaviour 2). Nothing here trusts the data: a range that does not fit the text is dropped on its own, a list
/// whose ranges overlap or run backwards is dropped whole, and no input can crash it.
enum LioPlaceMentions {
    /// What a span's text may not contain: it is put into a Markdown link as it is.
    private static let markdownCharacters = Set("*_`[]()<>#|\\~!".unicodeScalars)

    /// The spans of `entities` in `answer` that are safe to draw.
    ///
    /// - Ranges count Unicode scalar values (Swift's `unicodeScalars`), never UTF-16 units or `Character`s.
    /// - Both ends must sit on a `Character` boundary of `answer`: a range that starts or ends inside an emoji, a
    ///   flag, a combining sequence or a CRLF is dropped.
    /// - The piece may not be blank, start or end with a space, contain a line break or a Markdown character.
    /// - Only the first mention of a place is kept.
    /// - `knows` says whether the App's place library has the id; a place it does not have stays plain text.
    static func resolve(answer: String, entities: [LioTimelineWire.Entity],
                        knows: (String) -> Bool) -> [LioPlaceSpan] {
        guard !entities.isEmpty, !answer.isEmpty else { return [] }
        // Overlapping or unordered ranges mean the list cannot be trusted at all.
        var previousEnd = 0
        for entity in entities {
            guard entity.start >= previousEnd, entity.end >= entity.start else { return [] }
            previousEnd = entity.end
        }
        let scalars = Array(answer.unicodeScalars)
        var boundaries = Set<Int>()
        var offset = 0
        for character in answer {
            boundaries.insert(offset)
            offset += character.unicodeScalars.count
        }
        boundaries.insert(offset)

        var seen = Set<String>()
        var spans: [LioPlaceSpan] = []
        for entity in entities {
            guard entity.start >= 0, entity.end <= scalars.count, (2...32).contains(entity.end - entity.start),
                  boundaries.contains(entity.start), boundaries.contains(entity.end),
                  LioTimelineWire.validPlaceID(entity.placeID),
                  isDrawable(scalars[entity.start..<entity.end]),
                  knows(entity.placeID), seen.insert(entity.placeID).inserted else { continue }
            spans.append(LioPlaceSpan(start: entity.start, end: entity.end, placeID: entity.placeID))
        }
        return spans
    }

    static func resolve(answer: String, entities: [LioTimelineWire.Entity],
                        in repository: LioPlaceRepository) -> [LioPlaceSpan] {
        resolve(answer: answer, entities: entities) { repository.place(id: $0) != nil }
    }

    private static func isDrawable(_ piece: ArraySlice<Unicode.Scalar>) -> Bool {
        guard let first = piece.first, let last = piece.last,
              !first.properties.isWhitespace, !last.properties.isWhitespace else { return false }
        return !piece.contains { scalar in
            CharacterSet.newlines.contains(scalar) || markdownCharacters.contains(scalar)
                || scalar.properties.generalCategory == .control
        }
    }
}

/// How a place span becomes a tappable word while an answer is turned into Markdown (LIO-answer-rich.1, App behaviour 2).
///
/// The contract's wording is to wrap each range as `[piece](g2c-place-<nonce>:<place_id>)` before parsing. A link
/// written inside the text changes how Markdown reads the characters around it: `**[故宫](…)**` is no longer bold,
/// because `[` is punctuation and the `**` before it then fails the flanking rule, and a place the model put in
/// bold is the common case. So the range is wrapped in two private-use scalars, which Markdown treats like any
/// letter, and the link is set on the parsed text afterwards. What the contract asks for is unchanged:
/// - the marks are new for every render (random, and removed from the model's text first), so nothing the model
///   wrote can look like one;
/// - the link is `g2c-place-<nonce>:<place_id>` with a fresh nonce, and every other `g2c-place` link the model
///   wrote is removed with the other links that are not plain https;
/// - a mark that does not come back as expected (the parser dropped or moved it) removes every place word, never
///   some of them.
struct LioPlaceLinkMarker: Sendable {
    static let schemePrefix = "g2c-place-"

    let scheme: String
    let open: Unicode.Scalar
    let close: Unicode.Scalar

    init() {
        scheme = Self.schemePrefix + String(format: "%016llx%016llx", UInt64.random(in: .min ... .max),
                                            UInt64.random(in: .min ... .max))
        // Plane 15 private use (U+F0000...U+FFFFD): category Co, not punctuation, not a space.
        let first = UInt32.random(in: 0xF0000...0xFFFFD)
        var second = UInt32.random(in: 0xF0000...0xFFFFD)
        if second == first { second = first == 0xFFFFD ? 0xF0000 : first + 1 }
        open = Unicode.Scalar(first)!
        close = Unicode.Scalar(second)!
    }

    /// `source` with each span's text between this render's two marks, and the spans that were marked. Spans that do
    /// not fit `source` (it may be shorter than the answer the ranges were made for) are left as plain text and are
    /// not in the second part. Marks already in `source` are replaced by U+FFFD, one for one, so every range still
    /// lines up.
    func mark(_ source: String, spans: [LioPlaceSpan]) -> (text: String, words: [LioPlaceSpan]) {
        guard !spans.isEmpty else { return (source, []) }
        let scalars = source.unicodeScalars.map { $0 == open || $0 == close ? "\u{FFFD}" : $0 }
        var result = String.UnicodeScalarView()
        var words: [LioPlaceSpan] = []
        var cursor = 0
        for span in spans where span.start >= cursor && span.end <= scalars.count && span.start < span.end {
            result.append(contentsOf: scalars[cursor..<span.start])
            result.append(open)
            result.append(contentsOf: scalars[span.start..<span.end])
            result.append(close)
            words.append(span)
            cursor = span.end
        }
        result.append(contentsOf: scalars[cursor...])
        return (String(result), words)
    }

    /// The parsed text with the marks removed and a link on each marked word; `words` are the ones `mark` returned.
    /// If the marks are not exactly one open and one close per word, in order, no word gets a link (the marks are
    /// removed either way), so a place word is either right or plain.
    func link(_ text: AttributedString, words: [LioPlaceSpan]) -> AttributedString {
        var marks: [(offset: Int, isOpen: Bool)] = []
        var offset = 0
        for scalar in text.unicodeScalars {
            if scalar == open { marks.append((offset, true)) } else if scalar == close { marks.append((offset, false)) }
            offset += 1
        }
        guard !marks.isEmpty else { return text }
        var result = text
        func index(_ offset: Int) -> AttributedString.Index {
            result.unicodeScalars.index(result.unicodeScalars.startIndex, offsetBy: offset)
        }
        func remove(at offset: Int) {
            let from = index(offset)
            result.removeSubrange(from..<result.unicodeScalars.index(after: from))
        }
        let sound = marks.count == words.count * 2
            && marks.enumerated().allSatisfy { $0.element.isOpen == ($0.offset % 2 == 0) }
        guard sound else {
            for mark in marks.reversed() { remove(at: mark.offset) }
            return result
        }
        // From the back, so the offsets in front of the word being changed stay as they were.
        for pair in stride(from: marks.count - 2, through: 0, by: -2) {
            let opening = marks[pair].offset, closing = marks[pair + 1].offset
            remove(at: closing)
            if closing > opening + 1, let url = URL(string: "\(scheme):\(words[pair / 2].placeID)") {
                let word = index(opening + 1)..<index(closing)
                result[word].link = url
                result[word].underlineStyle = .single
                result[word].foregroundColor = LioTheme.vermilion
            }
            remove(at: opening)
        }
        return result
    }

    /// Whether `url` is one of this render's links.
    func owns(_ url: URL) -> Bool { url.scheme?.lowercased() == scheme }

    /// The place id of any `g2c-place-…` link, or nil for another link or a malformed id.
    static func placeID(in url: URL) -> String? {
        guard let scheme = url.scheme?.lowercased(), scheme.hasPrefix(schemePrefix) else { return nil }
        let text = url.absoluteString
        guard let colon = text.firstIndex(of: ":") else { return nil }
        let id = String(text[text.index(after: colon)...])
        return LioTimelineWire.validPlaceID(id) ? id : nil
    }

    static func isPlaceLink(_ url: URL) -> Bool {
        url.scheme?.lowercased().hasPrefix(schemePrefix) == true
    }
}
