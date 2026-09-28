# Turkey visa checker

A command-line checker for the nearest Turkish visa appointment published on [konsolosluk.gov.tr](https://www.konsolosluk.gov.tr/Visa).

You pick a country and a consulate. The tool reads the same nearest date the visa page shows after that consulate is selected, prints it, and can notify you when it changes. It does not log in, book an appointment, or solve a CAPTCHA. It is not affiliated with the Turkish Ministry of Foreign Affairs.

The site publishes one nearest date per consulate, not a full calendar and not a breakdown by visa type.

## Setup

You need Python 3.9 or newer and `curl`. There is nothing to install.

```bash
python3 tvc.py check france paris
```

That prints the nearest appointment at the Paris consulate general. Country and consulate names are the Turkish ones used on the site. Common English names work too: `france`, `germany`, `uk`, `usa`.

```bash
python3 tvc.py countries
python3 tvc.py missions france
python3 tvc.py missions uk
```

Some consulates do not take applications on this site. London and Berlin, for example, name an outside agency instead of a date:

```bash
python3 tvc.py check germany berlin
python3 tvc.py check uk london
```

Omit the consulate to check every consulate in a country. That sends a few requests per consulate, with a one-second pause between them.

```bash
python3 tvc.py check france
```

`--json` prints the same result as JSON.

Optional shortcut:

```bash
alias tvc='python3 /path/to/tvc.py'
```

## Notifications

`check` only prints. `watch` and `check --notify` also notify, and they remember the last date in `state.json` next to the script so a repeat of the same date stays quiet.

On macOS, a notification is shown automatically. Telegram is optional. Copy the example env file and fill it in:

```bash
cp .env.example .env
```

```
TELEGRAM_BOT_TOKEN=123456:abc
TELEGRAM_CHAT_ID=123456789
```

The file has to sit next to `tvc.py`. Leave either value empty and Telegram is skipped.

To get those values:

1. In Telegram, open [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the token.
2. Send any message to your new bot.
3. Open `https://api.telegram.org/bot<token>/getUpdates` and copy the `chat.id` from the reply.

Watch Paris, and play a sound if a date on or before 1 November 2026 appears:

```bash
python3 tvc.py watch france paris --interval 2h --alert-before 2026-11-01
```

`--interval` accepts `2h`, `90m`, or a bare number of hours. The shortest interval is 15 minutes. The default is 2 hours. `--alert-before` accepts `YYYY-MM-DD` or `DD.MM.YYYY`. The sound fires once per date. A later change to a different date alerts again.

## Run it on a schedule (macOS)

`install` registers a LaunchAgent that runs a check in the background and notifies you. It also removes an older agent from this folder that still launched `check.py`, so two jobs are not polling at once.

```bash
python3 tvc.py install france paris --interval 2h --alert-before 2026-11-01
python3 tvc.py agents
python3 tvc.py uninstall france paris
python3 tvc.py uninstall --all
```

`install` and `uninstall` need macOS. Elsewhere, leave `watch` running.

## If you were using check.py

`python3 check.py` still checks Paris and notifies on a new date. `--loop` and `--install` still work. Anything else should go through `tvc.py`.

The old September-only sound is now `--alert-before`. A date change is still announced either way.

## Be considerate

This reads a public government page. Check one consulate when you can, keep the interval in hours, and run one copy. The tool will not go faster than every 15 minutes, and it will not book the slot for you.
