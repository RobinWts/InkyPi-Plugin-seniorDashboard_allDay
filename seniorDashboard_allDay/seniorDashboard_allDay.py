from plugins.base_plugin.base_plugin import BasePlugin
from plugins.seniorDashboard_allDay.constants import LOCALE_MAP, LABELS, FONT_SIZES, WEATHER_ICONS
from plugins.seniorDashboard_allDay import reboot_manager
from plugins.seniorDashboard_allDay.reboot_manager import REBOOT_DELAY_SECONDS
from utils.app_utils import get_font
from PIL import ImageColor, Image, ImageDraw
import icalendar
import recurring_ical_events
import logging
import requests
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

# device.json key holding the last successfully fetched dashboard data (events + weather), used to
# keep showing a real dashboard when the network is down. Survives reboots.
CACHE_KEY = "seniorDashboard_allDay_cache"

# device.json key for the consecutive stale-refresh counter: how many refreshes in a row have shown
# cached (not freshly fetched) data since the last successful connection. Drives the corner
# indicator (green dot at 0, the number otherwise) and is reset on a successful fetch.
STALE_COUNT_KEY = "seniorDashboard_allDay_stale_count"


class SeniorDashboardAllDay(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['locale_map'] = LOCALE_MAP
        return template_params

    def generate_image(self, settings, device_config):
        """Always show a real dashboard. When online, fetch fresh data, cache it, and render with a
        green-dot indicator. When the fetch fails or the network is down, render the *same*
        dashboard from the cached data (correct current date + appointments + last weather) with a
        small number indicator instead, and -- if the network is genuinely down -- reboot a few
        minutes later to try to restore the Wi-Fi.

        Branches:
          1. No calendar configured  -> localized status screen, no reboot (a reboot can't add a URL).
          2. Online + fetch succeeds -> cache, reset counter, cancel reboot, dashboard + green dot.
          3. Online + fetch fails     -> re-check network; render cached dashboard + number.
                                         Reboot only if the network actually dropped mid-fetch.
          4. Offline                  -> render cached dashboard + number, reboot ~5 min later.
                                         (If no cache exists yet: localized status screen + reboot.)
        """
        calendar_urls = settings.get('calendarURLs[]')

        # 1. Configuration check.
        if not calendar_urls or not any((u or '').strip() for u in calendar_urls):
            logger.warning("seniorDashboard: no calendar URL configured")
            return self._handle_failure(device_config, settings, reason="config", urls=calendar_urls)

        # 2/3. Online path: try to fetch fresh data.
        if self._check_connectivity(calendar_urls):
            try:
                data = self._fetch_dashboard_data(settings, device_config, calendar_urls)
                image = self._render_from_data(
                    settings, device_config, data, indicator={"mode": "ok", "count": 0})
                # Only commit success once we have a rendered image in hand.
                self._save_cache(device_config, data)
                self._reset_stale_count(device_config)
                reboot_manager.cancel_reboot()
                return image
            except Exception:
                logger.exception("seniorDashboard: online update failed; falling back to cache")
                # A flap may have dropped the network mid-fetch -> re-classify.
                offline = not self._check_connectivity(calendar_urls)
                return self._render_stale_or_fallback(settings, device_config, offline=offline)

        # 4. Offline path: network is down.
        return self._render_stale_or_fallback(settings, device_config, offline=True)

    def _render_stale_or_fallback(self, settings, device_config, offline):
        """Render the dashboard from cached data with the stale-counter indicator. Falls back to the
        localized no-data status screen if no cache exists yet (a fresh install that has never
        connected). Schedules a recovery reboot only when the network is actually down."""
        cache = self._load_cache(device_config)
        count = self._increment_stale_count(device_config)

        if offline:
            tz = pytz.timezone(device_config.get_config("timezone", default="America/New_York"))
            reboot_manager.schedule_reboot(
                REBOOT_DELAY_SECONDS, datetime.now(tz) + timedelta(seconds=REBOOT_DELAY_SECONDS))

        if cache:
            try:
                image = self._render_from_data(
                    settings, device_config, cache, indicator={"mode": "stale", "count": count})
                if image:
                    return image
                logger.warning("seniorDashboard: cached render returned None; status fallback")
            except Exception:
                logger.exception("seniorDashboard: cached render failed; status fallback")

        # No usable cache (or cached render failed) -> bootstrap status screen.
        return self._handle_failure(
            device_config, settings,
            reason=("offline" if offline else "error"),
            urls=settings.get('calendarURLs[]'))

    # ----- Data fetch (network; online only) -----

    def _fetch_dashboard_data(self, settings, device_config, calendar_urls):
        """Fetch fresh calendar events + weather. Raises on any fetch error.

        Returns a JSON-serializable dict suitable for caching:
            {"events": [...], "weather": {...}, "fetched_at": "<ISO>"}
        The events are *unfiltered* within the ~2-week window; date-relative filtering happens at
        render time (_filter_active_events) so the cache stays reusable across multiple days.
        """
        calendar_colors = settings.get('calendarColors[]')
        default_color = '#007BFF'
        if not calendar_colors or len(calendar_colors) < len(calendar_urls):
            calendar_colors = [default_color] * len(calendar_urls)

        timezone = device_config.get_config("timezone", default="America/New_York")
        locale_code = settings.get("language") or "en"
        tz = pytz.timezone(timezone)

        current_dt = datetime.now(tz)
        start, end = self.get_view_range(current_dt)
        logger.info(f"Fetching events for this week and next week: {start} --> [{current_dt}] --> {end}")
        events = self.fetch_ics_events(calendar_urls, calendar_colors, tz, start, end, current_dt)
        if not events:
            logger.warning("No events found for ics url")

        # Weather is best-effort (fetch_weather_data catches its own errors and returns an empty block).
        # The weather API hiccups independently of the calendar (e.g. a transient 502). When it does,
        # don't blank the weather / clobber the cache -- reuse the last-known-good cached weather so a
        # weather outage never wipes the weather block while the calendar is still updating fine.
        weather_data = self.fetch_weather_data(timezone, locale_code)
        if not (weather_data and weather_data.get("current")):
            prev = self._load_cache(device_config)
            prev_weather = (prev or {}).get("weather") or {}
            if prev_weather.get("current"):
                logger.info("seniorDashboard: weather fetch failed; reusing last cached weather")
                weather_data = prev_weather

        return {
            "events": events,
            "weather": weather_data,
            "fetched_at": current_dt.isoformat(),
        }

    # ----- Render (always; from fresh or cached data) -----

    def _render_from_data(self, settings, device_config, data, indicator):
        """Build the dashboard image from a data dict ({events, weather}) -- fresh or cached.

        Re-applies today-relative event filtering and today/tomorrow/day-after placeholder
        injection against the *current* date, so cached events re-bucket correctly as days pass.
        Raises on render failure.
        """
        default_color = '#007BFF'
        view = "listWeek"  # Fixed to list view (today + next 2 days)
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)
        current_dt = datetime.now(tz)

        events = self._filter_active_events(data.get("events") or [], current_dt, tz)
        weather_data = data.get("weather") or {"current": None, "forecast": []}

        # Hardcode display options to True
        display_settings = settings.copy()
        display_settings["displayTitle"] = "true"
        display_settings["displayWeekends"] = "true"
        display_settings["displayEventTime"] = "true"

        # Ensure language is set (default to 'en' if not provided)
        if "language" not in display_settings or not display_settings["language"]:
            display_settings["language"] = "en"

        locale_code = display_settings.get("language", "en")
        labels = LABELS.get(locale_code, LABELS["en"])

        events = self._inject_placeholders(events, current_dt, tz, labels, default_color)

        template_params = {
            "view": view,
            "events": events,
            "current_dt": current_dt.replace(minute=0, second=0, microsecond=0).isoformat(),
            "timezone": timezone,
            "plugin_settings": display_settings,
            "time_format": time_format,
            "font_scale": FONT_SIZES.get(settings.get("fontSize", "normal")),
            "locale_code": locale_code,
            "labels": labels,
            "weather": weather_data,
            "indicator": indicator,
        }

        image = self.render_image(dimensions, "seniorDashboard_allDay.html", "seniorDashboard_allDay.css", template_params)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    def _inject_placeholders(self, events, current_dt, tz, labels, default_color):
        """Ensure the today/tomorrow/day-after sections are never dropped: add a placeholder event
        for any of those days that currently has no event."""
        contrast = self.get_contrast_color(default_color)

        # Today: a "nothing more for today" placeholder.
        if not self._has_event_on_date(events, current_dt.date(), tz):
            today_start = current_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            events = list(events) + [{
                "title": labels["nothingMoreToday"],
                "start": today_start,
                "allDay": True,
                "backgroundColor": default_color,
                "textColor": contrast,
                "classNames": ["senior-dashboard-nothing-more"],
            }]

        # Tomorrow and the day after: a "nothing scheduled" placeholder.
        for offset in (1, 2):
            day = current_dt.date() + timedelta(days=offset)
            if not self._has_event_on_date(events, day, tz):
                day_start = (current_dt + timedelta(days=offset)).replace(
                    hour=0, minute=0, second=0, microsecond=0).isoformat()
                events = list(events) + [{
                    "title": labels["noEventsContent"],
                    "start": day_start,
                    "allDay": True,
                    "backgroundColor": default_color,
                    "textColor": contrast,
                    "classNames": ["senior-dashboard-nothing-more"],
                }]
        return events

    def fetch_ics_events(self, calendar_urls, colors, tz, start_range, end_range, current_dt):
        """Fetch and parse all events in the [start_range, end_range] window (no date filtering).

        The ended-event filtering lives in _filter_active_events and runs at render time, so the
        returned (and cached) list stays reusable across multiple days of an offline outage.
        """
        parsed_events = []
        for calendar_url, color in zip(calendar_urls, colors):
            cal = self.fetch_calendar(calendar_url)
            events = recurring_ical_events.of(cal).between(start_range, end_range)
            contrast_color = self.get_contrast_color(color)

            for event in list(events):
                start, end, all_day = self.parse_data_points(event, tz)
                event_title = str(event.get('summary'))

                parsed_event = {
                    "title": event_title,
                    "start": start,
                    "backgroundColor": color,
                    "textColor": contrast_color,
                    "allDay": all_day
                }
                if end:
                    parsed_event['end'] = end

                parsed_events.append(parsed_event)

        logger.info(f"Parsed {len(parsed_events)} events in window")
        return parsed_events

    def _filter_active_events(self, events, current_dt, tz):
        """Drop events that have fully ended relative to current_dt (start of today). Keeps events
        whose date can't be parsed rather than hiding potentially valid data."""
        current_day_start = current_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        active = []
        for ev in events:
            start = ev.get("start")
            end = ev.get("end")
            all_day = ev.get("allDay", False)
            try:
                end_iso = end or start
                end_dt = datetime.fromisoformat(end_iso)
                if end_dt.tzinfo is None:
                    end_dt = tz.localize(end_dt)
                # Ended before today.
                if end_dt.date() < current_day_start.date():
                    continue
                # Today's timed event that has already ended.
                if end_dt.date() == current_dt.date() and not all_day and end_dt <= current_dt:
                    continue
            except Exception:
                pass  # keep on parse failure
            active.append(ev)
        return active

    def _has_event_on_date(self, events, target_date, tz):
        """Return True if any event starts on target_date (timezone-aware comparison)."""
        for ev in events:
            start_str = ev.get("start")
            if not start_str:
                continue
            try:
                dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = tz.localize(dt)
                else:
                    dt = dt.astimezone(tz)
                if dt.date() == target_date:
                    return True
            except (ValueError, TypeError):
                continue
        return False

    def get_view_range(self, current_dt):
        """Get the date range for this week and next week (2 weeks total)."""
        start = datetime(current_dt.year, current_dt.month, current_dt.day)
        end = start + timedelta(weeks=2)
        return start, end

    def parse_data_points(self, event, tz):
        all_day = False
        dtstart = event.decoded("dtstart")
        if isinstance(dtstart, datetime):
            start = dtstart.astimezone(tz).isoformat()
        else:
            start = dtstart.isoformat()
            all_day = True

        end = None
        if "dtend" in event:
            dtend = event.decoded("dtend")
            if isinstance(dtend, datetime):
                end = dtend.astimezone(tz).isoformat()
            else:
                end = dtend.isoformat()
        elif "duration" in event:
            duration = event.decoded("duration")
            end = (dtstart + duration).isoformat()
        return start, end, all_day

    def _normalize_url(self, calendar_url):
        """Rewrite webcal:// URLs to https:// (requests cannot handle the webcal scheme)."""
        if calendar_url.startswith("webcal://"):
            return calendar_url.replace("webcal://", "https://")
        return calendar_url

    def _check_connectivity(self, calendar_urls):
        """Return True if at least one calendar URL is reachable over the network.

        Only a connection-level failure (timeout / connection refused / DNS) for *all* URLs
        counts as offline. If any URL returns an HTTP response -- even an error like 404/500 --
        the network is up and we treat it as online (a reboot would not fix a server error).
        """
        for url in calendar_urls:
            if not url or not url.strip():
                continue
            try:
                # stream=True avoids downloading the body; we only care that bytes start flowing.
                response = requests.get(self._normalize_url(url.strip()), timeout=5, stream=True)
                response.close()
                return True  # got an HTTP response => network is reachable
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logger.warning(f"Calendar URL unreachable (network): {url} ({e})")
                continue
            except requests.exceptions.RequestException as e:
                # Any other request error still means the server answered/resolved => online.
                logger.warning(f"Calendar URL reachable but errored: {url} ({e})")
                return True
        return False

    # ----- Local state: cached data + stale counter (persisted in device.json) -----

    def _save_cache(self, device_config, data):
        try:
            device_config.update_value(CACHE_KEY, data, write=True)
        except Exception:
            logger.warning("seniorDashboard: could not persist data cache", exc_info=True)

    def _load_cache(self, device_config):
        """Return the cached data dict ({events, weather, ...}) or None if no usable cache exists."""
        try:
            cache = device_config.get_config(CACHE_KEY, default=None)
            if isinstance(cache, dict) and cache.get("events") is not None:
                return cache
        except Exception:
            logger.warning("seniorDashboard: could not read data cache", exc_info=True)
        return None

    def _get_stale_count(self, device_config):
        try:
            return int(device_config.get_config(STALE_COUNT_KEY, default=0) or 0)
        except Exception:
            return 0

    def _set_stale_count(self, device_config, value):
        try:
            device_config.update_value(STALE_COUNT_KEY, int(value), write=True)
        except Exception:
            logger.warning("seniorDashboard: could not persist stale count", exc_info=True)

    def _increment_stale_count(self, device_config):
        count = self._get_stale_count(device_config) + 1
        self._set_stale_count(device_config, count)
        return count

    def _reset_stale_count(self, device_config):
        if self._get_stale_count(device_config) != 0:
            self._set_stale_count(device_config, 0)

    # ----- No-data status screen (used only when there is no cached dashboard to show) -----

    def _format_reboot_time(self, device_config, reboot_at, labels):
        """Format a reboot time as e.g. '13:40 Uhr' / '1:40 PM', honoring 12h/24h + locale clock suffix."""
        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        local = reboot_at.astimezone(pytz.timezone(timezone))
        if time_format == "12h":
            s = local.strftime("%I:%M %p").lstrip("0")
        else:
            s = local.strftime("%H:%M")
        return f"{s} {labels.get('offlineClock', '')}".strip()

    def _handle_failure(self, device_config, settings, reason, urls):
        """Render a localized no-data status screen (never raises). Used only when there is no cached
        dashboard to show: reason 'config' (no calendar configured -> no reboot) or the
        'offline'/'error' bootstrap before the first successful fetch. Reboot scheduling for the
        offline bootstrap case is handled by the caller; here we only display any pending reboot time.
        """
        try:
            locale_code = settings.get("language") or "en"
            labels = LABELS.get(locale_code, LABELS["en"])

            # Config errors are not recoverable by a reboot.
            if reason == "config":
                return self._render_status_image(
                    settings, device_config,
                    title=labels.get("errorTitle", "Error"),
                    message=labels.get("configMessage", ""),
                    reboot_prefix=None, reboot_time=None, note=None)

            # Show the pending reboot time if the caller scheduled one.
            pending = reboot_manager.get_scheduled_reboot()
            reboot_time_str = self._format_reboot_time(device_config, pending, labels) if pending else None

            if reason == "offline":
                title = labels.get("offlineTitle", "No internet connection")
                message = None
                reboot_prefix = labels.get("offlineMessage")
            else:  # error
                title = labels.get("errorTitle", "Update failed")
                message = labels.get("errorMessage")
                reboot_prefix = labels.get("rebootPrefix")

            if not reboot_time_str:
                reboot_prefix = None
            note = labels.get("offlineReassure")

            return self._render_status_image(
                settings, device_config,
                title=title, message=message,
                reboot_prefix=reboot_prefix, reboot_time=reboot_time_str, note=note)
        except Exception:
            logger.exception("seniorDashboard: failure handler crashed; emergency PIL screen")
            try:
                return self._render_status_pil(device_config, "Error", None, None, None, None)
            except Exception:
                w, h = device_config.get_resolution()
                return Image.new("RGB", (w, h), "white")

    def _render_status_image(self, settings, device_config, title, message,
                             reboot_prefix, reboot_time, note):
        """Render the status/error screen via HTML; fall back to pure PIL if Chromium fails."""
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        timezone = device_config.get_config("timezone", default="America/New_York")
        locale_code = settings.get("language") or "en"
        tz = pytz.timezone(timezone)

        template_params = {
            "current_dt": datetime.now(tz).isoformat(),
            "timezone": timezone,
            "locale_code": locale_code,
            "title": title,
            "message": message,
            "reboot_prefix": reboot_prefix,
            "reboot_time": reboot_time,
            "note": note,
            "font_scale": FONT_SIZES.get(settings.get("fontSize", "normal")),
            "plugin_settings": settings,
        }
        try:
            image = self.render_image(dimensions, "offline.html", "offline.css", template_params)
            if image:
                return image
            logger.warning("seniorDashboard: status render returned None; PIL fallback")
        except Exception:
            logger.exception("seniorDashboard: status HTML render failed; PIL fallback")
        return self._render_status_pil(device_config, title, message, reboot_prefix, reboot_time, note)

    def _render_status_pil(self, device_config, title, message, reboot_prefix, reboot_time, note):
        """Last-resort status screen drawn with PIL only (no Chromium dependency)."""
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        w, h = dimensions
        tz = pytz.timezone(device_config.get_config("timezone", default="America/New_York"))
        now = datetime.now(tz)

        img = Image.new("RGB", (w, h), "white")
        draw = ImageDraw.Draw(img)

        # (text, y-fraction, font-size-fraction, weight, color); skip empty lines.
        reboot_line = None
        if reboot_time:
            reboot_line = f"{reboot_prefix} {reboot_time}".strip() if reboot_prefix else reboot_time
        rows = [
            (now.strftime("%d.%m.%Y"), 0.16, 0.085, "bold", (0, 0, 0)),
            (title, 0.36, 0.075, "bold", (200, 0, 0)),
            (message, 0.50, 0.050, "normal", (0, 0, 0)),
            (reboot_line, 0.64, 0.060, "bold", (0, 0, 200)),
            (note, 0.80, 0.045, "normal", (0, 0, 0)),
        ]
        for text, yf, sf, weight, color in rows:
            if not text:
                continue
            try:
                font = get_font("Jost", int(h * sf), weight)
                draw.text((w / 2, h * yf), text, font=font, fill=color, anchor="mm")
            except Exception:
                logger.warning("seniorDashboard: PIL draw failed for a line", exc_info=True)
        return img

    def fetch_calendar(self, calendar_url):
        calendar_url = self._normalize_url(calendar_url)
        try:
            response = requests.get(calendar_url, timeout=30)
            response.raise_for_status()
            return icalendar.Calendar.from_ical(response.text)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch iCalendar url: {str(e)}")

    def get_contrast_color(self, color):
        """
        Returns '#000000' (black) or '#ffffff' (white) depending on the contrast
        against the given color.
        """
        r, g, b = ImageColor.getrgb(color)
        # YIQ formula to estimate brightness
        yiq = (r * 299 + g * 587 + b * 114) / 1000

        return '#000000' if yiq >= 150 else '#ffffff'

    def get_weather_icon(self, code):
        """Get weather icon emoji for a given weather code."""
        return WEATHER_ICONS.get(code, "❓")

    def fetch_weather_data(self, timezone, locale_code="en"):
        """Fetch weather data from Open-Meteo API."""
        URL = "https://api.open-meteo.com/v1/dwd-icon"
        day_labels = LABELS.get(locale_code, LABELS["en"])

        # Default coordinates (can be made configurable later)
        params = {
            "latitude": 49.8728,
            "longitude": 8.6512,
            "current_weather": True,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
            "forecast_days": 3,
            "timezone": timezone
        }

        try:
            response = requests.get(URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Process current weather
            current = data.get("current_weather", {})
            current_weather = {
                "icon": self.get_weather_icon(current.get("weathercode", 0)),
                "temperature": current.get("temperature", 0),
                "windspeed": current.get("windspeed", 0),
                "weathercode": current.get("weathercode", 0)
            }

            # Process daily forecast (first 2 days: tomorrow and day after)
            daily = data.get("daily", {})
            forecast = []
            if "time" in daily:
                for i, day in enumerate(daily["time"][:2]):
                    date_label = day_labels["tomorrow"] if i == 0 else day_labels["dayAfterTomorrow"]
                    forecast.append({
                        "date": date_label,
                        "icon": self.get_weather_icon(daily.get("weathercode", [0])[i] if i < len(daily.get("weathercode", [])) else 0),
                        "temp_min": daily.get("temperature_2m_min", [0])[i] if i < len(daily.get("temperature_2m_min", [])) else 0,
                        "temp_max": daily.get("temperature_2m_max", [0])[i] if i < len(daily.get("temperature_2m_max", [])) else 0,
                        "precipitation": daily.get("precipitation_sum", [0])[i] if i < len(daily.get("precipitation_sum", [])) else 0,
                        "weathercode": daily.get("weathercode", [0])[i] if i < len(daily.get("weathercode", [])) else 0
                    })

            return {
                "current": current_weather,
                "forecast": forecast
            }
        except Exception as e:
            logger.warning(f"Failed to fetch weather data: {str(e)}")
            return {
                "current": None,
                "forecast": []
            }
