using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace PlayerokMonitor.Desktop;

internal static class PreviewRenderer
{
    public static void Render(string destination, string section)
    {
        var window = new MainWindow(true) { Width = 1280, Height = 820, WindowStartupLocation = WindowStartupLocation.Manual, Left = -3000, Top = -3000 };
        window.Show();
        window.LoadPreviewData(section);
        window.Dispatcher.Invoke(() => { }, DispatcherPriority.Loaded);
        window.Measure(new System.Windows.Size(window.Width, window.Height));
        window.Arrange(new System.Windows.Rect(0, 0, window.Width, window.Height));
        window.UpdateLayout();
        var dpi = VisualTreeHelper.GetDpi(window);
        var bitmap = new RenderTargetBitmap((int)(window.ActualWidth * dpi.DpiScaleX), (int)(window.ActualHeight * dpi.DpiScaleY), dpi.PixelsPerInchX, dpi.PixelsPerInchY, PixelFormats.Pbgra32);
        bitmap.Render(window);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(destination))!);
        using var output = File.Create(destination);
        encoder.Save(output);
        window.Close();
    }
}
