import Foundation
import Darwin

@main struct ResolveExtensionTests {
    static func main() throws {
        let fm = FileManager.default
        let root = URL(fileURLWithPath: fm.currentDirectoryPath).appendingPathComponent("output").appendingPathComponent("FoldsetExtensionTests-" + UUID().uuidString)
        let payload = URL(fileURLWithPath: CommandLine.arguments[1])
        // First launch: sample templates must exist on disk before menu installation.
        let firstRoot = root.appendingPathComponent("first-launch")
        let libraryURL = firstRoot.appendingPathComponent("XuXia/templates.json")
        let firstStore = TemplateStore(fileURL: libraryURL)
        let firstInstaller = ResolveExtension(root: firstRoot, payload: payload)
        precondition(!fm.fileExists(atPath: libraryURL.path))
        try firstInstaller.install(templates: firstStore.prepareResolveTemplates())
        let saved = try JSONDecoder().decode(Library.self, from: Data(contentsOf: libraryURL))
        precondition(saved.templates == firstStore.templates)
        for (name, contents) in ResolvePresetMenus.contents(saved.templates) {
            precondition(tryString(firstInstaller.menu.appendingPathComponent(name)) == contents)
        }
        // A damaged library must never be replaced with the in-memory examples.
        let corruptURL = root.appendingPathComponent("corrupt-library.json")
        try "broken".write(to: corruptURL, atomically: true, encoding: .utf8)
        let corruptStore = TemplateStore(fileURL: corruptURL)
        let blockedInstaller = ResolveExtension(root: root.appendingPathComponent("blocked-install"), payload: payload)
        do {
            try blockedInstaller.install(templates: corruptStore.prepareResolveTemplates())
            fatalError("Corrupt library must prevent installation")
        } catch {}
        precondition(tryString(corruptURL) == "broken")
        precondition(!fm.fileExists(atPath: blockedInstaller.support.path))
        // A write failure must also stop before any extension program is deployed.
        let blockedStore = TemplateStore(fileURL: corruptURL.appendingPathComponent("templates.json"))
        do {
            try blockedInstaller.install(templates: blockedStore.prepareResolveTemplates())
            fatalError("Failed persistence must prevent installation")
        } catch {}
        precondition(!fm.fileExists(atPath: blockedInstaller.support.path))
        let installer = ResolveExtension(root: root, payload: payload)
        let templates = [FolderTemplate(name: "测试模板", entries: [.init(name: "素材")])]
        precondition(installer.state(templates: templates) == .absent)
        precondition(!fm.fileExists(atPath: installer.support.path), "Checking must not install or create directories")
        try installer.install(templates: templates)
        let bundled = try installer.bundledManifest()
        precondition(installer.state(templates: templates) == .installed(bundled.version))
        precondition(fm.isExecutableFile(atPath: installer.support.appendingPathComponent("FoldsetTrashFile").path))
        let source = installer.support.appendingPathComponent("foldset_bins.py")
        try "broken".write(to: source, atomically: true, encoding: .utf8)
        precondition(installer.state(templates: templates) == .incomplete)
        try installer.install(templates: templates)
        let old = ResolveExtension.Manifest(version: "0.9.0", files: bundled.files)
        try JSONEncoder().encode(old).write(to: installer.receipt)
        precondition(installer.state(templates: templates) == .update("0.9.0"))
        try installer.install(templates: templates)
        precondition(installer.state(templates: templates) == .installed(bundled.version))
        let helper = installer.support.appendingPathComponent("FoldsetTrashFile")
        try fm.setAttributes([.posixPermissions: 0o644], ofItemAtPath: helper.path)
        precondition(installer.state(templates: templates) == .incomplete)
        try installer.install(templates: templates)
        precondition(installer.state(templates: templates) == .installed(bundled.version))
        let savedReceipt = root.appendingPathComponent("saved-receipt.json")
        try fm.moveItem(at: installer.receipt, to: savedReceipt)
        try fm.createSymbolicLink(at: installer.receipt, withDestinationURL: savedReceipt)
        precondition(installer.state(templates: templates) == .incomplete)
        do { try installer.install(templates: templates); fatalError("Must reject linked receipt") } catch {}
        try fm.moveItem(at: installer.receipt, to: root.appendingPathComponent("retired-receipt-link"))
        try fm.moveItem(at: savedReceipt, to: installer.receipt)
        // Migrate a complete legacy install with no receipt, preserving its data.
        try fm.moveItem(at: installer.receipt, to: root.appendingPathComponent("legacy-receipt.json"))
        precondition(installer.state(templates: templates) == .incomplete)
        try installer.install(templates: templates)
        precondition(installer.state(templates: templates) == .installed(bundled.version))
        // A late filesystem failure must restore already-written menus and modules.
        let locked = installer.support.appendingPathComponent("foldset_usage.py")
        let originalModule = try Data(contentsOf: source)
        let originalReceipt = try Data(contentsOf: installer.receipt)
        let originalMenu = try Data(contentsOf: installer.menu.appendingPathComponent("01 测试模板.py"))
        precondition(chflags(locked.path, UInt32(UF_IMMUTABLE)) == 0)
        do {
            defer { precondition(chflags(locked.path, 0) == 0) }
            do {
                try installer.install(templates: [FolderTemplate(name: "更新中的模板", entries: [])])
                fatalError("Locked program must fail installation")
            } catch {
                precondition(error.localizedDescription.contains("已恢复本次修改前"), error.localizedDescription)
            }
            precondition(tryData(source) == originalModule)
            precondition(tryData(installer.receipt) == originalReceipt)
            precondition(tryData(installer.menu.appendingPathComponent("01 测试模板.py")) == originalMenu)
            precondition(!fm.fileExists(atPath: installer.menu.appendingPathComponent("01 更新中的模板.py").path))
        }
        precondition(installer.state(templates: templates) == .installed(bundled.version))
        // The same late failure during uninstall must restore earlier retired files.
        precondition(chflags(locked.path, UInt32(UF_IMMUTABLE)) == 0)
        do {
            defer { precondition(chflags(locked.path, 0) == 0) }
            do { try installer.uninstall(); fatalError("Locked program must fail uninstall") }
            catch { precondition(error.localizedDescription.contains("已恢复本次修改前"), error.localizedDescription) }
        }
        precondition(installer.state(templates: templates) == .installed(bundled.version))
        // Menu conflicts must not overwrite user scripts or partially update the payload.
        let conflict = installer.menu.appendingPathComponent("01 冲突.py")
        try "user script".write(to: conflict, atomically: true, encoding: .utf8)
        do {
            try installer.install(templates: [FolderTemplate(name: "冲突", entries: [])])
            fatalError("Must reject menu collision")
        } catch {}
        precondition(tryString(conflict) == "user script")
        precondition(installer.state(templates: templates) == .installed(bundled.version))
        // Missing menus are detected and repaired too.
        let generated = installer.menu.appendingPathComponent("01 测试模板.py")
        try fm.moveItem(at: generated, to: root.appendingPathComponent("saved-menu.py"))
        precondition(installer.state(templates: templates) == .incomplete)
        try installer.install(templates: templates)
        // All user data must survive uninstall, including unrelated files in the same directory.
        let preserved = ["UsageReports/log.json", "MoveReports/log.json", "TrashReports/log.json", "ProjectBackups/project.drp", "custom.py"].map { installer.support.appendingPathComponent($0) } + [root.appendingPathComponent("XuXia/templates.json")]
        for url in preserved {
            try fm.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try "user data".write(to: url, atomically: true, encoding: .utf8)
        }
        try installer.uninstall()
        for url in preserved { precondition(tryString(url) == "user data") }
        precondition(tryString(conflict) == "user script")
        precondition(installer.state(templates: templates) == .absent)
        // A delayed template-save callback must not reinstall a removed extension.
        try ResolvePresetMenus.sync(templates, supportRoot: root)
        precondition(installer.state(templates: templates) == .absent)
        precondition(!fm.fileExists(atPath: generated.path))
        try installer.install(templates: templates)
        precondition(installer.state(templates: templates) == .installed(bundled.version))
        // Reject symlink destinations before touching any files.
        try fm.moveItem(at: source, to: root.appendingPathComponent("saved-module.py"))
        let outside = root.appendingPathComponent("outside.txt")
        try "untouched".write(to: outside, atomically: true, encoding: .utf8)
        try fm.createSymbolicLink(at: source, withDestinationURL: outside)
        do { try installer.install(templates: templates); fatalError("Must reject symlink") } catch {}
        precondition(tryString(outside) == "untouched")
        // Corrupt packaged content cannot be installed.
        let badPayload = root.appendingPathComponent("bad-payload")
        try fm.copyItem(at: payload, to: badPayload)
        try "broken".write(to: badPayload.appendingPathComponent("foldset_bins.py"), atomically: true, encoding: .utf8)
        do { try ResolveExtension(root: root.appendingPathComponent("clean"), payload: badPayload).install(templates: templates); fatalError("Must reject broken package") } catch {}
        print("PASS: first-launch persistence, corrupt/unwritable library protection, legacy migration, install/uninstall failure rollback, opt-in, install, executable, corruption, repair, update, menu conflict/missing, data preservation, no reinstall, symlink and package validation")
        print("Isolated test artifacts: \(root.path)")
    }
    static func tryData(_ url: URL) -> Data? { try? Data(contentsOf: url) }
    static func tryString(_ url: URL) -> String { (try? String(contentsOf: url, encoding: .utf8)) ?? "" }
}
