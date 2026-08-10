$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$assetDirectory = Join-Path $PSScriptRoot '..\assets'
New-Item -ItemType Directory -Force -Path $assetDirectory | Out-Null
$destination = Join-Path $assetDirectory 'app.ico'

$bitmap = New-Object System.Drawing.Bitmap 256, 256
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$gradient = $null
$glow = $null
$font = $null
$white = $null
$icon = $null
$stream = $null
try {
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.Clear([System.Drawing.Color]::Transparent)
    $path.AddArc(10, 10, 236, 236, 0, 360)
    $gradient = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
        (New-Object System.Drawing.Rectangle 0, 0, 256, 256),
        [System.Drawing.Color]::FromArgb(38, 113, 255),
        [System.Drawing.Color]::FromArgb(47, 202, 209),
        35.0
    )
    $graphics.FillPath($gradient, $path)
    $glow = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(42, 255, 255, 255))
    $graphics.FillEllipse($glow, 44, 28, 168, 168)
    $font = New-Object System.Drawing.Font 'Segoe UI', 126, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
    $white = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
    $size = $graphics.MeasureString('P', $font)
    $graphics.DrawString('P', $font, $white, ((256 - $size.Width) / 2 + 2), ((256 - $size.Height) / 2 - 5))
    $icon = [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
    $stream = [System.IO.File]::Create($destination)
    $icon.Save($stream)
}
finally {
    if ($stream) { $stream.Dispose() }
    if ($icon) { $icon.Dispose() }
    if ($white) { $white.Dispose() }
    if ($font) { $font.Dispose() }
    if ($glow) { $glow.Dispose() }
    if ($gradient) { $gradient.Dispose() }
    $path.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
}
Write-Host "Generated $destination"
