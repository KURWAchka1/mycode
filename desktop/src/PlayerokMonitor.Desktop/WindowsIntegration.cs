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
    private readonly string _logPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "PlayerokMonitor",
        "notifications.log");

    public bool IsRegistered => _registered;
    public string LastError { get; private set; } = "";

    public bool Register()
    {
        try
        {
            var manager = AppNotificationManager.Default;
            manager.NotificationInvoked -= NotificationInvoked;
            manager.NotificationInvoked += NotificationInvoked;
            manager.Register();
            _registered = true;
            LastError = "";
            WriteLog("AppNotificationManager registered");
            return true;
        }
        catch (Exception error)
        {
            _registered = false;
            LastError = $"{error.GetType().Name}: {error.Message}";
            WriteLog("Registration failed: " + LastError);
            return false;
        }
    }

    public bool Show(string title, string body, string dealId)
    {
        if (!_registered && !Register()) return false;
        try
        {
            var setting = AppNotificationManager.Default.Setting;
            if (setting != AppNotificationSetting.Enabled)
            {
                LastError = $"Windows notification setting: {setting}";
                WriteLog(LastError);
                return false;
            }
            var builder = new AppNotificationBuilder().AddText(title).AddText(body);
            if (!string.IsNullOrWhiteSpace(dealId)) builder.AddArgument("deal_id", dealId);
            AppNotificationManager.Default.Show(builder.BuildNotification());
            LastError = "";
            WriteLog($"Notification submitted deal={dealId}");
            return true;
        }
        catch (Exception error)
        {
            LastError = $"{error.GetType().Name}: {error.Message}";
            WriteLog("Show failed: " + LastError);
            return false;
        }
    }

    private static void NotificationInvoked(
        AppNotificationManager sender,
        AppNotificationActivatedEventArgs args)
    {
        // Subscription must exist before Register() for unpackaged WPF apps.
        // The running window already owns navigation; activation is intentionally
        // side-effect free so clicking a toast can never repeat a server action.
    }

    private void WriteLog(string message)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_logPath)!);
            File.AppendAllText(_logPath, $"{DateTimeOffset.Now:O} {message}{Environment.NewLine}");
        }
        catch { }
    }

    public void Dispose()
    {
        if (!_registered) return;
        try
        {
            AppNotificationManager.Default.NotificationInvoked -= NotificationInvoked;
            AppNotificationManager.Default.Unregister();
        }
        catch (Exception error) { WriteLog("Unregister failed: " + error.Message); }
        finally { _registered = false; }
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

    public void ShowNotification(string title, string body)
    {
        var safeTitle = string.IsNullOrWhiteSpace(title) ? "Playerok Monitor" : title.Trim();
        var safeBody = string.IsNullOrWhiteSpace(body) ? "Новое событие Playerok" : body.Trim();
        _icon.ShowBalloonTip(
            7000,
            safeTitle[..Math.Min(safeTitle.Length, 63)],
            safeBody[..Math.Min(safeBody.Length, 255)],
            System.Windows.Forms.ToolTipIcon.Info);
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
