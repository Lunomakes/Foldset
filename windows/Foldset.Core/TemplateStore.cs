using System.Collections.ObjectModel;
using System.Collections.Specialized;
using System.ComponentModel;
using System.Text.Json;

namespace Foldset.Core;

/// Owns the template library and saves it after every edit, including edits to nested entries.
public sealed class TemplateStore
{
    static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true };
    readonly string path;
    readonly bool allowSave;

    public static string DefaultPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Foldset", "templates.json");
    public ObservableCollection<FolderTemplate> Templates { get; } = [];
    public FolderTemplate? Default => Templates.FirstOrDefault(t => t.IsDefault);
    public string? PersistenceError { get; private set; }
    /// Raised after any template or entry changes and the library was saved (or failed to save).
    public event Action? Changed;

    public TemplateStore(string? path = null)
    {
        this.path = path ?? DefaultPath;
        var samples = FolderTemplate.Samples();
        var library = new Library { Templates = [.. samples], DefaultID = samples[0].Id };
        if (File.Exists(this.path))
        {
            try
            {
                library = JsonSerializer.Deserialize<Library>(File.ReadAllText(this.path), Json) ?? throw new FolderIssue("模板文件为空。");
                if (library.Templates.DistinctBy(t => t.Id).Count() != library.Templates.Count
                    || library.Templates.Any(t => t.Entries.DistinctBy(e => e.Id).Count() != t.Entries.Count))
                    throw new FolderIssue("模板标识重复。");
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException or FolderIssue)
            {
                library = new Library { Templates = [.. samples], DefaultID = samples[0].Id };
                PersistenceError = $"无法读取已保存的模板。原文件已保留，本次修改不会保存。\n{e.Message}";
            }
        }
        allowSave = PersistenceError is null;
        foreach (var template in library.Templates) { Attach(template); Templates.Add(template); }
        var fallback = Templates.FirstOrDefault(t => t.Id == library.DefaultID) ?? Templates.FirstOrDefault();
        foreach (var t in Templates) t.IsDefault = t == fallback;
        Templates.CollectionChanged += (_, e) =>
        {
            foreach (FolderTemplate t in e.NewItems ?? Array.Empty<FolderTemplate>()) Attach(t);
            if (Default is null && Templates.Count > 0) Templates[0].IsDefault = true; // raises Changed itself
            else OnChanged();
        };
    }

    void Attach(FolderTemplate template)
    {
        template.PropertyChanged += OnPropertyChanged;
        foreach (var entry in template.Entries) entry.PropertyChanged += OnPropertyChanged;
        template.Entries.CollectionChanged += (_, e) =>
        {
            // Reordering is a remove plus an insert; detach first so handlers never pile up.
            foreach (FolderEntry entry in e.OldItems ?? Array.Empty<FolderEntry>()) entry.PropertyChanged -= OnPropertyChanged;
            foreach (FolderEntry entry in e.NewItems ?? Array.Empty<FolderEntry>()) entry.PropertyChanged += OnPropertyChanged;
            OnChanged();
        };
    }

    void OnPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName != nameof(FolderTemplate.DisplayName)) OnChanged();
    }

    void OnChanged()
    {
        Save();
        Changed?.Invoke();
    }

    public void Save()
    {
        if (!allowSave) return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var library = new Library { Templates = [.. Templates], DefaultID = Default?.Id };
            var temporary = path + ".tmp";
            File.WriteAllText(temporary, JsonSerializer.Serialize(library, Json));
            File.Move(temporary, path, overwrite: true);
            PersistenceError = null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            PersistenceError = $"模板保存失败：{e.Message}";
        }
    }

    public FolderTemplate Add()
    {
        var template = new FolderTemplate("新模板", "视频素材", "工程文件");
        Templates.Add(template);
        return template;
    }

    public FolderTemplate Duplicate(FolderTemplate template)
    {
        var copy = template.Clone();
        copy.Name += " 副本";
        Templates.Add(copy);
        return copy;
    }

    public void Delete(FolderTemplate template) => Templates.Remove(template);

    public void SetDefault(FolderTemplate template)
    {
        foreach (var t in Templates) t.IsDefault = t == template;
    }
}
