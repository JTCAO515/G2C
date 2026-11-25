#if os(iOS)
import CJRunClient
import SwiftUI

private struct LioCloseMemoryKey: EnvironmentKey {
    static let defaultValue: (@MainActor () -> Void)? = nil
}

public extension EnvironmentValues {
    /// Set when the memory page is presented from Me; the page shows Done on its root and calls this.
    var lioCloseMemory: (@MainActor () -> Void)? {
        get { self[LioCloseMemoryKey.self] }
        set { self[LioCloseMemoryKey.self] = newValue }
    }
}

/// The "Me" tab (#1452): profile, saved memory, subscription preview, settings and account, help.
/// Settings and account rows come from the host (`menu`), so the tab adds no new account actions.
struct LioMeView<Menu: View>: View {
    let language: LioLanguage
    let memory: AnyView?
    let menu: Menu
    @State private var showingMemory = false

    var body: some View {
        NavigationStack {
            List {
                Section { header }
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets())
                Section {
                    // The memory page owns its NavigationStack (it was a tab root), so it is presented on its
                    // own instead of being pushed into this stack: no stack inside a stack (#1458 review).
                    Button { showingMemory = true } label: {
                        HStack {
                            row(language.text("My memory", "我的记忆"), symbol: "bookmark",
                                detail: language.text("What Lio remembers about you", "Lio 记住的你的偏好"))
                            Spacer(minLength: 8)
                            Image(systemName: "chevron.forward").font(.footnote.weight(.semibold))
                                .foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.me.memory")
                    NavigationLink {
                        LioProfilePreview(language: language)
                    } label: {
                        row(language.text("Profile", "个人信息"), symbol: "person.text.rectangle",
                            detail: language.text("Name, home country, travel style", "称呼、常住国家、出行偏好"))
                    }
                    .accessibilityIdentifier("lio.me.profile")
                }
                .lioRow()
                Section {
                    NavigationLink {
                        LioSubscriptionView(language: language)
                    } label: {
                        HStack(spacing: 12) {
                            icon("sparkles", tint: LioTheme.onVermilion, background: LioTheme.vermilion)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(language.text("Go2China plans", "Go2China 会员")).font(.headline)
                                Text(language.text("Coming soon · free during the beta", "即将推出 · 内测期间免费"))
                                    .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                            }
                        }
                        .frame(minHeight: 52)
                    }
                    .accessibilityIdentifier("lio.me.subscription")
                }
                .lioRow()
                Section(language.text("Settings and account", "设置与账号")) {
                    menu
                }
                .lioRow()
                Section(language.text("Help and feedback", "帮助与反馈")) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(language.text("Report a problem", "反馈问题")).font(.body)
                        Text(language.text("Share a screenshot, the copied issue record and the time in the internal testing group.",
                                           "在内部测试群发截图、问题记录和发生时间。"))
                            .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    }
                    .padding(.vertical, 4)
                }
                .lioRow()
            }
            .lioPage()
            .navigationTitle(language.text("Me", "我的"))
            .toolbarBackground(LioTheme.paper, for: .navigationBar)
        }
        .tint(LioTheme.vermilion)
        .sheet(isPresented: $showingMemory) { memorySheet }
    }

    /// The memory page keeps its own NavigationStack and puts Done in its own navigation bar (via
    /// `lioCloseMemory`), so nothing covers its back or keyboard Done buttons (#1489 follow-up).
    @ViewBuilder private var memorySheet: some View {
        if let memory {
            memory.environment(\.lioCloseMemory) { showingMemory = false }
        } else {
            NavigationStack {
                unavailable
                    .toolbar {
                        ToolbarItem(placement: .confirmationAction) {
                            Button { showingMemory = false } label: {
                                RunReadableText(text: language.text("Done", "完成"), color: LioTheme.vermilion)
                                    .fixedSize()
                                    .frame(minHeight: 44)
                            }
                            .accessibilityLabel(language.text("Done", "完成"))
                            .accessibilityIdentifier("lio.me.memory.done")
                        }
                    }
            }
            .tint(LioTheme.vermilion)
        }
    }

    private var header: some View {
        HStack(spacing: LioTheme.Spacing.sm) {
            Text("G")
                .font(LioTheme.display(.title).weight(.bold))
                .foregroundStyle(LioTheme.onVermilion)
                .frame(width: 60, height: 60)
                .background(LioTheme.vermilion, in: Circle())
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(language.text("Traveller", "旅行者")).font(LioTheme.display(.title2).weight(.semibold))
                Text(language.text("Internal tester", "内部测试账号"))
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(LioTheme.jade)
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    // Jade text on the plain surface keeps WCAG AA contrast; a tinted fill fell just short.
                    .background(LioTheme.surface, in: Capsule())
                    .overlay { Capsule().stroke(LioTheme.jade.opacity(0.5), lineWidth: 1) }
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, LioTheme.Spacing.sm)
    }

    private var unavailable: some View {
        Text(language.text("Nothing saved yet.", "还没有记住的内容。"))
            .foregroundStyle(LioTheme.inkSecondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(LioTheme.paper)
    }

    private func row(_ title: String, symbol: String, detail: String) -> some View {
        HStack(spacing: 12) {
            icon(symbol, tint: LioTheme.vermilion, background: LioTheme.surfaceSunken)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body)
                Text(detail).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
            }
        }
        .frame(minHeight: 52)
    }

    private func icon(_ symbol: String, tint: Color, background: Color) -> some View {
        Image(systemName: symbol)
            .font(.body.weight(.semibold))
            .foregroundStyle(tint)
            .frame(width: 36, height: 36)
            .background(background, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
            .accessibilityHidden(true)
    }
}

