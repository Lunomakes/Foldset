import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// Main window. Shows a template's creation as a visible flow — template → Foldset rules → each folder's
/// outcome with its reason — and edits the template in place. The preview build uses an isolated library.
struct NativeMainView: View {
    @ObservedObject var store: TemplateStore
    @ViewState private var confirmDelete = false
    @ViewState private var showHelp = false
    var body: some View {
        NavigationSplitView {
            TemplateSidebar(store: store, showHelp: $showHelp)
                .navigationSplitViewColumnWidth(min: 190, ideal: 220, max: 280)
        } detail: {
            Group {
                if let id = store.selectedID, let index = store.templates.firstIndex(where: { $0.id == id }) {
                    TemplateFlowPage(template: $store.templates[index], store: store).id(id)
                } else {
                    ContentUnavailableView {
                        Label("还没有选中模板", systemImage: "folder.badge.plus")
                    } description: {
                        Text("把常用的文件夹结构存成模板，之后一键创建到任意位置。")
                    } actions: {
                        Button("新建模板") { store.add() }.buttonStyle(InverseButtonStyle())
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.canvas)
            .navigationTitle(store.selected?.displayName ?? "Foldset")
            .toolbar {
                ToolbarItem {
                    Menu {
                        Button("复制模板") { store.duplicate() }
                        Button("删除模板…", role: .destructive) { confirmDelete = true }
                    } label: { Label("模板操作", systemImage: "ellipsis.circle") }
                    .disabled(store.selected == nil).help("模板操作")
                }
            }
        }
        .preferredColorScheme(.dark)
        .frame(minWidth: 760, minHeight: 560)
        .alert(item: $store.notice) { notice in
            Alert(title: Text(notice.title), message: Text(notice.message), dismissButton: .default(Text("好")))
        }
        .confirmationDialog("删除“\(store.selected?.name ?? "")”模板？", isPresented: $confirmDelete) {
            Button("删除模板", role: .destructive) { store.deleteSelected() }
        } message: { Text("只删除模板设置，不会删除已创建的文件夹。") }
        .sheet(isPresented: $showHelp) {
            VStack(alignment: .leading, spacing: 18) {
                Text("Finder 右键创建").font(.headline)
                Text("在 Finder 中右键点击目标文件夹，选择“服务” → “Foldset：使用默认模板创建”。")
                #if NATIVE_PREVIEW
                Text("此预览版用于确认界面；右键服务仍由应用程序中的正式版提供。").foregroundStyle(.secondary)
                #endif
                HStack { Spacer(); Button("完成") { showHelp = false }.keyboardShortcut(.defaultAction) }
            }.padding(24).frame(width: 430)
        }
    }
}

private struct TemplateSidebar: View {
    @ObservedObject var store: TemplateStore
    @Binding var showHelp: Bool
    var body: some View {
        List(selection: $store.selectedID) {
            Section {
                ForEach(store.templates) { template in
                    HStack(spacing: 8) {
                        Image(systemName: "folder").foregroundStyle(Theme.ink2).accessibilityHidden(true)
                        Text(template.displayName).lineLimit(1)
                        Spacer(minLength: 4)
                        if store.defaultID == template.id {
                            Text("Finder").font(.caption2.weight(.medium)).foregroundStyle(Theme.ink2)
                                .padding(.horizontal, 6).padding(.vertical, 1)
                                .overlay(Capsule().strokeBorder(Theme.border))
                                .help("Finder 右键“使用默认模板创建”会使用此模板")
                        }
                        Text("\(template.entries.count)").font(.caption.monospacedDigit()).foregroundStyle(Theme.ink3)
                    }
                    .padding(.vertical, 3)
                    .tag(template.id)
                    .accessibilityElement(children: .combine)
                    .accessibilityValue(store.defaultID == template.id ? "\(template.entries.count) 个文件夹，Finder 默认模板" : "\(template.entries.count) 个文件夹")
                }
            } header: { Text("文件夹模板").sectionLabel() }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .background(Theme.canvas)
        .safeAreaInset(edge: .top, spacing: 0) {
            HStack(spacing: 10) {
                Image(nsImage: BrandAsset.icon).resizable().interpolation(.high).scaledToFit()
                    .frame(width: 26, height: 24).accessibilityHidden(true)
                Text("Foldset").font(.system(size: 16, weight: .semibold)).foregroundStyle(Theme.ink)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            .accessibilityElement(children: .combine)
        }
        .safeAreaInset(edge: .bottom) {
            VStack(alignment: .leading, spacing: 10) {
                Button { store.add() } label: { Label("新建模板", systemImage: "plus") }
                    .buttonStyle(.bordered)
                Divider()
                SettingsLink { Label("设置", systemImage: "gearshape") }.buttonStyle(.borderless)
                Button { showHelp = true } label: { Label("Finder 右键与使用说明", systemImage: "questionmark.circle") }
                    .buttonStyle(.borderless)
            }
            .font(.callout).foregroundStyle(Theme.ink2)
            .padding(16)
        }
    }
}

/// One scrolling page: live flow card on top, template settings below, target and create action pinned at the bottom.
private enum SettingsField: Hashable { case name, start, separator }

private struct TemplateFlowPage: View {
    @Binding var template: FolderTemplate
    @ObservedObject var store: TemplateStore
    @FocusState private var focusedEntry: UUID?
    @FocusState private var settingsFocus: SettingsField?
    @Environment(\.accessibilityReduceMotion) private var systemStill
    @AppStorage("reduceMotion") private var preferStill = false
    private var preview: CreationPreview? { store.currentPreview }
    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let error = store.persistenceError {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .font(.callout).foregroundStyle(Theme.bad)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14).card(fill: Theme.bad.opacity(0.08))
                }
                HStack(spacing: 8) {
                    Text("创建流程").sectionLabel()
                    if store.checking {
                        ProgressView().controlSize(.mini)
                        Text("正在检查目标文件夹…").font(Theme.body).foregroundStyle(Theme.ink3)
                    } else {
                        StatusDot(kind: .filled, color: Theme.ok)
                        Text("实时预览，尚未写入任何内容").font(Theme.body).foregroundStyle(Theme.ink3)
                    }
                }
                FlowCard(template: $template, store: store, preview: preview, focusedEntry: $focusedEntry)
                Text("模板设置").sectionLabel().padding(.top, 10)
                TemplateSettingsCard(template: $template, store: store, focus: $settingsFocus)
            }
            .padding(.horizontal, 24).padding(.vertical, 20)
            .frame(maxWidth: 1040)
            .frame(maxWidth: .infinity)
        }
        .animation((systemStill || preferStill) ? nil : .easeInOut(duration: 0.18), value: preview)
        .safeAreaInset(edge: .bottom, spacing: 0) { CreateBar(store: store, preview: preview) }
        // Keyboard users tab into fields below the fold; keep the focused field on screen.
        .onChange(of: focusedEntry) { _, id in if let id { reveal(id, proxy) } }
        .onChange(of: settingsFocus) { _, field in if let field { reveal(field, proxy) } }
        }
    }
    private func reveal<ID: Hashable>(_ id: ID, _ proxy: ScrollViewProxy) {
        if systemStill || preferStill { proxy.scrollTo(id, anchor: .center) }
        else { withAnimation(.easeInOut(duration: 0.18)) { proxy.scrollTo(id, anchor: .center) } }
    }
}

