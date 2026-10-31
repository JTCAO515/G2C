#if os(iOS)
import SwiftUI
import CJTripClient
import CJRunClient
import CJMessageHTTP

struct TripTimelineView: View {
    let host: TripTimelineHost
    let language: ShellLanguage
    var onDiscuss:((TripDiscussionEntry)->Bool)?
    @Environment(\.dismiss) private var dismiss
    @State private var issue: String?
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:16) {
                    RunReadableText(text:language.text("Only accepted structured records. Dates, zones, precision and original item order are retained; unknown values are never filled from this device.","只显示已采用的结构化记录。保留声明日期、时区、精度和原条目顺序；不从设备补齐未知值。"))
                    if let display=host.display() {
                        RunReadableText(text:message(display.state)).accessibilityIdentifier("timeline.state")
                        button("timeline.refresh",language.text("Read formal trips","读取正式行程"),disabled:display.busy) { run { try host.page() } }
                        ForEach(display.trips,id:\.tripID) { trip in
                            button("timeline.trip."+trip.tripID,trip.title+" · "+String(trip.version),disabled:display.busy) { run { try host.select(trip.tripID) } }
                        }
                        if display.hasNext { button("timeline.next",language.text("Read next page","读取下一页"),disabled:display.busy) { run { try host.page(more:true) } } }
                        if let record=display.record,let timeline=display.timeline {
                            RunSelectableText(text:record.tripID+" · "+language.text("Read version ","读取版本 ")+String(record.version)).accessibilityIdentifier("timeline.record.version")
                            RunSelectableText(text:record.document.title).accessibilityIdentifier("timeline.record.title")
                            if onDiscuss != nil {
                                button("timeline.discuss.trip",language.text("Discuss this whole Trip","讨论整个行程"),disabled:display.busy) { discuss(day:nil,itemID:nil) }
                            }
                            ForEach(timeline.groups) { group in
                                RunReadableText(text:groupLabel(group),style:.headline).accessibilityIdentifier("timeline.day."+group.id)
                                if onDiscuss != nil,let date=group.date,let zone=group.timezone {
                                    button("timeline.discuss.day."+group.id,language.text("Discuss this declared day","讨论此声明日期"),disabled:display.busy) {
                                        do { discuss(day:try MessageTripSelection.Day(date:date,timezone:zone),itemID:nil) }
                                        catch { discussionFailed() }
                                    }
                                }
                                ForEach(group.entries) { entry in
                                    VStack(alignment:.leading,spacing:8) {
                                        RunSelectableText(text:entry.id+"\n"+entry.item.text).accessibilityIdentifier("timeline.item."+entry.id)
                                        RunSelectableText(text:language.text("Start: ","开始：")+event(entry.item.start)+"\n"+language.text("End: ","结束：")+event(entry.item.end))
                                            .accessibilityIdentifier("timeline.schedule."+entry.id)
                                        RunReadableText(text:span(entry.span)).accessibilityIdentifier("timeline.span."+entry.id)
                                        RunReadableText(text:language.text("Source declaration: ","来源声明：")+entry.item.sourceCategory.rawValue+" · "+entry.item.verification.rawValue,style:.caption)
                                        if onDiscuss != nil {
                                            button("timeline.discuss.item."+entry.id,language.text("Discuss this original item","讨论此原条目"),disabled:display.busy) {
                                                do {
                                                    let day:MessageTripSelection.Day?
                                                    if let date=group.date,let zone=group.timezone { day=try .init(date:date,timezone:zone) } else { day=nil }
                                                    discuss(day:day,itemID:entry.id)
                                                } catch { discussionFailed() }
                                            }
                                        }
                                    }.padding(.vertical,10)
                                }
                            }
                            RunReadableText(text:language.text("Grouping is a view only. It neither changes the formal order nor proves bookings, chronology or overall feasibility.","分组仅用于显示，不改变正式顺序，也不证明预订、时序或整体可行性。"),style:.caption)
                        }
                    } else { RunReadableText(text:language.text("Original account context unavailable.","原账号上下文不可用。")) }
                    if let issue { RunReadableText(text:issue).accessibilityIdentifier("timeline.issue") }
                }.frame(maxWidth:.infinity,alignment:.leading).padding()
            }.accessibilityIdentifier("timeline.content").navigationTitle(language.text("Timeline","时间线")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement:.topBarTrailing) { Button(language.text("Done","完成")) { host.invalidate();dismiss() }.accessibilityIdentifier("timeline.done") } }
                .onDisappear { host.invalidate() }
        }
    }
    private func button(_ id:String,_ title:String,disabled:Bool,action:@escaping()->Void) -> some View {
        Button(action:action) { RunReadableText(text:title).frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle()) }
            .buttonStyle(ShellReadableButtonStyle()).disabled(disabled).accessibilityIdentifier(id)
    }
    private func run(_ make:()throws->TripTimelineWork) {
        do { let work=try make();issue=nil;Task { await host.perform(work) } }
        catch { issue=language.text("Read unavailable; select the current original account again.","读取不可用，请重新选择当前原账号。") }
    }
    private func discuss(day:MessageTripSelection.Day?,itemID:String?) {
        do {
            let entry=try host.discussion(day:day,itemID:itemID)
            guard onDiscuss?(entry)==true else { discussionFailed();return }
        } catch { discussionFailed() }
    }
    private func discussionFailed() { issue=language.text("The original choice cannot be used. Read and select the current original account again.","原选择不可用，请重新读取并选择当前原账号的记录。") }
    private func groupLabel(_ group:TripTimelineGroup) -> String {
        if let date=group.date,let zone=group.timezone { return date+" · "+zone }
        return language.text("Date or timezone undetermined","日期或时区尚未确定")
    }
    private func event(_ value:StructuredTripEvent) -> String {
        [value.date,value.time,value.timezone,value.utcOffset].map(observation).joined(separator:" · ")
    }
    private func observation(_ value:TripObservation<String>) -> String {
        switch value {
        case .known(let text): text
        case .missing: language.text("Explicitly missing","明确缺失")
        case .unknown: language.text("Unknown","未知")
        case .uncertain(let note): language.text("Uncertain: ","不确定：")+note
        }
    }
    private func span(_ value:TripTimelineSpan) -> String {
        switch value {
        case .sameLocalDay: language.text("Same declared local day","声明为同一当地日期")
        case .continuesTo(let day): language.text("Continues to ","跨日至 ")+day+language.text("; the original item is shown once at its start day.","；原条目只在开始日显示一次。")
        case .differentZones: language.text("Different declared zones; no device-zone conversion or inferred day shift.","两端声明时区不同；不按设备时区转换或推断日期归属。")
        case .reversedLocalDates: language.text("End local date precedes start; verification needed.","结束当地日期早于开始日期，待核对。")
        case .undetermined: language.text("Incomplete local date/zone declarations; no inferred duration.","当地日期／时区声明不足，不推断时长。")
        }
    }
    private func message(_ value:TripTimelineLoadState) -> String {
        switch value {
        case .idle: language.text("No formal records read yet.","尚未读取正式记录。")
        case .loading: language.text("Reading the captured original selection…","正在读取已捕获的原选择…")
        case .loaded: language.text("Formal records read.","正式记录读取完成。")
        case .missing: language.text("No visible structured Trip for this ID.","此ID没有可见的结构化行程。")
        case .unavailable: language.text("Read unavailable. No empty result or older selection is substituted.","读取不可用，不以空结果或旧选择替代。")
        }
    }
}
#endif
