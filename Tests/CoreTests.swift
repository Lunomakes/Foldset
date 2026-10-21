import Foundation

@main struct Tests {
    static func main() throws {
        let fm = FileManager.default
        let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        var count = 0
        func check(_ condition: Bool, _ name: String) {
            guard condition else { fatalError("FAIL: \(name)") }; count += 1; print("PASS: \(name)")
        }
        func rejects(_ name: String, _ action: () throws -> Void) {
            do { try action(); fatalError("FAIL expected rejection: \(name)") } catch { count += 1; print("PASS: \(name)") }
        }
        var template = FolderTemplate(name: "测试", entries: [.init(name: "视频素材"), .init(name: "配音字幕")])
        check(try FolderEngine.names(for: template) == ["01_视频素材", "02_配音字幕"], "中文编号")
        let first = try FolderEngine.create(template: template, target: root)
        check(first.created.count == 2, "实际创建两个文件夹")
        let second = try FolderEngine.create(template: template, target: root)
        check(second.created.isEmpty && second.skipped.count == 2, "重复创建跳过已有目录")
        try Data("keep footage".utf8).write(to: root.appendingPathComponent("01_视频素材/素材.txt"))
        _ = try FolderEngine.create(template: template, target: root)
        let preserved = try String(contentsOf: root.appendingPathComponent("01_视频素材/素材.txt"), encoding: .utf8)
        check(preserved == "keep footage", "原有素材不变")
        template.entries = [.init(name: "应不创建"), .init(name: "冲突")]
        try Data("existing".utf8).write(to: root.appendingPathComponent("02_冲突"))
        rejects("同名文件拦截") { _ = try FolderEngine.create(template: template, target: root) }
        check(!fm.fileExists(atPath: root.appendingPathComponent("01_应不创建").path), "完整预检避免部分创建")
        template.numbered = false
        template.entries = [.init(name: "same"), .init(name: "SAME")]
        rejects("忽略大小写重复名称") { _ = try FolderEngine.names(for: template) }
        template.entries = [.init(name: "é"), .init(name: "e\u{301}")]
        rejects("Unicode 等价重复名称") { _ = try FolderEngine.names(for: template) }
        for name in ["", "  ", "../escape", "bad:name", "bad\nname", ".hidden", ".", "..", String(repeating: "中", count: 100)] {
            template.entries = [.init(name: name)]
            rejects("无效名称 \(name.debugDescription.prefix(25))") { _ = try FolderEngine.names(for: template) }
        }
        template.entries = [.init(name: "链接")]
        try fm.createSymbolicLink(at: root.appendingPathComponent("链接"), withDestinationURL: root.appendingPathComponent("01_视频素材"))
        rejects("不跟随已有符号链接") { _ = try FolderEngine.create(template: template, target: root) }
        template.entries = [.init(name: "断链")]
        try fm.createSymbolicLink(at: root.appendingPathComponent("断链"), withDestinationURL: root.appendingPathComponent("不存在"))
        rejects("断链也拦截") { _ = try FolderEngine.create(template: template, target: root) }
        rejects("目标必须存在") { _ = try FolderEngine.create(template: template, target: root.appendingPathComponent("missing")) }
        template.numbered = true; template.start = 8; template.digits = 3; template.separator = "-"; template.entries = [.init(name: " A "), .init(name: "B")]
        check(try FolderEngine.names(for: template) == ["008-A", "009-B"], "起始序号位数和分隔符")
        template.entries.swapAt(0, 1)
        check(template.folderName(at: 0) == "008-B", "调整顺序重新编号")
        template.start = -1
        rejects("负序号校验") { _ = try FolderEngine.names(for: template) }
        template.start = Int.max
        check(template.folderName(at: 1).hasPrefix("序号超出范围"), "超大序号预览不会溢出")
        rejects("超大序号不能创建") { _ = try FolderEngine.names(for: template) }
        let storage = root.appendingPathComponent("library/templates.json")
        let store = TemplateStore(fileURL: storage)
        store.add(); store.templates[store.templates.count - 1].name = "持久化测试"; store.defaultID = store.templates.last?.id
        let reloaded = TemplateStore(fileURL: storage)
        check(reloaded.templates.last?.name == "持久化测试" && reloaded.defaultID == store.defaultID, "模板与默认设置持久化")
        reloaded.selectedID = reloaded.defaultID; reloaded.duplicate()
        check(Set(reloaded.templates.map(\.id)).count == reloaded.templates.count, "复制模板使用独立标识")
        reloaded.deleteSelected()
        check(reloaded.templates.count == store.templates.count, "删除仅移除模板")
        rejects("拒绝多目标服务输入") { try store.accept([root, root], useDefault: false) }
        let serviceTarget = root.appendingPathComponent("service-target")
        try fm.createDirectory(at: serviceTarget, withIntermediateDirectories: false)
        try store.accept([serviceTarget], useDefault: false)
        check(try fm.contentsOfDirectory(atPath: serviceTarget.path).isEmpty, "选模板入口不提前创建")
        store.target = root
        let editorSelection = store.selectedID
        try store.accept([serviceTarget], useDefault: true)
        check(store.notice == nil, "默认模板成功不弹消息")
        check(store.target == root && store.selectedID == editorSelection, "默认模板不干扰编辑器状态")
        check(try fm.contentsOfDirectory(atPath: serviceTarget.path).count == 2, "默认模板入口立即创建")
        let corrupt = root.appendingPathComponent("corrupt.json")
        try Data("broken".utf8).write(to: corrupt)
        let bad = TemplateStore(fileURL: corrupt); bad.add()
        check(bad.persistenceError != nil, "损坏模板库提供错误")
        check(try String(contentsOf: corrupt, encoding: .utf8) == "broken", "损坏模板库不被覆盖")
        let previewRoot = root.appendingPathComponent("preview-target")
        try fm.createDirectory(at: previewRoot, withIntermediateDirectories: false)
        var sample = FolderTemplate(name: "预览", entries: [.init(name: "视频素材"), .init(name: "配音字幕"), .init(name: "成片")])
        let unchosen = FolderEngine.preview(template: sample, target: nil)
        check(unchosen.rows.allSatisfy { $0.outcome == .awaitingTarget } && !unchosen.canCreate, "未选目标时逐行待定且不可创建")
        try fm.createDirectory(at: previewRoot.appendingPathComponent("01_视频素材"), withIntermediateDirectories: false)
        let mixed = FolderEngine.preview(template: sample, target: previewRoot)
        check(mixed.rows.map(\.outcome) == [.exists, .willCreate, .willCreate] && mixed.canCreate, "预览区分已存在与将创建")
        check(try fm.contentsOfDirectory(atPath: previewRoot.path).count == 1, "预览不写入目标")
        let plan = try FolderEngine.plan(template: sample, target: previewRoot)
        check(Set(mixed.rows.filter { $0.outcome == .exists }.map(\.name)) == plan.existing, "预览与创建计划一致")
        try Data("x".utf8).write(to: previewRoot.appendingPathComponent("03_成片"))
        let conflict = FolderEngine.preview(template: sample, target: previewRoot)
        check(conflict.blocked == 1 && !conflict.canCreate, "同名文件逐行标为阻止")
        rejects("预览阻止时创建同样拒绝") { _ = try FolderEngine.create(template: sample, target: previewRoot) }
        check(!fm.fileExists(atPath: previewRoot.appendingPathComponent("02_配音字幕").path), "阻止时没有部分创建")
        sample.numbered = false
        sample.entries = [.init(name: "A"), .init(name: ""), .init(name: "a")]
        let invalid = FolderEngine.preview(template: sample, target: previewRoot)
        check(invalid.blocked == 2 && invalid.rows[0].outcome == .willCreate, "逐行列出全部名称问题")
        do { _ = try FolderEngine.names(for: sample); check(false, "首个问题仍然抛出") }
        catch { check(error.localizedDescription == "第 2 个文件夹名称为空。", "首个问题仍然抛出") }
        let gone = FolderEngine.preview(template: sample, target: previewRoot.appendingPathComponent("missing"))
        check(gone.targetIssue != nil && !gone.canCreate, "目标不存在时整体提示")
        check(AppVersion.isNewer("v1.2.3", than: "1.2.2") && AppVersion.isNewer("1.10.0", than: "1.9.9") && AppVersion.isNewer("2", than: "1.9"), "新版本号判定为更新")
        check(!AppVersion.isNewer("v1.2.2", than: "1.2.2") && !AppVersion.isNewer("1.2", than: "1.2.0") && !AppVersion.isNewer("1.2.1", than: "1.2.2"), "相同或更旧版本不更新")
        print("ALL \(count) CHECKS PASSED")
    }
}
