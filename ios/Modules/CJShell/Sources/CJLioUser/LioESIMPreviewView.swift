#if os(iOS) && DEBUG
import SwiftUI

struct LioESIMPreviewView: View {
    let language: LioLanguage
    @State private var coverage = Coverage.mainland
    @State private var tripDays = 7
    @State private var handoff: Plan?

    private enum Coverage: CaseIterable, Hashable {
        case mainland, hongKong, macao, regional

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .mainland: language.text("Mainland China", "中国大陆")
            case .hongKong: language.text("Hong Kong", "香港")
            case .macao: language.text("Macao", "澳门")
            case .regional: language.text("Mainland China, Hong Kong & Macao", "中国大陆、香港及澳门")
            }
        }
    }

    private struct Plan: Identifiable {
        let days: Int
        let gigabytes: Int
        let sampleUSD: Int
        var id: Int { days }
    }

    private var plans: [Plan] {
        let regionalExtra = coverage == .regional ? 5 : 0
        return [
            Plan(days: 7, gigabytes: 3, sampleUSD: 9 + regionalExtra),
            Plan(days: 15, gigabytes: 5, sampleUSD: 15 + regionalExtra),
            Plan(days: 30, gigabytes: 10, sampleUSD: 24 + regionalExtra),
        ]
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text(language.text("Sample plans and prices", "示例套餐及价格")).font(.footnote)
                menu
                Stepper(language.text("Travel days", "旅行天数") + " · \(tripDays)",
                        value: $tripDays, in: 1...60)
                    .frame(minHeight: 44)
                let recommended = plans.first { $0.days >= tripDays }?.id
                ForEach(plans) { plan in card(plan, recommended: plan.id == recommended) }
                NavigationLink {
                    installGuide
                } label: {
                    Label(language.text("Install an eSIM", "安装 eSIM"), systemImage: "esim")
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                }
                .buttonStyle(.plain)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("eSIM", "上网卡"))
        .navigationBarTitleDisplayMode(.inline)
        .alert(language.text("Airalo handoff", "前往 Airalo"), isPresented: Binding(
            get: { handoff != nil }, set: { if !$0 { handoff = nil } }
        )) {
            Button(language.text("Done", "完成"), role: .cancel) { handoff = nil }
        } message: {
            Text(language.text("This sample has no checkout link.", "示例套餐没有购买链接。"))
        }
    }

    private var menu: some View {
        Menu {
            ForEach(Coverage.allCases, id: \.self) { option in
                Button(option.title(language)) { coverage = option }
            }
        } label: {
            Label(coverage.title(language), systemImage: "chevron.down")
                .frame(minWidth: 44, minHeight: 44)
        }
    }

    private func card(_ plan: Plan, recommended: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(language.text("\(plan.days) days · \(plan.gigabytes) GB", "\(plan.days) 天 · \(plan.gigabytes) GB")).font(.headline)
            Text("USD \(plan.sampleUSD)")
            if recommended {
                Text(language.text("Fits your trip length", "符合旅行天数"))
            }
            Text(language.text("Check the plan for hotspot and identity requirements.", "热点和实名要求以购买页为准。"))
                .font(.subheadline)
            Button(language.text("View on Airalo", "在 Airalo 查看")) { handoff = plan }
                .buttonStyle(.plain)
                .frame(minHeight: 44)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private var installGuide: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                guide("iphone", language.text("Check compatibility", "先核对设备"),
                      language.text("Confirm that your iPhone model and sales region support eSIM and that the phone is carrier-unlocked.",
                                    "确认 iPhone 机型及销售地区支持 eSIM，并确认没有运营商锁。"))
                guide("qrcode", language.text("Install over Wi-Fi", "连接无线网络后安装"),
                      language.text("Follow the steps for your plan in Airalo. If it provides a QR code, open Settings → Cellular → Add eSIM.",
                                    "打开 Airalo 按套餐说明操作。如提供二维码，打开设置 → 蜂窝网络 → 添加 eSIM。"))
                guide("antenna.radiowaves.left.and.right", language.text("Switch your data line", "切换数据卡"),
                      language.text("Select the eSIM for cellular data. Set roaming and APN as your plan instructs.",
                                    "把这张 eSIM 设为蜂窝数据卡，按套餐说明设置漫游和 APN。"))
                guide("globe", language.text("Using data in China", "在中国使用数据"),
                      language.text("Check the China coverage and activation terms for your exact plan. Coverage applies while using that eSIM for data.",
                                    "核对所选套餐的中国覆盖和生效条款。请使用所选 eSIM 的数据线路。"))
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Install an eSIM", "安装 eSIM"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func guide(_ icon: String, _ title: String, _ instructions: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: icon).font(.headline)
            Text(instructions)
        }
    }
}
#Preview {
    NavigationStack {
        LioESIMPreviewView(language: .english)
    }
}
#endif