// MARK: - Flow card

private struct FlowCard: View {
    @Binding var template: FolderTemplate
    @ObservedObject var store: TemplateStore
    let preview: CreationPreview?
    var focusedEntry: FocusState<UUID?>.Binding
    @ViewState private var dragging: UUID?
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 0) {
                    Text(template.displayName).font(Theme.title).foregroundStyle(Theme.ink)
                    Text(" · 文件夹模板 · \(template.entries.count) 个文件夹").font(Theme.body).foregroundStyle(Theme.ink2)
                    if store.defaultID == template.id {
                        Text(" · Finder 默认").font(Theme.body).foregroundStyle(Theme.ink2)
                    }
                }
                Text(ruleSentence).font(Theme.body).foregroundStyle(Theme.ink2).fixedSize(horizontal: false, vertical: true)
            }
            .padding(.bottom, 18)
            ViewThatFits(in: .horizontal) {
                wideDiagram.frame(minWidth: 620)
                narrowDiagram
            }
            Button {
                let entry = FolderEntry(name: "")
                template.entries.append(entry)
                focusedEntry.wrappedValue = entry.id
            } label: { Label("添加文件夹", systemImage: "plus") }
            .buttonStyle(.borderless).foregroundStyle(Theme.ink2)
            .padding(.top, 10)
            Divider().overlay(Theme.border).padding(.vertical, 16)
            VerdictRow(preview: preview, target: store.target)
            Divider().overlay(Theme.border).padding(.vertical, 16)
            DecisionTrace(template: template, preview: preview, target: store.target, outcome: store.outcome)
        }
        .padding(20)
        .card()
    }
    private var ruleSentence: String {
        let numbering = template.numbered
            ? "按顺序编号：从 \(String(format: "%0\(max(1, template.digits))d", max(0, template.start))) 开始，\(template.digits) 位数，用“\(template.separator)”连接名称。"
            : "不编号，直接使用名称。"
        return numbering + "目标里已有的同名文件夹会保留并跳过；同名文件或链接会阻止整次创建，不会覆盖任何内容。"
    }
    // Wide: engine node on the left, a connector per folder, outcomes on the right.
    private var wideDiagram: some View {
        let rowsHeight = FolderRow.height * CGFloat(template.entries.count) + FolderRow.gap * CGFloat(max(0, template.entries.count - 1))
        let heroHeight: CGFloat = 172
        let heroTop = max(0, (min(rowsHeight, 520) - heroHeight) / 2)
        let rowsTop = max(0, (heroHeight - rowsHeight) / 2)
        return HStack(alignment: .top, spacing: 0) {
            EngineNode(template: template, target: store.target)
                .frame(width: 190, height: heroHeight)
                .padding(.top, heroTop)
            Connectors(outcomes: outcomes, anchorY: heroTop + heroHeight / 2, rowsTop: rowsTop)
                .frame(width: 56, height: max(rowsHeight + rowsTop, heroTop + heroHeight))
            rows.padding(.top, rowsTop)
        }
    }
    private var narrowDiagram: some View {
        VStack(alignment: .leading, spacing: 14) {
            EngineNode(template: template, target: store.target, compact: true)
            rows
        }
    }
    private var outcomes: [RowOutcome?] {
        template.entries.indices.map { preview?.rows[$0].outcome }
    }
    private var rows: some View {
        VStack(spacing: FolderRow.gap) {
            ForEach(Array(template.entries.enumerated()), id: \.element.id) { index, entry in
                FolderRow(id: entry.id, index: index, count: template.entries.count, entry: entryBinding(entry.id),
                          finalName: template.folderName(at: index), outcome: preview?.rows[index].outcome,
                          templateIssue: preview?.templateIssue, checking: store.checking,
                          focused: focusedEntry, dragging: $dragging,
                          move: { move(entry.id, $0) },
                          remove: { template.entries.removeAll { $0.id == entry.id } })
                .onDrop(of: [UTType.text], delegate: EntryDropDelegate(id: entry.id, entries: $template.entries, dragging: $dragging))
            }
        }
        .frame(maxWidth: .infinity)
    }
    func entryBinding(_ id: UUID) -> Binding<String> {
        Binding(get: { template.entries.first { $0.id == id }?.name ?? "" }, set: { name in
            if let index = template.entries.firstIndex(where: { $0.id == id }) { template.entries[index].name = name }
        })
    }
    func move(_ id: UUID, _ delta: Int) {
        if let index = template.entries.firstIndex(where: { $0.id == id }), template.entries.indices.contains(index + delta) {
            template.entries.swapAt(index, index + delta)
        }
    }
}

