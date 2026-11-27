#if os(iOS)
import SwiftUI

/// What is carried when a point is dragged: its id on this canvas, nothing else.
struct LioCanvasDragItem: Codable, Transferable {
    let pointID: String

    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .data)
    }
}

/// #1995 (T-2): the trip canvas screen behind `G2CTripCanvasEnabled`. It reads the canvas model on first show, so the
/// trip home's frequent redraws never reread the file.
struct LioTripCanvasScreen: View {
    let language: LioLanguage
    /// The trip this canvas follows (the saved plan); nil shows a canvas of its own with only "want to go" and days to add.
    let plan: LioPlanSummary?
    let store: LioTripCanvasStore?
    var openChat: (() -> Void)?
    /// The map view's place (#1996 / T-3). Nil shows a placeholder where it will go; the timeline never depends on it.
    var map: ((LioTripCanvas) -> AnyView)?
    @State private var model: LioTripCanvasModel?

    var body: some View {
        Group {
            if let model {
                LioTripCanvasView(language: language, model: model, openChat: openChat, map: map)
            } else {
                LioTheme.paper.ignoresSafeArea()
            }
        }
        .task {
            if model == nil { model = LioTripCanvasModel(plan: plan, store: store) }
        }
    }
}

/// The trip as days of points, one row each, with a thumbnail (a placeholder for now), the time, and the way to the next
/// point. A row can be dragged to another place in its day, to another day, or into "want to go", or moved with its menu
/// (the same moves, without dragging). Deleting and every move can be undone from the bar at the bottom.
struct LioTripCanvasView: View {
    enum Mode: Hashable { case timeline, map }

    let language: LioLanguage
    let model: LioTripCanvasModel
    var openChat: (() -> Void)?
    var map: ((LioTripCanvas) -> AnyView)?
    @State private var mode: Mode = .timeline
    @State private var editing: LioTripCanvas.Point?
    @State private var wish = ""
    /// The id of the row or card a drag is over, for its outline.
    @State private var targeted: String?
    @ScaledMetric(relativeTo: .body) private var thumbnailSize: CGFloat = 56
    @Environment(\.colorScheme) private var colorScheme

