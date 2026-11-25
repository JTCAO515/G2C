#if DEBUG
import Foundation

/// Debug-only roadbooks for previews and screenshots (#1514). Well-known public places; coordinates are
/// approximate and addresses are for display only. Release builds never contain this data.
enum LioRoadbookPreview {
    static var requested: Bool { ProcessInfo.processInfo.arguments.contains("--lio-roadbook-preview") }

    static func library(_ language: LioLanguage) -> [LioRoadbook] {
        [beijing(language), shanghai(language)]
    }

    static func beijing(_ language: LioLanguage) -> LioRoadbook {
        func t(_ en: String, _ zh: String) -> String { language.text(en, zh) }
        func place(_ zh: String, _ en: String, _ address: String?, _ lat: Double, _ lng: Double, matched: Bool = true) -> LioRichItinerary.Place {
            .init(nameZH: zh, nameEN: en, address: address, matched: matched, point: .init(latitude: lat, longitude: lng))
        }
        func stop(_ id: String, _ kind: LioRichItinerary.Kind, _ time: String, _ place: LioRichItinerary.Place,
                  _ text: String, _ note: String, _ tip: String? = nil) -> LioRichItinerary.Stop {
            .init(id: id, kind: kind, text: text, time: time, place: place, note: note, tip: tip)
        }
        func leg(_ from: LioRichItinerary.Stop, _ to: LioRichItinerary.Stop, _ mode: LioRichItinerary.Leg.Mode?,
                 _ minutes: Double, _ km: Double) -> LioRichItinerary.Leg {
            .init(fromID: from.id, toID: to.id, estimate: mode.map { .init(mode: $0, seconds: minutes * 60, metres: km * 1000) })
        }
        let a = stop("bj1a", .sight, "08:30", place("天安门广场", "Tian'anmen Square", "北京市东城区东长安街", 39.9055, 116.3976),
                     t("Walk the square and see Tian'anmen Gate.", "走一走广场，看天安门城楼。"), t("1 hr", "约 1 小时"),
                     t("Bring your passport for the security check.", "进入需安检，带好护照。"))
        let b = stop("bj1b", .sight, "09:45", place("故宫博物院", "Palace Museum", "北京市东城区景山前街4号", 39.9163, 116.3972),
                     t("Halls, courtyards and the imperial garden, south to north.", "由南向北看大殿、院落和御花园。"), t("3 hrs", "约 3 小时"),
                     t("Book with your passport about 7 days ahead; usually closed on Mondays.", "需凭护照提前约 7 天预约；通常周一闭馆。"))
        let c = stop("bj1c", .meal, "13:15", place("王府井一带的烤鸭店", "Roast duck near Wangfujing", nil, 39.9135, 116.4035, matched: false),
                     t("Roast duck for lunch.", "午饭吃烤鸭。"), t("1 hr", "约 1 小时"))
        let d = stop("bj1d", .sight, "15:00", place("景山公园", "Jingshan Park", "北京市西城区景山西街44号", 39.9255, 116.3966),
                     t("Climb for the view over the Forbidden City.", "登高俯瞰故宫全景。"), t("1 hr", "约 1 小时"))
        let e = stop("bj1e", .meal, "18:30", place("簋街", "Guijie Food Street", "北京市东城区东直门内大街", 39.9407, 116.4268),
                     t("Dinner on the lantern-lit food street.", "在簋街吃晚饭。"), t("1.5 hrs", "约 1.5 小时"))
        let day1 = LioRichItinerary.Day(number: 1, date: "2026-12-01", theme: t("Imperial centre", "皇城中轴"), area: t("Dongcheng", "东城区"),
                                        stops: [a, b, c, d, e],
                                        legs: [leg(a, b, .walking, 15, 1.1), leg(b, c, .walking, 18, 1.3), leg(c, d, .taxi, 10, 2.6),
                                               leg(d, e, .transit, 25, 5.2)])
        let f = stop("bj2a", .sight, "08:00", place("慕田峪长城", "Mutianyu Great Wall", "北京市怀柔区渤海镇慕田峪村", 40.4319, 116.5704),
                     t("Walk the restored section; cable car up.", "游览慕田峪长城，可坐缆车上山。"), t("4 hrs", "约 4 小时"),
                     t("About 90 minutes by car from the city; cable car hours vary by season.", "从市区开车约 90 分钟；缆车时间随季节调整。"))
        let g = stop("bj2b", .freeTime, "15:30", place("三里屯", "Sanlitun", "北京市朝阳区三里屯路", 39.9334, 116.4547),
                     t("Shops and cafés after the wall.", "逛街、喝咖啡。"), t("2 hrs", "约 2 小时"))
        let day2 = LioRichItinerary.Day(number: 2, date: "2026-12-02", theme: t("Great Wall day", "长城一日"), area: t("Huairou", "怀柔区"),
                                        stops: [f, g], legs: [leg(f, g, .taxi, 90, 72)])
        let h = stop("bj3a", .sight, "08:30", place("天坛公园", "Temple of Heaven", "北京市东城区天坛东里甲1号", 39.8822, 116.4066),
                     t("Morning tai chi and the Hall of Prayer.", "看晨练和祈年殿。"), t("2 hrs", "约 2 小时"))
        let i = stop("bj3b", .sight, "11:30", place("南锣鼓巷", "Nanluoguxiang", "北京市东城区南锣鼓巷", 39.9370, 116.4033),
                     t("Hutong lanes and Houhai lake.", "逛胡同和后海。"), t("2 hrs", "约 2 小时"))
        let day3 = LioRichItinerary.Day(number: 3, date: "2026-12-03", theme: t("Temples and hutongs", "天坛与胡同"), area: t("Dongcheng", "东城区"),
                                        stops: [h, i], legs: [leg(h, i, nil, 0, 0)])
        let itinerary = LioRichItinerary(
            title: t("Three free days in Beijing", "北京三天自由行"), undated: false, days: [day1, day2, day3],
            lodgingArea: t("Stay around Wangfujing or Dongsi for easy metro access.", "住王府井或东四一带，地铁方便。"),
            hotels: [.init(id: "bj-h1", place: place("王府井一带", "Wangfujing area", nil, 39.914, 116.410, matched: false),
                           note: t("Walk to the Palace Museum", "步行可到故宫"))])
        return .init(id: "preview.beijing", source: .planned, city: .init(nameZH: "北京", nameEN: "Beijing"),
                     createdAt: Date(timeIntervalSince1970: 1_795_000_000), itinerary: itinerary)
    }

