import CJMessageHTTP
import Foundation
import SwiftUI

enum LioReplyMarkdown {
    static func render(_ source: String) -> AttributedString? {
        guard LioPublicDisplay.permitsText(source) else { return nil }
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .full)
        guard let parsed = try? AttributedString(markdown: source, options: options) else { return nil }
        let sectionHeadings = headingParagraphs(in: parsed)

        // SwiftUI Text handles inline attributes. Add the spacing, markers and
        // fonts for block attributes explicitly, keeping one selectable reply.
        var answer = AttributedString()
        var lastBlock: Int?
        var startedListItems: Set<Int> = []
        for run in parsed.runs {
            let components = run.presentationIntent?.components ?? []
            let block = components.first
            let items = components.filter {
                if case .listItem = $0.kind { return true }
                return false
            }
            let item = items.first
            if block?.identity != lastBlock {
                if !answer.characters.isEmpty {
                    answer += AttributedString(item == nil ? "\n\n" : "\n")
                }
                if let item, case .listItem(let ordinal) = item.kind {
                    let indent = String(repeating: "  ", count: items.count - 1)
                    if startedListItems.insert(item.identity).inserted {
                        let list = components.drop(while: { $0.identity != item.identity }).dropFirst().first
                        if case .orderedList? = list?.kind {
                            answer += AttributedString(indent + "\(ordinal). ")
                        } else {
                            answer += AttributedString(indent + "• ")
                        }
                    } else {
                        answer += AttributedString(indent + "  ")
                    }
                }
                lastBlock = block?.identity
            }

            var text = AttributedString(parsed[run.range])
            text.presentationIntent = nil
            if case .header(let level)? = block?.kind {
                text.font = (level == 1 ? Font.title2 : Font.title3).weight(.semibold)
            } else if let block, sectionHeadings.contains(block.identity) {
                text.font = Font.title3.weight(.semibold)
            }
            if let url = run.link,
               url.scheme?.lowercased() != "https" || url.user != nil || url.password != nil
                || !LioPublicDisplay.permitsSource(url) {
                text.link = nil
            }
            answer += text
        }
        guard LioPublicDisplay.permitsText(String(answer.characters)) else { return nil }
        return answer
    }

    private static func headingParagraphs(in answer: AttributedString) -> Set<Int> {
        let blocks = Dictionary(grouping: answer.runs) { $0.presentationIntent?.components.first?.identity }
        return Set(blocks.compactMap { identity, runs in
            guard let identity, let first = runs.first, let last = runs.last,
                  let components = first.presentationIntent?.components, components.count == 1,
                  case .paragraph? = components.first?.kind
            else { return nil }
            let text = String(answer[first.range.lowerBound..<last.range.upperBound].characters)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty, text.count <= 90, !text.contains("•"), !text.contains("\n") else { return nil }
            let bold = runs.allSatisfy { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true }
            let day = text.range(of: #"^(?:Day [0-9]{1,2}|第[0-9一二三四五六七八九十]{1,3}天)[ \t]*[:：–—]"#,
                                 options: [.regularExpression, .caseInsensitive]) != nil
            return bold || day ? identity : nil
        })
    }
}
