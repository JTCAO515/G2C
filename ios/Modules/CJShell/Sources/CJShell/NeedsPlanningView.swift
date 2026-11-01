#if os(iOS)
import SwiftUI
import CJManualPreviewClient
import CJTripClient
import CJRunClient

struct NeedsPlanningView:View {
    let host:NeedsPlanningHost
    let messages:AssistantMessageHost
    let language:ShellLanguage
    private var originalMessageID:String? { messages.captureAcceptedRunReceipt()?.planningSource?.receipt.message_id }
    var body:some View {
        VStack(alignment:.leading,spacing:14) {
            RunReadableText(text:language.text("Planning candidate","规划候选"),style:.headline)
            command("planning.discover",language.text("Read this original message's planning result","读取此原消息的规划结果"),disabled:host.busy || originalMessageID==nil) {
                if let work=host.prepareDiscovery() { Task { await work() } }
            }
            if let read=host.read {
                RunReadableText(text:state(read.value.state)).accessibilityIdentifier("planning.discovery.state")
                if let candidate=read.value.candidate {
                    detail(candidate,discovery:read.value)
                    let choose=candidate.status=="pending" && candidate.expiresAt>Int64(Date().timeIntervalSince1970) && !host.busy && host.actionID==nil
                    command("planning.accept",language.text("Accept this exact new plan","采用这份确切的新规划"),disabled:!choose) {
                        if let work=host.prepareDecision(.accept,read:read) { Task { await work() } }
                    }
                    command("planning.reject",language.text("Reject this planning candidate","拒绝这份规划候选"),disabled:!choose) {
                        if let work=host.prepareDecision(.reject,read:read) { Task { await work() } }
                    }
                }
            } else if let original=host.actions.first(where:{$0.actionID==host.actionID}) {
                detail(original.candidate,discovery:original.discovery)
            }
            RunReadableText(text:activity).accessibilityIdentifier("planning.activity")
            if let id=host.actionID { RunSelectableText(text:id).accessibilityIdentifier("planning.action.id") }
            if let receipt=host.receipt {
                RunReadableText(text:receipt.kind == .accept
                    ? language.text("Original acceptance confirmed. This is a historical commit.","原采用动作已确认；这是历史提交。")
                    : language.text("Original rejection confirmed. This action created no formal plan.","原拒绝动作已确认；本动作未创建正式规划。"))
                    .accessibilityIdentifier("planning.receipt")
                if let version=receipt.committedVersion {
                    RunReadableText(text:language.text("Committed version ","已提交版本 ")+String(version)).accessibilityIdentifier("planning.receipt.version")
                }
            }
            if let formal=host.formal {
                RunReadableText(text:language.text("Current formal read: ","当前正式读回：")+formal.tripID+" · "+String(formal.version)).accessibilityIdentifier("planning.formal.version")
                StructuredTripDocumentView(document:formal.document,language:language,prefix:"planning.formal")
            }
            if host.formalUnavailable {
                RunReadableText(text:language.text("Acceptance confirmed; current formal read is unavailable. Keep the original receipt.","采用已确认；当前正式读回不可用，请保留原回执。"))
            }
            command("planning.originals",language.text("Read earlier planning actions","读取此前规划动作"),disabled:host.busy) { host.loadOriginals() }
            ForEach(host.actions) { original in
                command("planning.query."+original.actionID,language.text("Check original ","核对原动作 ")+original.actionID,disabled:host.busy) {
                    if let work=host.prepareQuery(original.actionID) { Task { await work() } }
                }
            }
            RunReadableText(text:language.text("Reads never plan again. UNKNOWN keeps the original action for read-only reconciliation.","读取不会重新规划。UNKNOWN 保留原动作，仅只读核对。"),style:.caption)
        }.accessibilityElement(children:.contain).accessibilityIdentifier("planning.candidate")
            .onChange(of:originalMessageID) { _,_ in host.clearSelection() }
    }
    private func detail(_ candidate:NeedsPlanningCandidate,discovery:NeedsPlanningDiscovery) -> some View {
        VStack(alignment:.leading,spacing:10) {
            RunReadableText(text:language.text("Unaccepted new plan · ","未采用的新规划 · ")+candidate.status).accessibilityIdentifier("planning.candidate.status")
            RunReadableText(text:language.text("Requirements ","需求 ")+discovery.needsID!+" · "+String(discovery.needsVersion!)).accessibilityIdentifier("planning.needs")
            if case .travel(let reference)=discovery.reference {
                RunReadableText(text:language.text("Original travel context ","原旅行上下文 ")+reference.context_id).accessibilityIdentifier("planning.namespace")
            }
            if let context=discovery.context {
                RunReadableText(text:language.text("Based on source plan ","基于来源行程 ")+context.tripID+" · "+String(context.version)).accessibilityIdentifier("planning.context")
                RunReadableText(text:context.contentSHA256,style:.caption).accessibilityIdentifier("planning.context.hash")
            }
            RunReadableText(text:language.text("Accepting creates and selects the proposed new Trip. It does not edit the source Trip in place.","采用将创建并选中候选的新行程，不会原地修改来源行程。"),style:.caption)
            StructuredTripDocumentView(document:candidate.content,language:language,prefix:"planning.proposal")
        }
    }
    private func command(_ id:String,_ title:String,disabled:Bool,action:@escaping()->Void) -> some View {
        Button(action:action) { RunReadableText(text:title).frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle()) }
            .buttonStyle(ShellReadableButtonStyle()).disabled(disabled).accessibilityIdentifier(id)
    }
    private func state(_ value:ScopedDiscoveryState) -> String {
        switch value {
        case .published:language.text("Original planning candidate recorded · not a formal Trip","原规划候选已记录 · 尚非正式行程")
        case .notRequested:language.text("This original message requested no plan","此原消息未请求规划")
        case .pending:language.text("Original run pending","原运行尚未完成")
        case .noCandidate:language.text("Original run produced no candidate","原运行未生成候选")
        case .unknown:language.text("UNKNOWN · reconcile the original only","UNKNOWN · 仅核对原动作")
        case .unavailable:language.text("Original result unavailable","原结果不可用")
        }
    }
    private var activity:String {
        switch host.activity {
        case .idle:language.text("Choose an accepted original message","请选择已接受的原消息")
        case .reading:language.text("Reading the original","正在读取原记录")
        case .deciding:language.text("Submitting the original decision","正在提交原选择")
        case .ready:language.text("Original result read","已读取原结果")
        case .unknown:language.text("UNKNOWN · query the original","UNKNOWN · 请查询原动作")
        case .conflict:language.text("Conflict · original input retained","冲突 · 原输入已保留")
        case .unavailable:language.text("Original read unavailable; do not plan again","原读取不可用；请勿重新规划")
        }
    }
}
#endif
