FONT_SIZES = {
    "x-small": 0.7,
    "smaller": 0.8,
    "small": 0.9,
    "normal": 1,
    "large": 1.1,
    "larger": 1.2,
    "x-large": 1.3
}

# Language options shown in the plugin settings dropdown.
# The selected locale code is passed to FullCalendar and to Intl.DateTimeFormat for the
# dashboard title and list-day headers, so dates (weekday, month, day, year) are already
# fully localized by the browser when the correct locale code is used.
LOCALE_MAP = {
    "en": "English",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
}

# UI strings for localization (keyed by locale code).
# To add a new language:
#   1. Add an entry to LOCALE_MAP above (e.g. "it": "Italian").
#   2. Add a corresponding entry here with the same keys as "en", translated.
# The calendar and date formatting use the same locale code, so weekday/month names and
# date order will be correct for that language without further changes.
LABELS = {
    "en": {
        "allDayText": "All day",
        "noEventsContent": "Nothing scheduled!",
        "nothingMoreToday": "Nothing more for today.",
        "today": "Today",
        "tomorrow": "Tomorrow",
        "dayAfterTomorrow": "Day after tomorrow",
    },
    "de": {
        "allDayText": "Ganztägig",
        "noEventsContent": "Nix geplant!",
        "nothingMoreToday": "Nix mehr los heute!",
        "today": "Heute",
        "tomorrow": "Morgen",
        "dayAfterTomorrow": "Übermorgen",
    },
    "es": {
        "allDayText": "Todo el día",
        "noEventsContent": "¡Nada programado!",
        "nothingMoreToday": "Nada más para hoy.",
        "today": "Hoy",
        "tomorrow": "Mañana",
        "dayAfterTomorrow": "Pasado mañana",
    },
    "fr": {
        "allDayText": "Toute la journée",
        "noEventsContent": "Rien de prévu !",
        "nothingMoreToday": "Rien d'autre pour aujourd'hui.",
        "today": "Aujourd'hui",
        "tomorrow": "Demain",
        "dayAfterTomorrow": "Après-demain",
    },
}

WEATHER_ICONS = {
    0: "☀️",   # klar
    1: "🌤️",  # meist klar
    2: "⛅",   # teilweise bewölkt
    3: "☁️",   # bedeckt
    45: "🌫️",  # Nebel
    48: "🌫️",
    51: "🌦️",  # Niesel
    53: "🌦️",
    55: "🌦️",
    61: "🌧️",  # Regen
    63: "🌧️",
    65: "🌧️",
    71: "❄️",  # Schnee
    73: "❄️",
    75: "❄️",
    80: "🌦️",  # Schauer
    81: "🌧️",
    82: "🌧️",
    95: "⛈️",  # Gewitter
    96: "⛈️",
    99: "⛈️",
}
