using System.Diagnostics;
using System.Windows;
using System.Windows.Media;
using PlayerokMonitor.Core;
using MediaColor = System.Windows.Media.Color;
using MediaPen = System.Windows.Media.Pen;
using WpfPoint = System.Windows.Point;

namespace PlayerokMonitor.Desktop;

public sealed class StatisticsChart : FrameworkElement
{
    private IReadOnlyList<DailyStatistic> _points = [];
    private readonly Stopwatch _animation = new();

    public void SetData(IReadOnlyList<DailyStatistic> points)
    {
        _points = points;
        CompositionTarget.Rendering -= OnRendering;
        if (SystemParameters.ClientAreaAnimation)
        {
            _animation.Restart();
            CompositionTarget.Rendering += OnRendering;
        }
        else _animation.Reset();
        InvalidateVisual();
    }

    private void OnRendering(object? sender, EventArgs e)
    {
        InvalidateVisual();
        if (_animation.ElapsedMilliseconds >= 520)
        {
            _animation.Stop();
            CompositionTarget.Rendering -= OnRendering;
        }
    }

    protected override void OnRender(DrawingContext drawingContext)
    {
        base.OnRender(drawingContext);
        if (_points.Count == 0 || ActualWidth < 80 || ActualHeight < 80) return;
        var progress = _animation.IsRunning ? Ease(Math.Min(1, _animation.Elapsed.TotalMilliseconds / 520d)) : 1d;
        var max = Math.Max(1m, _points.Max(point => point.NetRevenue));
        var plot = new Rect(12, 12, Math.Max(1, ActualWidth - 24), Math.Max(1, ActualHeight - 42));
        var gap = 7d;
        var barWidth = Math.Max(3, (plot.Width - gap * (_points.Count - 1)) / _points.Count);
        var gridPen = new MediaPen(new SolidColorBrush(MediaColor.FromArgb(25, 255, 255, 255)), 1);
        gridPen.Freeze();
        for (var row = 0; row <= 3; row++)
        {
            var y = plot.Top + plot.Height * row / 3d;
            drawingContext.DrawLine(gridPen, new WpfPoint(plot.Left, y), new WpfPoint(plot.Right, y));
        }
        var fill = new LinearGradientBrush(MediaColor.FromRgb(114, 169, 249), MediaColor.FromRgb(88, 214, 141), 90);
        fill.Freeze();
        for (var index = 0; index < _points.Count; index++)
        {
            var value = (double)(_points[index].NetRevenue / max);
            var height = Math.Max(_points[index].Sales > 0 ? 4 : 1, plot.Height * value * progress);
            var x = plot.Left + index * (barWidth + gap);
            drawingContext.DrawRoundedRectangle(fill, null, new Rect(x, plot.Bottom - height, barWidth, height), 5, 5);
            if (index % 3 == 0 || index == _points.Count - 1)
            {
                var label = new FormattedText(_points[index].Day.ToString("dd.MM"), System.Globalization.CultureInfo.GetCultureInfo("ru-RU"), System.Windows.FlowDirection.LeftToRight, new Typeface("Segoe UI Variable Text"), 10, new SolidColorBrush(MediaColor.FromRgb(164, 171, 182)), VisualTreeHelper.GetDpi(this).PixelsPerDip);
                drawingContext.DrawText(label, new WpfPoint(x, plot.Bottom + 8));
            }
        }
    }

    private static double Ease(double value) => 1 - Math.Pow(1 - value, 3);
}
