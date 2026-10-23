using System.Text;

namespace Foldset.Core;

public sealed class FolderIssue(string message) : Exception(message);

/// What creating one folder would do. Computed without writing anything.
public enum RowOutcome { WillCreate, Exists, AwaitingTarget, Blocked }

public sealed record PreviewRow(int Index, string Name, RowOutcome Outcome, string? Issue = null);

public sealed record CreationPreview(string? TemplateIssue, string? TargetIssue, IReadOnlyList<PreviewRow> Rows)
{
    int Count(RowOutcome outcome) => Rows.Count(r => r.Outcome == outcome);
    public int WillCreate => Count(RowOutcome.WillCreate);
    public int Existing => Count(RowOutcome.Exists);
    public int Blocked => Count(RowOutcome.Blocked);
    /// Mirrors `Create`: one blocked row or any issue stops the whole run.
    public bool CanCreate => TemplateIssue is null && TargetIssue is null && Blocked == 0 && Rows.Count > 0 && Rows.All(r => r.Outcome != RowOutcome.AwaitingTarget);
}

public sealed record FolderPlan(IReadOnlyList<string> Names, IReadOnlySet<string> Existing);

public sealed record CreationResult(IReadOnlyList<string> Created, IReadOnlyList<string> Skipped)
{
    public string Summary => $"已创建 {Created.Count} 个文件夹，跳过 {Skipped.Count} 个已有文件夹。";
}

public static class FolderEngine
{
    public const string MissingTarget = "目标文件夹不存在，请重新选择。";
    public static string Conflict(string name) => $"目标位置已有同名文件或链接“{name}”。请先更名；没有创建或覆盖任何内容。";

    static readonly char[] Forbidden = ['<', '>', ':', '"', '/', '\\', '|', '?', '*'];
    static readonly HashSet<string> Reserved = new(
        ["CON", "PRN", "AUX", "NUL", .. Enumerable.Range(1, 9).SelectMany(i => new[] { $"COM{i}", $"LPT{i}" })],
        StringComparer.OrdinalIgnoreCase);

    enum Kind { None, Directory, Other }
    /// Links and junctions count as Other: Foldset never creates through or next to them.
    static Kind Probe(string path)
    {
        try
        {
            var attributes = File.GetAttributes(path);
            return (attributes & (FileAttributes.Directory | FileAttributes.ReparsePoint)) == FileAttributes.Directory ? Kind.Directory : Kind.Other;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return Kind.None; }
    }

    static string? NameIssue(int index, string raw, string name)
    {
        if (raw.Length == 0) return $"第 {index + 1} 个文件夹名称为空。";
        if (raw is "." or ".." || name.StartsWith('.') || name.IndexOfAny(Forbidden) >= 0 || name.Any(char.IsControl)
            || name.EndsWith('.') || name.EndsWith(' ') || Reserved.Contains(name.Split('.')[0].TrimEnd()))
            return $"第 {index + 1} 个名称无效：不支持 \\ / : * ? \" < > |、控制字符、隐藏文件夹、结尾的点或空格，以及 CON、NUL 等系统保留名。";
        if (name.Length > 255) return $"“{name}”过长，请缩短名称。";
        return null;
    }

    /// Validates every row instead of stopping at the first problem. `Names` throws the first issue found here.
    public static (string? Issue, string[] Names, string?[] RowIssues) Validate(FolderTemplate template)
    {
        var names = template.Entries.Select((_, i) => template.FolderName(i)).ToArray();
        if (template.Name.Trim().Length == 0) return ("请先为模板命名。", names, new string?[names.Length]);
        if (names.Length == 0) return ("请至少添加一个文件夹。", names, []);
        if (template.Start is < 0 or > 999999 || names.Length > 1000)
            return ("起始序号须在 0–999999 之间，文件夹数量不能超过 1000 个。", names, new string?[names.Length]);
        var seen = new HashSet<string>();
        var issues = names.Select((name, i) =>
        {
            var issue = NameIssue(i, template.Entries[i].Name.Trim(), name);
            if (issue is null && !seen.Add(name.Normalize(NormalizationForm.FormC).ToLowerInvariant()))
                issue = $"存在重复名称“{name}”，请调整名称或开启编号。";
            return issue;
        }).ToArray();
        return (null, names, issues);
    }

    public static string[] Names(FolderTemplate template)
    {
        var (issue, names, rowIssues) = Validate(template);
        if ((issue ?? rowIssues.FirstOrDefault(i => i is not null)) is { } first) throw new FolderIssue(first);
        return names;
    }

    /// Read-only. Applies the same rules as `Plan` to every row, so the UI can show each outcome with its reason.
    public static CreationPreview Preview(FolderTemplate template, string? target)
    {
        var (issue, names, rowIssues) = Validate(template);
        var targetIssue = target is not null && !Directory.Exists(target) ? MissingTarget : null;
        var rows = names.Select((name, i) =>
        {
            if (i < rowIssues.Length && rowIssues[i] is { } rowIssue) return new PreviewRow(i, name, RowOutcome.Blocked, rowIssue);
            if (target is null || targetIssue is not null || issue is not null) return new PreviewRow(i, name, RowOutcome.AwaitingTarget);
            return Probe(Path.Combine(target, name)) switch
            {
                Kind.None => new PreviewRow(i, name, RowOutcome.WillCreate),
                Kind.Directory => new PreviewRow(i, name, RowOutcome.Exists),
                _ => new PreviewRow(i, name, RowOutcome.Blocked, Conflict(name)),
            };
        }).ToArray();
        return new CreationPreview(issue, targetIssue, rows);
    }

    public static FolderPlan Plan(FolderTemplate template, string target)
    {
        var names = Names(template);
        if (!Directory.Exists(target)) throw new FolderIssue(MissingTarget);
        var existing = new HashSet<string>();
        foreach (var name in names)
        {
            var kind = Probe(Path.Combine(target, name));
            if (kind == Kind.Other) throw new FolderIssue(Conflict(name));
            if (kind == Kind.Directory) existing.Add(name);
        }
        return new FolderPlan(names, existing);
    }

    public static CreationResult Create(FolderTemplate template, string target)
    {
        var plan = Plan(template, target);
        List<string> created = [], skipped = [];
        foreach (var name in plan.Names)
        {
            if (plan.Existing.Contains(name)) { skipped.Add(name); continue; }
            try
            {
                Directory.CreateDirectory(Path.Combine(target, name));
                created.Add(name);
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException)
            {
                throw new FolderIssue($"创建“{name}”失败：{e.Message}\n本次已创建 {created.Count} 个，跳过 {skipped.Count} 个。已创建的文件夹保留，现有内容未覆盖。");
            }
        }
        return new CreationResult(created, skipped);
    }
}
