using System.Diagnostics;
using Foldset.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Graphics;
using Windows.Storage.Pickers;

namespace Foldset.App;

public sealed partial class MainWindow : Window
{
    readonly TemplateStore store = new();
    string? target, outcomeTarget;
    int previewGeneration;
    bool loading;

    FolderTemplate? Selected => TemplateList.SelectedItem as FolderTemplate;

    public MainWindow()
    {
        InitializeComponent();
        AppWindow.Resize(new SizeInt32(1100, 760));
        TemplateList.ItemsSource = store.Templates;
        store.Changed += () => { ShowPersistence(); RefreshPreview(); };
        ShowPersistence();
        TemplateList.SelectedItem = store.Default;
        Load();
    }

    void ShowPersistence()
    {
        PersistenceBar.Message = store.PersistenceError;
        PersistenceBar.IsOpen = store.PersistenceError is not null;
    }

    /// Copies the selected template into the editor. Edits flow back through `Apply`.
    void Load()
    {
        var t = Selected;
        loading = true;
        NameBox.Text = t?.Name ?? "";
        NumberedSwitch.IsOn = t?.Numbered ?? false;
        StartBox.Value = t?.Start ?? 1;
        DigitsBox.Value = t?.Digits ?? 2;
        SeparatorBox.Text = t?.Separator ?? "";
        EntryList.ItemsSource = t?.Entries;
        loading = false;
        foreach (var control in new Control[] { NameBox, NumberedSwitch, DuplicateButton, DefaultButton, DeleteButton }) control.IsEnabled = t is not null;
        StartBox.IsEnabled = DigitsBox.IsEnabled = SeparatorBox.IsEnabled = t?.Numbered == true;
        OutcomeBar.IsOpen = false;
        RefreshPreview();
    }

    /// Writes every field at once, so a late TextChanged never mixes two templates' values.
    void Apply()
    {
        if (loading || Selected is not { } t) return;
        t.Name = NameBox.Text;
        t.Numbered = NumberedSwitch.IsOn;
        if (!double.IsNaN(StartBox.Value)) t.Start = (int)StartBox.Value;
        if (!double.IsNaN(DigitsBox.Value)) t.Digits = (int)DigitsBox.Value;
        t.Separator = SeparatorBox.Text;
        StartBox.IsEnabled = DigitsBox.IsEnabled = SeparatorBox.IsEnabled = t.Numbered;
    }

    void NameBox_TextChanged(object sender, TextChangedEventArgs e) => Apply();
    void Settings_Changed(object sender, RoutedEventArgs e) => Apply();
    void Number_Changed(NumberBox sender, NumberBoxValueChangedEventArgs e) => Apply();
    void TemplateList_SelectionChanged(object sender, SelectionChangedEventArgs e) => Load();

    /// Results from an older edit are dropped, so the preview always matches the latest template and target.
    async void RefreshPreview()
    {
        var generation = ++previewGeneration;
        CreateButton.IsEnabled = false;
        if (Selected is not { } t)
        {
            PreviewList.ItemsSource = null;
            PreviewIssue.Visibility = Visibility.Collapsed;
            return;
        }
        var snapshot = t.Clone();
        var target = this.target;
        var preview = await Task.Run(() => FolderEngine.Preview(snapshot, target));
        if (generation != previewGeneration) return;
        var issue = preview.TemplateIssue ?? preview.TargetIssue;
        PreviewIssue.Text = issue ?? "";
        PreviewIssue.Visibility = issue is null ? Visibility.Collapsed : Visibility.Visible;
        PreviewList.ItemsSource = preview.Rows.Select(r => $"{(r.Name.Length == 0 ? "（空）" : r.Name)}  ·  " + r.Outcome switch
        {
            RowOutcome.WillCreate => "将创建",
            RowOutcome.Exists => "已存在，跳过",
            RowOutcome.AwaitingTarget => "待选择目标",
            _ => r.Issue,
        }).ToList();
        CreateButton.IsEnabled = preview.CanCreate;
    }

    void Add_Click(object sender, RoutedEventArgs e) => TemplateList.SelectedItem = store.Add();

    void Duplicate_Click(object sender, RoutedEventArgs e)
    {
        if (Selected is { } t) TemplateList.SelectedItem = store.Duplicate(t);
    }

    void Default_Click(object sender, RoutedEventArgs e)
    {
        if (Selected is { } t) store.SetDefault(t);
    }

    async void Delete_Click(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } t) return;
        var dialog = new ContentDialog
        {
            XamlRoot = Content.XamlRoot,
            Title = $"删除“{t.DisplayName}”模板？",
            Content = "只删除模板设置，不会删除已创建的文件夹。",
            PrimaryButtonText = "删除模板",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
        store.Delete(t);
        TemplateList.SelectedItem = store.Templates.FirstOrDefault();
    }

    void AddEntry_Click(object sender, RoutedEventArgs e) => Selected?.Entries.Add(new FolderEntry("新文件夹"));

    void RemoveEntry_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement { DataContext: FolderEntry entry }) Selected?.Entries.Remove(entry);
    }

    async void PickTarget_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FolderPicker();
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        if (await picker.PickSingleFolderAsync() is not { } folder) return;
        target = folder.Path;
        TargetText.Text = target;
        OutcomeBar.IsOpen = false;
        RefreshPreview();
    }

    void Create_Click(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } t || target is null) return;
        try { ShowOutcome(InfoBarSeverity.Success, FolderEngine.Create(t, target).Summary); }
        catch (FolderIssue issue) { ShowOutcome(InfoBarSeverity.Error, issue.Message); }
        RefreshPreview();
    }

    void ShowOutcome(InfoBarSeverity severity, string message)
    {
        OutcomeBar.Severity = severity;
        OutcomeBar.Message = message;
        outcomeTarget = target;
        OutcomeBar.IsOpen = true;
    }

    void Reveal_Click(object sender, RoutedEventArgs e)
    {
        if (outcomeTarget is null) return;
        var explorer = new ProcessStartInfo("explorer.exe");
        explorer.ArgumentList.Add(outcomeTarget);
        Process.Start(explorer);
    }
}
