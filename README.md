# InkyPi-Plugin-seniorDashboard_allDay
![Example of InkyPi-Plugin-seniorDashboard_allDay](./example.png)

*InkyPi-Plugin-seniorDashboard_allDay* is a plugin for [InkyPi](https://github.com/fatihak/InkyPi) that shows a simple, at-a-glance view of the next few days: a calendar list and a small weather block. It is intended for an elderly person who has a calendar maintained for them by a family member or carer.

**What it does:**

- **Calendar** — Displays today and the next two of days in a list. Events that have already ended are hidden. 
- **Weather** — Shows current conditions and a short forecast (e.g. tomorrow and the day after) in a minimal layout: icon and temperature, with high/low for the next days.
It uses the DWD (Deutscher Wetter Dienst) free API, so no API-key config needed.
- **Always shows real data, even offline** — When the internet connection drops, the plugin keeps showing a normal dashboard built from the **last successfully fetched data** (correct current date, your appointments, last weather) instead of an error screen, and quietly reboots to try to restore the connection. A small corner indicator tells you at a glance whether the data is live. See [Offline behaviour & auto-recovery](#offline-behaviour--auto-recovery) below.

The layout is kept clear and low-clutter so it works well on an e-ink display and for quick, easy reading.

It is optimized for and tested only on landscape waveshare 7.2 inch display but should render ok on every comparable landscape display.

It's basically a mix of the calendar list view and weather template.
No additional dependencies whatsoever.

**Settings:**
![Screenshot of settings of InkyPi-Plugin-seniorDashboard_allDay](./settings.png)
Language can be set to **English**, **French** , **Spanish**  or **German**. 
Other languages can easily be added in *constants.py*, just make sure to use the correct international language ID so the calendar returns correct dates/formats.
You can add multiple calendars, they will all be used to compile the today, tomorrow and day after tomorrow list.
Location setting for the weather (DWD supplies world wide weather info).
Font size for the Calendar listing.


## Offline behaviour & auto-recovery

This plugin is built for an unattended display that someone depends on every day. A common real-world problem is that the Raspberry Pi or the router drops the Wi-Fi connection (often due to power-save) and the calendar can no longer be fetched. The worst thing the display can do then is show an error screen or freeze — the person relying on it just wants to see the date and their appointments.

**So when the connection is down, the plugin keeps showing a real dashboard.** On every successful refresh it quietly **stores the fetched calendar (a ~2-week window) and weather locally**. If a later refresh can't reach the internet, it rebuilds the **same dashboard from that stored data** — the **current date** (recomputed live), your appointments re-sorted into today / tomorrow / the day after for *today's* date, and the last-known weather. The screen looks normal; it's just not freshly fetched.

### The corner indicator

A small mark in the **lower-right corner** tells you, at a glance, whether what you're looking at is live:

- **Green dot** → the last refresh successfully fetched fresh data.
- **A number** (e.g. `3`) → how many refreshes in a row have shown **stored** data since the last successful connection. It counts up while the connection is down and resets to nothing (back to the green dot) the moment a refresh gets through again.

### Automatic recovery reboot

A few minutes (**~5 min**) after an offline refresh has finished drawing the cached dashboard, the device **reboots** to try to bring the Wi-Fi back. This is safe and does **not** cause a reboot loop:

- It's an e-paper display, so it **keeps showing** the cached dashboard across the reboot and until the next scheduled refresh.
- InkyPi does **not** refresh immediately on boot — it waits a full refresh cycle (e.g. ~45 min) — so reboots end up roughly one refresh-cycle apart, not back-to-back.

The result: there is **always a current date and your appointments on screen**, and the device keeps making gentle, spaced-out attempts to reconnect on its own. (Only the weather gradually goes stale during a long outage, which is fine.)

### Details & edge cases

- **What counts as "offline":** only a genuine network failure (timeout / connection refused / DNS) for **all** configured calendars. A reachable calendar *server* that returns an error (e.g. 404) or sends bad data still shows the cached dashboard with the number, but does **not** trigger a reboot (a reboot can't fix a server-side problem).
- **First run with no connection yet** (nothing has ever been fetched, so there's no cache): the plugin shows a localized **"no internet connection"** screen with the date and the restart time, and reboots to recover — the same fallback as before, used only until the first successful fetch fills the cache.
- **Nothing configured yet** (no calendar URL): a localized **"no calendar configured"** screen, with **no** reboot (a reboot can't fix configuration).
- **Renderer safety net:** the fallback status screen normally renders via the same HTML engine as the dashboard; if that itself fails, the plugin falls back to a plain built-in screen so it still shows the date.
- The reboot uses the same `sudo reboot` mechanism as InkyPi's built-in Reboot button, so it relies on the passwordless-sudo setup a standard InkyPi installation already configures. No extra setup is required.
- The stored data and the offline counter live in the device config, so they survive the reboot — the count keeps climbing across an outage rather than resetting each cycle.
- The fallback screens are localized in the same languages as the rest of the plugin (English, German, Spanish, French) and follow the device's 12h/24h time format.


## Installation

### Install

Install the plugin using the InkyPi CLI, providing the plugin ID and GitHub repository URL:

```bash
inkypi plugin install seniorDashboard_allDay https://github.com/RobinWts/InkyPi-Plugin-seniorDashboard_allDay
```

or install the [PluginManager](https://github.com/RobinWts/InkyPi-Plugin-PluginManager) first and use that to install via WebUI.


## Development-status

Feature complete and done for the moment. Probably will update in the future if needed.

## License

This project is licensed under the GNU public License.