/// The "engine" node: what Foldset will apply, and where. Dark card with a bright outline, as in the reference app;
/// only its mode pill is inverse.
private struct EngineNode: View {
    let template: FolderTemplate
    let target: URL?
    var compact = false
    @Environment(\.accessibilityReduceTransparency) private var systemOpaque
    @AppStorage("reduceTransparency") private var preferOpaque = false
    var body: some View {
        let layout = compact ? AnyLayout(HStackLayout(alignment: .center, spacing: 14)) : AnyLayout(VStackLayout(alignment: .center, spacing: 8))
        layout {
            Image(nsImage: BrandAsset.icon).resizable().interpolation(.high).scaledToFit()
                .frame(width: 34, height: 32).accessibilityHidden(true)
            VStack(alignment: compact ? .leading : .center, spacing: 4) {
                Text("Foldset").font(Theme.hero).foregroundStyle(Theme.ink)
                Text(target?.lastPathComponent ?? "未选择目标")
                    .font(Theme.mono).foregroundStyle(Theme.ink2)
                    .lineLimit(1).truncationMode(.middle)
                    .help(target?.path ?? "在底部选择创建位置")
            }
            if compact { Spacer(minLength: 0) }
            Text(template.numbered ? "编号 · \(template.separator.isEmpty ? "无分隔" : "“\(template.separator)”")" : "不编号")
                .font(.system(size: 12, weight: .semibold)).foregroundStyle(Theme.inverseInk)
                .padding(.horizontal, 12).padding(.vertical, 4)
                .background(Theme.inverse, in: Capsule())
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: compact ? nil : .infinity)
        .background(Theme.canvas, in: RoundedRectangle(cornerRadius: Theme.radiusCard + 2))
        .overlay(RoundedRectangle(cornerRadius: Theme.radiusCard + 2).strokeBorder(Theme.ink.opacity(0.85), lineWidth: 1.5))
        .shadow(color: .black.opacity((systemOpaque || preferOpaque) ? 0 : 0.35), radius: 12, y: 8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Foldset 创建规则")
        .accessibilityValue("\(template.numbered ? "按顺序编号" : "不编号")，目标：\(target?.path ?? "未选择")")
    }
}

/// One connector per folder from the engine node. Decorative; every state is also written in words on the row.
private struct Connectors: View {
    let outcomes: [RowOutcome?]
    let anchorY: CGFloat
    let rowsTop: CGFloat
    var body: some View {
        Canvas { context, size in
            for (index, outcome) in outcomes.enumerated() {
                let y = rowsTop + CGFloat(index) * (FolderRow.height + FolderRow.gap) + FolderRow.height / 2
                var path = Path()
                path.move(to: CGPoint(x: 0, y: anchorY))
                path.addCurve(to: CGPoint(x: size.width, y: y),
                              control1: CGPoint(x: size.width * 0.6, y: anchorY),
                              control2: CGPoint(x: size.width * 0.4, y: y))
                let (color, dashed) = Self.style(outcome)
                context.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: 1.4, lineCap: .round, dash: dashed ? [3, 4] : []))
            }
        }
        .accessibilityHidden(true)
    }
    static func style(_ outcome: RowOutcome?) -> (Color, Bool) {
        switch outcome {
        case .willCreate: return (Theme.ok, true)
        case .exists: return (Theme.connector, false)
        case .blocked: return (Theme.bad, true)
        case .awaitingTarget, nil: return (Theme.connector.opacity(0.6), true)
        }
    }
}

