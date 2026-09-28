#!/usr/bin/env python3
"""Check the nearest Turkish visa appointment published on konsolosluk.gov.tr.

Notification only. This does not log in, book an appointment, or solve a CAPTCHA.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

BASE = "https://www.konsolosluk.gov.tr"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)
MIN_INTERVAL_SECONDS = 15 * 60
REQUEST_GAP_SECONDS = 1.0
MAX_ATTEMPTS = 3
AGENT_PREFIX = "com.turkey-visa-checker"
ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state.json"
LOG_PATH = ROOT / "check.log"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"

# Longer suffixes first so "fahri konsoloslugu" is removed as a whole.
OFFICE_SUFFIXES = (
    "fahri konsoloslugu",
    "baskonsoloslugu",
    "buyukelciligi",
    "konsoloslugu",
    "elciligi",
    "maslahatguzarligi",
    "temsilciligi",
)

_FOLD = str.maketrans(
    {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)

# English names that do not already match the Turkish label after folding.
COUNTRY_ALIASES = {
    "afghanistan": "Afganistan",
    "algeria": "Cezayir",
    "albania": "Arnavutluk",
    "argentina": "Arjantin",
    "australia": "Avustralya",
    "austria": "Avusturya",
    "azerbaijan": "Azerbaycan",
    "bahrain": "Bahreyn",
    "bangladesh": "Bangladeş",
    "belgium": "Belçika",
    "bolivia": "Bolivya",
    "bosnia": "Bosna Hersek",
    "bosnia and herzegovina": "Bosna Hersek",
    "botswana": "Botsvana",
    "brazil": "Brezilya",
    "britain": "İngiltere",
    "bulgaria": "Bulgaristan",
    "cambodia": "Kamboçya",
    "cameroon": "Kamerun",
    "canada": "Kanada",
    "chad": "Çad",
    "chile": "Şili",
    "china": "Çin",
    "colombia": "Kolombiya",
    "costa rica": "Kosta Rika",
    "cote d'ivoire": "Fildişi Sahili",
    "croatia": "Hırvatistan",
    "cuba": "Küba",
    "czech": "Çek Cumhuriyeti",
    "czech republic": "Çek Cumhuriyeti",
    "czechia": "Çek Cumhuriyeti",
    "denmark": "Danimarka",
    "djibouti": "Cibuti",
    "dominican republic": "Dominik Cumhuriyeti",
    "drc": "Kongo Demokratik C.",
    "democratic republic of the congo": "Kongo Demokratik C.",
    "ecuador": "Ekvator",
    "egypt": "Mısır",
    "england": "İngiltere",
    "equatorial guinea": "Ekvator Ginesi",
    "eritrea": "Eritre",
    "estonia": "Estonya",
    "ethiopia": "Etiyopya",
    "finland": "Finlandiya",
    "france": "Fransa",
    "gambia": "Gambiya",
    "georgia": "Gürcistan",
    "germany": "Almanya",
    "ghana": "Gana",
    "great britain": "İngiltere",
    "greece": "Yunanistan",
    "guinea": "Gine",
    "guinea bissau": "Gine Bissau",
    "holland": "Hollanda",
    "hungary": "Macaristan",
    "india": "Hindistan",
    "indonesia": "Endonezya",
    "iraq": "Irak",
    "ireland": "İrlanda",
    "israel": "İsrail",
    "italy": "İtalya",
    "ivory coast": "Fildişi Sahili",
    "japan": "Japonya",
    "jordan": "Ürdün",
    "kazakhstan": "Kazakistan",
    "korea": "Kore Cum. (Güney Kore)",
    "kosovo": "Kosova",
    "kuwait": "Kuveyt",
    "kyrgyzstan": "Kırgızistan",
    "latvia": "Letonya",
    "lebanon": "Lübnan",
    "lithuania": "Litvanya",
    "luxembourg": "Lüksemburg",
    "madagascar": "Madagaskar",
    "malaysia": "Malezya",
    "mauritania": "Moritanya",
    "mexico": "Meksika",
    "mongolia": "Moğolistan",
    "montenegro": "Karadağ",
    "morocco": "Fas",
    "mozambique": "Mozambik",
    "namibia": "Namibya",
    "netherlands": "Hollanda",
    "new zealand": "Yeni Zelanda",
    "niger": "Nijer",
    "nigeria": "Nijerya",
    "north cyprus": "K.K.T.C.",
    "north macedonia": "Kuzey Makedonya",
    "northern cyprus": "K.K.T.C.",
    "norway": "Norveç",
    "oman": "Umman",
    "philippines": "Filipinler",
    "poland": "Polonya",
    "portugal": "Portekiz",
    "qatar": "Katar",
    "republic of korea": "Kore Cum. (Güney Kore)",
    "republic of the congo": "Kongo Cumhuriyeti",
    "romania": "Romanya",
    "russia": "Rusya Federasyonu",
    "rwanda": "Ruanda",
    "saudi": "Suudi Arabistan",
    "saudi arabia": "Suudi Arabistan",
    "serbia": "Sırbistan",
    "singapore": "Singapur",
    "slovakia": "Slovakya",
    "slovenia": "Slovenya",
    "somalia": "Somali",
    "south africa": "Güney Afrika",
    "south korea": "Kore Cum. (Güney Kore)",
    "south sudan": "Güney Sudan Cumhuriyeti",
    "spain": "İspanya",
    "sweden": "İsveç",
    "switzerland": "İsviçre",
    "syria": "Suriye",
    "tajikistan": "Tacikistan",
    "tanzania": "Tanzanya",
    "thailand": "Tayland",
    "the netherlands": "Hollanda",
    "trinidad": "Trinidad ve Tobago",
    "trinidad and tobago": "Trinidad ve Tobago",
    "trnc": "K.K.T.C.",
    "tunisia": "Tunus",
    "turkey": "Türkiye",
    "ukraine": "Ukrayna",
    "united arab emirates": "Birleşik Arap Emirlikleri",
    "united kingdom": "İngiltere",
    "united states": "A.B.D.",
    "united states of america": "A.B.D.",
    "uae": "Birleşik Arap Emirlikleri",
    "uk": "İngiltere",
    "us": "A.B.D.",
    "usa": "A.B.D.",
    "uzbekistan": "Özbekistan",
    "vatican": "Vatikan",
    "zambia": "Zambiya",
    "zimbabwe": "Zimbabve",
}

# Spellings confirmed against the consulate list, where English does not match.
MISSION_ALIASES = {
    "bordeaux": "Bordo",
    "chicago": "Şikago",
    "cologne": "Köln",
    "edinburgh": "Edinburg",
    "hanover": "Hannover",
    "london": "Londra",
    "lyon": "Liyon",
    "marseille": "Marsilya",
    "munich": "Münih",
    "nantes": "Nant",
    "nuremberg": "Nürnberg",
    "strasbourg": "Strazburg",
    "washington": "Vaşington",
}

EXAMPLES = """
examples:
  python3 tvc.py countries
  python3 tvc.py missions france
  python3 tvc.py check france paris
  python3 tvc.py check germany berlin
  python3 tvc.py watch france paris --interval 2h --alert-before 2026-11-01
  python3 tvc.py install france paris --interval 2h
