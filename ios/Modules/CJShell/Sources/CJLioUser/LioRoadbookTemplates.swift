import Foundation

/// Popular routes (JT 2026-11-25): Beijing 3 days and Shanghai 2 days first; Xi'an and Chengdu follow.
/// Written by hand in both languages: well-known public places, suggested times, general reminders only.
/// No prices, no live information and no travel times. Places stay "suggested" (no taxi, no driver card)
/// until G2C - S has checked each address and coordinate with Gaode (M4 item 18, ids bj-001…, sh-001…).
enum LioRoadbookTemplates {
    static func all(_ language: LioLanguage) -> [LioRoadbook] {
        [beijing(language), shanghai(language)]
    }

    private struct Spot {
        let id: String
        let zh: String
        let en: String
        let kind: LioRichItinerary.Kind
        let time: String
        let text: (String, String)
        let note: (String, String)
        let tip: (String, String)?
    }

    private static func book(_ id: String, city: LioRoadbook.City, title: (String, String),
                             days: [(theme: (String, String), area: (String, String), spots: [Spot])],
                             lodging: (String, String), hotels: [(String, String, String)],
                             _ language: LioLanguage) -> LioRoadbook {
        func t(_ pair: (String, String)) -> String { language.text(pair.1, pair.0) }
        func place(_ zh: String, _ en: String) -> LioRichItinerary.Place {
            .init(nameZH: zh, nameEN: en, address: nil, matched: false, point: nil)
        }
        let builtDays = days.enumerated().map { offset, day in
            let stops = day.spots.map { spot in
                LioRichItinerary.Stop(id: spot.id, kind: spot.kind, text: t(spot.text), time: spot.time,
                                      place: place(spot.zh, spot.en), note: t(spot.note), tip: spot.tip.map(t))
            }
            // No legs: travel between stops is not estimated for a route nobody has planned yet.
            return LioRichItinerary.Day(number: offset + 1, date: nil, theme: t(day.theme), area: t(day.area),
                                        stops: stops, legs: [])
        }
        let itinerary = LioRichItinerary(title: t(title), undated: true, days: builtDays, lodgingArea: t(lodging),
                                         hotels: hotels.map { .init(id: $0.0, place: place($0.1, $0.2), note: nil) })
        return LioRoadbook(id: id, source: .template, city: city, createdAt: Date(timeIntervalSince1970: 0),
                           itinerary: itinerary)
    }

    static func beijing(_ language: LioLanguage) -> LioRoadbook {
        let security = ("需提前实名预约，进入时安检，带好护照。", "Book ahead with your passport; there is a security check at the entrance.")
        return book("template.beijing-3d", city: .init(nameZH: "北京", nameEN: "Beijing"),
                    title: ("北京三日经典路线", "Three classic days in Beijing"), days: [
            (theme: ("皇城中轴", "The imperial axis"), area: ("东城区", "Dongcheng"), spots: [
                Spot(id: "bj-001", zh: "天安门广场", en: "Tian'anmen Square", kind: .sight, time: "08:30",
                     text: ("从广场走到天安门城楼前。", "Walk the square up to Tian'anmen Gate."),
                     note: ("约 1 小时", "About 1 hour"), tip: security),
                Spot(id: "bj-002", zh: "故宫博物院", en: "Palace Museum", kind: .sight, time: "09:45",
                     text: ("由南向北看大殿、院落和御花园。", "Halls, courtyards and the imperial garden, from south to north."),
                     note: ("约 3 小时", "About 3 hours"),
                     tip: ("需提前实名预约，通常周一闭馆。", "Book ahead with your passport; usually closed on Mondays.")),
                Spot(id: "bj-003", zh: "景山公园", en: "Jingshan Park", kind: .sight, time: "14:30",
                     text: ("登上万春亭，俯瞰故宫全景。", "Climb to Wanchun Pavilion for the view over the Forbidden City."),
                     note: ("约 1 小时", "About 1 hour"), tip: nil),
                Spot(id: "bj-004", zh: "王府井大街", en: "Wangfujing Street", kind: .meal, time: "18:30",
                     text: ("晚饭和夜间散步。", "Dinner and an evening walk."),
                     note: ("约 2 小时", "About 2 hours"), tip: nil),
            ]),
            (theme: ("长城一日", "A day on the Great Wall"), area: ("怀柔区", "Huairou"), spots: [
                Spot(id: "bj-005", zh: "慕田峪长城", en: "Mutianyu Great Wall", kind: .sight, time: "08:00",
                     text: ("修复完好的一段长城，可坐缆车上下。", "A restored section; cable cars go up and down."),
                     note: ("约 4 小时，不含往返市区", "About 4 hours, plus the ride from the city"),
                     tip: ("出发前确认往返交通和缆车开放情况。", "Arrange the ride back and check the cable car before you go.")),
                Spot(id: "bj-006", zh: "簋街", en: "Guijie Food Street", kind: .meal, time: "18:30",
                     text: ("回城后在灯笼街吃晚饭。", "Dinner back in town on the lantern-lit food street."),
                     note: ("约 1.5 小时", "About 1.5 hours"), tip: nil),
            ]),
            (theme: ("天坛与胡同", "Temples and hutongs"), area: ("东城区、西城区", "Dongcheng and Xicheng"), spots: [
                Spot(id: "bj-007", zh: "天坛公园", en: "Temple of Heaven", kind: .sight, time: "08:30",
                     text: ("看晨练和祈年殿。", "Morning exercises in the park and the Hall of Prayer."),
                     note: ("约 2 小时", "About 2 hours"), tip: nil),
                Spot(id: "bj-008", zh: "南锣鼓巷", en: "Nanluoguxiang", kind: .freeTime, time: "13:00",
                     text: ("逛胡同，吃午饭。", "Hutong lanes and lunch."),
                     note: ("约 1.5 小时", "About 1.5 hours"), tip: nil),
                Spot(id: "bj-010", zh: "鼓楼", en: "Drum Tower", kind: .sight, time: "15:00",
                     text: ("登楼看老城屋顶。", "Climb for the view over the old city's rooftops."),
                     note: ("约 1 小时", "About 1 hour"),
                     tip: ("登楼可能要预约，傍晚前停止售票。", "Climbing may require a booking; ticket sales stop before evening.")),
                Spot(id: "bj-009", zh: "什刹海", en: "Shichahai", kind: .sight, time: "16:30",
                     text: ("沿后海散步，看老北京胡同人家。", "Walk around Houhai lake past old courtyard homes."),
                     note: ("约 1.5 小时", "About 1.5 hours"), tip: nil),
            ]),
        ], lodging: ("住王府井或东四一带，地铁方便，步行可到故宫和胡同。",
                     "Stay around Wangfujing or Dongsi: easy metro and a walk to the palace and hutongs."),
           hotels: [("bj-011", "王府井", "Wangfujing area"), ("bj-012", "东四", "Dongsi area")], language)
    }