private struct FolderRow: View {
    static let height: CGFloat = 52
    static let gap: CGFloat = 8
    let id: UUID
    let index: Int
    let count: Int
    @Binding var entry: String
    let finalName: String
    let outcome: RowOutcome?
    let templateIssue: String?
    let checking: Bool
    var focused: FocusState<UUID?>.Binding
    @Binding var dragging: UUID?
    let move: (Int) -> Void
    let remove: () -> Void
    var body: some View {
        let status = self.status
        HStack(spacing: 10) {
            Image(systemName: "line.3.horizontal").font(.caption).foregroundStyle(Theme.ink3)
                .frame(width: 14, height: Self.height).contentShape(Rectangle())
                .onDrag { dragging = id; return NSItemProvider(object: id.uuidString as NSString) }
                .help("拖动排序；也可使用行尾菜单上移或下移")
                .accessibilityHidden(true)
            StatusDot(kind: status.dot, color: status.color)
            VStack(alignment: .leading, spacing: 2) {
                TextField("文件夹名称", text: $entry)
                    .textFieldStyle(.plain).font(.system(size: 14, weight: .medium)).foregroundStyle(Theme.ink)
                    .focused(focused, equals: id)
                    .accessibilityLabel("第 \(index + 1) 个文件夹名称")
                Text(finalName.isEmpty ? "—" : finalName).font(.system(size: 11.5, design: .monospaced)).foregroundStyle(Theme.ink2)
                    .lineLimit(1).truncationMode(.middle).help(finalName)
                    .accessibilityLabel("将创建为：\(finalName)")
            }
            Spacer(minLength: 8)
            Text(status.text).font(Theme.body).foregroundStyle(status.color)
                .lineLimit(1).help(status.help ?? status.text)
                .accessibilityLabel("状态：\(status.help ?? status.text)")
            Menu {
                Button("上移") { move(-1) }.disabled(index == 0)
                Button("下移") { move(1) }.disabled(index == count - 1)
                Divider()
                Button("移除", role: .destructive, action: remove)
            } label: { Image(systemName: "ellipsis") }
                .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                .accessibilityLabel("第 \(index + 1) 个文件夹操作")
        }
        .padding(.horizontal, 12)
        .frame(height: Self.height)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay {
            let shape = RoundedRectangle(cornerRadius: 12)
            if case .blocked = outcome {
                shape.strokeBorder(Theme.bad.opacity(0.55), style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
            } else {
                shape.strokeBorder(Theme.border)
            }
        }
    }
    private struct Status {
        let text: String
        var help: String?
        let dot: StatusDot.Kind
        let color: Color
    }
    private var status: Status {
        if templateIssue != nil { return Status(text: "未检查", help: "先解决上方模板问题", dot: .hollow, color: Theme.ink3) }
        switch outcome {
        case .willCreate: return Status(text: "将创建", dot: .filled, color: Theme.ok)
        case .exists: return Status(text: "已存在 · 跳过", help: "目标里已有同名文件夹，保留其中内容并跳过", dot: .hollow, color: Theme.ink2)
        case .blocked(let reason): return Status(text: "阻止 · " + Self.short(reason), help: reason, dot: .stopped, color: Theme.bad)
        case .awaitingTarget: return Status(text: "待选目标", dot: .hollow, color: Theme.ink3)
        case nil: return Status(text: checking ? "检查中…" : "—", dot: .hollow, color: Theme.ink3)
        }
    }
    static func short(_ reason: String) -> String {
        if reason.contains("同名文件或链接") { return "同名文件或链接" }
        if reason.contains("为空") { return "名称为空" }
        if reason.contains("重复") { return "名称重复" }
        if reason.contains("过长") { return "名称过长" }
        if reason.contains("无效") { return "名称无效" }
        return "无法创建"
    }
}

/// Verdict sentence and the three counters, as in the reference's footer.
private struct VerdictRow: View {
    let preview: CreationPreview?
    let target: URL?
    var body: some View {
        HStack(alignment: .bottom, spacing: 28) {
            Text(verdict).font(.system(size: 14)).foregroundStyle(Theme.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
            // Before a location is chosen nothing has been checked, so show "–" rather than 0.
            let checked = target != nil && preview?.targetIssue == nil ? preview : nil
            Counter(value: checked?.willCreate, label: "将创建")
            Counter(value: checked?.existing, label: "已存在 · 跳过")
            Counter(value: checked?.blocked ?? (preview?.blocked == 0 ? nil : preview?.blocked), label: "阻止", alert: (preview?.blocked ?? 0) > 0)
        }
    }
    private var verdict: String {
        guard let preview else { return "正在检查…" }
        if let issue = preview.templateIssue { return issue }
        if let issue = preview.targetIssue { return issue }
        if preview.blocked > 0 { return "有 \(preview.blocked) 项被阻止，修正前不会创建任何文件夹。" }
        guard let target else { return "选择创建位置后，逐项检查同名文件夹。" }
        if preview.willCreate == 0 { return "全部已存在于 \(target.lastPathComponent)，创建不会产生新文件夹。" }
        return "将在 \(target.lastPathComponent) 中创建 \(preview.willCreate) 个文件夹。"
    }
}

private struct Counter: View {
    let value: Int?
    let label: String
    var alert = false
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value.map(String.init) ?? "–").font(.system(size: 26, weight: .semibold).monospacedDigit())
                .foregroundStyle(alert ? Theme.bad : Theme.ink)
            Text(label).font(Theme.body).foregroundStyle(Theme.ink2)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(label)：\(value.map(String.init) ?? "未知")")
    }
}

