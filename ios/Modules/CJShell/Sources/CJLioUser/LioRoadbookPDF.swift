import CoreGraphics
import CoreText
import Foundation

/// Lays a roadbook out as an A4 PDF with Core Text, entirely on the device: no web view, no server, no third party.
/// Cover, then each day starting on a new page, then where to stay and the essentials. Long days continue
/// on the next page. Places keep their Chinese name and address in English roadbooks so a driver can read them.
enum LioRoadbookPDF {
    static let pageSize = CGSize(width: 595, height: 842)
    private static let margin: CGFloat = 48
    private static let footerHeight: CGFloat = 28

    static func data(for roadbook: LioRoadbook, language: LioLanguage) -> Data {
        let output = NSMutableData()
        var box = CGRect(origin: .zero, size: pageSize)
        let info = [kCGPDFContextTitle as String: roadbook.itinerary.title, kCGPDFContextCreator as String: "Go2China"]
        guard let consumer = CGDataConsumer(data: output as CFMutableData),
              let context = CGContext(consumer: consumer, mediaBox: &box, info as CFDictionary) else { return Data() }
        var writer = Writer(context: context, footer: roadbook.coverTitle(language) + " · " + LioRoadbook.officialNotice(language))
        writer.chapter(cover(roadbook, language), accent: true)
        for day in roadbook.itinerary.days { writer.chapter(dayPages(roadbook, day, language)) }
        writer.chapter(backMatter(roadbook, language))
        context.closePDF()
        return output as Data
    }

    static func fileName(for roadbook: LioRoadbook, language: LioLanguage) -> String {
        let source = roadbook.city?.name(language) ?? roadbook.itinerary.title
        var name = ""
        for character in source {
            if character.isLetter || character.isNumber { name.append(character) }
            else if !name.isEmpty, name.last != "-" { name.append("-") }
        }
        while name.last == "-" { name.removeLast() }
        if name.isEmpty { name = language.text("Trip", "行程") }
        return name + language.text("-roadbook.pdf", "-路书.pdf")
    }

