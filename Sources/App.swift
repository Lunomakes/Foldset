import SwiftUI
import AppKit

// Use the property-wrapper type explicitly with SDKs that also export a State macro.
typealias ViewState<Value> = SwiftUI.State<Value>

final class AppDelegate: NSObject, NSApplicationDelegate {
    #if NATIVE_PREVIEW
    let store = TemplateStore(fileURL: URL(fileURLWithPath: Bundle.main.object(forInfoDictionaryKey: "PreviewLibraryPath") as! String))
    #else
    let store = TemplateStore()
    #endif
    private var window: NSWindow?
    private var helpWindow: NSWindow?
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.appearance = NSAppearance(named: .darkAqua)
        NSApp.servicesProvider = self
        // AppKit explicitly marks launches for Services as non-default.
        if (notification.userInfo?[NSApplication.launchIsDefaultUserInfoKey] as? NSNumber)?.boolValue == true {
            showWindow()
        }
        if (try? Updater.failureMarker.checkResourceIsReachable()) == true {
            try? FileManager.default.removeItem(at: Updater.failureMarker)
            store.notice = .init(title: "更新未完成", message: "安装新版本时出错，已保留当前版本。可在“设置 → 通用”中重试。")
        }
        // Silent: a newer release only shows the sidebar badge; nothing pops up.
        if UserDefaults.standard.object(forKey: Updater.autoCheckKey) as? Bool ?? true {
            Task { await Updater.shared.check(quietly: true) }
        }
    }
    // Normal launches request an untitled window; service launches do not.
    func applicationShouldOpenUntitledFile(_ sender: NSApplication) -> Bool {
        showWindow()
        return false
    }
    func showWindow() {
        NSApp.setActivationPolicy(.regular)
        if window == nil {
            let view = NativeMainView(store: store)
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 980, height: 890), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
            window.title = "Foldset — 模板"
            window.titleVisibility = .hidden
            window.titlebarAppearsTransparent = true
            window.isOpaque = true
            window.backgroundColor = NSColor(Theme.canvas)
            window.appearance = NSAppearance(named: .darkAqua)
            window.minSize = NSSize(width: 760, height: 600)
            window.contentView = NSHostingView(rootView: view)
            window.isReleasedWhenClosed = false
            window.center()
            #if NATIVE_PREVIEW
            window.setFrameAutosaveName("FoldsetNativePreview")
            #else
            window.setFrameAutosaveName("FoldsetNativeMain")
            #endif
            self.window = window
        }
        window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        // Folder names are editable in place; do not start with one selected, where a keystroke would replace it.
        DispatchQueue.main.async { [weak self] in self?.window?.makeFirstResponder(nil) }
    }
    func showHelp() {
        if helpWindow == nil {
            let panel = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 570, height: 390), styleMask: [.titled, .closable], backing: .buffered, defer: false)
            panel.title = "Foldset使用说明"; panel.contentView = NSHostingView(rootView: HelpView().padding(20))
            panel.isReleasedWhenClosed = false; panel.center(); helpWindow = panel
        }
        helpWindow?.makeKeyAndOrderFront(nil)
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        receive(filenames.map { URL(fileURLWithPath: $0) }, useDefault: false)
        sender.reply(toOpenOrPrint: .success)
    }
    private func receive(_ urls: [URL], useDefault: Bool) {
        do { try store.accept(urls, useDefault: useDefault) }
        catch { store.notice = .init(title: "无法使用此位置", message: error.localizedDescription) }
        showWindow()
    }
    @objc func chooseTemplate(_ pasteboard: NSPasteboard, userData: String?, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        handleService(pasteboard, useDefault: false, error: error)
    }
    @objc func createDefault(_ pasteboard: NSPasteboard, userData: String?, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        handleService(pasteboard, useDefault: true, error: error)
    }
    private func handleService(_ pasteboard: NSPasteboard, useDefault: Bool, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        var urls = pasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL] ?? []
        if urls.isEmpty, let paths = pasteboard.propertyList(forType: .init("NSFilenamesPboardType")) as? [String] { urls = paths.map { URL(fileURLWithPath: $0) } }
        do { try store.accept(urls, useDefault: useDefault) }
        catch let issue {
            // Finder displays the service error. Do not open our editor or duplicate the alert.
            error.pointee = issue.localizedDescription as NSString
            return
        }
        if useDefault {
            // A service launch must yield focus back to the calling application.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in
                guard self?.window?.isVisible != true else { return }
                NSApp.hide(nil)
            }
        } else {
            showWindow()
        }
    }
}