/// "How this will be created" — the plain-language trace of each decision.
private struct DecisionTrace: View {
    let template: FolderTemplate
    let preview: CreationPreview?
    let target: URL?
    let outcome: TemplateStore.Outcome?
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("这次会怎样创建").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.ink)
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    StatusDot(kind: line.dot, color: line.color).alignmentGuide(.firstTextBaseline) { $0[.bottom] - 1 }
                    Text(line.text).font(.system(size: 13)).foregroundStyle(line.color == Theme.bad ? Theme.bad : (line.dot == .filled ? Theme.ink : Theme.ink2))
                        .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                }
            }
            if let outcome {
                HStack(spacing: 10) {
                    Label(outcome.message, systemImage: outcome.succeeded ? "checkmark.circle" : "exclamationmark.triangle")
                        .font(.callout).foregroundStyle(outcome.succeeded ? Theme.ok : Theme.bad)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Button("在 Finder 中显示") { NSWorkspace.shared.activateFileViewerSelecting([outcome.target]) }
                        .buttonStyle(.bordered).controlSize(.small)
                }
                .padding(12).card(fill: (outcome.succeeded ? Theme.ok : Theme.bad).opacity(0.08))
            }
        }
    }
    private struct Line { let text: String; let dot: StatusDot.Kind; let color: Color }
    private var lines: [Line] {
        var result = [Line(text: "使用模板「\(template.displayName)」，共 \(template.entries.count) 个文件夹，单层创建。", dot: .hollow, color: Theme.ink3)]
        result.append(Line(text: template.numbered ? "编号：第一个是 \(template.entries.isEmpty ? "—" : template.folderName(at: 0))，依次递增。" : "未开启编号，直接使用名称。", dot: .hollow, color: Theme.ink3))
        result.append(target.map { Line(text: "目标：\($0.path)", dot: .filled, color: Theme.ink) } ?? Line(text: "尚未选择目标文件夹。", dot: .hollow, color: Theme.ink3))
        guard let preview else { return result }
        if let issue = preview.templateIssue { result.append(Line(text: issue, dot: .stopped, color: Theme.bad)) }
        if let issue = preview.targetIssue { result.append(Line(text: issue, dot: .stopped, color: Theme.bad)) }
        let existing = preview.rows.filter { $0.outcome == .exists }.map(\.name)
        if !existing.isEmpty {
            let shown = existing.prefix(3).joined(separator: "、") + (existing.count > 3 ? " 等 \(existing.count) 个" : "")
            result.append(Line(text: "\(shown) 已存在：保留其中内容，跳过。", dot: .hollow, color: Theme.ink3))
        }
        for row in preview.rows {
            if case .blocked(let reason) = row.outcome { result.append(Line(text: reason, dot: .stopped, color: Theme.bad)) }
        }
        if preview.canCreate {
            result.append(Line(text: preview.willCreate > 0 ? "点击“创建文件夹”（⌘↩）后创建 \(preview.willCreate) 个；创建前会再检查一次，不覆盖任何内容。" : "没有需要新建的文件夹。", dot: .filled, color: Theme.ink))
        }
        return result
    }
}

