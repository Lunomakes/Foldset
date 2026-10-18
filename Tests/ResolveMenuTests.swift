import Foundation
@main struct ResolveMenuTests {
    static func main() throws {
        let fm = FileManager.default
        let root = URL(fileURLWithPath: CommandLine.arguments[1])
        let integration = root.appendingPathComponent("Foldset/Resolve")
        try fm.createDirectory(at: integration, withIntermediateDirectories: true)
        try "".write(to: integration.appendingPathComponent("foldset_resolve.py"), atomically: true, encoding: .utf8)
        let menu = root.appendingPathComponent("Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/Foldset")
        var first = FolderTemplate(name: "剪辑/项目", entries: [.init(name: "素材")])
        let second = FolderTemplate(name: "剪辑/项目", entries: [.init(name: "输出")])
        try ResolvePresetMenus.sync([first, second], supportRoot: root)
        let names = try fm.contentsOfDirectory(atPath: menu.path)
        precondition(names.count == 2 && names.contains("01 剪辑_项目.py"))
        let script = try String(contentsOf: menu.appendingPathComponent("01 剪辑_项目.py"), encoding: .utf8)
        precondition(script.contains(first.id.uuidString) && script.contains("template_id="))
        first.name = "改名"
        try ResolvePresetMenus.sync([first], supportRoot: root)
        let renamed = try fm.contentsOfDirectory(atPath: menu.path)
        precondition(renamed.count == 1)
        let archived = try fm.contentsOfDirectory(atPath: integration.appendingPathComponent("MenuArchive").path)
        precondition(archived.count == 2)
        try ResolvePresetMenus.sync([], supportRoot: root)
        let empty = try fm.contentsOfDirectory(atPath: menu.path)
        precondition(empty.isEmpty)
        print("PASS: direct IDs, duplicate names, safe filenames, rename, removal and archival")
    }
}
