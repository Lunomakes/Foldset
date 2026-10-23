using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json.Serialization;

namespace Foldset.Core;

public abstract class Observable : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;
    protected void Set<T>(ref T field, T value, [CallerMemberName] string name = "")
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return;
        field = value;
        Raise(name);
    }
    protected void Raise(string name) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}

public sealed class FolderEntry : Observable
{
    string name = "";
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Name { get => name; set => Set(ref name, value); }
    public FolderEntry() { }
    public FolderEntry(string name) => this.name = name;
}

/// Same JSON shape as the macOS app's `FolderTemplate`.
public sealed class FolderTemplate : Observable
{
    string name = "", separator = "_";
    bool numbered = true, isDefault;
    int start = 1, digits = 2;
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Name { get => name; set { Set(ref name, value); Raise(nameof(DisplayName)); } }
    public bool Numbered { get => numbered; set => Set(ref numbered, value); }
    public int Start { get => start; set => Set(ref start, value); }
    public int Digits { get => digits; set => Set(ref digits, value); }
    public string Separator { get => separator; set => Set(ref separator, value); }
    public ObservableCollection<FolderEntry> Entries { get; set; } = [];
    [JsonIgnore] public bool IsDefault { get => isDefault; set => Set(ref isDefault, value); }
    [JsonIgnore] public string DisplayName => string.IsNullOrEmpty(Name) ? "未命名模板" : Name;

    public FolderTemplate() { }
    public FolderTemplate(string name, params string[] entries)
    {
        this.name = name;
        Entries = [.. entries.Select(e => new FolderEntry(e))];
    }

    public string FolderName(int index)
    {
        var name = Entries[index].Name.Trim();
        if (!Numbered) return name;
        long number = (long)Start + index;
        if (number > int.MaxValue) return "序号超出范围" + Separator + name;
        return number.ToString().PadLeft(Math.Clamp(Digits, 0, 6), '0') + Separator + name;
    }

    /// Same settings and names, fresh identities.
    public FolderTemplate Clone() => new(Name, [.. Entries.Select(e => e.Name)])
    {
        Numbered = Numbered, Start = Start, Digits = Digits, Separator = Separator
    };

    public static FolderTemplate[] Samples() =>
    [
        new("剪辑项目", "视频素材", "配音字幕", "音乐音效", "工程文件", "输出成片"),
        new("简单剪辑", "视频素材", "配音字幕") { Digits = 1 },
        new("访谈项目", "机位A", "机位B", "录音", "工程文件", "成片"),
        new("包装项目", "参考资料", "设计素材", "AE工程", "输出") { Digits = 1, Separator = "-" },
    ];
}

public sealed class Library
{
    public List<FolderTemplate> Templates { get; set; } = [];
    public Guid? DefaultID { get; set; }
}
