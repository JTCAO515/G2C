private struct LioDayChipCardFixture: View {
 let chinese: Bool
 @State private var viewed=0
 var body: some View {
  let stops=(1...6).map { LioItinerary.Stop(id:"synthetic-\($0)",name:"Day1 stop \($0)",time:nil,point:nil,fixed:$0 == 1) }
  let trip=LioItinerary(id:"synthetic-card",title:chinese ? "三天的旅行安排":"A three-day plan",description:chinese ? "按轻松节奏安排。":"Planned at a relaxed pace.",days:[.init(number:1,stops:stops),.init(number:2,stops:[.init(id:"synthetic-other",name:"Day2 stop",time:nil,point:nil,fixed:nil)]),.init(number:3,stops:[])],calendar:.undated)
  ScrollView { VStack(alignment:.leading,spacing:16) {
   LioItineraryCard(itinerary:trip,language:chinese ? .chinese:.english,showTrips:{viewed += 1}) { EmptyView() }
   Text(String(viewed)).accessibilityIdentifier("fixture.card.viewed")
  }.padding(16) }.lioPage()
 }
}
