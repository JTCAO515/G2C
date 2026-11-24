import Foundation

#if DEBUG
/// Synthetic demo network for the #1454 framework: invented names and positions, not a real city.
/// Real Guangzhou, Shanghai and Beijing data comes from S as bundled `METRO.1` files once JT approves the source.
enum LioMetroMapPreview {
    static var requested: Bool { ProcessInfo.processInfo.arguments.contains("--lio-metro-map-preview") }

    static let json = Data("""
    {"version":"METRO.1","city":"demo","data_version":"demo-1",
     "source":{"name":"Demo data","license":"Not for travel","url":"https://example.invalid/metro-demo"},
     "lines":[
      {"id":"red","name_zh":"示例 1 号线","name_en":"Demo Line 1","color":"#C8102E","stations":["a","b","c","d","e","f"]},
      {"id":"blue","name_zh":"示例 2 号线","name_en":"Demo Line 2","color":"#0057B8","stations":["g","h","c","i","j"]},
      {"id":"green","name_zh":"示例环线","name_en":"Demo Loop","color":"#00843D","stations":["k","e","l","j","m","h","k"]}
     ],
     "stations":[
      {"id":"a","name_zh":"西门","name_en":"West Gate","lat":30.00,"lng":120.00,"coordinate_system":"WGS-84","x":0.08,"y":0.50},
      {"id":"b","name_zh":"博物馆","name_en":"Museum","lat":30.00,"lng":120.01,"coordinate_system":"WGS-84","x":0.24,"y":0.50},
      {"id":"c","name_zh":"中心广场","name_en":"Central Square","lat":30.00,"lng":120.02,"coordinate_system":"WGS-84","x":0.42,"y":0.50},
      {"id":"d","name_zh":"老街","name_en":"Old Street","lat":30.00,"lng":120.03,"coordinate_system":"WGS-84","x":0.58,"y":0.50},
      {"id":"e","name_zh":"东湖","name_en":"East Lake","lat":30.00,"lng":120.04,"coordinate_system":"WGS-84","x":0.72,"y":0.50},
      {"id":"f","name_zh":"火车东站","name_en":"East Railway Station","lat":30.00,"lng":120.05,"coordinate_system":"WGS-84","x":0.90,"y":0.50},
      {"id":"g","name_zh":"北山","name_en":"North Hill","lat":30.02,"lng":120.02,"coordinate_system":"WGS-84","x":0.42,"y":0.08},
      {"id":"h","name_zh":"大学城","name_en":"University Town","lat":30.01,"lng":120.02,"coordinate_system":"WGS-84","x":0.42,"y":0.28},
      {"id":"i","name_zh":"体育中心","name_en":"Sports Centre","lat":29.99,"lng":120.02,"coordinate_system":"WGS-84","x":0.42,"y":0.70},
      {"id":"j","name_zh":"南港","name_en":"South Harbour","lat":29.98,"lng":120.02,"coordinate_system":"WGS-84","x":0.42,"y":0.88},
      {"id":"k","name_zh":"花园","name_en":"Garden","lat":30.01,"lng":120.03,"coordinate_system":"WGS-84","x":0.62,"y":0.24},
      {"id":"l","name_zh":"会展中心","name_en":"Expo Centre","lat":29.99,"lng":120.04,"coordinate_system":"WGS-84","x":0.68,"y":0.80},
      {"id":"m","name_zh":"机场","name_en":"Airport","lat":29.98,"lng":120.00,"coordinate_system":"WGS-84","x":0.18,"y":0.80}
     ]}
    """.utf8)

    static var map: LioMetroMap? { try? LioMetroMapWire.read(json) }
}
#endif
