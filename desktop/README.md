# Playerok Monitor Desktop

Нативный Windows 11-клиент на WPF/.NET 10 с интерфейсом в духе Samsung One UI, общим API с Android и локальной статистикой.

## Нагрузка и совместная работа клиентов

- Android и Windows используют независимые курсоры одного журнала событий; чтение одним клиентом не потребляет событие для другого.
- При первом подключении desktop-клиент фиксирует текущий курсор, затем тихо загружает историю. Старые уведомления не воспроизводятся.
- В обычном режиме открыт один долгий `/poll`; список заказов обновляется только после события или по ручной кнопке.
- Статистика и её анимация рассчитываются из локального снимка заказов и не обращаются к VPS.
- Действия «Я проснулся» и «Выставить снова» остаются идемпотентными на сервере.

## Сборка

```powershell
dotnet run --project tests/PlayerokMonitor.Core.Tests/PlayerokMonitor.Core.Tests.csproj -c Release
dotnet publish src/PlayerokMonitor.Desktop/PlayerokMonitor.Desktop.csproj -c Release -r win-x64 --self-contained true -o publish
vpk pack --packId PlayerokMonitorDesktop --packVersion 1.0.0 --packDir publish --mainExe PlayerokMonitor.Desktop.exe
```

Установщик и пакеты обновлений выпускаются workflow `desktop.yml`. Настройки хранятся в `%LocalAppData%\PlayerokMonitor`; Pairing URL защищён Windows DPAPI.
