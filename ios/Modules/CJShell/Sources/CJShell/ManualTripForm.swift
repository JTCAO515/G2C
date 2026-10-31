#if os(iOS)
import SwiftUI
import CJTripClient
import CJRunClient

struct ManualTripForm: View {
    let draft: ManualTripDraft
    let language: ShellLanguage
    let change: (ManualTripDraft)->Void
    @State private var issue: String?
    private var order: [String] { draft.order ?? draft.original.document.items.map(\.id) }
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            RunReadableText(text:language.text("Editing basis ","编辑基准 ")+String(draft.original.version)).accessibilityIdentifier("trip.manual.input.basis")
            Toggle(language.text("Select title change","选中标题修改"),isOn:Binding(get:{draft.title != nil},set:{ selected in edit { $0.setTitle(selected ? draft.original.document.title : nil) } }))
                .accessibilityIdentifier("trip.manual.title.selected")
            if let title=draft.title {
                TextField(language.text("New title","新标题"),text:Binding(get:{title},set:{value in edit { $0.setTitle(value) } }),axis:.vertical)
                    .lineLimit(1...4).textFieldStyle(.roundedBorder).accessibilityIdentifier("trip.manual.title.value")
            }
            RunReadableText(text:language.text("Select every moved item before reordering. Unknown/locked protection cannot be treated as unlocked. Lock changes are separate from text/time edits.","重排前请选中所有移动项。保护未知或已固定不等于未固定。固定状态须与文字／时间修改分开提交。"),style:.caption)
            ForEach(order,id:\.self) { id in
                let item=draft.original.document.items.first { $0.id==id }!
                let selected=draft.selectedIDs.contains(id), contentAllowed=selected && item.fixed == .known(false) && draft.fixed[id] == nil
                DisclosureGroup {
                    Toggle(language.text("Select this item","选中此条目"),isOn:Binding(get:{selected},set:{value in edit { try $0.selectItem(id,selected:value) } }))
                        .accessibilityIdentifier("trip.manual.selected."+id)
                    Toggle(language.text("Change text","修改文字"),isOn:Binding(get:{draft.texts[id] != nil},set:{value in
                        edit { if value { try $0.setText(item.text,itemID:id) } else { try $0.leaveUnchanged(.text,itemID:id) } }
                    })).disabled(!contentAllowed).accessibilityIdentifier("trip.manual.text.selected."+id)
                    if let text=draft.texts[id] {
                        TextField(language.text("Explicit new text","明确的新文字"),text:Binding(get:{text},set:{value in edit { try $0.setText(value,itemID:id) } }),axis:.vertical)
                            .lineLimit(1...4).textFieldStyle(.roundedBorder).disabled(!contentAllowed).accessibilityIdentifier("trip.manual.text.value."+id)
                    }
                    Toggle(language.text("Change explicit schedule","修改明确的起止观察"),isOn:Binding(get:{draft.schedules[id] != nil},set:{value in
                        edit { if value { try $0.setSchedule(.init(item:item),itemID:id) } else { try $0.leaveUnchanged(.schedule,itemID:id) } }
                    })).disabled(!contentAllowed).accessibilityIdentifier("trip.manual.schedule.selected."+id)
                    if let schedule=draft.schedules[id] {
                        RunReadableText(text:language.text("Start","开始"),style:.headline)
                        ManualTripEventForm(value:schedule.start,language:language,prefix:"trip.manual.start."+id,change:{ value in
                            var next=schedule;next.start=value;edit { try $0.setSchedule(next,itemID:id) }
                        }).disabled(!contentAllowed)
                        RunReadableText(text:language.text("End","结束"),style:.headline)
                        ManualTripEventForm(value:schedule.end,language:language,prefix:"trip.manual.end."+id,change:{ value in
                            var next=schedule;next.end=value;edit { try $0.setSchedule(next,itemID:id) }
                        }).disabled(!contentAllowed)
                    }
                    let lockAllowed=selected && draft.texts[id] == nil && draft.schedules[id] == nil
                    rowButton("trip.manual.fixed.true."+id,language.text("Explicitly fix this item","明确固定此条目"),disabled:!lockAllowed) { edit { try $0.setFixed(true,itemID:id) } }
                    rowButton("trip.manual.fixed.false."+id,language.text("Explicitly unlock this item","明确取消固定此条目"),disabled:!lockAllowed) { edit { try $0.setFixed(false,itemID:id) } }
                    if let lock=draft.fixed[id] {
                        RunReadableText(text:lock ? language.text("Selected change: fixed","选定改动：固定") : language.text("Selected change: unlocked","选定改动：取消固定"))
                            .accessibilityIdentifier("trip.manual.fixed.input."+id)
                        rowButton("trip.manual.fixed.clear."+id,language.text("Leave protection unchanged","不修改保护状态")) { edit { try $0.leaveUnchanged(.fixed,itemID:id) } }
                    }
                    rowButton("trip.manual.up."+id,language.text("Move up","上移"),disabled:!selected || item.fixed != .known(false)) { move(id,-1) }
                    rowButton("trip.manual.down."+id,language.text("Move down","下移"),disabled:!selected || item.fixed != .known(false)) { move(id,1) }
                } label: { Text(item.id+" · "+item.text).fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("trip.manual.item.open."+id) }
            }
            if draft.order != nil {
                rowButton("trip.manual.order.clear",language.text("Keep the original order","保留原顺序")) { edit { try $0.setOrder(nil) } }
            }
            if let issue { RunReadableText(text:issue).accessibilityIdentifier("trip.manual.input.issue") }
        }
    }
    private func edit(_ body:(inout ManualTripDraft)throws->Void) {
        var next=draft
        do { try body(&next);issue=nil;change(next) }
        catch { issue=language.text("This choice touches unselected or protected content, or mixes lock and content edits. Input is retained.","此选择触及未选中或受保护的内容，或混合了固定和内容修改。输入已保留。") }
    }
    private func move(_ id: String,_ offset: Int) {
        let index=order.firstIndex(of:id)!, target=index+offset
        guard order.indices.contains(target) else { return }
        var next=order;next.swapAt(index,target);edit { try $0.setOrder(next) }
    }
    private func rowButton(_ id:String,_ title:String,disabled:Bool=false,action:@escaping()->Void) -> some View {
        Button(action:action) { RunReadableText(text:title).frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle()) }
            .buttonStyle(ShellReadableButtonStyle()).disabled(disabled).accessibilityIdentifier(id)
    }
}