#if !RENDER_STATES
@main struct XuXiaApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    var body: some Scene {
        Settings { FoldsetSettingsView(store: delegate.store) }
        .commands {
            #if NATIVE_PREVIEW
            CommandMenu("预览检查") {
                Button("深色外观") { NSApp.appearance = NSAppearance(named: .darkAqua) }.keyboardShortcut("d", modifiers: [.command, .shift])
                Divider()
                Button("紧凑窗口 760 × 640") { NSApp.keyWindow?.setContentSize(NSSize(width: 760, height: 640)) }.keyboardShortcut("1", modifiers: [.command, .shift])
                Button("标准窗口 980 × 890") { NSApp.keyWindow?.setContentSize(NSSize(width: 980, height: 890)) }.keyboardShortcut("2", modifiers: [.command, .shift])
                Button("宽窗口 1320 × 890") { NSApp.keyWindow?.setContentSize(NSSize(width: 1320, height: 890)) }.keyboardShortcut("3", modifiers: [.command, .shift])
            }
            #endif
            CommandGroup(replacing: .newItem) {
                Button("显示Foldset") { delegate.showWindow() }.keyboardShortcut("0")
                Button("新建模板") { delegate.store.add(); delegate.showWindow() }.keyboardShortcut("n")
                Button("选择目标文件夹…") { delegate.store.selectTarget() }.keyboardShortcut("o")
                CreateCommand(store: delegate.store)
            }
            CommandGroup(replacing: .help) { Button("Foldset使用说明") { delegate.showHelp() } }
        }
    }
}

/// Observes the store so the menu item enables and disables with the create button.
struct CreateCommand: View {
    @ObservedObject var store: TemplateStore
    var body: some View {
        Button("创建文件夹") { store.create() }
            .keyboardShortcut(.return, modifiers: .command)
            .disabled(!store.canCreate)
    }
}
#endif

struct EntryDropDelegate: DropDelegate {
    let id: UUID
    @Binding var entries: [FolderEntry]
    @Binding var dragging: UUID?
    func dropEntered(info: DropInfo) {
        guard let dragging, dragging != id, let from = entries.firstIndex(where: { $0.id == dragging }), let to = entries.firstIndex(where: { $0.id == id }) else { return }
        withAnimation(.easeInOut(duration: 0.15)) { entries.move(fromOffsets: IndexSet(integer: from), toOffset: to > from ? to + 1 : to) }
    }
    func dropUpdated(info: DropInfo) -> DropProposal? { DropProposal(operation: .move) }
    func performDrop(info: DropInfo) -> Bool { dragging = nil; return true }
}
struct HelpView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("Foldset使用说明", systemImage: "folder.badge.plus").font(.title2.weight(.semibold)).foregroundStyle(.primary)
            Text("1. 选择或新建模板，自定义名称、编号和分隔符。修改会自动保存在本机。")
            Text("2. 选择目标文件夹，核对预览，点击“创建文件夹”。已有目录自动跳过，同名文件或链接会阻止创建。")
            Text("3. 如需 Finder 右键入口，将 App 拖到“应用程序”并打开一次。右键选中一个文件夹，在“服务”中选择“Foldset：按模板创建…”或“Foldset：使用默认模板创建”。")
            Text("4. 若入口未显示，在“系统设置 → 键盘 → 键盘快捷键 → 服务”中检查是否启用。菜单显示由 macOS 管理；无需重启 Finder。")
            Text("每次可在一个目标文件夹中创建单层目录，现有素材会保留。").font(.caption).foregroundStyle(.secondary)
        }.font(.system(size: 13)).lineSpacing(3).padding(12)
    }
}

