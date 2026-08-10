# Desktop redesign research

Playerok Monitor 1.1 uses an original WPF implementation. No UI source was copied. The following open-source projects were inspected to identify established interaction patterns and failure modes.

## Files

- Source: https://github.com/files-community/Files
- Professional assessment: https://www.windowscentral.com/software-apps/windows-11/how-to-get-started-with-the-files-app-on-windows-11-to-replace-file-explorer
- Useful patterns: adaptive sidebar, content-first shell, keyboard accelerators, inline `InfoBar`, compact toolbar states, list/detail preview pane, selection state separated from hover state.
- Applied here: the order list and details use the entire content surface; the separator and selected rail replace nested cards; search and filters remain in a compact fixed command row.

## DevToys

- Source: https://github.com/DevToys-app/DevToys
- UI engineering write-up: https://devtoys.app/blog/the-journey-to-devtoys-2.0
- Useful patterns: 49 px collapsed navigation, explicit compact mode, 3 px selected-item indicator, sticky grouping, restrained 167–200 ms transitions, system reduced-motion support.
- Applied here: a 54–62 px navigation rail, compact order rows, a 3 px selection rail, responsive breakpoints and disabled chart animation when Windows client-area animations are disabled.

## Windows Terminal

- Source: https://github.com/microsoft/terminal
- Useful patterns: small title/command bars, keyboard-first command palette, inline warnings instead of blocking dialogs, lazy overlay controls, shortcut hints in tooltips.
- Applied here: `Ctrl+K` command palette, `Ctrl+F`, `F5`, `Ctrl+1`, `Ctrl+2`, `Ctrl+,`, inline update state and a 40 px title bar.

## Microsoft PowerToys

- Source: https://github.com/microsoft/PowerToys
- Professional assessment: https://www.windowscentral.com/software-apps/microsoft-powertoys-had-99-problems-but-a-glitch-aint-one
- Useful patterns: glanceable dashboard, clear separation of quick actions and state, settings rows with descriptions and right-aligned switches, adaptive two-column layouts.
- Applied here: compact statistics summary, locally calculated chart, structured state panel, and settings rows that keep labels, explanations and switches aligned.

## Windows iconography and emoji

- Official icon guidance: https://learn.microsoft.com/en-us/windows/apps/design/iconography/segoe-fluent-icons-font
- Windows typography guidance: https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/typography
- WPF colour emoji renderer: https://github.com/samhocevar/emoji.wpf
- Applied here: Windows 11 Fluent glyphs at documented optical sizes, plus COLR/CPAL colour emoji rendering for order content and editable automatic messages.

## Deliberately avoided

- mobile-style oversized headers and cards;
- decorative cards without a semantic grouping purpose;
- multiple saturated accent colors competing for attention;
- shrinking text to make a layout fit;
- animations that ignore the Windows accessibility preference;
- polling the VPS to animate or populate desktop-only statistics.
