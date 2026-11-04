"""Entry point: the menu bar app by default, or one core command
(`museum-wallpapers next`, `status`, … see core.py), or `selftest`."""

import sys


def use_system_trust():
    """Verify HTTPS certificates with the operating system's trust store (the
    macOS Keychain). The bundled OpenSSL looks for a CA file the Python that
    built the app had and a user's Mac does not: every request failed with
    CERTIFICATE_VERIFY_FAILED."""
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception as exc:  # noqa: BLE001 - OpenSSL's own paths stay
        print(f"museum-wallpapers: system trust store unavailable: {exc}", file=sys.stderr)


def main(argv=None):
    use_system_trust()
    argv = [a for a in (sys.argv[1:] if argv is None else argv) if not a.startswith("-psn_")]
    if not argv or argv[0] in ("app", "--background"):
        from . import app
        return app.main(background="--background" in argv)
    if argv[0] == "selftest":
        from . import selftest
        out = argv[argv.index("--out") + 1] if "--out" in argv[1:-1] else None
        return selftest.run(out)
    from . import core
    return core.main(argv)


if __name__ == "__main__":
    sys.exit(main())
