"""Process-scoped reboot scheduler for the Senior Dashboard plugin.

When the device loses its network connection the dashboard cannot fetch fresh data. Power-save on
the Pi/router occasionally kills the WLAN until the device is rebooted, so the plugin schedules a
delayed reboot to recover automatically. This module holds the scheduling state (a single
``threading.Timer``) so it survives across ``generate_image()`` calls within the same process.

The reboot fires a short time *after* an offline refresh has already rendered the cached dashboard,
so the e-paper keeps showing the current date + appointments across the reboot. InkyPi does not
refresh on boot -- the refresh thread waits a full ``plugin_cycle_interval_seconds`` (~45 min)
before its first check -- so this produces a gentle ~45-min reboot cadence, not a tight boot-loop.

The reboot uses ``os.system("sudo reboot")`` -- the same mechanism the core ``settings.py``
``/shutdown`` endpoint uses, relying on the already-configured passwordless sudo.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

# Delay before the reboot fires after an offline refresh has rendered the cached dashboard.
# Long enough that the rendered image is on screen before the device restarts.
REBOOT_DELAY_SECONDS = 300  # 5 minutes

_lock = threading.Lock()
_timer = None
_reboot_at = None


def schedule_reboot(delay_seconds, reboot_at_dt):
    """Schedule a one-shot reboot after ``delay_seconds``.

    Idempotent: if a reboot is already pending, the existing schedule is kept and its
    ``reboot_at`` time is returned. This keeps the time shown on the offline screen stable
    across repeated refreshes during the same outage.

    Args:
        delay_seconds (float): Seconds from now until the reboot fires.
        reboot_at_dt (datetime): The wall-clock time the reboot is expected to occur, used
            only for display.

    Returns:
        datetime: The effective scheduled reboot time (existing one if already pending).
    """
    global _timer, _reboot_at
    with _lock:
        if _timer is not None:
            logger.info(f"Reboot already scheduled for {_reboot_at}; keeping existing schedule")
            return _reboot_at
        _reboot_at = reboot_at_dt
        _timer = threading.Timer(delay_seconds, _do_reboot)
        _timer.daemon = True
        _timer.start()
        logger.warning(
            f"Reboot scheduled in {delay_seconds:.0f}s (at {_reboot_at}) due to a failed update"
        )
        return _reboot_at


def cancel_reboot():
    """Cancel a pending reboot, if any.

    Returns:
        bool: True if a pending reboot was canceled, False if none was scheduled.
    """
    global _timer, _reboot_at
    with _lock:
        if _timer is None:
            return False
        _timer.cancel()
        logger.info(f"Connectivity restored -- canceled reboot that was scheduled for {_reboot_at}")
        _timer = None
        _reboot_at = None
        return True


def get_scheduled_reboot():
    """Return the currently scheduled reboot time, or None if no reboot is pending."""
    with _lock:
        return _reboot_at


def _do_reboot():
    """Fire the actual reboot. Runs on the Timer thread."""
    logger.warning("Rebooting device now due to lost connectivity")
    os.system("sudo reboot")
