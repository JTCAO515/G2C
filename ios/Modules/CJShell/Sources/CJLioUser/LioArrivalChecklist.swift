import Foundation

/// Arrival mode: the first hours in China as one checklist. Each step opens the tool that does it and can be ticked.
enum LioArrivalStep: String, CaseIterable, Sendable, Identifiable {
    case entry, payment, internet, taxi, emergency

    var id: Self { self }
    var identifier: String { "lio.arrival.step." + rawValue }

    var symbol: String {
        switch self {
        case .entry: "person.text.rectangle"
        case .payment: "wallet.pass"
        case .internet: "simcard"
        case .taxi: "car.fill"
        case .emergency: "cross.case"
        }
    }

    func title(_ language: LioLanguage) -> String {
        switch self {
        case .entry: language.text("Before you land", "入境前准备")
        case .payment: language.text("Set up mobile payment", "开通手机支付")
        case .internet: language.text("Get online", "解决上网")
        case .taxi: language.text("Taxi to your hotel", "打车去酒店")
        case .emergency: language.text("Emergency help", "应急求助")
        }
    }

    func summary(_ language: LioLanguage) -> String {
        switch self {
        case .entry: language.text("Visa-free or visa, and the official arrival card",
                                   "免签还是签证，官方入境卡")
        case .payment: language.text("Link your card to Alipay or Weixin Pay", "支付宝、微信绑定境外卡")
        case .internet: language.text("Roaming, eSIM or a local SIM", "漫游、eSIM 或当地 SIM 卡")
        case .taxi: language.text("Show the driver your hotel or open DiDi", "给司机看酒店地址，或用滴滴")
        case .emergency: language.text("110, 120, your embassy, medical card", "110、120、使领馆、医疗卡")
        }
    }
}

/// Ticked steps, stored on the device as a comma-separated list of step names.
struct LioArrivalProgress: Equatable, Sendable {
    private(set) var done: Set<LioArrivalStep>

    init(stored: String) {
        done = Set(stored.split(separator: ",").compactMap { LioArrivalStep(rawValue: String($0)) })
    }

    var stored: String { LioArrivalStep.allCases.filter(done.contains).map(\.rawValue).joined(separator: ",") }
    var doneCount: Int { done.count }
    func isDone(_ step: LioArrivalStep) -> Bool { done.contains(step) }

    mutating func toggle(_ step: LioArrivalStep) {
        if done.contains(step) { done.remove(step) } else { done.insert(step) }
    }
}

/// Where the taxi step goes: the trip's first stay with a matched address, or what the traveller typed.
struct LioArrivalHotel: Equatable, Sendable {
    enum Source: Equatable, Sendable { case trip, typed }
    let nameZH: String
    let nameEN: String?
    let addressZH: String?
    let source: Source

    var driverRequestZH: String { "请送我到这家酒店" }

    init(nameZH: String, nameEN: String?, addressZH: String?, source: Source) {
        self.nameZH = nameZH; self.nameEN = nameEN; self.addressZH = addressZH; self.source = source
    }

    /// Only a matched place is trusted for the driver card, as on the trip timeline.
    init?(hotels: [LioRichItinerary.Hotel]) {
        guard let hotel = hotels.first(where: { $0.place.driverAddress?.isEmpty == false }) else { return nil }
        self.init(nameZH: hotel.place.nameZH, nameEN: hotel.place.nameEN, addressZH: hotel.place.driverAddress,
                  source: .trip)
    }

    init?(typedName: String, address: String) {
        let name = typedName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return nil }
        let address = address.trimmingCharacters(in: .whitespacesAndNewlines)
        self.init(nameZH: name, nameEN: nil, addressZH: address.isEmpty ? nil : address, source: .typed)
    }
}

/// `G2CArrivalModeEnabled` in the build's Info.plist; off unless it says YES. JT decides when to turn it on.
enum LioArrivalFeature {
    static let infoKey = "G2CArrivalModeEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }
}

/// Getting online: guidance only. Nothing is sold here and there are no partner or promotion links.
enum LioArrivalInternetOption: String, CaseIterable, Sendable, Identifiable {
    case roaming, esim, localSIM

    var id: Self { self }

    var symbol: String {
        switch self {
        case .roaming: "antenna.radiowaves.left.and.right"
        case .esim: "esim"
        case .localSIM: "simcard"
        }
    }

    func title(_ language: LioLanguage) -> String {
        switch self {
        case .roaming: language.text("Roaming on your own number", "用自己号码漫游")
        case .esim: language.text("Travel eSIM", "旅行 eSIM")
        case .localSIM: language.text("Chinese SIM card", "中国本地 SIM 卡")
        }
    }

    func detail(_ language: LioLanguage) -> String {
        switch self {
        case .roaming:
            language.text("Simplest: nothing to install and you keep your number for bank and app codes. Ask your carrier about China roaming prices before you fly.",
                          "最省事：不用另装，自己的号码照常收银行和 App 验证码。出发前向你的运营商问清中国漫游资费。")
        case .esim:
            language.text("Check that your phone supports eSIM and is not locked to one carrier. Buy from a seller you trust and install it before you fly, while you still have Wi-Fi.",
                          "先确认手机支持 eSIM、没有锁网。从你信任的渠道购买，出发前在有 Wi-Fi 时装好。")
        case .localSIM:
            language.text("Sold at carrier shops in China. Bring your passport: SIM cards are registered to your real name. A local number can help with some Chinese apps.",
                          "在中国运营商营业厅办理。带上护照：手机卡需要实名登记。本地号码对部分国内 App 更方便。")
        }
    }

    static func footnote(_ language: LioLanguage) -> String {
        language.text("Keep your home number able to receive texts: payment apps and banks may send codes to it.",
                      "让自己的号码保持能收短信：支付 App 和银行可能会把验证码发到这个号码。")
    }
}
