#if os(iOS)
import SwiftUI
import UIKit

struct LioHotelsView: View {
    private typealias Operation = LioHotelFormState.Operation
    let language: LioLanguage
    let service: LioHotelService
    let suggestedArea: LioHotelArea?
    @State private var searchForm = LioHotelFormState()
    @State private var reviewLink: LioHotelLink?
    @State private var notice: String?
    @Environment(\.scenePhase) private var scenePhase

    private var draft: LioHotelFormState.Draft { searchForm.draft }
    private var pending: Operation? { searchForm.pending }

    private var disclosure: String {
        language.text(
            "Some links are affiliate links. If you book through them, Go2China may earn a commission at no extra cost to you.",
            "部分链接为推广链接，你通过它预订时，Go2China 可能获得佣金，价格不受影响。"
        )
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                form
                if let suggestedArea {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(language.text("Your trip suggests staying around \(suggestedArea.nameEN)",
                                           "你的行程建议住在\(suggestedArea.nameZH)一带"))
                            .font(.headline)
                        affiliateButton(
                            language.text("See hotels in this area on Trip.com", "在 Trip.com 看这一带的酒店"),
                            id: "lio.hotels.area"
                        ) { find(in: .area(suggestedArea)) }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
                    .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                }
                if pending != nil { ProgressView(language.text("Getting hotels…", "正在获取酒店信息…")) }
                if let notice { Text(notice).accessibilityIdentifier("lio.hotels.notice") }
                if let reviewLink {
                    affiliateButton(language.text("Open Trip.com", "打开 Trip.com"),
                                    id: "lio.hotels.partial-link") {
                        searchForm.start(.open(reviewLink.destination))
                    }
                }
                VStack(alignment: .leading, spacing: 8) {
                    Text(language.text("Booking and payment happen on Trip.com", "预订和付款在 Trip.com 完成"))
                    disclosureText(id: "lio.hotels.footer")
                }
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
            }
            .padding(18)
        }
        .scrollDismissesKeyboard(.interactively)
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .tint(LioTheme.vermilion)
        .navigationTitle(language.text("Hotels", "酒店"))
        .navigationBarTitleDisplayMode(.inline)
        .environment(\.calendar, LioHotelSearch.calendar)
        .environment(\.timeZone, LioHotelSearch.calendar.timeZone)
        .onDisappear { searchForm.retire() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { searchForm.retire() }
        }
        .task(id: pending?.id) {
            guard let pending else { return }
            await perform(pending)
        }
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(language.text("City", "城市")).font(.headline).accessibilityAddTraits(.isHeader)
            TextField(language.text("City", "城市"), text: field(\.city),
                      prompt: Text(language.text("Enter a city", "输入城市")).foregroundStyle(LioTheme.inkSecondary))
                .padding(.horizontal, 12)
                .frame(minHeight: 44)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                .accessibilityIdentifier("lio.hotels.city")
            DatePicker(language.text("Check-in", "入住日期"), selection: field(\.checkIn), displayedComponents: .date)
                .accessibilityIdentifier("lio.hotels.check-in")
            DatePicker(language.text("Checkout", "退房日期"), selection: field(\.checkOut), displayedComponents: .date)
                .accessibilityIdentifier("lio.hotels.check-out")
            Stepper(value: field(\.guests), in: 1...Int.max) {
                Text(language.text("Guests: \(draft.guests)", "人数：\(draft.guests)"))
            }
            .accessibilityLabel(language.text("Guests", "人数"))
            .accessibilityValue(String(draft.guests))
            .accessibilityIdentifier("lio.hotels.guests")
            affiliateButton(language.text("Find hotels on Trip.com", "在 Trip.com 查看酒店"),
                            id: "lio.hotels.find") { find(in: .city(draft.city)) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func field<Value: Equatable>(_ keyPath: WritableKeyPath<LioHotelFormState.Draft, Value>) -> Binding<Value> {
        Binding(
            get: { draft[keyPath: keyPath] },
            set: { value in
                guard searchForm.edit(keyPath, to: value) else { return }
                reviewLink = nil
                notice = nil
            }
        )
    }

    private func affiliateButton(_ title: String, id: String, action: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Button(action: action) {
                Text(title)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(minHeight: 44)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier(id)
            .disabled(pending != nil)
            disclosureText(id: id)
        }
    }

    private func disclosureText(id: String) -> some View {
        Text(disclosure)
            .font(.footnote)
            .foregroundStyle(LioTheme.inkSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("\(id).disclosure")
    }

    private func find(in scope: LioHotelSearch.Scope) {
        guard pending == nil else { return }
        reviewLink = nil
        notice = nil
        do {
            let search = try LioHotelSearch(scope: scope, checkIn: draft.checkIn, checkOut: draft.checkOut,
                                            guests: draft.guests, language: language)
            searchForm.start(.find(search))
        } catch {
            switch error {
            case .cityRequired:
                notice = language.text("Enter a city to search for hotels.", "请输入城市再查找酒店。")
            case .checkoutMustFollowCheckin:
                notice = language.text("Checkout must be after check-in.", "退房日期须晚于入住日期。")
            case .invalidGuestCount:
                notice = language.text("Enter at least one guest.", "请至少选择一位入住客人。")
            }
        }
    }

    private func isCurrent(_ operation: Operation) -> Bool {
        !Task.isCancelled && searchForm.accepts(operation)
    }

    private func perform(_ operation: Operation) async {
        guard isCurrent(operation) else { return }
        do {
            switch operation.action {
            case .find(let search):
                let reply = try await service.link(search)
                guard isCurrent(operation) else { return }
                if reply.unappliedFilters.isEmpty {
                    await open(reply.destination, for: operation)
                } else {
                    let filters = reply.unappliedFilters.map { $0.title(language) }
                        .joined(separator: language.text(", ", "、"))
                    notice = language.text("On Trip.com, check \(filters).",
                                           "到 Trip.com 后，请确认\(filters)。")
                    reviewLink = reply
                }
            case .open(let url):
                await open(url, for: operation)
            }
        } catch is CancellationError {
            if isCurrent(operation) { searchForm.retire() }
            return
        } catch {
            guard isCurrent(operation) else { return }
            notice = language.text("Can’t get a Trip.com link right now. Try again.",
                                   "暂时无法获取 Trip.com 链接，请重试。")
        }
        if isCurrent(operation) { searchForm.retire() }
    }

    private func open(_ url: URL, for operation: Operation) async {
        guard isCurrent(operation), UIApplication.shared.applicationState == .active else { return }
        let opened = await service.open(url)
        guard isCurrent(operation) else { return }
        if !opened {
            notice = language.text("Couldn’t open Trip.com. Try again.", "暂时无法打开 Trip.com，请重试。")
        }
    }
}
#endif
