import SwiftUI
import AppKit

/// Renders every SwiftUI UI state to PNG.
/// Shows each state in a real window briefly and captures it, because ImageRenderer cannot draw AppKit-backed controls.
/// Only writes inside the directory given as the first argument.
@main struct RenderStates {
    static let out = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
    static let fixtures = out.appendingPathComponent("fixtures", isDirectory: true)
    static let fm = FileManager.default

    static func main() throws {
        _ = NSApplication.shared
        NSApp.setActivationPolicy(.prohibited)
        NSApp.appearance = NSAppearance(named: .darkAqua)
        try fm.createDirectory(at: fixtures, withIntermediateDirectories: true)
        var count = 0
        func shot(_ name: String, size: NSSize = NSSize(width: 1180, height: 1040), late: ((TemplateStore) -> Void)? = nil, _ make: () throws -> (TemplateStore, (TemplateStore) -> Void)) throws {
            let (store, adjust) = try make()
            settle()
            adjust(store)
            render(NativeMainView(store: store), name: name, size: size, late: late.map { late in { late(store) } })
            count += 1
        }
        // S1 — empty: library exists but holds no templates.
        try shot("S1-empty") { (try store("empty", library: #"{"templates":[]}"#), { _ in }) }
        // S1 — no target yet: every row waits for a location.
        try shot("S1-awaiting-target") { (try store("samples"), { _ in }) }
        // S1 — success: empty target, every row will be created.
        try shot("S1-success") { (try store("samples"), { $0.target = try? target("clean"); settle() }) }
        // S1 — partial: two folders already exist and are skipped.
        try shot("S1-partial") { (try store("samples"), { s in
            let t = try? target("partial", folders: ["01_视频素材", "03_音乐音效"]); s.target = t; settle() }) }
        // S1 — blocked: a same-named file stops the whole run.
        try shot("S1-blocked") { (try store("samples"), { s in
            let t = try? target("blocked", folders: ["01_视频素材"], files: ["04_工程文件"]); s.target = t; settle() }) }
        // S1 — invalid names: empty and duplicate rows are listed individually.
        try shot("S1-invalid-names") { (try store("samples"), { s in
            s.templates[0].entries.append(FolderEntry(name: ""))
            s.templates[0].entries.append(FolderEntry(name: "视频素材"))
            s.templates[0].numbered = false
            s.target = try? target("invalid"); settle() }) }
        // S1 — loading: a slow volume is still being checked.
        // Set after the window appears: building the view writes bindings back, which refreshes the preview.
        try shot("S1-loading", late: { s in s.preview = nil; s.checking = true }) { (try store("samples"), { s in
            s.target = try? target("loading"); settle() }) }
        // S1 — disabled: the saved library cannot be read, so edits are not saved.
        try shot("S1-persistence-error") { (try store("corrupt", library: "broken"), { _ in }) }
        // S2 — created: inline result after creating.
        try shot("S2-created") { (try store("samples"), { s in
            s.target = try? target("created", folders: ["02_配音字幕"]); settle(); s.create(); settle() }) }
        // S2 — failed midway: inline error, created folders kept.
        try shot("S2-failed") { (try store("samples"), { s in
            let t = try? target("failed"); s.target = t; settle()
            s.outcome = .init(succeeded: false, message: "创建“03_音乐音效”失败：权限不足。\n本次已创建 2 个，跳过 0 个。已创建的文件夹保留，现有内容未覆盖。", target: t!) }) }
        // Narrow window: the diagram falls back to a stacked layout.
        try shot("S1-narrow-760", size: NSSize(width: 760, height: 900)) { (try store("samples"), { s in
            s.target = try? target("narrow", folders: ["01_视频素材"]); settle() }) }
        // Settings tabs.
        let settingsStore = try store("settings")
        settle()
        render(FoldsetSettingsView(store: settingsStore), name: "S3-settings-general", size: NSSize(width: 560, height: 430))
        count += 1
        print("Rendered \(count) states to \(out.path)")
    }

    static func store(_ name: String, library: String? = nil) throws -> TemplateStore {
        let url = fixtures.appendingPathComponent("library-\(name)-\(UUID().uuidString).json")
        if let library { try Data(library.utf8).write(to: url) }
        return TemplateStore(fileURL: url)
    }
    static func target(_ name: String, folders: [String] = [], files: [String] = []) throws -> URL {
        let url = fixtures.appendingPathComponent("工博会-\(name)", isDirectory: true)
        try? fm.removeItem(at: url)
        try fm.createDirectory(at: url, withIntermediateDirectories: true)
        for folder in folders { try fm.createDirectory(at: url.appendingPathComponent(folder), withIntermediateDirectories: false) }
        for file in files { try Data().write(to: url.appendingPathComponent(file)) }
        return url
    }
    static func settle(_ seconds: Double = 0.35) {
        RunLoop.main.run(until: Date().addingTimeInterval(seconds))
    }
    static func render<V: View>(_ view: V, name: String, size: NSSize, late: (() -> Void)? = nil) {
        let window = NSWindow(contentRect: NSRect(origin: NSPoint(x: 60, y: 60), size: size),
                              styleMask: [.titled, .closable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = NSColor(Theme.canvas)
        window.contentView = NSHostingView(rootView: view)
        window.orderFrontRegardless()
        settle(0.8)
        window.makeFirstResponder(nil)
        settle(0.3)  // ending editing commits field values, which refreshes the preview
        if let late { late(); settle(0.1) }
        let file = out.appendingPathComponent(name + ".png")
        // Capture the real window: cacheDisplay cannot draw the sidebar's visual-effect view or List rows.
        // Needs Screen Recording permission; falls back to cacheDisplay (sidebar then renders blank).
        let capture = Process()
        capture.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        capture.arguments = ["-x", "-o", "-l", String(window.windowNumber), file.path]
        if (try? capture.run()) != nil { capture.waitUntilExit() }
        if capture.terminationStatus != 0 || !fm.fileExists(atPath: file.path) {
            print("screencapture unavailable for \(name); using cacheDisplay")
            let frame = window.contentView!.superview ?? window.contentView!
            if let rep = frame.bitmapImageRepForCachingDisplay(in: frame.bounds) {
                frame.cacheDisplay(in: frame.bounds, to: rep)
                try? rep.representation(using: .png, properties: [:])?.write(to: file)
            }
        }
        window.orderOut(nil)
    }
}