    /// The one folder exports go to: the app's temporary folder, never the account's roadbook folder
    /// (whose cleanup accepts only roadbook copies). Removed when sharing ends.
    static var exportDirectory: URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("LioRoadbookExport", isDirectory: true)
    }

    /// Removes every exported PDF; a missing folder is fine.
    static func removeExports() {
        try? FileManager.default.removeItem(at: exportDirectory)
    }

    /// Writes into a folder inside the app (normally its temporary folder) for the share sheet.
    /// Earlier exports in the folder are removed first so only the file being shared stays on the phone.
    static func write(_ roadbook: LioRoadbook, language: LioLanguage, to directory: URL) throws -> URL {
        let files = FileManager.default
        if files.fileExists(atPath: directory.path) { try files.removeItem(at: directory) }
        try files.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let url = directory.appendingPathComponent(fileName(for: roadbook, language: language))
        #if os(iOS)
        try data(for: roadbook, language: language).write(to: url, options: [.atomic, .completeFileProtection])
        #else
        try data(for: roadbook, language: language).write(to: url, options: [.atomic])
        #endif
        return url
    }

    // MARK: content

    private static func placeName(_ place: LioRichItinerary.Place, _ language: LioLanguage) -> String {
        language == .english && place.nameEN != place.nameZH ? "\(place.nameEN)  \(place.nameZH)" : place.nameZH
    }

    private static func cover(_ roadbook: LioRoadbook, _ language: LioLanguage) -> NSAttributedString {
        let text = Text()
        text.add(language.text("Travel roadbook", "自由行路书"), .accent)
        text.add(roadbook.coverTitle(language), .cover)
        if roadbook.city != nil { text.add(roadbook.itinerary.title, .subheading) }
        text.add(roadbook.coverLine(language), .secondary)
        text.add(" ", .body)
        for day in roadbook.itinerary.days {
            text.add(roadbook.dayTitle(day, language) + " · " + [day.theme, day.area].filter { !$0.isEmpty }.joined(separator: " · "), .body)
        }
        text.add(" ", .body)
        text.add(LioRoadbook.officialNotice(language), .caption)
        text.add(language.text("Made on this phone by Go2China. Works offline.", "由 Go2China 在本机生成，可离线查看。"), .caption)
        return text.value
    }

    private static func dayPages(_ roadbook: LioRoadbook, _ day: LioRichItinerary.Day, _ language: LioLanguage) -> NSAttributedString {
        let text = Text()
        text.add(roadbook.dayTitle(day, language), .title)
        let summary = [day.theme, day.area].filter { !$0.isEmpty }.joined(separator: " · ")
        if !summary.isEmpty { text.add(summary, .secondary) }
        let segments = LioRoadbook.segments(day)
        if segments.isEmpty { text.add(language.text("No activities planned for this day yet.", "这一天还没有安排。"), .body) }
        for segment in segments {
            text.add(segment.period.title(language), .heading)
            for entry in segment.entries {
                let stop = entry.stop
                text.add("\(entry.number). " + placeName(stop.place, language), .subheading)
                let meta = [stop.kind.title(language), stop.time, stop.note].compactMap { $0 }.filter { !$0.isEmpty }
                text.add(meta.joined(separator: " · "), .secondary)
                if !stop.text.isEmpty { text.add(stop.text, .body) }
                if let address = LioRoadbook.driverAddress(stop.place) {
                    text.add(language.text("Address: ", "地址：") + address, .body)
                } else {
                    text.add(language.text("Suggested place — check the address before you go.", "地点建议，出发前请再确认地址。"), .caption)
                }
                if let tip = stop.tip, !tip.isEmpty {
                    text.add(language.text("Reminder: ", "提醒：") + tip + language.text(" (check official sources)", "（以官方为准）"), .accentBody)
                }
                if let leg = entry.legAfter { text.add("↓ " + leg.description(language), .secondary) }
            }
        }
        return text.value
    }

    private static func backMatter(_ roadbook: LioRoadbook, _ language: LioLanguage) -> NSAttributedString {
        let text = Text()
        let itinerary = roadbook.itinerary
        if !itinerary.lodgingArea.isEmpty || !itinerary.hotels.isEmpty {
            text.add(language.text("Where to stay", "住宿区域"), .title)
            if !itinerary.lodgingArea.isEmpty { text.add(itinerary.lodgingArea, .body) }
            for hotel in itinerary.hotels {
                text.add(placeName(hotel.place, language), .subheading)
                if let note = LioRoadbook.visibleNote(hotel.note) { text.add(note, .secondary) }
            }
        }
        for section in LioRoadbookEssentials.sections(language) {
            text.add(section.title, .title)
            for item in section.items {
                let phone = item.phone.map { "  " + $0 } ?? ""
                text.add(item.title + phone, .subheading)
                if language == .english, let chinese = item.chinese, chinese != item.title { text.add(chinese, .body) }
                if let detail = item.detail { text.add(detail, .secondary) }
            }
        }
        return text.value
    }

    // MARK: drawing

    private enum Style {
        case cover, title, heading, subheading, body, secondary, caption, accent, accentBody

        var size: CGFloat {
            switch self {
            case .cover: 40
            case .title: 22
            case .heading: 15
            case .subheading: 13
            case .body, .accentBody: 11
            case .secondary: 10
            case .caption, .accent: 9
            }
        }
        var bold: Bool { [.cover, .title, .heading, .subheading, .accent].contains(self) }
        var colour: String {
            switch self {
            case .accent, .heading, .accentBody: "vermilion"
            case .secondary, .caption: "inkSecondary"
            default: "ink"
            }
        }
        var spacingBefore: CGFloat {
            switch self {
            case .title: 6
            case .heading: 12
            case .subheading: 8
            default: 0
            }
        }
        var spacingAfter: CGFloat { self == .cover || self == .title ? 10 : 3 }
    }

    private struct Text {
        let value = NSMutableAttributedString()

        func add(_ string: String, _ style: Style) {
            let font = CTFontCreateUIFontForLanguage(style.bold ? .emphasizedSystem : .system, style.size, "zh-Hans" as CFString)
                ?? CTFontCreateWithName("Helvetica" as CFString, style.size, nil)
            var attributes: [NSAttributedString.Key: Any] = [
                NSAttributedString.Key(kCTFontAttributeName as String): font,
                NSAttributedString.Key(kCTForegroundColorAttributeName as String): LioRoadbookPDF.colour(style.colour),
            ]
            attributes[NSAttributedString.Key(kCTParagraphStyleAttributeName as String)] =
                LioRoadbookPDF.paragraph(before: style.spacingBefore, after: style.spacingAfter)
            value.append(NSAttributedString(string: string + "\n", attributes: attributes))
        }
    }

    private static func colour(_ name: String) -> CGColor {
        let hex = LioTheme.swatches.first { $0.name == name }?.light ?? 0x1F1A15
        return CGColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                       blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }

    private static func paragraph(before: CGFloat, after: CGFloat) -> CTParagraphStyle {
        var before = before, after = after, lineSpacing: CGFloat = 2
        return withUnsafeBytes(of: &before) { beforeBytes in
            withUnsafeBytes(of: &after) { afterBytes in
                withUnsafeBytes(of: &lineSpacing) { lineBytes in
                    let size = MemoryLayout<CGFloat>.size
                    let settings = [
                        CTParagraphStyleSetting(spec: .paragraphSpacingBefore, valueSize: size, value: beforeBytes.baseAddress!),
                        CTParagraphStyleSetting(spec: .paragraphSpacing, valueSize: size, value: afterBytes.baseAddress!),
                        CTParagraphStyleSetting(spec: .lineSpacingAdjustment, valueSize: size, value: lineBytes.baseAddress!),
                    ]
                    return CTParagraphStyleCreate(settings, settings.count)
                }
            }
        }
    }

    private struct Writer {
        let context: CGContext
        let footer: String
        var page = 0

        init(context: CGContext, footer: String) {
            self.context = context
            self.footer = footer
        }

        /// Starts on a new page and keeps adding pages until every character has been drawn.
        mutating func chapter(_ text: NSAttributedString, accent: Bool = false) {
            let framesetter = CTFramesetterCreateWithAttributedString(text)
            let body = CGRect(x: LioRoadbookPDF.margin, y: LioRoadbookPDF.margin + LioRoadbookPDF.footerHeight,
                              width: LioRoadbookPDF.pageSize.width - 2 * LioRoadbookPDF.margin,
                              height: LioRoadbookPDF.pageSize.height - 2 * LioRoadbookPDF.margin - LioRoadbookPDF.footerHeight)
            var location = 0
            repeat {
                let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: location, length: 0),
                                                     CGPath(rect: body, transform: nil), nil)
                let drawn = CTFrameGetVisibleStringRange(frame).length
                // Nothing fits (a line taller than the page): stop rather than add blank pages.
                guard drawn > 0 else { break }
                begin(accent: accent && location == 0)
                CTFrameDraw(frame, context)
                context.endPDFPage()
                location += drawn
            } while location < text.length
        }

        private mutating func begin(accent: Bool) {
            page += 1
            context.beginPDFPage(nil)
            context.textMatrix = .identity
            context.setFillColor(LioRoadbookPDF.colour("vermilion"))
            let size = LioRoadbookPDF.pageSize
            context.fill(CGRect(x: 0, y: size.height - (accent ? 12 : 4), width: size.width, height: accent ? 12 : 4))
            context.setFillColor(LioRoadbookPDF.colour("hairline"))
            context.fill(CGRect(x: LioRoadbookPDF.margin, y: LioRoadbookPDF.margin + 18,
                                width: size.width - 2 * LioRoadbookPDF.margin, height: 0.5))
            let footer = Text()
            footer.add("\(self.footer)   \(page)", .caption)
            let line = CTLineCreateWithAttributedString(footer.value)
            context.textPosition = CGPoint(x: LioRoadbookPDF.margin, y: LioRoadbookPDF.margin)
            CTLineDraw(line, context)
        }
    }
}
