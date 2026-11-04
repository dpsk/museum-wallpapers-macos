"""The menu bar app's logic: what the status item, its card and its menu show,
what their buttons do, and a scheduler thread that does what the Omarchy
plugin's minute tick did. The AppKit side (status item, popover, menu) lives
in macui.py and calls in here; this module needs no AppKit, so it is tested
on any OS with a stand-in view."""

import argparse
import datetime
import sys
import threading
import traceback
from pathlib import Path
from typing import NamedTuple

from . import APP_NAME, BUNDLE_ID, VERSION, card, core, filelock, strings

TICK_SECONDS = 60
LOG_LIMIT = 1_000_000
SHOW_NOTIFICATION = f"{BUNDLE_ID}.show"  # a second launch asks the running app to open its card


class TimestampedLog:
    """stderr for an app without a terminal: a log file."""

    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if path.exists() and path.stat().st_size > LOG_LIMIT:
                path.replace(path.with_suffix(".old.log"))
        except OSError:
            pass
        self._file = open(path, "a", encoding="utf-8", buffering=1)
        self._lock = threading.Lock()

    def write(self, text):
        if not text.strip():
            return len(text)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            for line in text.rstrip("\n").splitlines():
                self._file.write(f"{stamp} {line}\n")
        return len(text)

    def flush(self):
        self._file.flush()


class MenuItem(NamedTuple):
    """One entry of the status item's menu; `submenu` is a list of MenuItems."""

    title: str = ""
    action: object = None
    checked: bool = False
    enabled: bool = True
    submenu: object = None
    separator: bool = False


SEPARATOR = MenuItem(separator=True)


class NullView:
    """What the app shows on screen; macui.MacView is the real one. Every
    method may be called from any thread."""

    card_open = False

    def update_status(self, tooltip, active, busy):
        pass

    def show_card(self, data):
        pass

    def update_card(self, data):
        pass

    def quit(self):
        pass


