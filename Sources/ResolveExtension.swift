import Foundation
import CryptoKit

/// File-only installer. Never launches Resolve, Python, or a compiler.
struct ResolveExtension {
    struct Manifest: Codable, Equatable {
        let version: String
        let files: [String: String]
    }
    enum State: Equatable {
        case absent, installed(String), update(String), incomplete
        var label: String {
            switch self {
            case .absent: return "尚未安装"
            case .installed(let version): return "已安装 · \(version)"
            case .update(let version): return "可更新 · 当前 \(version)"
            case .incomplete: return "安装不完整或旧版安装"
            }
        }
    }
    static let modules = ["bins", "resolve", "usage", "tags", "usage_ui", "moves", "browser", "trash", "dialogs", "pool_cleanup"].map { "foldset_\($0).py" }
    static let launcher = "Finder 使用状态标记.py"
    static let filenames = modules + ["FoldsetTrashFile", launcher]
    let root: URL
    let payload: URL
    private let fm = FileManager.default
    var support: URL { root.appendingPathComponent("Foldset/Resolve") }
    var menu: URL { root.appendingPathComponent("Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/Foldset") }
    var receipt: URL { support.appendingPathComponent("extension-manifest.json") }
    init(root: URL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0], payload: URL) {
        self.root = root
        self.payload = payload
    }
    private func failure(_ message: String) -> Error { FolderIssue(message: message) }
    private func hash(_ url: URL) throws -> String {
        SHA256.hash(data: try Data(contentsOf: url)).map { String(format: "%02x", $0) }.joined()
    }
    private func manifest(_ url: URL) throws -> Manifest {
        let value = try JSONDecoder().decode(Manifest.self, from: Data(contentsOf: url))
        guard Set(value.files.keys) == Set(Self.filenames), !value.version.isEmpty else {
            throw failure("扩展版本清单无效。请重新下载 Foldset。")
        }
        return value
    }
    func bundledManifest() throws -> Manifest {
        let value = try manifest(payload.appendingPathComponent("manifest.json"))
        for name in Self.filenames {
            guard try hash(payload.appendingPathComponent(name)) == value.files[name] else {
                throw failure("随 App 携带的扩展文件损坏：\(name)")
            }
        }
        return value
    }
    private func destination(_ name: String) -> URL {
        (name == Self.launcher ? menu : support).appendingPathComponent(name)
    }
    // Reject symlinks at every existing path component, including parent directories.
    private func checkPath(_ url: URL) throws {
        var current = url.standardizedFileURL
        while current.path != "/" {
            if (try? fm.attributesOfItem(atPath: current.path)[.type]) as? FileAttributeType == .typeSymbolicLink {
                throw failure("路径包含符号链接，未作更改：\(current.path)")
            }
            current.deleteLastPathComponent()
        }
        if fm.fileExists(atPath: url.path) {
            guard (try fm.attributesOfItem(atPath: url.path)[.type]) as? FileAttributeType == .typeRegular else {
                throw failure("预期为普通文件：\(url.path)")
            }
        }
    }
    func state(templates: [FolderTemplate]) -> State {
        let known = Self.filenames.map(destination) + [receipt]
        guard known.contains(where: { fm.fileExists(atPath: $0.path) }) || !(managedMenus().isEmpty) else { return .absent }
        do {
            try checkPath(receipt)
            let installed = try manifest(receipt)
            for name in Self.filenames {
                try checkPath(destination(name))
                guard try hash(destination(name)) == installed.files[name] else { return .incomplete }
            }
            guard fm.isExecutableFile(atPath: destination("FoldsetTrashFile").path) else { return .incomplete }
            let expected = ResolvePresetMenus.contents(templates)
            for (name, content) in expected {
                let file = menu.appendingPathComponent(name)
                try checkPath(file)
                guard try String(contentsOf: file, encoding: .utf8) == content else { return .incomplete }
            }
            guard Set(managedMenus().map(\.lastPathComponent)) == Set(expected.keys) else { return .incomplete }
            let bundled = try bundledManifest()
            return installed == bundled ? .installed(installed.version) : .update(installed.version)
        } catch { return .incomplete }
    }
    private func managedMenus() -> [URL] {
        ((try? fm.contentsOfDirectory(at: menu, includingPropertiesForKeys: nil)) ?? []).filter {
            $0.pathExtension == "py" && ((try? String(contentsOf: $0, encoding: .utf8))?.contains(ResolvePresetMenus.marker) == true)
        }
    }
    /// Exact program files only. User reports, templates, archives and project backups are never traversed.
    func install(templates: [FolderTemplate]) throws {
        let bundled = try bundledManifest()
        var writes = try Dictionary(uniqueKeysWithValues: Self.filenames.map { (destination($0), try Data(contentsOf: payload.appendingPathComponent($0))) })
        let expected = ResolvePresetMenus.contents(templates)
        for (name, content) in expected {
            let target = menu.appendingPathComponent(name)
            if fm.fileExists(atPath: target.path), !managedMenus().contains(target) {
                throw failure("菜单名称与用户文件冲突：\(name)。请先重命名模板。")
            }
            writes[target] = Data(content.utf8)
        }
        // The receipt is committed last, after all files and executable permissions.
        writes[receipt] = try JSONEncoder().encode(bundled)
        let obsolete = managedMenus().filter { expected[$0.lastPathComponent] == nil }
        try transaction(writes: writes, retire: obsolete)
    }
    func uninstall() throws {
        try transaction(writes: [:], retire: Self.filenames.map(destination) + managedMenus() + [receipt])
    }
    private func transaction(writes: [URL: Data], retire: [URL]) throws {
        let targets = Set(writes.keys).union(retire)
        for target in targets { try checkPath(target) }
        let archive = support.appendingPathComponent("InstallBackups/\(UUID().uuidString)")
        try checkPath(archive.appendingPathComponent("probe"))
        try fm.createDirectory(at: archive, withIntermediateDirectories: true)
        // Back up every existing file before changing anything; preserve original permissions.
        var backups: [URL: URL] = [:]
        for target in targets where fm.fileExists(atPath: target.path) {
            let copy = archive.appendingPathComponent(UUID().uuidString + "-" + target.lastPathComponent)
            try fm.copyItem(at: target, to: copy)
            backups[target] = copy
        }
        let recovery = Dictionary(uniqueKeysWithValues: backups.map { ($0.value.lastPathComponent, $0.key.path) })
        try JSONEncoder().encode(recovery).write(to: archive.appendingPathComponent("restore-map.json"), options: .atomic)
        var touched: [URL] = []
        do {
            for target in targets.filter({ $0 != receipt }).sorted(by: { $0.path < $1.path }) + (targets.contains(receipt) ? [receipt] : []) {
                try checkPath(target)
                if let data = writes[target] {
                    try fm.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
                    try data.write(to: target, options: .atomic)
                    touched.append(target)
                    if target.lastPathComponent == "FoldsetTrashFile" {
                        try fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: target.path)
                    }
                } else if fm.fileExists(atPath: target.path) {
                    try fm.moveItem(at: target, to: archive.appendingPathComponent("retired-" + UUID().uuidString + "-" + target.lastPathComponent))
                    touched.append(target)
                }
            }
        } catch {
            var rollbackFailed = false
            for target in touched.reversed() {
                do {
                    if fm.fileExists(atPath: target.path) {
                        try fm.moveItem(at: target, to: archive.appendingPathComponent("failed-" + UUID().uuidString))
                    }
                    if let backup = backups[target] { try fm.copyItem(at: backup, to: target) }
                } catch { rollbackFailed = true }
            }
            throw failure("操作失败：\(error.localizedDescription)\n\(rollbackFailed ? "部分文件未能恢复，请保留备份并检查安装。" : "已恢复本次修改前的程序文件。")\n备份：\(archive.path)")
        }
    }
}
