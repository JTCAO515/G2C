#if os(iOS)
import SwiftUI
import UIKit

struct LioTaxiView: View {
    private typealias Action = LioTaxiRequestState.Action
    let language: LioLanguage
    let service: LioTaxiService
    let tripPlaces: [LioTaxiPlace]
    let recentStore: LioTaxiRecentPlaces?
    @State var destination: LioTaxiPlace?
    @State private var pickup: LioTaxiPlace?
    @State private var recent: [LioTaxiPlace] = []
    @State private var fares: [LioTaxiFare] = []
    @State private var pickupNotice: String?
    @State private var recentNotice: String?
    @State private var failure: RequestFailure?
    @State private var requests = LioTaxiRequestState()
    @State private var sheet: Sheet?
    @State private var driverPlace: LioTaxiPlace?
    @State private var showOptions = false
    @AppStorage("lio.taxi.seen-guide.v1") private var seenGuide = false
    @Environment(\.scenePhase) private var scenePhase

    private enum Sheet: String, Identifiable {
        case destination, pickup, guide, alipay
        var id: Self { self }
    }

    private struct RequestFailure {
        let action: Action
        let message: String
    }

    private var route: LioTaxiRoute? {
        guard let pickup, let destination else { return nil }
        return LioTaxiRoute(pickup: pickup, destination: destination)
    }

