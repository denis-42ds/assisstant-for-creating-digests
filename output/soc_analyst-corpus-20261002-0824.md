# Дайджест ИТ/ИБ — SOC-аналитик (L2/L3), мониторинг и реагирование на инциденты

_Сформировано: 2026-10-03 06:55 UTC · профиль: `soc_analyst` · публикаций: 30_

## Атака
### Низкий (не РФ)
- **Вредонос SC для WordPress восстанавливает удалённый бэкдор за секунды** — Описывает техники закрепления вредоносного ПО на веб-ресурсах, что полезно для анализа инцидентов и создания правил детектирования веб-шеллов.
  Источники: [anti_malware](https://www.anti-malware.ru/news/2026-10-01-111332/51602)

- **Мошенники используют ChatGPT[.]com для заражения Windows трояном** — Описывает актуальную фишинговую кампанию с доставкой трояна на Windows через скомпрометированные сценарии социнженерии. Полезна для настройки сетевых детектирований и анализа индикаторов.
  Источники: [anti_malware](https://www.anti-malware.ru/news/2026-10-01-111332/51603)

## Уязвимость
### Высокая (есть эксплойт)
- **Critical Zero-Day Vulnerabilities Exploited in Citrix NetScaler ADC, Gateway** — Критические уязвимости zero-day в Citrix NetScaler активно эксплуатируются в дикой природе, что требует срочного мониторинга сетевого периметра.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/alerts/2026/09/27/critical-zero-day-vulnerabilities-exploited-citrix-netscaler-adc-gateway)

- **CISA Adds Two Known Exploited Vulnerabilities to Catalog** — Добавление уязвимостей Citrix NetScaler в каталог KEV указывает на их активную эксплуатацию и необходимость проверки инфраструктуры.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/alerts/2026/09/27/cisa-adds-two-known-exploited-vulnerabilities-catalog)

- **CISA Adds One Known Exploited Vulnerability to Catalog** — Уязвимость Fortinet FortiMail внесена в KEV в связи с фактами реальной эксплуатации, критична для приоритизации алертов.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/alerts/2026/10/01/cisa-adds-one-known-exploited-vulnerability-catalog)

- **CISA Adds One Known Exploited Vulnerability to Catalog** — Уязвимость Apple добавлена в KEV как используемая в атаках, требует внимания при мониторинге конечных точек.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/alerts/2026/09/29/cisa-adds-one-known-exploited-vulnerability-catalog)

- **CISA Adds One Known Exploited Vulnerability to Catalog** — Уязвимость WordPress Core зафиксирована в каталоге KEV с признаками активной эксплуатации в сети.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/alerts/2026/09/25/cisa-adds-one-known-exploited-vulnerability-catalog)

- **CISA Adds One Known Exploited Vulnerability to Catalog** — Попадание уязвимости Cisco Catalyst SD-WAN в KEV требует проверки сетевого оборудования на наличие признаков компрометации.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/alerts/2026/09/30/cisa-adds-one-known-exploited-vulnerability-catalog)

- **Apple исправила использовавшуюся в атаках 0-day-уязвимость в CoreGraphics** — Уязвимость нулевого дня в Apple CoreGraphics активно применялась в целевых атаках, что важно для анализа угроз.
  Источники: [xakep](https://xakep.ru/2026/10/01/cve-2026-86950/)

- **CVE-2026-43783: Починить права — получить root: LPE через DesktopServicesHelper в macOS 26.5** — Детальный разбор локального повышения привилегий (LPE) в macOS с примером логики уязвимости. Полезно для понимания векторов атак на конечные точки.
  Источники: [habr_infosec](https://habr.com/ru/companies/pt/articles/1088628/?utm_campaign=1088628&utm_source=habrahabr&utm_medium=rss)

- **MikroTik RouterOS** — Критическая уязвимость (RCE) в MikroTik RouterOS с высоким CVSS, затрагивающая инфраструктурное сетевое оборудование. Требует срочной проверки периметра сети на наличие уязвимых версий.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-272-06)

- **Lantronix G520 Series Cellular Gateway** — Уязвимость в сотовых шлюзах позволяет выполнять произвольный код с правами root. Важно для контроля периметра удаленных точек подключения и IoT/IIoT устройств.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-272-01)

### Средняя (нет эксплойта)
- **Toptech TMS7 and TopHAT** — Множественные уязвимости в ПО Toptech требуют патч-менеджмента, но прямых данных об активной эксплуатации в дикой природе нет.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-272-02)