struct FoldsetSettingsView: View {
    @ObservedObject var store: TemplateStore
    @AppStorage("reduceTransparency") private var reduceTransparency = false
    @AppStorage("reduceMotion") private var reduceMotion = false
    @AppStorage(Updater.autoCheckKey) private var autoCheckUpdates = true
    @ObservedObject private var updater = Updater.shared
    @Environment(\.accessibilityReduceTransparency) private var systemOpaque
    @Environment(\.accessibilityReduceMotion) private var systemStill
    var body: some View {
        TabView {
            Form {
                Section {
                    Picker("默认模板", selection: $store.defaultID) {
                        if store.templates.isEmpty {
                            Text("暂无模板").tag(nil as UUID?)
                        }
                        ForEach(store.templates) { template in
                            Text(template.displayName).tag(Optional(template.id))
                        }
                    }
                    .disabled(store.templates.isEmpty || store.persistenceError != nil)
                } header: { Text("Finder 快速创建") }
                footer: { Text("在 Finder 中右键点击目标文件夹，选择“服务” → “Foldset：使用默认模板创建”。") }
                Section("创建规则") {
                    LabeledContent("已有同名文件夹", value: "保留并跳过")
                    LabeledContent("原有文件与素材", value: "保留")
                }
                Section("软件更新") {
                    UpdateStatusView(updater: updater)
                    Toggle("启动时自动检查更新", isOn: $autoCheckUpdates)
                }
                if let issue = store.persistenceError {
                    Section { Label(issue, systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
                }
            }.tabItem { Label("通用", systemImage: "gearshape") }
            Form {
                Section("主题") {
                    LabeledContent("界面配色", value: "石墨（深色）")
                    Text("中性深色背景，状态用圆点加文字表示，不单靠颜色区分。").font(.caption).foregroundStyle(.secondary)
                }
                Section {
                    Toggle("减少透明度", isOn: $reduceTransparency)
                    Toggle("减少动态效果", isOn: $reduceMotion)
                } header: { Text("显示与交互") }
                footer: { Text("界面背景已全部不透明；减少透明度会再去掉卡片阴影。减少动态效果会关闭按钮缩放与流程更新动画。系统辅助功能偏好始终优先。") }
                if systemOpaque || systemStill {
                    Section { Text("系统已启用：" + [systemOpaque ? "减少透明度" : nil, systemStill ? "减少动态效果" : nil].compactMap { $0 }.joined(separator: "、")).foregroundStyle(.secondary) }
                }
            }.tabItem { Label("外观", systemImage: "paintpalette") }
            ResolveExtensionView(store: store)
                .tabItem { Label("扩展", systemImage: "puzzlepiece.extension") }
            Form {
                Section {
                    HStack(spacing: 16) {
                        Image(nsImage: BrandAsset.icon).resizable().scaledToFit().frame(width: 64, height: 60).accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 5) {
                            Text("Foldset").font(.title2.weight(.semibold))
                            Text("为剪辑项目整理文件夹与媒体夹").foregroundStyle(.secondary)
                        }
                    }.padding(.vertical, 6)
                    LabeledContent("版本", value: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—")
                }
                Section { Text("模板保存在本机，修改后自动保存。").foregroundStyle(.secondary) }
            }.tabItem { Label("关于", systemImage: "info.circle") }
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .padding(16)
        .frame(width: 560, height: 430)
        .background(Theme.canvas)
        .preferredColorScheme(.dark)
    }
}