/// Profile page proposal: fields gathered from saved memory, editable later.
private struct LioProfilePreview: View {
    let language: LioLanguage

    var body: some View {
        List {
            Section {
                field(language.text("What Lio calls you", "称呼"), language.text("Not set", "未设置"))
                field(language.text("Home country", "常住国家"), language.text("Not set", "未设置"))
                field(language.text("Languages", "语言"), language.text("English", "中文"))
                field(language.text("Food and travel style", "饮食与出行偏好"),
                      language.text("From your memory", "来自「我的记忆」"))
            } footer: {
                Text(language.text("Lio fills these in from what you tell it. You can change or clear them any time.",
                                   "Lio 会根据你说过的内容整理这些信息，你可以随时修改或清除。"))
            }
            .lioRow()
        }
        .lioPage()
        .navigationTitle(language.text("Profile", "个人信息"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func field(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title)
            Spacer(minLength: 8)
            Text(value).foregroundStyle(LioTheme.inkSecondary)
        }
        .frame(minHeight: 44)
    }
}

/// Plans preview only: no purchase button is enabled and nothing talks to StoreKit.
struct LioSubscriptionView: View {
    let language: LioLanguage

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                Text(language.text("Everything is free during the internal beta. Plans below are a preview and can't be bought yet.",
                                   "内测期间全部功能免费。以下会员方案仅供预览，暂不能购买，也不会扣费。"))
                    .font(.subheadline)
                    .foregroundStyle(LioTheme.inkSecondary)
                ForEach(LioSubscriptionPlans.plans) { plan in planCard(plan) }
                comparison
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Go2China plans", "Go2China 会员"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func planCard(_ plan: LioSubscriptionPlans.Plan) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            HStack(alignment: .firstTextBaseline) {
                Text(language.text(plan.nameEN, plan.nameZH)).font(LioTheme.display(.title2).weight(.bold))
                if plan.highlighted {
                    Text(language.text("Popular", "推荐"))
                        .font(.caption.weight(.semibold))
                        .lineLimit(1)
                        .fixedSize()
                        .foregroundStyle(LioTheme.onVermilion)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(LioTheme.vermilion, in: Capsule())
                }
                Spacer(minLength: 8)
                Text(plan.priceText).font(.title2.weight(.semibold)).monospacedDigit()
                Text(language.text("/ month", "/ 月")).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
            }
            Button(language.text("Coming soon", "即将推出")) {}
                .buttonStyle(LioSecondaryButtonStyle())
                .disabled(true)
                .accessibilityIdentifier("lio.subscription.\(plan.id)")
        }
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .overlay {
            if plan.highlighted {
                RoundedRectangle(cornerRadius: LioTheme.Radius.card).stroke(LioTheme.vermilion, lineWidth: 1.5)
            }
        }
    }

    private var comparison: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(language.text("Compare plans", "权益对比")).font(.headline).padding(.bottom, LioTheme.Spacing.xs)
            HStack {
                Spacer(minLength: 0).frame(maxWidth: .infinity)
                ForEach(LioSubscriptionPlans.plans) { plan in
                    Text(language.text(plan.nameEN, plan.nameZH)).font(.footnote.weight(.semibold))
                        .lineLimit(1).minimumScaleFactor(0.75)
                        .frame(width: 74)
                }
            }
            .padding(.vertical, 6)
            ForEach(LioSubscriptionPlans.benefits) { benefit in
                Divider().overlay(LioTheme.hairline)
                HStack {
                    Text(language.text(benefit.en, benefit.zh)).font(.subheadline)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    ForEach(Array(benefit.values.enumerated()), id: \.offset) { _, value in
                        cell(value).frame(width: 74)
                    }
                }
                .padding(.vertical, 8)
            }
            Text(language.text("Draft benefits. Final plans and prices will be announced before any charge.",
                               "权益为草案。正式方案与价格会在收费前另行公布。"))
                .font(.footnote).foregroundStyle(LioTheme.inkSecondary).padding(.top, LioTheme.Spacing.xs)
        }
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    @ViewBuilder private func cell(_ value: LioSubscriptionPlans.Benefit.Value) -> some View {
        switch value {
        case .included:
            Image(systemName: "checkmark").foregroundStyle(LioTheme.jade)
                .accessibilityLabel(language.text("Included", "包含"))
        case .excluded:
            Text("—").foregroundStyle(LioTheme.inkSecondary)
                .accessibilityLabel(language.text("Not included", "不包含"))
        case .text(let en, let zh):
            Text(language.text(en, zh)).font(.caption).multilineTextAlignment(.center)
        }
    }
}
#endif
