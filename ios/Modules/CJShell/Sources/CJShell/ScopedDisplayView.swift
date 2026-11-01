#if os(iOS)
import SwiftUI
import CJManualPreviewClient
import CJRunClient

struct ScopedDisplayView:View {
    let host:ScopedDisplayHost
    let runs:RunContainerHost
    let language:ShellLanguage
    let chooseAgain:()->Void
    var body:some View {
        VStack(alignment:.leading,spacing:14) {
            RunReadableText(text:language.text("Original scope result","原范围结果"),style:.headline)
            Button { if let work=host.prepareRead() { Task { await work() } } } label: {
                RunReadableText(text:language.text("Read this original result","读取此原结果")).frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle())
            }.buttonStyle(ShellReadableButtonStyle()).disabled(!host.canRead).accessibilityIdentifier("scope.result.read")
            RunReadableText(text:activity).accessibilityIdentifier("scope.result.activity")
            if let read=host.read {
                let value=read.value
                RunReadableText(text:language.text("Original version ","原版本 ")+String(value.expectedVersion)+language.text(" · current version "," · 当前版本 ")+String(value.currentVersion)).accessibilityIdentifier("scope.result.versions")
                if value.state == .stale {
                    RunReadableText(text:language.text("The Trip changed. This old result cannot be used; read the current Trip and choose again.","行程已变化；此旧结果不可继续使用，请读取当前行程并重新选择。")).accessibilityIdentifier("scope.result.stale")
                } else if let result=value.result {
                    RunReadableText(text:result.kind == .clarificationRequired ? language.text("Clarification needed","需要澄清") : language.text("A wider selection is needed","需要扩大选区")).accessibilityIdentifier("scope.result.kind")
                    RunReadableText(text:language == .english ? result.explanation.english : result.explanation.chinese).accessibilityIdentifier("scope.result.reason")
                    if !result.explanation.outsideItemIDs.isEmpty {
                        RunReadableText(text:language.text("Outside the original selection: ","超出原选区的条目：")+result.explanation.outsideItemIDs.joined(separator:", ")).accessibilityIdentifier("scope.result.outside.items")
                    }
                    if !result.explanation.outsideDates.isEmpty {
                        RunReadableText(text:language.text("Outside the original dates: ","超出原日期：")+result.explanation.outsideDates.joined(separator:", ")).accessibilityIdentifier("scope.result.outside.dates")
                    }
                    ForEach(Array(result.explanation.changes.enumerated()),id:\.offset) { index,change in
                        VStack(alignment:.leading,spacing:8) {
                            RunReadableText(text:(change.itemID.map {$0+" · "} ?? "")+field(change.field),style:.headline)
                            RunReadableText(text:language.text("Before","修改前"),style:.caption)
                            RunSelectableText(text:language == .english ? change.beforeEnglish : change.beforeChinese).accessibilityIdentifier("scope.result.change.before."+String(index))
                            RunReadableText(text:language.text("Requested change · not committed","请求的变化 · 尚未提交"),style:.caption)
                            RunSelectableText(text:language == .english ? change.afterEnglish : change.afterChinese).accessibilityIdentifier("scope.result.change.after."+String(index))
                        }
                    }
                    if let required=result.explanation.requiredSelection {
                        RunReadableText(text:language.text("Required items: ","所需条目：")+required.itemIDs.joined(separator:", ")).accessibilityIdentifier("scope.result.required.items")
                        RunReadableText(text:language.text("Declared dates: ","已声明日期：")+required.dates.known.joined(separator:", ")+(required.dates.incomplete ? " · UNKNOWN" : "")).accessibilityIdentifier("scope.result.required.dates")
                        if !required.localSelectionSufficient {
                            RunReadableText(text:language.text("A whole-Trip title change is not authorized by this local selector. Keep the Trip or use the explicit manual title editor.","整份行程标题不能由当前局部选区授权修改。请保留行程，或使用明确的手动标题编辑。")).accessibilityIdentifier("scope.result.whole.trip")
                        }
                    } else {
                        if let facts=result.explanation.facts {
                            RunReadableText(text:language.text("Items with unknown dates: ","日期未知的条目：")+facts.unknownDateItemIDs.joined(separator:", ")).accessibilityIdentifier("scope.result.unknown.items")
                            RunReadableText(text:language.text("Cross-day items: ","跨日条目：")+facts.crossDayItemIDs.joined(separator:", ")).accessibilityIdentifier("scope.result.cross.day")
                            RunReadableText(text:language.text("Unmatched declared dates: ","未匹配的明确日期：")+facts.unmatchedDates.joined(separator:", ")).accessibilityIdentifier("scope.result.unmatched.dates")
                            RunReadableText(text:language.text("Observed dates: ","观测到的日期：")+facts.observedDates.known.joined(separator:", ")+(facts.observedDates.incomplete ? " · UNKNOWN" : "")).accessibilityIdentifier("scope.result.observed.dates")
                        }
                        RunReadableText(text:language.text("No replacement selection was inferred. Unknown dates remain UNKNOWN.","未推断替代选区；未知日期仍为 UNKNOWN。")).accessibilityIdentifier("scope.result.no.inferred.scope")
                    }
                    if let report=result.feasibility {
                        RunReadableText(text:language.text("Feasibility: ","可行性：")+report.status).accessibilityIdentifier("scope.result.feasibility")
                        ForEach(Array(report.checks.enumerated()),id:\.offset) { _,check in RunReadableText(text:language == .english ? check.english : check.chinese) }
                        RunReadableText(text:language == .english ? report.english : report.chinese)
                    }
                    Button { host.keepOriginal() } label: { RunReadableText(text:language.text("Keep the original Trip","保留原行程")).frame(maxWidth:.infinity,minHeight:44,alignment:.leading) }
                        .buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("scope.result.keep.original")
                }
                Button(action:chooseAgain) { RunReadableText(text:language.text("Open the current Trip and choose a new scope","查看当前行程并明确新范围")).frame(maxWidth:.infinity,minHeight:44,alignment:.leading) }
                    .buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("scope.result.choose.again")
            }
            RunReadableText(text:language.text("This result is not a candidate and cannot be accepted. A change needs a new explicit selection and message; reading never plans again.","此结果不是候选，不能接受。修改需要你明确新选区并发送新请求；读取不会重新规划。"),style:.caption)
        }.accessibilityElement(children:.contain).accessibilityIdentifier("scope.result")
            .onChange(of:runs.originalPresentationID) { _,_ in host.clearSelection() }
    }
    private var activity:String {
        switch host.activity {
        case .idle:language.text("Read the original run first","请先读取原运行")
        case .reading:language.text("Reading the protected original result…","正在读取受保护的原结果…")
        case .ready:language.text("Original result read; no Trip write","已读取原结果，未写入行程")
        case .unavailable:language.text("Original result unavailable; keep the original IDs and do not send again automatically","原结果暂不可用；保留原记录，不自动重发")
        case .keptOriginal:language.text("Original Trip kept. No action was sent.","已保留原行程，未发送任何接受或拒绝动作。")
        }
    }
    private func field(_ value:String)->String {
        switch value { case "text":language.text("Item text","条目文字");case "schedule":language.text("Time observations","时间观察");case "order":language.text("Item order","条目顺序");default:language.text("Trip title","行程标题") }
    }
}
#endif
