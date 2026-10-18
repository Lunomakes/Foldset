import SwiftUI
import AppKit

final class TemplateStore: ObservableObject {
    @Published var templates: [FolderTemplate] { didSet { save(); refreshPreview() } }
    @Published var defaultID: UUID? { didSet { save() } }
    @Published var selectedID: UUID? { didSet { if selectedID != oldValue { outcome = nil; refreshPreview() } } }
    @Published var target: URL? { didSet { if target != oldValue { outcome = nil; refreshPreview() } } }
    @Published var notice: Notice?
    /// Read-only check of what creating the selected template would do; `previewID` names its template.
    @Published var preview: CreationPreview?
    @Published var previewID: UUID?
    /// Only becomes true when a check takes longer than 200 ms, e.g. on a network volume.
    @Published var checking = false
    @Published var outcome: Outcome?
    private var previewGeneration = 0
    @Published var persistenceError: String?
    private let syncResolveMenus: Bool
    private var menuSyncWork: DispatchWorkItem?
    private var allowSave = false
    private let fileURL: URL
    struct Outcome: Equatable {
        let succeeded: Bool
        let message: String
        let target: URL
    }
    struct Notice: Identifiable {
        var id = UUID()
        let title: String
        let message: String
    }
    init(fileURL: URL? = nil) {
        syncResolveMenus = fileURL == nil
        self.fileURL = fileURL ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("XuXia/templates.json")
        var loaded = Library(templates: FolderTemplate.samples, defaultID: FolderTemplate.samples.first?.id)
        var issue: String?
        if FileManager.default.fileExists(atPath: self.fileURL.path) {
            do {
                loaded = try JSONDecoder().decode(Library.self, from: Data(contentsOf: self.fileURL))
                guard Set(loaded.templates.map(\.id)).count == loaded.templates.count,
                      loaded.templates.allSatisfy({ Set($0.entries.map(\.id)).count == $0.entries.count }) else { throw FolderIssue(message: "模板标识重复。") }
            } catch { issue = "无法读取已保存的模板。原文件已保留，本次修改不会保存。\n\(error.localizedDescription)" }
        }
        templates = loaded.templates
        defaultID = loaded.templates.contains(where: { $0.id == loaded.defaultID }) ? loaded.defaultID : loaded.templates.first?.id
        selectedID = defaultID ?? templates.first?.id
        persistenceError = issue
        allowSave = issue == nil
        if allowSave { scheduleResolveMenuSync() }
        refreshPreview()
    }
    /// Results from an older edit are dropped, so the preview always matches the latest template and target.
    func refreshPreview() {
        guard let template = selected else { preview = nil; previewID = nil; checking = false; return }
        previewGeneration += 1
        let generation = previewGeneration, target = self.target
        let slow = DispatchWorkItem { [weak self] in
            if self?.previewGeneration == generation { self?.checking = true }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: slow)
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = FolderEngine.preview(template: template, target: target)
            DispatchQueue.main.async {
                guard let self, self.previewGeneration == generation else { return }
                slow.cancel()
                self.checking = false
                self.preview = result
                self.previewID = template.id
            }
        }
    }
    /// The preview for the selected template, or nil while it is still being computed.
    var currentPreview: CreationPreview? {
        guard let preview, previewID == selectedID, preview.rows.count == (selected?.entries.count ?? -1) else { return nil }
        return preview
    }
    /// Shared by the create button and the 文件 menu item.
    var canCreate: Bool { currentPreview?.canCreate == true && !checking }
    var selected: FolderTemplate? { templates.first { $0.id == selectedID } }
    func save() {
        guard allowSave else { return }
        do {
            try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(Library(templates: templates, defaultID: defaultID)).write(to: fileURL, options: .atomic)
            persistenceError = nil
            scheduleResolveMenuSync()
        } catch { persistenceError = "模板保存失败：\(error.localizedDescription)" }
    }
    /// Resolve reads the library from disk, including on the very first app launch.
    func prepareResolveTemplates() throws -> [FolderTemplate] {
        guard allowSave else {
            throw FolderIssue(message: persistenceError ?? "无法保存模板，扩展尚未安装。")
        }
        save()
        if let issue = persistenceError { throw FolderIssue(message: issue) }
        return templates
    }
    func add() {
        let item = FolderTemplate(name: "新模板", entries: [.init(name: "视频素材"), .init(name: "工程文件")])
        templates.append(item); selectedID = item.id
        if defaultID == nil { defaultID = item.id }
    }
    func duplicate() {
        guard var item = selected else { return }
        item.id = UUID(); item.name += " 副本"; item.entries = item.entries.map { FolderEntry(name: $0.name) }
        templates.append(item); selectedID = item.id
    }
    func deleteSelected() {
        guard let id = selectedID else { return }
        templates.removeAll { $0.id == id }
        selectedID = templates.first?.id
        if defaultID == id { defaultID = selectedID }
    }
    func selectTarget() {
        let panel = NSOpenPanel()
        panel.title = "选择要创建文件夹的位置"; panel.prompt = "选择此文件夹"
        panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        if let target { panel.directoryURL = target }
        if panel.runModal() == .OK { target = panel.url }
    }
    func accept(_ urls: [URL], useDefault: Bool) throws {
        guard urls.count == 1 else { throw FolderIssue(message: "请只选择一个目标文件夹。") }
        guard FileManager.default.isDirectory(urls[0]) else { throw FolderIssue(message: "请选择文件夹，而不是文件。") }
        if useDefault {
            guard let template = templates.first(where: { $0.id == defaultID }) else { throw FolderIssue(message: "请先在Foldset中设置默认模板。") }
            _ = try FolderEngine.create(template: template, target: urls[0])
        } else {
            target = urls[0]
        }
    }
    func create() {
        guard let template = selected, let target else { return }
        do { outcome = Outcome(succeeded: true, message: try FolderEngine.create(template: template, target: target).summary, target: target) }
        catch { outcome = Outcome(succeeded: false, message: error.localizedDescription, target: target) }
        refreshPreview()
    }
}