    static func shanghai(_ language: LioLanguage) -> LioRoadbook {
        func t(_ en: String, _ zh: String) -> String { language.text(en, zh) }
        func place(_ zh: String, _ en: String, _ address: String, _ lat: Double, _ lng: Double) -> LioRichItinerary.Place {
            .init(nameZH: zh, nameEN: en, address: address, matched: true, point: .init(latitude: lat, longitude: lng))
        }
        let a = LioRichItinerary.Stop(id: "sh1a", kind: .sight, text: t("Old garden and bazaar.", "逛园林和老街。"), time: "09:00",
                                      place: place("豫园", "Yu Garden", "上海市黄浦区福佑路168号", 31.2272, 121.4921),
                                      note: t("2 hrs", "约 2 小时"), tip: t("Busy on weekends; arrive early.", "周末人多，建议早到。"))
        let b = LioRichItinerary.Stop(id: "sh1b", kind: .sight, text: t("Riverside walk and the skyline at dusk.", "沿江散步，看黄昏天际线。"),
                                      time: "17:30", place: place("外滩", "The Bund", "上海市黄浦区中山东一路", 31.2400, 121.4900),
                                      note: t("1.5 hrs", "约 1.5 小时"), tip: nil)
        let c = LioRichItinerary.Stop(id: "sh2a", kind: .sight, text: t("Plane-tree streets of the former French Concession.", "走梧桐树下的老街区。"),
                                      time: "10:00", place: place("武康路", "Wukang Road", "上海市徐汇区武康路", 31.2069, 121.4385),
                                      note: t("2 hrs", "约 2 小时"), tip: nil)
        let itinerary = LioRichItinerary(
            title: t("Two days in Shanghai", "上海两日"), undated: true,
            days: [.init(number: 1, date: nil, theme: t("Old town and the Bund", "老城厢与外滩"), area: t("Huangpu", "黄浦区"),
                         stops: [a, b], legs: [.init(fromID: a.id, toID: b.id, estimate: .init(mode: .walking, seconds: 1500, metres: 1800))]),
                   .init(number: 2, date: nil, theme: t("Leafy streets", "梧桐街区"), area: t("Xuhui", "徐汇区"), stops: [c], legs: [])],
            lodgingArea: t("Stay near People's Square for metro lines 1, 2 and 8.", "住人民广场附近，1、2、8 号线方便。"), hotels: [])
        return .init(id: "template.shanghai-2d", source: .template, city: .init(nameZH: "上海", nameEN: "Shanghai"),
                     createdAt: Date(timeIntervalSince1970: 1_794_000_000), itinerary: itinerary)
    }
}
#endif
