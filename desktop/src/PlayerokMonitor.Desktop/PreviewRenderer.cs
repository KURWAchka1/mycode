using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace PlayerokMonitor.Desktop;

internal static class PreviewRenderer
{
    public static void Render(string destination, string section, double width = 1280, double height = 820)
    {
        var window = new MainWindow(true) { Width = width, Height = height, WindowStartupLocation = WindowStartupLocation.Manual, Left = -3000, Top = -3000 };
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
