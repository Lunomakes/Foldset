// Mirrors Tests/CoreTests.swift: plain checks, first failure exits non-zero.
using Foldset.Core;

var root = Path.Combine(Path.GetTempPath(), "FoldsetTests-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
var count = 0;
void Check(bool condition, string name)
{
    if (!condition) { Console.Error.WriteLine($"FAIL: {name}"); Environment.Exit(1); }
    count++; Console.WriteLine($"PASS: {name}");
}
void Rejects(string name, Action action)
{
    try { action(); } catch (FolderIssue) { count++; Console.WriteLine($"PASS: {name}"); return; }
    Console.Error.WriteLine($"FAIL expected rejection: {name}"); Environment.Exit(1);
}
string P(params string[] parts) => Path.Combine([root, .. parts]);

var template = new FolderTemplate("测试", "视频素材", "配音字幕");
Check(FolderEngine.Names(template).SequenceEqual(["01_视频素材", "02_配音字幕"]), "中文编号");
Check(FolderEngine.Create(template, root).Created.Count == 2, "实际创建两个文件夹");
var second = FolderEngine.Create(template, root);
Check(second.Created.Count == 0 && second.Skipped.Count == 2, "重复创建跳过已有目录");
File.WriteAllText(P("01_视频素材", "素材.txt"), "keep footage");
FolderEngine.Create(template, root);
Check(File.ReadAllText(P("01_视频素材", "素材.txt")) == "keep footage", "原有素材不变");

template.Entries = [new("应不创建"), new("冲突")];
File.WriteAllText(P("02_冲突"), "existing");
Rejects("同名文件拦截", () => FolderEngine.Create(template, root));
Check(!Directory.Exists(P("01_应不创建")), "完整预检避免部分创建");

template.Numbered = false;
template.Entries = [new("same"), new("SAME")];
Rejects("忽略大小写重复名称", () => FolderEngine.Names(template));
template.Entries = [new("é"), new("é")];
Rejects("Unicode 等价重复名称", () => FolderEngine.Names(template));
foreach (var name in new[] { "", "  ", "../escape", @"a\b", "bad:name", "bad\nname", ".hidden", ".", "..", "q?", "trail.", "CON", "nul.txt", "com1", new string('中', 256) })
{
    template.Entries = [new(name)];
    Rejects($"无效名称 {name[..Math.Min(name.Length, 12)].ReplaceLineEndings("\\n")}", () => FolderEngine.Names(template));
}
template.Entries = [new("CONSOLE")];
Check(FolderEngine.Names(template).Length == 1, "保留名只匹配完整名称");

template.Entries = [new("链接")];
Directory.CreateSymbolicLink(P("链接"), P("01_视频素材"));
Rejects("不跟随已有符号链接", () => FolderEngine.Create(template, root));
template.Entries = [new("断链")];
Directory.CreateSymbolicLink(P("断链"), P("不存在"));
Rejects("断链也拦截", () => FolderEngine.Create(template, root));
Rejects("目标必须存在", () => FolderEngine.Create(template, P("missing")));

template.Numbered = true; template.Start = 8; template.Digits = 3; template.Separator = "-";
template.Entries = [new(" A "), new("B")];
Check(FolderEngine.Names(template).SequenceEqual(["008-A", "009-B"]), "起始序号位数和分隔符");
template.Entries.Move(0, 1);
Check(template.FolderName(0) == "008-B", "调整顺序重新编号");
template.Separator = "/";
Rejects("分隔符同样校验", () => FolderEngine.Names(template));
template.Separator = "-";
template.Start = -1;
Rejects("负序号校验", () => FolderEngine.Names(template));
template.Start = int.MaxValue;
Check(template.FolderName(1).StartsWith("序号超出范围"), "超大序号预览不会溢出");
Rejects("超大序号不能创建", () => FolderEngine.Names(template));

var storage = P("library", "templates.json");
var store = new TemplateStore(storage);
Check(store.Templates.Count == 4 && store.Default == store.Templates[0], "首次启动使用预置模板");
var added = store.Add();
added.Name = "持久化测试";
added.Entries.Add(new("新增"));
store.SetDefault(added);
var reloaded = new TemplateStore(storage);
Check(reloaded.Templates[^1].Name == "持久化测试" && reloaded.Templates[^1].Entries.Count == 3 && reloaded.Default?.Id == added.Id, "模板、条目与默认设置持久化");
var copy = reloaded.Duplicate(reloaded.Templates[^1]);
Check(reloaded.Templates.Select(t => t.Id).Distinct().Count() == reloaded.Templates.Count && copy.Entries[0].Id != added.Entries[0].Id, "复制模板使用独立标识");
reloaded.Delete(reloaded.Default!);
Check(reloaded.Templates.Count == 5 && reloaded.Default == reloaded.Templates[0], "删除默认模板后改用第一套");
Check(new TemplateStore(storage).Templates.Count == 5, "删除已保存");

var corrupt = P("corrupt.json");
File.WriteAllText(corrupt, "broken");
var bad = new TemplateStore(corrupt);
bad.Add();
Check(bad.PersistenceError is not null, "损坏模板库提供错误");
Check(File.ReadAllText(corrupt) == "broken", "损坏模板库不被覆盖");

// The macOS app writes this shape (Swift Codable, uppercase UUIDs).
var macFile = P("mac.json");
File.WriteAllText(macFile, """
{"defaultID":"6A1F2C1E-0000-4000-8000-000000000002","templates":[{"digits":2,"entries":[{"id":"6A1F2C1E-0000-4000-8000-000000000001","name":"素材"}],"id":"6A1F2C1E-0000-4000-8000-000000000002","name":"来自 Mac","numbered":true,"separator":"_","start":1}]}
""");
var mac = new TemplateStore(macFile);
Check(mac.PersistenceError is null && mac.Default?.Name == "来自 Mac" && mac.Default.Entries[0].Name == "素材", "读取 macOS 版模板格式");

var previewRoot = P("preview-target");
Directory.CreateDirectory(previewRoot);
var sample = new FolderTemplate("预览", "视频素材", "配音字幕", "成片");
var unchosen = FolderEngine.Preview(sample, null);
Check(unchosen.Rows.All(r => r.Outcome == RowOutcome.AwaitingTarget) && !unchosen.CanCreate, "未选目标时逐行待定且不可创建");
Directory.CreateDirectory(Path.Combine(previewRoot, "01_视频素材"));
var mixed = FolderEngine.Preview(sample, previewRoot);
Check(mixed.Rows.Select(r => r.Outcome).SequenceEqual([RowOutcome.Exists, RowOutcome.WillCreate, RowOutcome.WillCreate]) && mixed.CanCreate, "预览区分已存在与将创建");
Check(Directory.GetFileSystemEntries(previewRoot).Length == 1, "预览不写入目标");
var plan = FolderEngine.Plan(sample, previewRoot);
Check(mixed.Rows.Where(r => r.Outcome == RowOutcome.Exists).Select(r => r.Name).ToHashSet().SetEquals(plan.Existing), "预览与创建计划一致");
File.WriteAllText(Path.Combine(previewRoot, "03_成片"), "x");
var conflict = FolderEngine.Preview(sample, previewRoot);
Check(conflict.Blocked == 1 && !conflict.CanCreate, "同名文件逐行标为阻止");
Rejects("预览阻止时创建同样拒绝", () => FolderEngine.Create(sample, previewRoot));
Check(!Directory.Exists(Path.Combine(previewRoot, "02_配音字幕")), "阻止时没有部分创建");
sample.Numbered = false;
sample.Entries = [new("A"), new(""), new("a")];
var invalid = FolderEngine.Preview(sample, previewRoot);
Check(invalid.Blocked == 2 && invalid.Rows[0].Outcome == RowOutcome.WillCreate, "逐行列出全部名称问题");
try { FolderEngine.Names(sample); Check(false, "首个问题仍然抛出"); }
catch (FolderIssue e) { Check(e.Message == "第 2 个文件夹名称为空。", "首个问题仍然抛出"); }
var gone = FolderEngine.Preview(sample, Path.Combine(previewRoot, "missing"));
Check(gone.TargetIssue is not null && !gone.CanCreate, "目标不存在时整体提示");

Directory.Delete(root, recursive: true);
Console.WriteLine($"ALL {count} CHECKS PASSED");
