# InkyPi-Plugin-seniorDashboard_allDay

*InkyPi-Plugin-seniorDashboard_allDay* is a plugin for [InkyPi](https://github.com/fatihak/InkyPi) thatshows a simple, at-a-glance view of the next few days: a calendar list and a small weather block. It is intended for an elderly person who has a calendar maintained for them by a family member or carer.

**What it does:**

- **Calendar** — Displays today and the next couple of days in a list. Events that have already ended are hidden. The calendar is read-only on the display; someone else (e.g. a relative or carer) updates the shared calendar (e.g. Google Calendar, iCal URL) via the InkyPi settings. The senior only needs to look at the screen to see what’s coming up.
- **Weather** — Shows current conditions and a short forecast (e.g. tomorrow and the day after) in a minimal layout: icon and temperature, with optional high/low and precipitation. Right now it's hardcoded to Darmstad, Germany but a setting will be added soon to change that :)

Language can be set to **English** or **German**. The layout is kept clear and low-clutter so it works well on an e-ink display and for quick, easy reading.

It is optimized for and tested only on landscape waveshare 7.2 inch display...


## Screenshot

![Example of InkyPi-Plugin-seniorDashboard_allDay](./example.png)

## Installation

### Install

Install the plugin using the InkyPi CLI, providing the plugin ID and GitHub repository URL:

```bash
inkypi install seniorDashboard_allDay https://github.com/RobinWts/InkyPi-Plugin-seniorDashboard_allDay
```



## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE.md) file for details.