- **Armatura LLC Armatura One** — Содержит информацию о критических уязвимостях удаленного выполнения кода и несанкционированного доступа в системах контроля доступа.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-274-01)

- **Anjvision YSSD-RTMP-H5** — Перечисление уязвимостей IoT-устройств с возможностью выполнения команд ОС и полного захвата контроля над устройствами.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-272-05)

- **VIVOTEK Camera Firmware** — Уязвимость удаленного выполнения команд с привилегиями root в IP-камерах, требующая учета при сканировании периметра.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-272-03)

- **Monta monta.app** — Множественные критические уязвимости в ПО зарядных станций без явных упоминаний активных эксплойтов в дикой природе. Требует внимания для оценки периметра, но имеет низкий приоритет для немедленного реагирования.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-274-02)

- **Johnson Controls EasyIO Neo Series EC and CW Controllers** — Уязвимость раскрытия чувствительных данных в промышленных контроллерах. Информация полезна для мониторинга ICS/SCADA систем, но признаков эксплуатации нет.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-274-04)

- **Johnson Controls EasyIO Neo Series EC and CW Controllers** — Еще одна уязвимость контроллеров Johnson Controls, связанная с перехватом сессий и учетных данных. Информация важна для защиты инфраструктуры, но эксплойты в паблике не отмечены.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-274-05)

- **Baicells Nova 430H** — Уязвимость вызывает DoS в телекоммуникационном оборудовании Baicells. Информация полезна для профильных сетевых инженеров и SOC-мониторинга критической инфраструктуры.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-272-04)

- **Viidure Dashcam Android Application** — Критические уязвимости с некорректным назначением прав в мобильном приложении. Прямого отношения к корпоративному мониторингу инцидентов и корпоративным сетям не имеет.
  Источники: [cisa_advisories](https://www.cisa.gov/news-events/ics-advisories/icsa-26-272-07)

## Инфо
### Новости ТГ
- **Microsoft опубликовал WSL 3.0 с поддержкой запуска Linux-контейнеров в Windows** — Релиз функционала WSL 3.0 полезен для общего кругозора SOC-аналитика, но не содержит непосредственных индикаторов угроз.
  Источники: [opennet](https://www.opennet.ru/opennews/art.shtml?num=66369)

- **[Перевод] Оптимизация правил YARA: руководство по ускорению и точности сканирования** — Практическое руководство по оптимизации YARA-правил напрямую помогает SOC-аналитику эффективнее строить детектирование.
  Источники: [habr_infosec](https://habr.com/ru/companies/garda/articles/1088954/?utm_campaign=1088954&utm_source=habrahabr&utm_medium=rss)

- **Выпуск Wifibox 0.17, окружения для использования WiFi-драйверов Linux во FreeBSD** — Обзор системного ПО общего назначения, не содержит информации об угрозах или уязвимостях для работы SOC.
  Источники: [opennet](https://www.opennet.ru/opennews/art.shtml?num=66354)

- **Бета-выпуск f4 0.3, кроссплатформенного ремейка Far Manager** — Релиз утилиты для конечных пользователей, не относится к мониторингу инцидентов безопасности.
  Источники: [opennet](https://www.opennet.ru/opennews/art.shtml?num=66366)

- **Проект Argon Forge опубликовал оптимизированные сборки Mesa, Gamescope, DXVK, VKD3D-Proton и Wine** — Новость игровой и околосистемной тематики Linux, не представляющая интереса для расследования инцидентов.
  Источники: [opennet](https://www.opennet.ru/opennews/art.shtml?num=66380)

- **Выпуск инсталлятора Archinstall 4.5, применяемого в дистрибутиве Arch Linux** — Обновление инструмента установки операционной системы общего назначения.
  Источники: [opennet](https://www.opennet.ru/opennews/art.shtml?num=66372)

- **Первый бета-выпуск видеоредактора GoZen, созданного на базе игрового движка Godot и FFmpeg** — Релиз мультимедийного приложения, не связан с профилем информационной безопасности.
  Источники: [opennet](https://www.opennet.ru/opennews/art.shtml?num=66359)

- **Релиз фреймворка Qt 6.12 LTS** — Релиз программного фреймворка общего назначения для разработчиков ПО.
  Источники: [opennet](https://www.opennet.ru/opennews/art.shtml?num=66377)

- **Опубликован легковесный дистрибутив antiX 26.1** — Релиз дистрибутива Linux общей тематики. Не содержит информации об угрозах, уязвимостях или тактиках злоумышленников, релевантность для SOC минимальна.
  Источники: [opennet](https://www.opennet.ru/opennews/art.shtml?num=66373)