    private var requestPending: Bool { requests.current != nil }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                placeCard(language.text("Destination", "终点"), place: destination,
                          identifier: "lio.taxi.destination",
                          placeholder: language.text("Choose a destination", "选择终点")) {
                    sheet = .destination
                }
                placeCard(language.text("Pickup", "起点"), place: pickup,
                          identifier: "lio.taxi.pickup",
                          placeholder: language.text("Choose a pickup point", "选择起点")) {
                    sheet = .pickup
                }
                if let pickupNotice { Text(pickupNotice).foregroundStyle(LioTheme.inkSecondary) }
                if let recentNotice { Text(recentNotice).foregroundStyle(LioTheme.inkSecondary) }
                estimateCard
                rideActions
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .foregroundStyle(LioTheme.ink)
        .tint(LioTheme.vermilion)
        .navigationTitle(language.text("Taxi", "打车"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { sheet = .guide } label: { Image(systemName: "questionmark.circle") }
                    .accessibilityLabel(language.text("Taxi guide", "打车指南"))
            }
        }
        .task {
            if !seenGuide { sheet = .guide }
            do {
                if let recentStore { recent = try recentStore.load() }
            } catch {
                recentNotice = language.text("Recent places are unavailable.", "最近地点暂不可用。")
            }
            guard pickup == nil else { return }
            do {
                let location = try await service.currentPickup()
                guard pickup == nil, !Task.isCancelled else { return }
                selectPickup(location)
            } catch {
                guard pickup == nil, !Task.isCancelled else { return }
                pickupNotice = message(error)
            }
        }
        .onDisappear { requests.retire() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { requests.retire() }
        }
        .task(id: requests.current?.id) {
            guard let operation = requests.current else { return }
            await perform(operation)
        }
        .sheet(item: $sheet) { shown in
            switch shown {
            case .destination, .pickup:
                NavigationStack {
                    LioTaxiPlacePicker(
                        language: language, destination: shown == .destination,
                        tripPlaces: tripPlaces, recent: recent, search: service.search
                    ) { place in
                        if shown == .destination {
                            if destination != place {
                                retireRouteRequest()
                                destination = place
                            }
                            record(place)
                        } else {
                            selectPickup(place)
                        }
                        sheet = nil
                    }
                }
            case .guide, .alipay:
                guide(alipayOnly: shown == .alipay)
                    .onDisappear {
                        if shown == .guide { seenGuide = true }
                    }
            }
        }
        .fullScreenCover(item: $driverPlace) { place in
            LioTaxiDriverCard(language: language, place: place)
        }
        .confirmationDialog(language.text("Open DiDi another way", "换一种方式打开滴滴"), isPresented: $showOptions,
                            titleVisibility: .visible) {
            Button(language.text("Get DiDi in the App Store", "前往 App Store 安装"), action: service.openAppStore)
            Button(language.text("Use DiDi in Alipay", "查看支付宝小程序说明")) { sheet = .alipay }
            if let destination, destination.addressZH != nil {
                Button(language.text("Show the driver", "给司机看")) { driverPlace = destination }
            }
        }
    }

    private func placeCard(_ title: String, place: LioTaxiPlace?, identifier: String, placeholder: String,
                           action: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline).accessibilityAddTraits(.isHeader)
            Button(action: action) {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(place?.name(in: language) ?? placeholder)
                        if let address = place?.addressZH {
                            Text(address).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                        }
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.forward").accessibilityHidden(true)
                }
                .foregroundStyle(LioTheme.ink)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(identifier)
        }
        .padding(16)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private var estimateCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(language.text("Estimated fares", "预估车费")).font(.headline).accessibilityAddTraits(.isHeader)
            ForEach(fares) { fare in
                VStack(alignment: .leading, spacing: 4) {
                    Text(language.text(fare.nameEN, fare.nameZH))
                    Text(fare.priceDisplay).foregroundStyle(LioTheme.inkSecondary)
                }
            }
            if !fares.isEmpty {
                Text(language.text("Final price is set by DiDi", "以滴滴实际价格为准"))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
            }
            Button(language.text("Get an estimate", "查看估价")) { start(.estimate) }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .accessibilityIdentifier("lio.taxi.estimate")
                .disabled(route == nil || requestPending)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private var rideActions: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button(language.text("Open in DiDi", "在滴滴打开")) { start(.handoff) }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .accessibilityIdentifier("lio.taxi.handoff")
                .disabled(route == nil || requestPending)
            if let destination, destination.addressZH != nil {
                Button(language.text("Show the driver", "给司机看")) { driverPlace = destination }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                    .accessibilityIdentifier("lio.taxi.driver")
            }
            if requestPending { ProgressView(language.text("Getting ride details…", "正在获取打车信息…")) }
            if let failure {
                Text(failure.message)
                Button(language.text("Try again", "重试")) { start(failure.action) }
                    .frame(minHeight: 44)
                    .disabled(route == nil || requestPending)
            }
        }
    }

    private func record(_ place: LioTaxiPlace) {
        guard let recentStore else { return }
        do {
            recent = try recentStore.record(place)
            recentNotice = nil
        } catch {
            recentNotice = language.text("Couldn’t save to recent places.", "暂时无法保存到最近地点。")
        }
    }

    private func start(_ action: Action) {
        guard let route else { return }
        requests.start(action, route: route)
    }

    private func selectPickup(_ place: LioTaxiPlace) {
        if pickup != place {
            retireRouteRequest()
            pickup = place
        }
        pickupNotice = nil
    }

    private func retireRouteRequest() {
        requests.retire()
        failure = nil
        fares = []
        showOptions = false
    }

    private func isCurrent(_ operation: LioTaxiRequestState.Operation) -> Bool {
        !Task.isCancelled && requests.accepts(operation, route: route)
    }

    private func perform(_ operation: LioTaxiRequestState.Operation) async {
        guard isCurrent(operation) else { return }
        failure = nil
        do {
            switch operation.action {
            case .estimate:
                let result = try await service.estimate(operation.route)
                guard isCurrent(operation) else { return }
                fares = result
            case .handoff:
                let link = try await service.rideLink(operation.route)
                guard isCurrent(operation) else { return }
                guard UIApplication.shared.applicationState == .active else {
                    requests.retire()
                    return
                }
                let opened = await service.openRideLink(link)
                guard isCurrent(operation) else { return }
                showOptions = !opened
            }
        } catch is CancellationError {
            if isCurrent(operation) { requests.retire() }
            return
        } catch {
            guard isCurrent(operation) else { return }
            failure = RequestFailure(action: operation.action, message: message(error))
        }
        requests.retire()
    }

    private func message(_ error: Error) -> String {
        switch error as? LioTaxiFailure {
        case .locationDenied:
            language.text("Location is unavailable. Choose a pickup point.", "无法使用定位，请手动选择起点。")
        case .outOfService:
            language.text("Rides aren’t available in this area.", "这个区域暂不提供打车服务。")
        case .rateLimited:
            language.text("Too many requests. Try again in a moment.", "请求过于频繁，请稍后重试。")
        case .quotaExceeded:
            language.text("You’ve reached today’s limit.", "已达到今天的使用上限。")
        case .coordinateUnverified:
            language.text("Choose a more specific pickup or destination.", "请选择更具体的起点或终点。")
        case .signInRequired:
            language.text("Sign in again, then try again.", "请重新登录后重试。")
        case .notEnabled:
            language.text("Taxi isn’t available for this account.", "此账号暂未开通打车。")
        case .timedOut:
            language.text("DiDi took too long. Try again.", "滴滴响应超时，请重试。")
        case .unavailable, nil:
            language.text("Taxi details aren’t available right now. Try again.", "暂时无法获取打车信息，请重试。")
        }
    }

    private func guide(alipayOnly: Bool) -> some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if !alipayOnly {
                        Text(language.text("In DiDi settings, switch the app language to English.",
                                           "在滴滴设置中把语言切换到英文。"))
                        Text(language.text("In DiDi payment settings, add your international card and check that it is accepted.",
                                           "在滴滴的支付设置中添加境外银行卡，并确认是否可用。"))
                    }
                    Text(language.text("In Alipay, search for the DiDi mini program and choose your ride there.",
                                       "在支付宝搜索滴滴小程序，可在小程序里打车。"))
                }
                .padding(18)
            }
            .background(LioTheme.paper)
            .navigationTitle(alipayOnly ? language.text("DiDi in Alipay", "支付宝里的滴滴")
                                      : language.text("Taxi guide", "打车指南"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(language.text("Done", "完成")) { sheet = nil }
                }
            }
        }
    }
}

