// Demonstration values only; this generated acceptance route is absent from shipping builds.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
struct LioRichItineraryFixture: View {
 let chinese: Bool
 private func text(_ english:String,_ chinese:String) -> String { self.chinese ? chinese:english }
 private func place(_ zh:String,_ en:String, _ point:Bool = true) -> LioRichItinerary.Place {
  .init(nameZH:zh, nameEN:en, address:point ? "演示市示例路 1 号":nil, matched:point,
        point:point ? .init(latitude:39.9,longitude:116.4):nil)
 }
 private var trip:LioRichItinerary {
  let a=LioRichItinerary.Stop(id:"sight",kind:.sight,text:text("Enjoy the garden at an easy pace.","慢慢游览花园。"),time:"09:00",
   place:place("示例花园","Sample garden"),note:text("Allow time for a break.","留些时间休息。"),tip:text("Bring drinking water.","带好饮用水。"))
  let b=LioRichItinerary.Stop(id:"meal",kind:.meal,text:text("A relaxed lunch nearby.","在附近悠闲地吃午餐。"),time:"12:00",
   place:place("示例餐馆","Sample restaurant",false),note:nil,tip:nil)
  let c=LioRichItinerary.Stop(id:"hotel",kind:.hotel,text:text("Return for a rest.","回去休息。"),time:"15:00",
   place:place("示例酒店","Sample hotel"),note:nil,tip:nil)
  let d=LioRichItinerary.Stop(id:"transport",kind:.transport,text:text("Head to the station.","前往车站。"),time:"10:00",
   place:place("示例车站","Sample station",false),note:nil,tip:nil)
  let f=LioRichItinerary.Stop(id:"free",kind:.freeTime,text:text("Leave the afternoon open.","下午自由安排。"),time:nil,
   place:place("自由活动","Free time",false),note:nil,tip:nil)
  let day=LioRichItinerary.Day(number:1,date:nil,theme:text("Gardens and a relaxed lunch","花园与悠闲午餐"),area:text("Central neighbourhood","市中心街区"),stops:[a,b,c],legs:[
   .init(fromID:a.id,toID:b.id,estimate:.init(mode:.walking,seconds:660,metres:800)),
   .init(fromID:b.id,toID:c.id,estimate:nil)])
  let second=LioRichItinerary.Day(number:2,date:nil,theme:text("An open afternoon","留白的下午"),area:text("Station neighbourhood","车站街区"),stops:[d,f],legs:[.init(fromID:d.id,toID:f.id,estimate:.init(mode:.transit,seconds:1200,metres:4500))])
  let third=LioRichItinerary.Day(number:3,date:nil,theme:text("A day to rest","休息一天"),area:text("At your own pace","按自己的节奏"),stops:[],legs:[])
  return .init(title:text("Three-day sample trip","三天的示例行程"),undated:true,days:[day,second,third],lodgingArea:text("Stay near the city centre","建议住在市中心附近"),hotels:[
   .init(id:"stay-a",place:place("示例酒店甲","Sample stay A",false),note:text("A quieter setting.","环境安静些。")),
   .init(id:"stay-b",place:place("示例酒店乙","Sample stay B",false),note:text("Close to public transport.","靠近公共交通。"))])
 }
 var body:some View {
  LioRichItineraryView(itinerary:trip,language:chinese ? .chinese:.english)
   .preferredColorScheme(ProcessInfo.processInfo.arguments.contains("--lio-rich-dark-acceptance") ? .dark : .light)
 }
}
#endif
