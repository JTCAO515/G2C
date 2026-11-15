#if os(iOS)
import SwiftUI

struct LioTripCalendarLabel: View {
    let calendar: LioItinerary.CalendarState?
    let language: LioLanguage

    var body: some View {
        if calendar == .undated {
            Label(language.text("Start date not set", "出发日期待定"), systemImage: "calendar.badge.questionmark")
                .font(.subheadline)
                .foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("lio.trip.calendar.pending")
        }
    }
}
#endif
