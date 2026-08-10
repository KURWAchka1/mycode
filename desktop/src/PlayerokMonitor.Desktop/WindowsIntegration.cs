using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Windows;
using Microsoft.Win32;
using Microsoft.Windows.AppNotifications;
using Microsoft.Windows.AppNotifications.Builder;
using Velopack;
using Velopack.Sources;

namespace PlayerokMonitor.Desktop;

public sealed class WindowsNotifier : IDisposable
{
    private bool _registered;

    public void Register()
    {
        try
        {
            AppNotificationManager.Default.Register();
            _registered = true;
        }
        catch { _registered = false; }
    }

    public void Show(string title, string body, string dealId)
    {
        if (!_registered) return;
        try
        {
            var builder = new AppNotificationBuilder().AddText(title).AddText(body);
            if (!string.IsNullOrWhiteSpace(dealId)) builder.AddArgument("deal_id", dealId);
            AppNotificationManager.Default.Show(builder.BuildNotification());
        }
        catch { }
    }

    public void Dispose()
    {
        if (!_registered) return;
        try { AppNotificationManager.Default.Unregister(); } catch { }
    }
}

public sealed class TrayService : IDisposable
{
    private readonly System.Windows.Forms.NotifyIcon _icon;
    private readonly Icon? _ownedIcon;
    public event Action? OpenRequested;
    public event Action? RefreshRequested;
    public event Action? ExitRequested;

    public TrayService()
    {
        var menu = new System.Windows.Forms.ContextMenuStrip();
        menu.Items.Add("Открыть Playerok Monitor", null, (_, _) => OpenRequested?.Invoke());
        menu.Items.Add("Обновить заказы", null, (_, _) => RefreshRequested?.Invoke());
        menu.Items.Add(new System.Windows.Forms.ToolStripSeparator());
        menu.Items.Add("Выход", null, (_, _) => ExitRequested?.Invoke());
        var iconPath = Path.Combine(AppContext.BaseDirectory, "app.ico");
        _ownedIcon = File.Exists(iconPath) ? new Icon(iconPath) : null;
        _icon = new System.Windows.Forms.NotifyIcon
        {
            Icon = _ownedIcon ?? SystemIcons.Information,
            Text = "Playerok Monitor",
            Visible = true,
            ContextMenuStrip = menu
        };
        _icon.DoubleClick += (_, _) => OpenRequested?.Invoke();
    }

    public void Update(int newOrders, bool connected)
    {
        _icon.Text = connected ? $"Playerok Monitor · новых: {newOrders}" : "Playerok Monitor · нет связи";
    }

    public void Dispose()
    {
        _icon.Visible = false;
        _icon.Dispose();
        _ownedIcon?.Dispose();
    }
}

public static class AutoStartManager
{
    private const string KeyPath = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string Name = "PlayerokMonitorDesktop";

    public static void SetEnabled(bool enabled)
    {
        using var key = Registry.CurrentUser.OpenSubKey(KeyPath, true) ?? Registry.CurrentUser.CreateSubKey(KeyPath, true);
        if (!enabled) { key.DeleteValue(Name, false); return; }
        var current = Environment.ProcessPath ?? Path.Combine(AppContext.BaseDirectory, "PlayerokMonitor.Desktop.exe");
        var root = Directory.GetParent(AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar))?.FullName;
        var updater = root is null ? "" : Path.Combine(root, "Update.exe");
        var command = File.Exists(updater) ? $"\"{updater}\" --processStart PlayerokMonitor.Desktop.exe" : $"\"{current}\"";
        key.SetValue(Name, command, RegistryValueKind.String);
    }
}

public sealed class DesktopUpdateService
{
    private const string Repository = "https://github.com/KURWAchka1/mycode";

    public async Task<UpdateInfo?> CheckAsync()
    {
        try
        {
            var manager = new UpdateManager(new GithubSource(Repository, null, false));
            var update = await manager.CheckForUpdatesAsync();
            return update is null ? null : new UpdateInfo(manager, update);
        }
        catch (Exception error) when (error.GetType().Name is "NotInstalledException") { return null; }
    }

    public sealed class UpdateInfo
    {
        private readonly UpdateManager _manager;
        private readonly Velopack.UpdateInfo _update;
        internal UpdateInfo(UpdateManager manager, Velopack.UpdateInfo update) { _manager = manager; _update = update; }
        public string Version => _update.TargetFullRelease.Version.ToString();
        public async Task DownloadAndRestartAsync()
        {
            await _manager.DownloadUpdatesAsync(_update);
            _manager.ApplyUpdatesAndRestart(_update);
        }
    }
}
