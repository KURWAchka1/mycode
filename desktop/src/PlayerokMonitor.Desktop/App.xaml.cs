using System.IO;
using System.Windows;
using Velopack;

namespace PlayerokMonitor.Desktop;

public partial class App : System.Windows.Application
{
    [STAThread]
    public static void Main(string[] args)
    {
        VelopackApp.Build().SetAppUserModelId("PlayerokMonitor.Desktop").Run();
        if (args.Contains("--smoke-test", StringComparer.OrdinalIgnoreCase))
        {
            var snapshot = Core.StatisticsEngine.Calculate([]);
            if (snapshot.Sales != 0) throw new InvalidDataException("Statistics smoke test failed");
            return;
        }
        var app = new App();
        app.InitializeComponent();
        var previewIndex = Array.FindIndex(args, value => value.Equals("--render-preview", StringComparison.OrdinalIgnoreCase));
        if (previewIndex >= 0 && previewIndex + 1 < args.Length)
        {
            var sectionIndex = Array.FindIndex(args, value => value.Equals("--preview-section", StringComparison.OrdinalIgnoreCase));
            PreviewRenderer.Render(args[previewIndex + 1], sectionIndex >= 0 && sectionIndex + 1 < args.Length ? args[sectionIndex + 1] : "orders");
            return;
        }
        app.Run();
    }

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var window = new MainWindow();
        MainWindow = window;
        window.Show();
    }
}