class App:
    def __init__(self, background=False, view=None):
        self.background = background
        self.platform = core.PLATFORM
        self.view = view or NullView()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.switching = threading.Lock()
        self.instance = None
        self.log = None

    # -- start and stop

    def run(self):
        """Run the menu bar app until it quits."""
        # One app at a time: a second launch asks the first to open its card.
        self.instance = filelock.acquire(core.STATE / ".instance.lock", wait=False)
        if self.instance is None:
            from . import macui
            macui.signal_running()
            return 0
        self.log = TimestampedLog(self.platform.log_file(core.STATE))
        if sys.stderr is None or getattr(sys, "frozen", False) or not sys.stderr.isatty():
            sys.stderr = self.log
        sys.excepthook = lambda *exc: print("".join(traceback.format_exception(*exc)), file=sys.stderr)
        threading.excepthook = lambda args: print(
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)), file=sys.stderr)
        print(f"museum-wallpapers: {APP_NAME} {VERSION} starting on {self.platform.name}"
              f"{' (app bundle)' if self.platform.packaged else ''}", file=sys.stderr)
        from . import macui
        return macui.run(self)

    def started(self):
        """Called once the view is up (on the main thread)."""
        self.platform.setup()
        if self.platform.launched_at_startup():
            self.background = True
        core.RUNNER = self.run_command
        threading.Thread(target=self._scheduler, name="scheduler", daemon=True).start()
        if not (core.STATE / "state.json").exists():
            # First run: say where the app lives; the first painting follows within seconds.
            self._in_background(lambda: core.notify(APP_NAME, strings.t("started", core.load_config())))
        elif not self.background:
            # Opened by the user rather than at login: show what is on screen.
            threading.Timer(1.0, self.about).start()
        self._in_background(self.refresh)

    def quit(self, *_args):
        self.stop.set()
        self.wake.set()
        self.view.quit()

    # -- background work

    def _scheduler(self):
        while not self.stop.is_set():
            self._safely(self.tick)
            self.wake.wait(TICK_SECONDS)
            self.wake.clear()

    def tick(self):
        with self.switching:
            core.cmd_tick(core.load_config(), None)
        self.refresh()

    def run_command(self, command):
        """core.spawn() lands here: helper commands on threads, not processes."""
        work = {"prefetch": core.cmd_prefetch, "notify": core.cmd_notify}.get(command)
        if work:
            threading.Thread(target=self._safely, args=(lambda: work(core.load_config(), None),),
                             name=command, daemon=True).start()

    @staticmethod
    def _safely(work):
        try:
            work()
        except Exception:  # noqa: BLE001 - logged; the app keeps running
            print("museum-wallpapers: " + traceback.format_exc(), file=sys.stderr)

    def _in_background(self, work):
        threading.Thread(target=self._safely, args=(work,), daemon=True).start()

    # -- what macOS tells the app

    def space_changed(self):
        """Another Space (virtual desktop) came up: macOS keeps a wallpaper
        per Space, so give this one the painting too."""
        self._in_background(self.reapply)

    def reapply(self):
        if not self.switching.acquire(blocking=False):
            return  # a switch is running and will set every screen anyway
        try:
            state = core.read_json(core.STATE / "state.json", {})
            original = Path(state.get("original") or "/nonexistent")
            if not original.exists():
                return
            last = getattr(self.platform, "last_images", None) or {}
            shown = self.platform.wallpapers() if hasattr(self.platform, "wallpapers") else {}
            if last and all(shown.get(key) == path for key, path in last.items() if key in shown):
                return
            config = core.load_config()
            if last and all(Path(path).exists() for path in last.values()) and not core.needs_refit(state, config):
                self.platform.set_wallpaper(last)
            else:
                core.show(original, config)
        finally:
            self.switching.release()

    def screens_changed(self):
        """A screen plugged in or out, a resolution or the Dock changed:
        re-frame now rather than at the next minute."""
        self.wake.set()

    def woke(self):
        self.wake.set()

    # -- actions

    def next(self, *_args):
        if not self.switching.acquire(blocking=False):
            return  # a switch is already running; presses meanwhile are ignored
        self.refresh_status()

        def work():
            try:
                core.cmd_next(core.load_config(), None)
            finally:
                self.switching.release()
            self.refresh()

        self._in_background(work)
        self._in_background(self.refresh)

    def read_more(self, *_args):
        self._in_background(lambda: core.cmd_open(core.load_config(), None))

    def save(self, *_args):
        self._in_background(lambda: core.cmd_keep(core.load_config(), None))

    def about(self, *_args):
        self.view.show_card(self.card_data())

    def _filter(self, action, **values):
        args = argparse.Namespace(action=action, artist=None, movement=None, genre=None, years=None, label=None,
                                  switch=True)
        for key, value in values.items():
            setattr(args, key, value)
        if not self.switching.acquire(blocking=False):
            return

        def work():
            try:
                core.cmd_filter(core.load_config(), args)
            finally:
                self.switching.release()
            self.refresh()

        self._in_background(work)
        self._in_background(self.refresh)

    def more_by(self, qid, name):
        self._filter("set", artist=[qid], label=name)

    def more_of(self, qid, name):
        self._filter("set", movement=[qid], label=name)

    def show_all(self, *_args):
        self._filter("clear")

    def set_setting(self, key, value):
        core.save_setting(key, value)
        self._in_background(self.refresh)
        self.wake.set()  # re-frame or switch now, not in a minute

    def autostart(self):
        try:
            return bool(self.platform.autostart_enabled())
        except Exception:  # noqa: BLE001
            return False

    def toggle_autostart(self, *_args):
        wanted = not self.autostart()
        try:
            done = self.platform.set_autostart(wanted)
        except Exception as exc:  # noqa: BLE001
            print(f"museum-wallpapers: open at login: {exc}", file=sys.stderr)
            done = False
        if wanted and done is False:
            core.notify(APP_NAME, strings.t("autostart_blocked", core.load_config()))

    def open_collection(self, *_args):
        self._in_background(lambda: self.platform.open_folder(core.load_config()["saveDir"]))

    def card_action(self, name, args):
        """A button in the card: `name` and its arguments, as card.js posts them."""
        args = list(args or [])
        actions = {
            "next": self.next,
            "open": self.read_more,
            "save": self.save,
            "more_by": lambda: self.more_by(str(args[0]), str(args[1])),
            "more_of": lambda: self.more_of(str(args[0]), str(args[1])),
            "show_all": self.show_all,
            "set": lambda: self.set_setting(*card.setting(args)),
        }
        work = actions.get(name)
        if work:
            work()

    # -- what the status item, card and menu show

    def current(self):
        config = core.load_config()
        return config, core.status(config)

    def tooltip(self, status):
        info = status.get("info")
        if info and info.get("title"):
            text = " — ".join(x for x in (info["title"], info.get("artist")) if x)
            return text if len(text) <= 120 else text[:119] + "…"
        return APP_NAME

    def refresh_status(self):
        config, status = self.current()
        self.view.update_status(self.tooltip(status), bool(status.get("active")), self.switching.locked())

    def refresh(self):
        """Status item and an open card after anything changed."""
        config, status = self.current()
        self.view.update_status(self.tooltip(status), bool(status.get("active")), self.switching.locked())
        if self.view.card_open:
            self.view.update_card(self.card_data(config, status))

    def card_data(self, config=None, status=None):
        if config is None:
            config, status = self.current()
        return card.data(config, status, busy=self.switching.locked())

    def menu(self):
        """The status item's menu (right click), built fresh each time it opens."""
        config, status = self.current()
        t = lambda key, **values: strings.t(key, config, **values)  # noqa: E731
        has_painting = bool(status.get("active"))

        def choice(key, value, title, current=None):
            current = config.get(key) if current is None else current
            return MenuItem(title, lambda: self.set_setting(key, value), checked=current == value)

        languages = [choice("language", "auto", t("lang_auto"), config["languageSetting"])]
        languages += [choice("language", code, strings.LANGUAGE_NAMES[code], config["languageSetting"])
                      for code in core.LANGUAGES[1:]]
        items = [
            MenuItem(t("about"), self.about),
            MenuItem(t("next"), self.next, enabled=not self.switching.locked()),
            MenuItem(t("read_more"), self.read_more, enabled=has_painting),
            MenuItem(t("save"), self.save, enabled=has_painting and bool(status.get("fromCache"))),
            SEPARATOR,
        ]
        override = status.get("filter")
        if override:
            items += [MenuItem(t("showing_only", name=card.filter_label(override)), enabled=False),
                      MenuItem(t("show_all"), self.show_all), SEPARATOR]
        items += [
            MenuItem(t("change_every"), submenu=[choice("intervalMinutes", m, strings.interval_label(m, config))
                                                 for m in core.INTERVALS]),
            MenuItem(t("artists"), submenu=[choice("fame", f, t(f"fame_{f}")) for f in ("famous", "known", "any")]),
            MenuItem(t("fit"), submenu=[choice("fit", f, t(f"fit_{f}")) for f in ("blur", "auto", "wall", "cover")]),
            MenuItem(t("caption"), submenu=[choice("caption", c, t(f"caption_{c}"))
                                            for c in ("off", "bottom-right", "bottom-left", "top-right", "top-left")]),
            MenuItem(t("language"), submenu=languages),
            MenuItem(t("notify_on_change"), lambda: self.set_setting("notifyOnChange", not config["notifyOnChange"]),
                     checked=config["notifyOnChange"]),
            MenuItem(t("start_at_login"), self.toggle_autostart, checked=self.autostart()),
            MenuItem(t("open_collection"), self.open_collection),
            SEPARATOR,
            MenuItem(t("quit"), self.quit),
        ]
        return items


def main(background=False):
    return App(background=background).run()


if __name__ == "__main__":
    sys.exit(main("--background" in sys.argv))
