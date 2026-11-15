import Foundation
import SwiftUI

/// Layout the existing Markdown result with one text style per native Text view.
/// Inline emphasis, links and list indentation stay in the attributed content.
struct LioReplyTextBlock {
    var text: AttributedString
    let font: Font?
    let leadingSeparator: String

    init(text: AttributedString, font: Font?, leadingSeparator: String = "") {
        self.text = text
        self.font = font
        self.leadingSeparator = leadingSeparator
    }

    static func make(from rendered: AttributedString) -> [Self] {
        var blocks: [Self] = []
        for run in rendered.runs {
            var text = AttributedString(rendered[run.range])
            text.font = nil
            if let last = blocks.last, last.font == run.font {
                blocks[blocks.count - 1].text += text
            } else {
                blocks.append(Self(text: text, font: run.font))
            }
        }
        var result: [Self] = []
        var separator = ""
        for block in blocks {
            var block = block
            while block.text.characters.first == "\n" {
                separator += "\n"
                block.text.removeSubrange(block.text.startIndex..<block.text.characters.index(after: block.text.startIndex))
            }
            if block.text.characters.isEmpty { continue }
            var trailing = ""
            while block.text.characters.last == "\n" {
                trailing += "\n"
                block.text.removeSubrange(block.text.characters.index(before: block.text.endIndex)..<block.text.endIndex)
            }
            result.append(Self(text: block.text, font: block.font, leadingSeparator: separator))
            separator = trailing
        }
        if !separator.isEmpty, !result.isEmpty {
            result[result.count - 1].text += AttributedString(separator)
        }
        return result
    }
}
