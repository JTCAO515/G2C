import Foundation

/// What the traveller types for a meeting card (#1766): who they are meeting, when, and where. A business card's
/// Chinese text works best; nothing is sent anywhere and nothing is kept after the page closes.
struct LioMeetingCardInput: Equatable, Sendable {
    var contact = ""
    var time = ""
    var address = ""

    private static func trimmed(_ text: String) -> String { text.trimmingCharacters(in: .whitespacesAndNewlines) }

    /// The card needs at least who it is for.
    var isReady: Bool { !Self.trimmed(contact).isEmpty }
}

extension LioShowCardContent {
    /// The meeting card (#1766): shown at a reception desk, to security or to a driver. Chinese large, English small.
    static func meeting(_ input: LioMeetingCardInput) -> Self {
        func clean(_ text: String) -> String? {
            let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
            return value.isEmpty ? nil : value
        }
        let time = clean(input.time)
        let address = clean(input.address)
        return Self(
            leadZH: "您好，我约了人见面，请帮我联系或带路：",
            mainZH: clean(input.contact) ?? "",
            detailsZH: [time.map { "时间：" + $0 }, address.map { "地点：" + $0 }].compactMap { $0 },
            english: ["I'm here to meet the person or company above. Could you help me find them, or call them for me?"]
                + [time.map { "Time: " + $0 }, address.map { "Place: " + $0 }].compactMap { $0 }
        )
    }
}

#if os(iOS)
import SwiftUI

/// The Business section of the Show Cards page (#1766). It reuses the show-card screen, the Taxi tool's place search
/// and driver card, and the business phrases (#1767); it adds no tool card of its own.
struct LioMeetingCardView: View {
    let language: LioLanguage
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @State private var input = LioMeetingCardInput()
    @State private var showing = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                Text(language.text("Copy the name, company and address from their business card. Chinese works best.",
                                   "把对方的姓名、公司和地址抄在这里，最好用名片上的中文。"))
                    .font(.subheadline)
                    .foregroundStyle(LioTheme.inkSecondary)
                if input.isReady {
                    LioShowCardFace(content: .meeting(input), compact: true, identifierPrefix: "lio.business.meeting.preview")
                        .padding(LioTheme.Spacing.md)
                        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                }
                Button {
                    showing = true
                } label: {
                    Label(language.text("Show full screen", "全屏出示"), systemImage: "arrow.up.left.and.arrow.down.right")
                }
                .buttonStyle(LioPrimaryButtonStyle())
                .disabled(!input.isReady)
                .accessibilityIdentifier("lio.business.meeting.show")
                field(language.text("Who you are meeting (name, company)", "约见的人（姓名、公司）"), $input.contact,
                      identifier: "lio.business.meeting.contact")
                field(language.text("Time (e.g. 14:00)", "时间（如 14:00）"), $input.time,
                      identifier: "lio.business.meeting.time", keyboard: .numbersAndPunctuation)
                field(language.text("Address (optional)", "地址（选填）"), $input.address,
                      identifier: "lio.business.meeting.address")
                if let taxiEntry {
                    NavigationLink {
                        LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                                    recentStore: taxiEntry.recentStore, opensDestinationPicker: true,
                                    initialSearch: input.address.trimmingCharacters(in: .whitespacesAndNewlines))
                    } label: {
                        Label(language.text("Taxi to the venue", "打车去会面地点"), systemImage: "car")
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }
                    .accessibilityIdentifier("lio.business.meeting.taxi")
                }
            }
            .padding(LioTheme.Spacing.md)
        }
        .background(LioTheme.paper)
        .foregroundStyle(LioTheme.ink)
        .navigationTitle(language.text("Meeting card", "会面卡"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.hidden, for: .tabBar)
        .fullScreenCover(isPresented: $showing) {
            LioShowCardSheet(language: language, content: .meeting(input), title: language.text("Meeting card", "会面卡"),
                             identifierPrefix: "lio.business.meeting.sheet")
        }
    }

    private func field(_ title: String, _ value: Binding<String>, identifier: String,
                       keyboard: UIKeyboardType = .default) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
            TextField(title, text: value)
                .keyboardType(keyboard)
                .textFieldStyle(.roundedBorder)
                .frame(minHeight: 44)
                .accessibilityIdentifier(identifier)
        }
    }
}
#endif