private struct LioTaxiPlacePicker: View {
    let language: LioLanguage
    let destination: Bool
    let tripPlaces: [LioTaxiPlace]
    let recent: [LioTaxiPlace]
    let search: @MainActor (String) async throws -> [LioTaxiPlace]
    let select: (LioTaxiPlace) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var submittedQuery: String?
    @State private var result: [LioTaxiPlace] = []
    @State private var searchNotice: String?
    @State private var isSearching = false

    var body: some View {
        List {
            Section(language.text("Search for a place", "搜索地点")) {
                TextField(language.text("Place name or address", "地点名或地址"), text: $query)
                    .submitLabel(.search)
                    .onSubmit(submit)
                Button(language.text("Search", "搜索"), action: submit)
                    .disabled(query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if isSearching { ProgressView(language.text("Searching…", "正在搜索…")) }
                if let searchNotice { Text(searchNotice) }
                rows(result, identifier: "lio.taxi.search-row")
            }
            if destination {
                Section(language.text("My trip", "我的行程")) {
                    if tripPlaces.isEmpty { Text(language.text("No places from your trip.", "当前行程暂无可选地点。")) }
                    rows(tripPlaces, identifier: "lio.taxi.trip-row")
                }
                Section(language.text("Recent", "最近")) {
                    if recent.isEmpty { Text(language.text("No recent destinations.", "暂无最近终点。")) }
                    rows(recent, identifier: "lio.taxi.recent-row")
                }
            }
        }
        .lioPage()
        .navigationTitle(destination ? language.text("Choose a destination", "选择终点")
                                     : language.text("Choose a pickup point", "选择起点"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(language.text("Cancel", "取消")) { dismiss() }
            }
        }
        .task(id: submittedQuery) {
            guard let submittedQuery else { return }
            isSearching = true
            searchNotice = nil
            result = []
            do {
                let matches = try await search(submittedQuery)
                try Task.checkCancellation()
                result = matches
                if matches.isEmpty { searchNotice = language.text("No matches. Try another name.", "没有匹配地点，请换个名称。") }
            } catch is CancellationError {
                return
            } catch {
                guard !Task.isCancelled else { return }
                searchNotice = language.text("Search is unavailable. Try again.", "搜索暂不可用，请重试。")
            }
            isSearching = false
            self.submittedQuery = nil
        }
    }

    private func submit() {
        let value = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        submittedQuery = value
    }

    private func rows(_ places: [LioTaxiPlace], identifier: String) -> some View {
        ForEach(places) { place in
            Button { select(place) } label: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(place.name(in: language)).foregroundStyle(LioTheme.ink)
                    if let address = place.addressZH {
                        Text(address).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    }
                }
                .frame(minHeight: 44)
            }
            .accessibilityIdentifier(identifier)
        }
    }
}

private struct LioTaxiDriverCard: View {
    let language: LioLanguage
    let place: LioTaxiPlace
    @Environment(\.dismiss) private var dismiss
    @State private var priorIdleTimer: Bool?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(place.nameZH).font(LioTheme.display(.largeTitle).weight(.bold))
                    if let address = place.addressZH { Text(address).font(.title2.weight(.semibold)) }
                    Text(place.nameEN).font(.body).foregroundStyle(LioTheme.inkSecondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(24)
            }
            .background(LioTheme.paper)
            .foregroundStyle(LioTheme.ink)
            .navigationTitle(language.text("Show the driver", "给司机看"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(language.text("Close", "关闭")) { dismiss() }
                }
            }
        }
        .onAppear {
            guard priorIdleTimer == nil else { return }
            priorIdleTimer = UIApplication.shared.isIdleTimerDisabled
            UIApplication.shared.isIdleTimerDisabled = true
        }
        .onDisappear {
            if let priorIdleTimer {
                UIApplication.shared.isIdleTimerDisabled = priorIdleTimer
                self.priorIdleTimer = nil
            }
        }
    }
}
#endif