// MARK: - Settings card and bottom bar

private struct TemplateSettingsCard: View {
    @Binding var template: FolderTemplate
    @ObservedObject var store: TemplateStore
    var focus: FocusState<SettingsField?>.Binding
    var body: some View {
        VStack(spacing: 0) {
            SettingRow("模板名称") {
                TextField("模板名称", text: $template.name).labelsHidden().textFieldStyle(.roundedBorder).frame(maxWidth: 260)
                    .accessibilityLabel("模板名称").focused(focus, equals: .name)
            }.id(SettingsField.name)
            Divider().overlay(Theme.border)
            SettingRow("Finder 快速创建", detail: "右键“使用默认模板创建”时，静默使用这一套") {
                if store.defaultID == template.id {
                    Label("当前默认", systemImage: "checkmark").foregroundStyle(Theme.ink2)
                } else {
                    Button("设为默认") { store.defaultID = template.id }.buttonStyle(.bordered)
                }
            }
            Divider().overlay(Theme.border)
            SettingRow("自动编号", detail: "按文件夹顺序添加序号") {
                Toggle("自动编号", isOn: $template.numbered).labelsHidden().toggleStyle(.switch)
                    .accessibilityHint("按文件夹顺序添加序号")
            }
            Group {
                Divider().overlay(Theme.border)
                SettingRow("起始序号") {
                    TextField("起始序号", value: $template.start, format: .number.grouping(.never))
                        .labelsHidden().textFieldStyle(.roundedBorder).multilineTextAlignment(.trailing).frame(width: 90)
                        .accessibilityLabel("起始序号").focused(focus, equals: .start)
                }.id(SettingsField.start)
                Divider().overlay(Theme.border)
                SettingRow("编号格式") {
                    Picker("编号格式", selection: $template.digits) {
                        Text("1, 2, 3").tag(1)
                        Text("01, 02, 03").tag(2)
                        Text("001, 002, 003").tag(3)
                    }.labelsHidden().fixedSize()
                }
                Divider().overlay(Theme.border)
                SettingRow("分隔符") {
                    TextField("分隔符", text: $template.separator)
                        .labelsHidden().textFieldStyle(.roundedBorder).multilineTextAlignment(.trailing).frame(width: 90)
                        .accessibilityLabel("分隔符").focused(focus, equals: .separator)
                }.id(SettingsField.separator)
            }.disabled(!template.numbered)
        }
        .padding(.horizontal, 20).padding(.vertical, 6)
        .card()
    }
}