    private var canvas: LioTripCanvas { model.canvas }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                header
                modePicker
                switch mode {
                case .timeline: timeline
                case .map: mapSlot
                }
                if model.saveFailed {
                    Label(language.text("This change could not be saved on this phone.", "这次改动没能存到手机上。"),
                          systemImage: "exclamationmark.triangle")
                        .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                        .accessibilityIdentifier("lio.trip-canvas.save-failed")
                }
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .lioPage()
        .navigationTitle(language.text("Trip canvas", "行程画布"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .safeAreaInset(edge: .bottom) { undoBar }
        .sheet(item: $editing) { point in
            LioTripCanvasEditSheet(language: language, point: point) { name, time in
                model.edit(point.id, name: name, in: language, time: time)
            }
        }
        .accessibilityIdentifier("lio.trip-canvas")
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            Text(canvas.title.isEmpty ? language.text("Your China trip", "这趟中国之行") : canvas.title)
                .font(LioTheme.display(.title).weight(.bold))
                .foregroundStyle(LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text(summary)
                .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lio.trip-canvas.header")
    }

    private var summary: String {
        let days = canvas.days.count
        let placed = canvas.days.reduce(0) { $0 + $1.points.count }
        let line = language.text("\(days) days · \(placed) places", "\(days) 天 · \(placed) 个地点")
        let wishes = canvas.wishlist.count
        return wishes == 0 ? line : line + language.text(" · \(wishes) to go", " · 想去 \(wishes) 个")
    }

    /// Timeline and map. The map is T-3's; until it is wired the tab says so instead of doing nothing.
    private var modePicker: some View {
        Picker(language.text("View", "视图"), selection: $mode) {
            Text(language.text("Timeline", "时间线")).tag(Mode.timeline)
            Text(language.text("Map", "地图")).tag(Mode.map)
        }
        .pickerStyle(.segmented)
        .accessibilityIdentifier("lio.trip-canvas.mode")
    }

    @ViewBuilder private var mapSlot: some View {
        if let map {
            map(canvas)
        } else {
            VStack(spacing: LioTheme.Spacing.xs) {
                Image(systemName: "map").font(.title).foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
                Text(language.text("The map view is coming soon.", "地图视图即将上线。"))
                    .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity, minHeight: 160)
            .padding(LioTheme.Spacing.md)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("lio.trip-canvas.map-placeholder")
        }
    }

    // MARK: - Timeline

    @ViewBuilder private var timeline: some View {
        if canvas.days.isEmpty { emptyTrip }
        ForEach(canvas.segments) { segment in
            if let name = segment.name {
                Text(name)
                    .font(LioTheme.display(.title3).weight(.semibold)).foregroundStyle(LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(segment.days) { day in dayCard(day) }
        }
        Button { model.addDay() } label: {
            Label(language.text("Add a day", "加一天"), systemImage: "plus")
        }
        .buttonStyle(LioSecondaryButtonStyle())
        .accessibilityIdentifier("lio.trip-canvas.add-day")
        wishlistCard
    }

    private var emptyTrip: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text(language.text("No days planned yet", "还没有按天的安排"))
                .font(.headline).foregroundStyle(LioTheme.ink)
            Text(language.text("Plan a trip with Lio and save it, and its days appear here. You can also add days and places yourself.",
                               "和 Lio 聊一段行程并保存，每一天就会出现在这里。也可以自己加天数和地点。"))
                .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let openChat {
                Button(action: openChat) { Text(language.text("Plan with Lio", "和 Lio 规划")) }
                    .buttonStyle(LioPrimaryButtonStyle())
                    .accessibilityIdentifier("lio.trip-canvas.plan-with-lio")
            }
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityIdentifier("lio.trip-canvas.empty")
    }

    private func dayCard(_ day: LioTripCanvas.Day) -> some View {
        let number = canvas.dayNumber(day.id) ?? 0
        return VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            VStack(alignment: .leading, spacing: 2) {
                Text([language.text("Day \(number)", "第 \(number) 天"), day.date].compactMap { $0 }.joined(separator: " · "))
                    .font(.headline).foregroundStyle(LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
                let sub = [day.theme, day.area].filter { !$0.isEmpty }.joined(separator: " · ")
                if !sub.isEmpty { Text(sub).font(.footnote).foregroundStyle(LioTheme.inkSecondary) }
            }
            if day.points.isEmpty {
                Text(language.text("Nothing planned yet. Drag a place here.", "这一天还没有安排，把地点拖到这里。"))
                    .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            }
            ForEach(Array(day.points.enumerated()), id: \.element.id) { index, point in
                pointRow(point, position: .day(day, index))
                if index + 1 < day.points.count { legRow(from: point, to: day.points[index + 1]) }
            }
        }
        .padding(LioTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .outlined(targeted == day.id)
        .dropDestination(for: LioCanvasDragItem.self) { items, _ in
            guard let id = items.first?.pointID else { return false }
            model.moveToEnd(id, ofDay: day.id)
            return true
        } isTargeted: { over in setTargeted(day.id, over) }
        .accessibilityIdentifier("lio.trip-canvas.day.\(day.id)")
    }

    private var wishlistCard: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            HStack(alignment: .firstTextBaseline) {
                Label(language.text("Want to go", "想去"), systemImage: "heart")
                    .font(.headline).foregroundStyle(LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
                Spacer(minLength: LioTheme.Spacing.xs)
                Text("\(canvas.wishlist.count)").font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
            Text(language.text("Keep places here first. Drag one to a day when you know when.",
                               "先存在这里，想好哪天去再拖到那一天。"))
                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(Array(canvas.wishlist.enumerated()), id: \.element.id) { index, point in
                pointRow(point, position: .wishlist(index))
            }
            HStack(spacing: LioTheme.Spacing.xs) {
                TextField(language.text("A place you want to go", "想去的地方"), text: $wish)
                    .textFieldStyle(.roundedBorder)
                    .submitLabel(.done)
                    .onSubmit(addWish)
                    .frame(minHeight: 44)
                    .accessibilityIdentifier("lio.trip-canvas.wish-field")
                Button(action: addWish) { Text(language.text("Add", "加入")) }
                    .buttonStyle(LioSecondaryButtonStyle(fullWidth: false))
                    .disabled(wish.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityIdentifier("lio.trip-canvas.wish-add")
            }
        }
        .padding(LioTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .outlined(targeted == "wishlist")
        .dropDestination(for: LioCanvasDragItem.self) { items, _ in
            guard let id = items.first?.pointID else { return false }
            model.moveToWishlist(id)
            return true
        } isTargeted: { over in setTargeted("wishlist", over) }
        .accessibilityIdentifier("lio.trip-canvas.wishlist")
    }

    private func addWish() {
        guard !wish.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        model.addWish(wish)
        wish = ""
    }

    private func setTargeted(_ id: String, _ over: Bool) {
        if over { targeted = id } else if targeted == id { targeted = nil }
    }

    // MARK: - Rows

    private enum Position {
        case day(LioTripCanvas.Day, Int)
        case wishlist(Int)
    }

    private func pointRow(_ point: LioTripCanvas.Point, position: Position) -> some View {
        HStack(alignment: .top, spacing: LioTheme.Spacing.sm) {
            thumbnail(point)
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                if let time = point.time {
                    Text(time).font(.footnote.monospacedDigit()).foregroundStyle(LioTheme.inkSecondary)
                }
                Text(point.name(language))
                    .font(.headline).foregroundStyle(LioTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if language == .english, point.nameZH != point.nameEN, !point.nameZH.isEmpty {
                    Text(point.nameZH).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                }
                let kind = point.kind.title(language)
                if !kind.isEmpty { Text(kind).font(.caption).foregroundStyle(LioTheme.inkSecondary) }
            }
            Spacer(minLength: 0)
            actionsMenu(point, position: position)
        }
        .padding(LioTheme.Spacing.xs)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LioTheme.surfaceSunken.opacity(0.4), in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
        .outlined(targeted == point.id, radius: LioTheme.Radius.small)
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.small))
        .draggable(LioCanvasDragItem(pointID: point.id)) {
            Text(point.name(language))
                .font(.headline).foregroundStyle(LioTheme.ink)
                .padding(LioTheme.Spacing.xs)
                .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
        }
        .dropDestination(for: LioCanvasDragItem.self) { items, _ in
            guard let id = items.first?.pointID else { return false }
            model.drop(id, onto: point.id)
            return true
        } isTargeted: { over in setTargeted(point.id, over) }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("lio.trip-canvas.point.\(point.id)")
    }

    /// The thumbnail. Places have no pictures yet, so each shows its kind's symbol; the picture goes here when they do.
    private func thumbnail(_ point: LioTripCanvas.Point) -> some View {
        RoundedRectangle(cornerRadius: LioTheme.Radius.small)
            .fill(LioTheme.surfaceSunken)
            .frame(width: thumbnailSize, height: thumbnailSize)
            .overlay {
                Image(systemName: point.kind.symbol).font(.title3).foregroundStyle(LioTheme.inkSecondary)
            }
            .accessibilityHidden(true)
    }

    private func legRow(from: LioTripCanvas.Point, to: LioTripCanvas.Point) -> some View {
        let leg = canvas.leg(from: from.id, to: to.id)
        return HStack(spacing: LioTheme.Spacing.sm) {
            Image(systemName: leg?.symbol ?? "arrow.down")
                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                .frame(width: thumbnailSize)
                .accessibilityHidden(true)
            Text(leg?.description(language) ?? language.text("Travel to be set", "交通待定"))
                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, LioTheme.Spacing.xs)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lio.trip-canvas.leg.\(from.id)")
    }

    /// The same moves as dragging, for those who cannot drag, plus edit and delete.
    private func actionsMenu(_ point: LioTripCanvas.Point, position: Position) -> some View {
        Menu {
            Button { model.shift(point.id, by: -1) } label: {
                Label(language.text("Move up", "上移"), systemImage: "arrow.up")
            }
            Button { model.shift(point.id, by: 1) } label: {
                Label(language.text("Move down", "下移"), systemImage: "arrow.down")
            }
            Menu {
                ForEach(canvas.days) { day in
                    if !isOn(day, point) {
                        Button(language.text("Day \(canvas.dayNumber(day.id) ?? 0)", "第 \(canvas.dayNumber(day.id) ?? 0) 天")) {
                            model.moveToEnd(point.id, ofDay: day.id)
                        }
                    }
                }
            } label: {
                Label(language.text("Move to day", "移到某一天"), systemImage: "calendar")
            }
            if case .day = position {
                Button { model.moveToWishlist(point.id) } label: {
                    Label(language.text("Move to Want to go", "移到想去"), systemImage: "heart")
                }
            }
            Button { editing = point } label: {
                Label(language.text("Edit", "修改"), systemImage: "pencil")
            }
            Button(role: .destructive) { model.remove(point.id) } label: {
                Label(language.text("Delete", "删除"), systemImage: "trash")
            }
        } label: {
            Image(systemName: "ellipsis.circle")
                .font(.title3)
                .foregroundStyle(LioTheme.inkSecondary)
                .frame(minWidth: 44, minHeight: 44)
                .contentShape(Rectangle())
        }
        .accessibilityLabel(language.text("Actions for \(point.name(language))", "\(point.name(language)) 的操作"))
        .accessibilityIdentifier("lio.trip-canvas.menu.\(point.id)")
    }

    private func isOn(_ day: LioTripCanvas.Day, _ point: LioTripCanvas.Point) -> Bool {
        day.points.contains { $0.id == point.id }
    }

    // MARK: - Undo

    @ViewBuilder private var undoBar: some View {
        if let notice = model.notice, model.canUndo {
            HStack(spacing: LioTheme.Spacing.sm) {
                Text(notice.text(language))
                    .font(.subheadline).foregroundStyle(LioTheme.ink)
                    .lineLimit(2)
                Spacer(minLength: LioTheme.Spacing.xs)
                Button { model.undo() } label: {
                    Text(language.text("Undo", "撤销"))
                        .font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.vermilion)
                        .frame(minWidth: 44, minHeight: 44)
                }
                .accessibilityIdentifier("lio.trip-canvas.undo")
                Button { model.dismissNotice() } label: {
                    Image(systemName: "xmark").font(.footnote.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary)
                        .frame(minWidth: 44, minHeight: 44)
                }
                .accessibilityLabel(language.text("Dismiss", "关闭"))
                .accessibilityIdentifier("lio.trip-canvas.undo-dismiss")
            }
            .padding(.horizontal, LioTheme.Spacing.md)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .padding(.horizontal, LioTheme.Spacing.md)
            .padding(.bottom, LioTheme.Spacing.xs)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("lio.trip-canvas.undo-bar")
        }
    }
}

private extension View {
    /// A vermilion outline while a drag is over this view; no layout change.
    func outlined(_ on: Bool, radius: CGFloat = LioTheme.Radius.card) -> some View {
        overlay {
            if on {
                RoundedRectangle(cornerRadius: radius).stroke(LioTheme.vermilion, lineWidth: 2)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
        }
    }
}

/// Edits a point's name and time. Saving a point changed at all makes it the traveller's.
private struct LioTripCanvasEditSheet: View {
    let language: LioLanguage
    let point: LioTripCanvas.Point
    /// What the traveller changed: the name, and the time (a time cleared is `.some(nil)`); nil for what they left alone.
    let save: (String?, String??) -> Void
    @State private var name: String
    @State private var time: String
    @Environment(\.dismiss) private var dismiss

    init(language: LioLanguage, point: LioTripCanvas.Point, save: @escaping (String?, String??) -> Void) {
        self.language = language
        self.point = point
        self.save = save
        _name = State(initialValue: point.name(language))
        _time = State(initialValue: point.time ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section(language.text("Name", "名称")) {
                    TextField(language.text("Name", "名称"), text: $name)
                        .accessibilityIdentifier("lio.trip-canvas.edit.name")
                }
                .lioRow()
                Section(language.text("Time", "时段")) {
                    TextField(language.text("For example 09:30", "例如 09:30"), text: $time)
                        .accessibilityIdentifier("lio.trip-canvas.edit.time")
                }
                .lioRow()
            }
            .lioPage()
            .navigationTitle(language.text("Edit place", "修改地点"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.text("Cancel", "取消")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(language.text("Save", "保存")) {
                        // Only what the traveller changed is passed on, so an untouched field never marks the point.
                        let cleanTime = time.trimmingCharacters(in: .whitespacesAndNewlines)
                        save(name == point.name(language) ? nil : name,
                             cleanTime == (point.time ?? "") ? nil : .some(cleanTime.isEmpty ? nil : cleanTime))
                        dismiss()
                    }
                    .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityIdentifier("lio.trip-canvas.edit.save")
                }
            }
        }
        .presentationDetents([.medium])
    }
}
#endif