extension TemplateStore {
    private func scheduleResolveMenuSync() {
        guard syncResolveMenus else { return }
        menuSyncWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            do { try ResolvePresetMenus.sync(self.templates) }
            catch { self.persistenceError = "模板已保存，但达芬奇菜单同步失败：\(error.localizedDescription)" }
        }
        menuSyncWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6, execute: work)
    }
}

/// Only manages explicitly marked Foldset files; obsolete entries are archived.
enum ResolvePresetMenus {
    static let marker = "# Foldset managed preset"
    static func contents(_ templates: [FolderTemplate]) -> [String: String] {
        var desired: [String: String] = [:]
        for (index, template) in templates.enumerated() {
            let clean = template.name.trimmingCharacters(in: .whitespacesAndNewlines).unicodeScalars.map {
                CharacterSet.controlCharacters.contains($0) || $0 == "/" || $0 == ":" ? "_" : String($0)
            }.joined()
            let name = clean.isEmpty ? "未命名模板" : String(clean.prefix(60))
            let filename = String(format: "%02d", index + 1) + " " + name + ".py"
            desired[filename] = """
            # -*- coding: utf-8 -*-
            # Foldset managed preset
            import sys
            from pathlib import Path
            support = str(Path.home() / 'Library/Application Support/Foldset/Resolve')
            if support not in sys.path:
                sys.path.insert(0, support)
            import importlib
            import foldset_bins
            import foldset_resolve
            importlib.reload(foldset_bins)
            importlib.reload(foldset_resolve)
            foldset_resolve.main(resolve, bmd, template_id="\(template.id.uuidString)")

            """
        }
        return desired
    }
    static func sync(_ templates: [FolderTemplate], supportRoot: URL? = nil) throws {
        let fm = FileManager.default
        let support = supportRoot ?? fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        guard fm.fileExists(atPath: support.appendingPathComponent("Foldset/Resolve/foldset_resolve.py").path) else { return }
        let menu = support.appendingPathComponent("Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/Foldset")
        let archive = support.appendingPathComponent("Foldset/Resolve/MenuArchive")
        try fm.createDirectory(at: menu, withIntermediateDirectories: true)
        let desired = contents(templates)
        let files = try fm.contentsOfDirectory(at: menu, includingPropertiesForKeys: nil).filter { $0.pathExtension == "py" }
        // Preflight collisions before modifying the generated menu.
        for file in files where desired[file.lastPathComponent] != nil {
            guard try String(contentsOf: file, encoding: .utf8).contains(marker) else {
                throw FolderIssue(message: "菜单中存在非 Foldset 文件：\(file.lastPathComponent)")
            }
        }
        for file in files where desired[file.lastPathComponent] == nil {
            guard try String(contentsOf: file, encoding: .utf8).contains(marker) else { continue }
            try fm.createDirectory(at: archive, withIntermediateDirectories: true)
            try fm.moveItem(at: file, to: archive.appendingPathComponent(UUID().uuidString + "-" + file.lastPathComponent))
        }
        for (filename, contents) in desired {
            let target = menu.appendingPathComponent(filename)
            if (try? String(contentsOf: target, encoding: .utf8)) != contents {
                try contents.write(to: target, atomically: true, encoding: .utf8)
            }
        }
    }
}