private struct SettingRow<Control: View>: View {
    let title: String
    var detail: String?
    @ViewBuilder let control: Control
    init(_ title: String, detail: String? = nil, @ViewBuilder control: () -> Control) {
        self.title = title; self.detail = detail; self.control = control()
    }
    @Environment(\.isEnabled) private var enabled
    var body: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 13.5)).foregroundStyle(enabled ? Theme.ink : Theme.ink3)
                if let detail { Text(detail).font(.caption).foregroundStyle(Theme.ink2) }
            }
            Spacer(minLength: 12)
            control
        }
        .padding(.vertical, 11)
        .accessibilityElement(children: .contain)
    }
}

private struct CreateBar: View {
    @ObservedObject var store: TemplateStore
    let preview: CreationPreview?
    var body: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text("创建位置").font(.system(size: 13, weight: .medium)).foregroundStyle(Theme.ink)
                Text(store.target?.path ?? "尚未选择目标文件夹")
                    .font(.system(size: 11.5, design: store.target == nil ? .default : .monospaced))
                    .foregroundStyle(Theme.ink2).lineLimit(1).truncationMode(.middle)
                    .help(store.target?.path ?? "选择一个目标文件夹")
            }
            Spacer(minLength: 12)
            Button(store.target == nil ? "选择…" : "更换…") { store.selectTarget() }.buttonStyle(.bordered)
            Button { store.create() } label: { Label("创建文件夹", systemImage: "folder.badge.plus") }
                .buttonStyle(InverseButtonStyle())
                .disabled(!store.canCreate)
                .help(preview?.canCreate == true ? "⌘↩" : "先处理流程中的问题")
        }
        .padding(.horizontal, 24).padding(.vertical, 14)
        .background(Theme.canvas)
        .overlay(alignment: .top) { Rectangle().fill(Theme.border).frame(height: 1) }
    }
}
