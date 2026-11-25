import Foundation

/// Ticket tips for foreign visitors, per transport mode (#1519). Static text: checked against the sources
/// below on `checkedOn`; re-check before each public release. Rules change, so the wording stays general.
enum LioTransportGuide {
    static let checkedOn = "2026-11-25"

    struct Tip: Identifiable, Sendable {
        let id: String
        let titleEN: String
        let titleZH: String
        let bodyEN: String
        let bodyZH: String

        func title(_ language: LioLanguage) -> String { language.text(titleEN, titleZH) }
        func body(_ language: LioLanguage) -> String { language.text(bodyEN, bodyZH) }
    }

    struct Source: Sendable {
        let name: String
        let url: URL
    }

    static func tips(for mode: LioTransportMode) -> [Tip] {
        switch mode {
        case .rail: rail
        case .flight: flight
        case .bus: bus
        }
    }

    static func sources(for mode: LioTransportMode) -> [Source] {
        switch mode {
        case .rail: [railway12306, mtr12306, beijingTickets]
        case .flight: [beijingTickets, beijingPowerBanks]
        case .bus: [busRealName]
        }
    }

    private static let rail: [Tip] = [
        Tip(id: "rail.passport", titleEN: "Book with your passport", titleZH: "凭护照购票",
            bodyEN: "Train tickets are real-name. Book on the 12306 English website or app after registering and verifying your passport (allow a few days), or on Trip.com in English with a foreign card. The name and number must match the passport you travel with.",
            bodyZH: "火车票实名制。可在 12306 英文网站或 App 注册并核验护照后购票（核验可能需要几天，请提前办），也可在 Trip.com 用英文和境外银行卡订票。姓名和证件号必须与出行所持护照一致。"),
        Tip(id: "rail.ticket", titleEN: "Your passport is your ticket", titleZH: "护照就是车票",
            bodyEN: "Tickets are electronic. You do not need to print anything; keep the booking confirmation with the train number, car and seat on your phone.",
            bodyZH: "车票是电子票，不用打印。手机里保存好订单，记下车次、车厢和座位号。"),
        Tip(id: "rail.arrive-early", titleEN: "Arrive about an hour early", titleZH: "提前约 1 小时到站",
            bodyEN: "Big stations have an ID check at the entrance, a bag scan and a long walk to the platform. Boarding gates close a few minutes before departure, so do not cut it close.",
            bodyZH: "大站进站要验证件、过安检，到站台还要走很远。检票口在开车前几分钟就停止检票，不要卡点。"),
        Tip(id: "rail.gates", titleEN: "Use the staffed lane", titleZH: "走人工通道",
            bodyEN: "Automatic gates may not read a foreign passport. Use the staffed lane at the entrance and at the boarding gate and show your passport.",
            bodyZH: "自动闸机可能识别不了外国护照。进站和检票时走人工通道，出示护照即可。"),
        Tip(id: "rail.security", titleEN: "Security check", titleZH: "安检",
            bodyEN: "All bags go through an X-ray scan. Lighters, fireworks and other flammables are not allowed.",
            bodyZH: "所有行李都要过安检机。打火机、烟花爆竹等易燃物品不能带。"),
        Tip(id: "rail.changes", titleEN: "Changes and refunds", titleZH: "改签和退票",
            bodyEN: "Change or refund on 12306 or Trip.com, or at a station ticket window with your passport. Fees depend on how close to departure you are.",
            bodyZH: "可在 12306、Trip.com 或车站售票窗口凭护照改签、退票，手续费按离开车时间长短收取。"),
    ]

    private static let flight: [Tip] = [
        Tip(id: "flight.passport", titleEN: "Name exactly as in your passport", titleZH: "姓名与护照一致",
            bodyEN: "Book with your name and passport number exactly as printed in the passport you will fly with; a mismatch can stop you at check-in.",
            bodyZH: "订票时姓名和护照号要与登机所持护照完全一致，否则可能无法值机。"),
        Tip(id: "flight.airports", titleEN: "Check which airport", titleZH: "看清是哪个机场",
            bodyEN: "Beijing, Shanghai and Chengdu each have two airports far apart. Check the airport code on your booking before you take a taxi.",
            bodyZH: "北京、上海、成都都有两个机场，相距很远。打车前先核对订单上的机场代码。"),
        Tip(id: "flight.arrive-early", titleEN: "Arrive two hours early", titleZH: "提前 2 小时到机场",
            bodyEN: "Check-in for domestic flights usually closes 45 minutes before departure, and security lines can be long.",
            bodyZH: "国内航班通常在起飞前 45 分钟截止值机，安检排队也可能较久。"),
        Tip(id: "flight.power-bank", titleEN: "Power banks need the 3C mark", titleZH: "充电宝要有 3C 标识",
            bodyEN: "On domestic flights, power banks without a clear China 3C mark, or recalled models, are not allowed. Keep any power bank in your carry-on, never in checked bags.",
            bodyZH: "国内航班禁止携带没有 3C 标识、标识不清或被召回的充电宝。充电宝只能随身携带，不能托运。"),
    ]

    private static let bus: [Tip] = [
        Tip(id: "bus.station", titleEN: "Buy at the bus station", titleZH: "到客运站买票",
            bodyEN: "Long-distance buses leave from intercity bus stations. Buy at the ticket window with your passport; tickets are real-name and checked again when you board.",
            bodyZH: "长途大巴从城际客运站发车。凭护照到售票窗口买票；车票实名，上车时还会查验。"),
        Tip(id: "bus.online", titleEN: "Online booking is mostly in Chinese", titleZH: "网上订票多为中文",
            bodyEN: "Bus booking apps and self-service machines are mostly in Chinese and often need a Chinese ID. Ask your hotel to help, or buy at the window.",
            bodyZH: "大巴订票 App 和自助机大多只有中文，常要求中国身份证。可请酒店帮忙，或直接到窗口买票。"),
        Tip(id: "bus.arrive-early", titleEN: "Arrive 30 minutes early", titleZH: "提前 30 分钟到站",
            bodyEN: "Bus stations have a bag scan and ID check. Have the destination written in Chinese to show staff.",
            bodyZH: "客运站要安检和验证件。准备好中文目的地，方便给工作人员看。"),
        Tip(id: "bus.when", titleEN: "When a bus makes sense", titleZH: "什么时候坐大巴",
            bodyEN: "For most trips between big cities the train is faster. Buses help for towns and scenic areas without a railway station.",
            bodyZH: "大城市之间一般坐高铁更快。没有火车站的县城和景区，可以考虑大巴。"),
    ]

    private static let railway12306 = Source(name: "12306 China Railway (English)",
                                             url: URL(string: "https://www.12306.cn/en/index.html")!)
    private static let mtr12306 = Source(
        name: "MTR: Create a 12306 account",
        url: URL(string: "https://www.highspeed.mtr.com.hk/en/latest-news/ticketing-via-12306-account-registration.html")!)
    private static let beijingTickets = Source(
        name: "Beijing Government: Guide to Buying Train and Air Tickets",
        url: URL(string: "https://english.beijing.gov.cn/latest/news/202108/t20210820_2473220.html")!)
    private static let beijingPowerBanks = Source(
        name: "Beijing Government: Power banks without 3C certification banned on domestic flights",
        url: URL(string: "https://english.beijing.gov.cn/latest/news/202506/t20250628_4131163.html")!)
    private static let busRealName = Source(
        name: "Travel China Guide: Long-distance bus tickets are real-name",
        url: URL(string: "https://www.travelchinaguide.com/tour/news/20170228.htm")!)
}
