import Foundation

struct FolderEntry: Codable, Identifiable, Equatable {
    var id = UUID()
    var name: String
}
struct FolderTemplate: Codable, Identifiable, Equatable {
    var id = UUID()
    var name: String
    var numbered = true
    var start = 1
    var digits = 2
    var separator = "_"
    var entries: [FolderEntry]
    var displayName: String { name.isEmpty ? "未命名模板" : name }
    func folderName(at index: Int) -> String {
        let name = entries[index].name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard numbered else { return name }
        let (number, overflow) = start.addingReportingOverflow(index)
        guard !overflow else { return "序号超出范围" + separator + name }
        let value = String(number)
        return String(repeating: "0", count: max(0, min(6, digits) - value.count)) + value + separator + name
    }
    static let samples: [FolderTemplate] = [
        .init(name: "剪辑项目", entries: ["视频素材", "配音字幕", "音乐音效", "工程文件", "输出成片"].map { .init(name: $0) }),
        .init(name: "简单剪辑", digits: 1, entries: ["视频素材", "配音字幕"].map { .init(name: $0) }),
        .init(name: "访谈项目", entries: ["机位A", "机位B", "录音", "工程文件", "成片"].map { .init(name: $0) }),
        .init(name: "包装项目", digits: 1, separator: "-", entries: ["参考资料", "设计素材", "AE工程", "输出"].map { .init(name: $0) })
    ]
}
struct Library: Codable {
    var templates: [FolderTemplate]
    var defaultID: UUID?
}
struct FolderIssue: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}
struct FolderPlan {
    let names: [String]
    let existing: Set<String>
}
struct CreationResult {
    let created: [String]
    let skipped: [String]
    var summary: String { "已创建 \(created.count) 个文件夹，跳过 \(skipped.count) 个已有文件夹。" }
}
/// What creating one folder would do. Computed without writing anything.
enum RowOutcome: Equatable {
    case willCreate
    case exists
    case awaitingTarget
    case blocked(String)
}
struct PreviewRow: Equatable {
    let index: Int
    let name: String
    let outcome: RowOutcome
}
struct CreationPreview: Equatable {
    /// A problem that stops the whole template, independent of any row.
    let templateIssue: String?
    /// A problem with the chosen location, independent of any row.
    let targetIssue: String?
    let rows: [PreviewRow]
    func count(_ match: (RowOutcome) -> Bool) -> Int { rows.filter { match($0.outcome) }.count }
    var willCreate: Int { count { $0 == .willCreate } }
    var existing: Int { count { $0 == .exists } }
    var blocked: Int { count { if case .blocked = $0 { return true }; return false } }
    /// Mirrors `create`: one blocked row or any issue stops the whole run.
    var canCreate: Bool { templateIssue == nil && targetIssue == nil && blocked == 0 && !rows.isEmpty && !rows.contains { $0.outcome == .awaitingTarget } }
}
extension FileManager {
    func isDirectory(_ url: URL) -> Bool {
        var isDir: ObjCBool = false
        return fileExists(atPath: url.path, isDirectory: &isDir) && isDir.boolValue
    }
}
enum FolderEngine {
    static let missingTarget = "目标文件夹不存在，请重新选择。"
    static func conflict(_ name: String) -> String { "目标位置已有同名文件或链接“\(name)”。请先更名；没有创建或覆盖任何内容。" }
    /// Validates every row instead of stopping at the first problem. `names` throws the first issue found here.
    static func validate(_ template: FolderTemplate) -> (issue: String?, names: [String], rowIssues: [String?]) {
        let names = template.entries.indices.map { template.folderName(at: $0) }
        if template.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return ("请先为模板命名。", names, names.map { _ in nil }) }
        if template.entries.isEmpty { return ("请至少添加一个文件夹。", names, []) }
        guard template.start >= 0 && template.start <= 999999 && template.entries.count <= 1000 else {
            return ("起始序号须在 0–999999 之间，文件夹数量不能超过 1000 个。", names, names.map { _ in nil })
        }
        var seen = Set<String>()
        let issues: [String?] = template.entries.indices.map { index in
            let raw = template.entries[index].name.trimmingCharacters(in: .whitespacesAndNewlines)
            let name = names[index]
            guard !raw.isEmpty else { return "第 \(index + 1) 个文件夹名称为空。" }
            guard raw != "." && raw != ".." && !name.hasPrefix(".") && !name.contains("/") && !name.contains(":") && !name.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else {
                return "第 \(index + 1) 个名称无效：不支持斜杠、冒号、控制字符或隐藏文件夹。"
            }
            guard name.utf8.count <= 255 else { return "“\(name)”过长，请缩短名称。" }
            let key = name.precomposedStringWithCanonicalMapping.lowercased()
            guard seen.insert(key).inserted else { return "存在重复名称“\(name)”，请调整名称或开启编号。" }
            return nil
        }
        return (nil, names, issues)
    }
    static func names(for template: FolderTemplate) throws -> [String] {
        let result = validate(template)
        if let issue = result.issue ?? result.rowIssues.compactMap({ $0 }).first { throw FolderIssue(message: issue) }
        return result.names
    }
    /// Read-only. Applies the same rules as `plan` to every row, so the UI can show each outcome with its reason.
    static func preview(template: FolderTemplate, target: URL?) -> CreationPreview {
        let checked = validate(template)
        let targetIssue = target.map { $0.isFileURL && FileManager.default.isDirectory($0) } == false ? missingTarget : nil
        let rows = checked.names.indices.map { index -> PreviewRow in
            let name = checked.names[index]
            if let issue = checked.rowIssues.indices.contains(index) ? checked.rowIssues[index] : nil {
                return PreviewRow(index: index, name: name, outcome: .blocked(issue))
            }
            guard let target, targetIssue == nil, checked.issue == nil else { return PreviewRow(index: index, name: name, outcome: .awaitingTarget) }
            let child = target.appendingPathComponent(name, isDirectory: true)
            guard let attrs = try? FileManager.default.attributesOfItem(atPath: child.path) else { return PreviewRow(index: index, name: name, outcome: .willCreate) }
            guard attrs[.type] as? FileAttributeType == .typeDirectory else {
                return PreviewRow(index: index, name: name, outcome: .blocked(conflict(name)))
            }
            return PreviewRow(index: index, name: name, outcome: .exists)
        }
        return CreationPreview(templateIssue: checked.issue, targetIssue: targetIssue, rows: rows)
    }
    static func plan(template: FolderTemplate, target: URL) throws -> FolderPlan {
        let names = try names(for: template)
        let fm = FileManager.default
        guard target.isFileURL && fm.isDirectory(target) else { throw FolderIssue(message: missingTarget) }
        var existing = Set<String>()
        for name in names {
            let child = target.appendingPathComponent(name, isDirectory: true)
            if let attrs = try? fm.attributesOfItem(atPath: child.path) {
                guard attrs[.type] as? FileAttributeType == .typeDirectory else { throw FolderIssue(message: conflict(name)) }
                existing.insert(name)
            }
        }
        return FolderPlan(names: names, existing: existing)
    }
    static func create(template: FolderTemplate, target: URL) throws -> CreationResult {
        let plan = try plan(template: template, target: target)
        var created: [String] = [], skipped: [String] = []
        for name in plan.names {
            if plan.existing.contains(name) { skipped.append(name); continue }
            do {
                try FileManager.default.createDirectory(at: target.appendingPathComponent(name, isDirectory: true), withIntermediateDirectories: false)
                created.append(name)
            } catch {
                throw FolderIssue(message: "创建“\(name)”失败：\(error.localizedDescription)\n本次已创建 \(created.count) 个，跳过 \(skipped.count) 个。已创建的文件夹保留，现有内容未覆盖。")
            }
        }
        return CreationResult(created: created, skipped: skipped)
    }
}

enum AppVersion {
    /// True when `remote` (e.g. "v1.3.0") is a later dotted version than `local` (e.g. "1.2.2").
    static func isNewer(_ remote: String, than local: String) -> Bool {
        func parts(_ v: String) -> [Int] {
            v.trimmingCharacters(in: CharacterSet(charactersIn: "vV ")).split(separator: ".").map { Int($0.prefix { $0.isNumber }) ?? 0 }
        }
        let r = parts(remote), l = parts(local)
        for i in 0..<max(r.count, l.count) {
            let a = i < r.count ? r[i] : 0, b = i < l.count ? l[i] : 0
            if a != b { return a > b }
        }
        return false
    }
}