"""


class CLIError(Exception):
    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Country:
    id: str
    name: str


@dataclass(frozen=True)
class Mission:
    id: str
    name: str


@dataclass(frozen=True)
class Appointment:
    mission_id: str
    mission_name: str
    country_id: str
    country_name: str
    appointment_date: str | None
    appointment_exist: bool
    iso_date: str | None
    note: str | None = None


@dataclass(frozen=True)
class Notice:
    title: str
    body: str
    sound: bool = False


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def log(message: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    eprint(line)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"missions": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"missions": {}}
    if not isinstance(data, dict):
        return {"missions": {}}
    if "missions" not in data and data.get("mission_id"):
        data = {"missions": {str(data["mission_id"]): data}}
    if not isinstance(data.get("missions"), dict):
        data["missions"] = {}
    return data


def save_state(state: dict) -> None:
    temporary = STATE_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(STATE_PATH)


def norm(value: str) -> str:
    text = value.replace("İ", "i").replace("I", "ı")
    text = text.casefold().translate(_FOLD)
    text = "".join(char if char.isalnum() else " " for char in text)
    return " ".join(text.split())


def strip_office(name: str) -> str:
    normalized = norm(name)
    for suffix in OFFICE_SUFFIXES:
        tail = " " + suffix
        if normalized.endswith(tail):
            return normalized[: -len(tail)].strip()
    return normalized


def alias_for(query: str, table: dict[str, str]) -> str | None:
    spaced = norm(query)
    compact = spaced.replace(" ", "")
    index: dict[str, str] = {}
    for key, value in table.items():
        folded = norm(key)
        index.setdefault(folded, value)
        index.setdefault(folded.replace(" ", ""), value)
    return index.get(spaced) or index.get(compact)


def rank_item(item: Country | Mission, query: str) -> int | None:
    raw = query.strip()
    if raw.isdigit() and item.id == raw:
        return 0
    spaced = norm(raw)
    if not spaced:
        return None
    compact = spaced.replace(" ", "")
    full = norm(item.name)
    short = strip_office(item.name)
    if spaced == full or compact == full.replace(" ", ""):
        return 1
    if spaced == short or compact == short.replace(" ", ""):
        return 2
    if len(spaced) >= 3 and (full.startswith(spaced) or short.startswith(spaced)):
        return 3
    return None


def best_matches(items: list[Country] | list[Mission], query: str) -> list[Country | Mission]:
    ranked: list[tuple[int, Country | Mission]] = []
    for item in items:
        score = rank_item(item, query)
        if score is not None:
            ranked.append((score, item))
    if not ranked:
        return []
    top = min(score for score, _item in ranked)
    return [item for score, item in ranked if score == top]


def pick(
    items: list[Country] | list[Mission],
    query: str,
    kind: str,
    aliases: dict[str, str],
    hint: str,
) -> Country | Mission:
    matches = best_matches(items, query)
    if not matches:
        alias = alias_for(query, aliases)
        if alias and norm(alias) != norm(query):
            matches = best_matches(items, alias)
    if not matches:
        raise CLIError(f'No {kind} matching "{query}".\n{hint}')
    if len(matches) > 1:
        preview = matches[:12]
        lines = [f'"{query}" matches more than one {kind}:']
        for item in preview:
            lines.append(f"  {item.id}  {item.name}")
        remaining = len(matches) - len(preview)
        if remaining:
            lines.append(f"  … and {remaining} more")
        lines.append("Pass an id or a longer name.")
        raise CLIError("\n".join(lines))
    return matches[0]


def pick_country(countries: list[Country], query: str) -> Country:
    chosen = pick(
        countries,
        query,
        "country",
        COUNTRY_ALIASES,
        "Names are Turkish, as on konsolosluk.gov.tr. List them with:\n"
        "  python3 tvc.py countries",
    )
    if not isinstance(chosen, Country):
        raise CLIError(f'No country matching "{query}".')
    return chosen


def pick_mission(missions: list[Mission], query: str, country: Country) -> Mission:
    chosen = pick(
        missions,
        query,
        "consulate",
        MISSION_ALIASES,
        f"List consulates with:\n  python3 tvc.py missions {country.id}",
    )
    if not isinstance(chosen, Mission):
        raise CLIError(f'No consulate matching "{query}".')
    return chosen


def parse_interval(value: str) -> int:
    text = "".join(value.split()).lower()
    multiplier = 3600
    if text.endswith("h"):
        multiplier = 3600
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 60
        text = text[:-1]
    elif text.endswith("s"):
        multiplier = 1
        text = text[:-1]
    try:
        amount = float(text)
    except ValueError as exc:
        raise CLIError("Interval should look like 2h, 90m, or 2.") from exc
    if amount <= 0:
        raise CLIError("Interval has to be greater than zero.")
    seconds = int(amount * multiplier)
    if seconds < MIN_INTERVAL_SECONDS:
        raise CLIError("Interval has to be at least 15 minutes.")
    return seconds


def format_interval(seconds: int) -> str:
    if seconds % 3600 == 0:
        hours = seconds // 3600
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit}"
    if seconds % 60 == 0:
        return f"{seconds // 60} minutes"
    return f"{seconds} seconds"


def parse_user_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise CLIError(f'Could not read "{value}". Use YYYY-MM-DD or DD.MM.YYYY.')


def calendar_day(row: dict) -> date | None:
    """Use the displayed calendar date.

    DateFormatAppointment sometimes carries a clock time that changes on every
    request. The date the consulate shows is AppointmentDate.
    """
    if row.get("AppointmentExist") is False:
        return None
    raw = str(row.get("AppointmentDate") or "").strip()
    if raw and raw != "-":
        try:
            return datetime.strptime(raw, "%d.%m.%Y").date()
        except ValueError:
            pass
    head = str(row.get("DateFormatAppointment") or "").split("T", 1)[0]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date()
    except ValueError:
        return None


class Session:
    def __init__(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="tvc-", suffix=".cookies", delete=False)
        handle.close()
        self.cookie_path = handle.name

    def close(self) -> None:
        try:
            os.unlink(self.cookie_path)
        except FileNotFoundError:
            pass

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *_args: object) -> bool:
        self.close()
        return False

    def request(self, method: str, path: str, form: dict | None = None) -> str:
        command = [
            "curl",
            "-sS",
            "-L",
            "--compressed",
            "--fail-with-body",
            "--retry",
            "2",
            "--retry-all-errors",
            "--max-time",
            "60",
            "-A",
            USER_AGENT,
            "-H",
            "Accept: text/html,application/json,*/*;q=0.8",
            "-H",
            "Accept-Language: en-GB,en;q=0.9,tr;q=0.8",
            "-H",
            f"Origin: {BASE}",
            "-H",
            f"Referer: {BASE}/Visa",
            "-c",
            self.cookie_path,
            "-b",
            self.cookie_path,
        ]
        if form is not None:
            command.extend(
                [
                    "-H",
                    "X-Requested-With: XMLHttpRequest",
                    "--data",
                    urllib.parse.urlencode(form),
                ]
            )
        elif method != "GET":
            command.extend(["-X", method])
        command.append(BASE + path)

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                result = subprocess.run(command, check=False, capture_output=True, text=True)
            except FileNotFoundError as exc:
                raise RuntimeError("curl is required but was not found on PATH.") from exc
            if result.returncode == 0:
                return result.stdout
            last_error = RuntimeError(result.stderr.strip() or f"curl exited {result.returncode}")
            if attempt == MAX_ATTEMPTS:
                break
            eprint(f"retry {attempt}/{MAX_ATTEMPTS} {method} {path}: {last_error}")
            time.sleep(2 * attempt)
        raise RuntimeError(f"{method} {path} failed: {last_error}")


def parse_countries(page: str) -> list[Country]:
    match = re.search(r'id="ddlCountries1".*?</select>', page, re.S)
    if not match:
        raise RuntimeError("The consulate site did not include a country list.")
    countries: list[Country] = []
    for value, text in re.findall(
        r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>',
        match.group(0),
        re.S,
    ):
        name = html.unescape(re.sub(r"\s+", " ", text)).strip()
        if value and name:
            countries.append(Country(value, name))
    if not countries:
        raise RuntimeError("The country list was empty.")
    return countries


def parse_missions(payload: str) -> list[Mission]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The consulate list was not JSON. The site may be down.") from exc
    if isinstance(data, dict) and isinstance(data.get("d"), list):
        data = data["d"]
    if not isinstance(data, list):
        raise RuntimeError("The consulate list had an unexpected shape.")
    missions: list[Mission] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        value = str(row.get("Value") or "").strip()
        name = str(row.get("Text") or "").strip()
        if value and name and value != "-1":
            missions.append(Mission(value, name))
    return missions


def parse_appointment_blob(page: str) -> list[dict] | None:
    match = re.search(r'class="EnYakinRandevu"[^>]*>(.*?)</i>', page, re.S | re.I)
    if not match:
        return None
    payload = html.unescape(match.group(1)).strip()
    if not payload:
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The appointment date on the page could not be read.") from exc
    if not isinstance(data, list):
        raise RuntimeError("The appointment date had an unexpected shape.")
    return [row for row in data if isinstance(row, dict)]


def parse_page_note(page: str) -> str | None:
    """Some consulates do not publish a date and instead name an outside agency."""
    info = re.search(r'class="ks-result-info"[^>]*>(.*?)</span>', page, re.S)
    if not info:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", info.group(1)))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    start = page.find(info.group(0))
    footer = page.find("ks-content-footer", start)
    chunk = page[start:footer if footer != -1 else start + 4000]
    agencies: list[str] = []
    for raw in re.findall(r'ks-operation-header"[^>]*>(.*?)</span>', chunk, re.S):
        name = html.unescape(re.sub(r"<[^>]+>", " ", raw))
        name = re.sub(r"\s+", " ", name).strip()
        if name:
            agencies.append(name)
    if agencies:
        return "via " + ", ".join(agencies)
    return text


def appointment_from(row: dict, country: Country, mission: Mission) -> Appointment:
    day = calendar_day(row)
    return Appointment(
        mission_id=str(row.get("MissionId") or mission.id),
        mission_name=str(row.get("MissionName") or mission.name),
        country_id=country.id,
        country_name=country.name,
        appointment_date=day.strftime("%d.%m.%Y") if day else None,
        appointment_exist=day is not None,
        iso_date=day.isoformat() if day else None,
        note=None,
    )


def empty_appointment(country: Country, mission: Mission, note: str | None = None) -> Appointment:
    return Appointment(
        mission_id=mission.id,
        mission_name=mission.name,
        country_id=country.id,
        country_name=country.name,
        appointment_date=None,
        appointment_exist=False,
        iso_date=None,
        note=note,
    )


def load_appointment(session: Session, country: Country, mission: Mission) -> Appointment:
    selected = session.request("POST", "/Home/MissionSelected", {"selectedMission": mission.id})
    try:
        payload = json.loads(selected)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Selecting {mission.name} did not return JSON.") from exc
    if not isinstance(payload, dict) or not payload.get("IsSuccessful"):
        message = payload.get("Message") if isinstance(payload, dict) else None
        raise RuntimeError(message or f"The site rejected {mission.name}.")
    page = session.request("GET", "/Visa")
    rows = parse_appointment_blob(page)
    if rows is None:
        note = parse_page_note(page)
        if note:
            return empty_appointment(country, mission, note)
        raise RuntimeError("The page did not include an appointment date. Try the check again.")
    for row in rows:
        if str(row.get("MissionId")) == mission.id:
            return appointment_from(row, country, mission)
    if not rows:
        return empty_appointment(country, mission)
    if len(rows) == 1:
        return appointment_from(rows[0], country, mission)
    raise RuntimeError(f"{mission.name} was not in the appointment data.")


def lookup(
    session: Session, country_query: str, mission_query: str | None
) -> tuple[Country, list[Mission]]:
    country = pick_country(parse_countries(session.request("GET", "/Visa")), country_query)
    missions = parse_missions(
        session.request("POST", "/Home/GetMissionsList", {"countryId": country.id})
    )
    if mission_query:
        missions = [pick_mission(missions, mission_query, country)]
    if not missions:
        raise CLIError(f"{country.name} has no consulates listed.")
    return country, missions


def fetch_target(country_query: str, mission_query: str | None) -> tuple[Country, list[Appointment]]:
    with Session() as session:
        country, missions = lookup(session, country_query, mission_query)
        appointments: list[Appointment] = []
        total = len(missions)
        for index, mission in enumerate(missions):
            if index:
                time.sleep(REQUEST_GAP_SECONDS)
            if total > 1:
                eprint(f"Checking {index + 1}/{total} {mission.name}")
            appointments.append(load_appointment(session, country, mission))
        return country, appointments


def display_date(appointment: Appointment) -> str:
    if appointment.appointment_date:
        return appointment.appointment_date
    if appointment.note:
        return appointment.note
    return "none listed"


def summary(appointment: Appointment) -> str:
    return f"{appointment.mission_name}: {display_date(appointment)}"


def format_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells)).rstrip()

    rendered = [line(headers), line(tuple("-" * width for width in widths))]
    rendered.extend(line(row) for row in rows)
    return "\n".join(rendered)


def format_id_name(rows: list[tuple[str, str]]) -> str:
    width = max(len(row[0]) for row in rows)
    return "\n".join(f"{item_id.ljust(width)}  {name}" for item_id, name in rows)


def format_appointments(country: Country, appointments: list[Appointment]) -> str:
    title = country.name
    if len(appointments) > 1:
        title = f"{country.name} — {len(appointments)} consulates"
    table = format_table(
        ("Consulate", "Nearest appointment"),
        tuple((item.mission_name, display_date(item)) for item in appointments),
    )
    return f"{title}\n\n{table}"


def appointment_json(appointment: Appointment) -> dict:
    return {
        "country": appointment.country_name,
        "country_id": appointment.country_id,
        "mission": appointment.mission_name,
        "mission_id": appointment.mission_id,
        "appointment_date": appointment.appointment_date,
        "appointment_exist": appointment.appointment_exist,
        "iso_date": appointment.iso_date,
        "note": appointment.note,
    }


def emit_json(payload: object) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def join_lines(lines: list[str], limit: int = 8) -> str:
    shown = lines[:limit]
    if len(lines) > limit:
        shown.append(f"and {len(lines) - limit} more")
    return "\n".join(shown)


def earliest(appointments: list[Appointment]) -> Appointment | None:
    dated = [item for item in appointments if item.iso_date]
    if not dated:
        return None
    return min(dated, key=lambda item: item.iso_date or "")


def in_window(appointment: Appointment, threshold: date | None) -> bool:
    if threshold is None or not appointment.iso_date:
        return False
    return date.fromisoformat(appointment.iso_date) <= threshold


def changed(previous: dict, appointment: Appointment) -> bool:
    previous_date = previous.get("appointment_date") or None
    previous_exist = bool(previous.get("appointment_exist"))
    previous_note = previous.get("note") or None
    return (
        previous_date != appointment.appointment_date
        or previous_exist != appointment.appointment_exist
        or previous_note != appointment.note
    )


def already_alerted(previous: dict | None, appointment: Appointment, threshold: date) -> bool:
    if not previous:
        return False
    return (
        previous.get("alerted_date") == appointment.appointment_date
        and previous.get("alerted_before") == threshold.isoformat()
    )


def plan_notices(
    state: dict,
    appointments: list[Appointment],
    threshold: date | None,
) -> tuple[list[Notice], dict]:
    missions = dict(state.get("missions") or {})
    alerts: list[Appointment] = []
    changes: list[tuple[dict, Appointment]] = []
    fresh: list[Appointment] = []
    now = datetime.now(timezone.utc).isoformat()

    for appointment in appointments:
        previous = missions.get(appointment.mission_id)
        previous_dict = previous if isinstance(previous, dict) else None
        if previous_dict is None:
            fresh.append(appointment)
        elif changed(previous_dict, appointment):
            changes.append((previous_dict, appointment))
        record = {
            "mission_id": appointment.mission_id,
            "mission_name": appointment.mission_name,
            "country_id": appointment.country_id,
            "country_name": appointment.country_name,
            "appointment_date": appointment.appointment_date,
            "appointment_exist": appointment.appointment_exist,
            "iso_date": appointment.iso_date,
            "note": appointment.note,
            "checked_at": now,
        }
        if previous_dict and previous_dict.get("alerted_date"):
            record["alerted_date"] = previous_dict.get("alerted_date")
            record["alerted_before"] = previous_dict.get("alerted_before")
        if threshold is not None and in_window(appointment, threshold):
            if not already_alerted(previous_dict, appointment, threshold):
                alerts.append(appointment)
                record["alerted_date"] = appointment.appointment_date
                record["alerted_before"] = threshold.isoformat()
        elif threshold is not None:
            record.pop("alerted_date", None)
            record.pop("alerted_before", None)
        missions[appointment.mission_id] = record

    notices: list[Notice] = []
    alert_ids = {item.mission_id for item in alerts}
    if alerts and threshold is not None:
        notices.append(
            Notice(
                "Visa date in range",
                join_lines(
                    [
                        f"{item.mission_name}: {item.appointment_date} "
                        f"(on or before {threshold.isoformat()})"
                        for item in alerts
                    ]
                ),
                sound=True,
            )
        )
    fresh_outside = [item for item in fresh if item.mission_id not in alert_ids]
    if fresh_outside:
        if len(fresh_outside) == 1:
            body = summary(fresh_outside[0])
        else:
            soonest = earliest(fresh_outside)
            body = f"Watching {len(fresh_outside)} consulates."
            if soonest:
                body += f"\nEarliest: {summary(soonest)}"
            else:
                body += "\nNone of them list an appointment."
        notices.append(Notice("Visa appointment", body))
    changed_outside = [item for item in changes if item[1].mission_id not in alert_ids]
    if changed_outside:
        notices.append(
            Notice(
                "Visa appointment changed",
                join_lines(
                    [
                        f"{appointment.mission_name}: "
                        f"{previous.get('appointment_date') or 'none'} → {display_date(appointment)}"
                        for previous, appointment in changed_outside
                    ]
                ),
            )
        )
    return notices, {"missions": missions}


def applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def deliver(title: str, body: str, sound: bool = False) -> None:
    if sys.platform == "darwin":
        banner = body.replace("\n", " · ")
        sound_clause = ' sound name "Sosumi"' if sound else ""
        script = (
            f"display notification {applescript_string(banner)} "
            f"with title {applescript_string(title)}{sound_clause}"
        )
        subprocess.run(["osascript", "-e", script], check=False)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": f"{title}\n{body}"}).encode()
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        urllib.request.urlopen(request, timeout=30).read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log(f"telegram notify failed: {exc}")


def remember_error(exc: Exception) -> None:
    message = str(exc)
    log(message)
    state = load_state()
    if state.get("last_error") == message:
        return
    deliver("Visa checker error", message)
    state["last_error"] = message
    save_state(state)


def clear_error() -> None:
    state = load_state()
    if "last_error" not in state:
        return
    state.pop("last_error", None)
    save_state(state)


def announce(appointments: list[Appointment], threshold: date | None) -> None:
    notices, new_state = plan_notices(load_state(), appointments, threshold)
    for notice in notices:
        deliver(notice.title, notice.body, notice.sound)
        log(f"{notice.title}: {notice.body.replace(chr(10), ' | ')}")
    save_state(new_state)


def print_appointments(country: Country, appointments: list[Appointment], as_json: bool) -> None:
    if as_json:
        emit_json([appointment_json(item) for item in appointments])
        return
    print(format_appointments(country, appointments))


def run_check(args: argparse.Namespace, notify: bool) -> int:
    threshold = parse_user_date(args.alert_before) if getattr(args, "alert_before", None) else None
    country, appointments = fetch_target(args.country, args.mission)
    print_appointments(country, appointments, bool(getattr(args, "json", False)))
    if notify:
        clear_error()
        log("; ".join(summary(item) for item in appointments))
        announce(appointments, threshold)
    return 0


def run_watch(args: argparse.Namespace) -> int:
    seconds = parse_interval(args.interval)
    threshold = parse_user_date(args.alert_before) if args.alert_before else None
    target = args.mission or "all consulates"
    log(f"Watching {target} in {args.country} every {format_interval(seconds)}")
    while True:
        try:
            country, appointments = fetch_target(args.country, args.mission)
        except CLIError:
            raise
        except Exception as exc:
            remember_error(exc)
        else:
            clear_error()
            print_appointments(country, appointments, False)
            log("; ".join(summary(item) for item in appointments))
            announce(appointments, threshold)
        time.sleep(seconds)


def agent_label(country_id: str, mission_id: str | None) -> str:
    if mission_id:
        return f"{AGENT_PREFIX}.{country_id}.{mission_id}"
    return f"{AGENT_PREFIX}.{country_id}"


def agent_path(label: str) -> Path:
    return LAUNCH_AGENTS / f"{label}.plist"


def build_agent(label: str, interval: int, tvc_args: list[str]) -> dict:
    return {
        "Label": label,
        "WorkingDirectory": str(ROOT),
        "ProgramArguments": [sys.executable, str(ROOT / "tvc.py"), *tvc_args],
        "StartInterval": interval,
        "RunAtLoad": True,
        "StandardOutPath": str(ROOT / "launchd.out.log"),
        "StandardErrorPath": str(ROOT / "launchd.err.log"),
    }


def retire_check_py_agents() -> None:
    if not LAUNCH_AGENTS.is_dir():
        return
    needle = str(ROOT / "check.py")
    for path in sorted(LAUNCH_AGENTS.glob("*.plist")):
        try:
            data = plistlib.loads(path.read_bytes())
        except (OSError, plistlib.InvalidFileException, ValueError):
            continue
        arguments = [str(item) for item in data.get("ProgramArguments") or []]
        if needle not in arguments:
            continue
        subprocess.run(["launchctl", "unload", str(path)], check=False)
        path.unlink(missing_ok=True)
        eprint(f"Removed previous agent {path.name}")


def note_overlap(country_id: str, mission_id: str | None) -> None:
    if not LAUNCH_AGENTS.is_dir():
        return
    if mission_id:
        broader = agent_path(agent_label(country_id, None))
        if broader.exists():
            eprint(f"Note: an agent for every consulate in this country is already installed ({broader.name}).")
        return
    narrower = sorted(LAUNCH_AGENTS.glob(f"{AGENT_PREFIX}.{country_id}.*.plist"))
    if narrower:
        eprint(f"Note: {len(narrower)} agent(s) for individual consulates in this country are already installed.")


def run_install(args: argparse.Namespace) -> int:
    if sys.platform != "darwin":
        raise CLIError(
            "install only works on macOS. Use python3 tvc.py watch … on this machine instead."
        )
    seconds = parse_interval(args.interval)
    threshold = parse_user_date(args.alert_before) if args.alert_before else None
    with Session() as session:
        country, missions = lookup(session, args.country, args.mission)
    mission_id = missions[0].id if args.mission else None
    label = agent_label(country.id, mission_id)
    tvc_args = ["check", country.id]
    if mission_id:
        tvc_args.append(mission_id)
    tvc_args.append("--notify")
    if threshold:
        tvc_args.extend(["--alert-before", threshold.isoformat()])
    path = agent_path(label)
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    retire_check_py_agents()
    note_overlap(country.id, mission_id)
    path.write_bytes(plistlib.dumps(build_agent(label, seconds, tvc_args)))
    subprocess.run(["launchctl", "unload", str(path)], check=False)
    subprocess.run(["launchctl", "load", str(path)], check=True)
    target = missions[0].name if args.mission else f"all {len(missions)} consulates"
    print(f"Installed {path}")
    print(f"Checking {target} in {country.name} every {format_interval(seconds)}.")
    uninstall = f"python3 tvc.py uninstall {country.id}"
    if mission_id:
        uninstall += f" {mission_id}"
    print(f"Remove it with: {uninstall}")
    return 0


def remove_agent(path: Path) -> None:
    if not path.exists():
        raise CLIError(f"No agent installed at {path}")
    subprocess.run(["launchctl", "unload", str(path)], check=False)
    path.unlink(missing_ok=True)
    print(f"Removed {path}")


def run_uninstall(args: argparse.Namespace) -> int:
    if sys.platform != "darwin":
        raise CLIError("uninstall only works on macOS.")
    if args.all:
        paths = sorted(LAUNCH_AGENTS.glob(f"{AGENT_PREFIX}.*.plist")) if LAUNCH_AGENTS.is_dir() else []
        if not paths:
            print("No agents installed.")
            return 0
        for path in paths:
            remove_agent(path)
        return 0
    if not args.country:
        raise CLIError("Pass a country, or use: python3 tvc.py uninstall --all")
    with Session() as session:
        country, missions = lookup(session, args.country, args.mission)
    mission_id = missions[0].id if args.mission else None
    remove_agent(agent_path(agent_label(country.id, mission_id)))
    return 0


def run_agents(_args: argparse.Namespace) -> int:
    if not LAUNCH_AGENTS.is_dir():
        print("No agents installed.")
        return 0
    paths = sorted(LAUNCH_AGENTS.glob(f"{AGENT_PREFIX}.*.plist"))
    if not paths:
        print("No agents installed.")
        return 0
    for path in paths:
        try:
            data = plistlib.loads(path.read_bytes())
        except (OSError, plistlib.InvalidFileException, ValueError):
            eprint(f"Could not read {path.name}")
            continue
        arguments = [str(item) for item in data.get("ProgramArguments") or []]
        command = arguments[2:] if len(arguments) > 2 else arguments
        interval = data.get("StartInterval")
        every = format_interval(int(interval)) if isinstance(interval, int) else "unknown interval"
        print(f"{data.get('Label', path.stem)}  every {every}")
        print(f"  {' '.join(command)}")
    return 0


def run_countries(args: argparse.Namespace) -> int:
    with Session() as session:
        countries = parse_countries(session.request("GET", "/Visa"))
    if args.json:
        emit_json([{"id": item.id, "name": item.name} for item in countries])
        return 0
    print(format_id_name([(item.id, item.name) for item in countries]))
    return 0


def run_missions(args: argparse.Namespace) -> int:
    with Session() as session:
        country, missions = lookup(session, args.country, None)
    if args.json:
        emit_json(
            {
                "country": country.name,
                "country_id": country.id,
                "missions": [{"id": item.id, "name": item.name} for item in missions],
            }
        )
        return 0
    print(country.name)
    print()
    print(format_id_name([(item.id, item.name) for item in missions]))
    return 0


def add_place(parser: argparse.ArgumentParser, mission_help: str) -> None:
    parser.add_argument("country", help="country name or id, in Turkish or English")
    parser.add_argument("mission", nargs="?", help=mission_help)


def add_alert(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--alert-before",
        metavar="DATE",
        help="sound an alert when a date is on or before DATE (YYYY-MM-DD or DD.MM.YYYY)",
    )


def add_interval(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--interval",
        default="2h",
        help="how often to check (default: 2h, minimum 15m). A bare number means hours",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tvc.py",
        description=(
            "Check the nearest Turkish visa appointment published for a consulate "
            "on konsolosluk.gov.tr. Notification only: it does not book."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EXAMPLES,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    countries = sub.add_parser("countries", help="list countries")
    countries.add_argument("--json", action="store_true")

    missions = sub.add_parser("missions", help="list consulates in a country")
    missions.add_argument("country", help="country name or id, in Turkish or English")
    missions.add_argument("--json", action="store_true")

    check = sub.add_parser("check", help="print the nearest appointment")
    add_place(check, "consulate name or id. Omit to check every consulate in the country")
    check.add_argument("--json", action="store_true")
    check.add_argument(
        "--notify",
        action="store_true",
        help="send a notification now, on later changes, and for --alert-before",
    )
    add_alert(check)

    watch = sub.add_parser("watch", help="keep checking and notify when a date changes")
    add_place(watch, "consulate name or id. Omit to watch every consulate in the country")
    add_interval(watch)
    add_alert(watch)

    install = sub.add_parser("install", help="install a macOS LaunchAgent")
    add_place(install, "consulate name or id. Omit to check every consulate in the country")
    add_interval(install)
    add_alert(install)

    uninstall = sub.add_parser("uninstall", help="remove a macOS LaunchAgent")
    uninstall.add_argument("country", nargs="?", help="country name or id")
    uninstall.add_argument("mission", nargs="?", help="consulate name or id")
    uninstall.add_argument("--all", action="store_true", help="remove every agent this tool installed")

    sub.add_parser("agents", help="list macOS LaunchAgents installed by this tool")
    return parser


def dispatch(args: argparse.Namespace) -> int:
    if args.command == "countries":
        return run_countries(args)
    if args.command == "missions":
        return run_missions(args)
    if args.command == "check":
        return run_check(args, notify=bool(args.notify))
    if args.command == "watch":
        return run_watch(args)
    if args.command == "install":
        return run_install(args)
    if args.command == "uninstall":
        return run_uninstall(args)
    if args.command == "agents":
        return run_agents(args)
    raise CLIError(f"Unknown command {args.command}")


def report(exc: CLIError) -> int:
    text = str(exc)
    if "\n" in text:
        eprint(text)
    else:
        eprint(f"error: {text}")
    return exc.code


def main(argv: list[str] | None = None) -> int:
    load_env()
    args = build_parser().parse_args(argv)
    try:
        return dispatch(args)
    except CLIError as exc:
        return report(exc)
    except RuntimeError as exc:
        eprint(f"error: {exc}")
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
