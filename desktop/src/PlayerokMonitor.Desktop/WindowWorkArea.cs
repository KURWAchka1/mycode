using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

namespace PlayerokMonitor.Desktop;

internal static class WindowWorkArea
{
    private const int WmGetMinMaxInfo = 0x0024;
    private const uint MonitorDefaultToNearest = 0x00000002;

    public static void Attach(Window window)
    {
        window.SourceInitialized += (_, _) =>
        {
            if (PresentationSource.FromVisual(window) is HwndSource source)
            {
                source.AddHook(WindowProc);
            }
        };
    }

    private static nint WindowProc(nint hwnd, int message, nint wParam, nint lParam, ref bool handled)
    {
        if (message != WmGetMinMaxInfo || lParam == nint.Zero) return nint.Zero;

        var monitor = MonitorFromWindow(hwnd, MonitorDefaultToNearest);
        var monitorInfo = new MonitorInfo { Size = Marshal.SizeOf<MonitorInfo>() };
        if (monitor != nint.Zero && GetMonitorInfo(monitor, ref monitorInfo))
        {
            var info = Marshal.PtrToStructure<MinMaxInfo>(lParam);
            var work = monitorInfo.WorkArea;
            var bounds = monitorInfo.MonitorArea;

            info.MaxPosition.X = work.Left - bounds.Left;
            info.MaxPosition.Y = work.Top - bounds.Top;
            info.MaxSize.X = work.Right - work.Left;
            info.MaxSize.Y = work.Bottom - work.Top;

            Marshal.StructureToPtr(info, lParam, false);
            handled = true;
        }

        return nint.Zero;
    }

    [DllImport("user32.dll")]
    private static extern nint MonitorFromWindow(nint window, uint flags);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetMonitorInfo(nint monitor, ref MonitorInfo monitorInfo);

    [StructLayout(LayoutKind.Sequential)]
    private struct NativePoint
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MinMaxInfo
    {
        public NativePoint Reserved;
        public NativePoint MaxSize;
        public NativePoint MaxPosition;
        public NativePoint MinTrackSize;
        public NativePoint MaxTrackSize;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NativeRect
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct MonitorInfo
    {
        public int Size;
        public NativeRect MonitorArea;
        public NativeRect WorkArea;
        public uint Flags;
    }
}