private struct ManualTripEventForm: View {
    let value: ManualTripEventInput
    let language: ShellLanguage
    let prefix: String
    let change: (ManualTripEventInput)->Void
    var body: some View {
        VStack(alignment:.leading,spacing:10) {
            control("date",language.text("Date YYYY-MM-DD","日期 YYYY-MM-DD"),\.date)
            control("time",language.text("Local time · preserve minute/second precision","当地时间 · 保留分／秒精度"),\.time)
            control("timezone",language.text("Explicit IANA timezone","明确的 IANA 时区"),\.timezone)
            control("offset",language.text("Explicit offset ±HH:MM","明确偏移 ±HH:MM"),\.utcOffset)
        }
    }
    private func control(_ id:String,_ label:String,_ path:WritableKeyPath<ManualTripEventInput,TripObservation<String>>) -> some View {
        ManualTripObservationForm(value:value[keyPath:path],label:label,language:language,prefix:prefix+"."+id,change:{ field in
            var next=value;next[keyPath:path]=field;change(next)
        })
    }
}
private struct ManualTripObservationForm: View {
    let value: TripObservation<String>
    let label: String
    let language: ShellLanguage
    let prefix: String
    let change: (TripObservation<String>)->Void
    private enum State: String,CaseIterable { case known,missing,unknown,uncertain }
    private var state: State {
        switch value { case .known: .known;case .missing: .missing;case .unknown: .unknown;case .uncertain: .uncertain }
    }
    var body: some View {
        VStack(alignment:.leading,spacing:6) {
            RunReadableText(text:label)
            Picker(language.text("Observation state","观察状态"),selection:Binding(get:{state},set:setState)) {
                ForEach(State.allCases,id:\.self) { value in Text(stateLabel(value)).tag(value) }
            }.accessibilityIdentifier(prefix+".state")
            switch value {
            case .known(let text):
                TextField(label,text:Binding(get:{text},set:{change(.known($0))})).textFieldStyle(.roundedBorder).accessibilityIdentifier(prefix+".value")
            case .uncertain(let note):
                TextField(language.text("Uncertainty note","不确定说明"),text:Binding(get:{note},set:{change(.uncertain($0))}),axis:.vertical)
                    .lineLimit(1...4).textFieldStyle(.roundedBorder).accessibilityIdentifier(prefix+".note")
            case .missing,.unknown: RunReadableText(text:stateLabel(state),style:.caption)
            }
        }
    }
    private func setState(_ next: State) {
        switch next {
        case .known: if case .known(let text)=value { change(.known(text)) } else { change(.known("")) }
        case .uncertain: if case .uncertain(let note)=value { change(.uncertain(note)) } else { change(.uncertain("")) }
        case .missing: change(.missing)
        case .unknown: change(.unknown)
        }
    }
    private func stateLabel(_ value:State) -> String {
        switch value {
        case .known: language.text("Explicit value","明确值")
        case .missing: language.text("Explicitly missing","明确缺失")
        case .unknown: language.text("Unknown","未知")
        case .uncertain: language.text("Uncertain","不确定")
        }
    }
}
#endif