    static func shanghai(_ language: LioLanguage) -> LioRoadbook {
        book("template.shanghai-2d", city: .init(nameZH: "上海", nameEN: "Shanghai"),
             title: ("上海两日经典路线", "Two classic days in Shanghai"), days: [
            (theme: ("老城厢与外滩", "Old town and the Bund"), area: ("黄浦区", "Huangpu"), spots: [
                Spot(id: "sh-001", zh: "豫园", en: "Yu Garden", kind: .sight, time: "09:00",
                     text: ("明代园林，亭台假山。", "A Ming-dynasty garden of pavilions and rockeries."),
                     note: ("约 1.5 小时", "About 1.5 hours"),
                     tip: ("周末和节假日人多，建议早到；除节假日外通常周一闭园。", "Busy at weekends and holidays; arrive early. Usually closed on Mondays except public holidays.")),
                Spot(id: "sh-002", zh: "城隍庙", en: "City God Temple", kind: .meal, time: "11:30",
                     text: ("在老街吃小笼包等小吃。", "Soup dumplings and snacks in the old streets."),
                     note: ("约 1 小时", "About 1 hour"), tip: nil),
                Spot(id: "sh-003", zh: "南京路步行街", en: "Nanjing Road Pedestrian Street", kind: .freeTime, time: "14:30",
                     text: ("逛老字号和商场。", "Old shops and department stores."),
                     note: ("约 2 小时", "About 2 hours"), tip: nil),
                Spot(id: "sh-004", zh: "外滩", en: "The Bund", kind: .sight, time: "18:00",
                     text: ("沿江散步，看对岸陆家嘴夜景。", "Walk the riverfront and watch Lujiazui light up across the river."),
                     note: ("约 1.5 小时", "About 1.5 hours"), tip: nil),
            ]),
            (theme: ("博物馆与梧桐街区", "Museums and leafy streets"), area: ("黄浦区、徐汇区、浦东新区", "Huangpu, Xuhui and Pudong"), spots: [
                Spot(id: "sh-005", zh: "上海博物馆", en: "Shanghai Museum", kind: .sight, time: "09:30",
                     text: ("青铜器、陶瓷和书画。", "Bronzes, ceramics and painting."),
                     note: ("约 2.5 小时", "About 2.5 hours"),
                     tip: ("节假日和特展期间通常要预约，周一闭馆。", "Booking is usually required on holidays and for special shows; closed on Mondays.")),
                Spot(id: "sh-006", zh: "武康路", en: "Wukang Road", kind: .freeTime, time: "13:30",
                     text: ("走梧桐树下的老洋房街区。", "Plane trees and old villas in the former French Concession."),
                     note: ("约 2 小时", "About 2 hours"), tip: nil),
                Spot(id: "sh-007", zh: "新天地", en: "Xintiandi", kind: .meal, time: "17:30",
                     text: ("在石库门弄堂里吃晚饭。", "Dinner among restored shikumen lane houses."),
                     note: ("约 1.5 小时", "About 1.5 hours"), tip: nil),
                Spot(id: "sh-008", zh: "陆家嘴", en: "Lujiazui", kind: .sight, time: "19:30",
                     text: ("看摩天楼群和江景。", "Skyscrapers and the river at night."),
                     note: ("约 1.5 小时", "About 1.5 hours"),
                     tip: ("观光厅要另外购票。", "Observation decks charge for entry.")),
            ]),
        ], lodging: ("住人民广场附近，地铁 1、2、8 号线方便。", "Stay near People's Square for metro lines 1, 2 and 8."),
           hotels: [("sh-009", "人民广场", "People's Square area")], language)
    }
}
