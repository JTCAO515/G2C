import CJMessageHTTP
import Foundation
import SwiftUI

enum LioReplyMarkdown {
    static func render(_ source: String) -> AttributedString? {
        guard LioPublicDisplay.permitsText(source) else { return nil }
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .full)
        guard let parsed = try? AttributedString(markdown: source, options: options) else { return nil }

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
                text.font = (level == 1 ? Font.title2 : Font.headline).bold()
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
}
