#!/usr/bin/env python3
"""Unit tests for the visa checker. No network."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import check
import tvc

COUNTRY_HTML = """
<select id="ddlCountries1">
<option value="">Lütfen Ülke Seçiniz</option>
<option value="9890">Fransa</option>
<option value="9893">Almanya</option>
<option value="9988">A.B.D.</option>
<option value="9985">&#304;ngiltere</option>
<option value="9898">Gine</option>
<option value="9899">Gine Bissau</option>
</select>
"""

APPOINTMENT_HTML = """
<i class="EnYakinRandevu" style="display:none">[{&quot;MissionId&quot;:&quot;294&quot;,&quot;MissionName&quot;:&quot;Paris Başkonsolosluğu&quot;,&quot;AppointmentDate&quot;:&quot;02.12.2026&quot;,&quot;AppointmentExist&quot;:true,&quot;DateFormatAppointment&quot;:&quot;2026-12-02T00:00:00&quot;}]</i>
"""

AGENCY_HTML = """
<span class="ks-result-info" lang="tr"><h4 lang="tr">Başvurunuzu yetkili acenteler aracılığı ile yapmanız gerekmektedir!</h4></span>
<span class="ks-operation-header" style="padding-left:15px" lang="tr">VfT GmbH-Berlin</span>
<div class="ks-content-footer"></div>
"""

FRANCE = [
    tvc.Mission("448", "Bordo Başkonsolosluğu"),
    tvc.Mission("271", "Liyon Başkonsolosluğu"),
    tvc.Mission("274", "Marsilya Başkonsolosluğu"),
    tvc.Mission("458", "NANT BAŞKONSOLOSLUĞU"),
    tvc.Mission("294", "Paris Başkonsolosluğu"),
    tvc.Mission("310", "Strazburg Başkonsolosluğu"),
]


def appointment(
    mission_id: str,
    name: str,
    shown: str | None,
    *,
    country_id: str = "9890",
    country_name: str = "Fransa",
) -> tvc.Appointment:
    day = None if shown is None else tvc.datetime.strptime(shown, "%d.%m.%Y").date()
    return tvc.Appointment(
        mission_id=mission_id,
        mission_name=name,
        country_id=country_id,
        country_name=country_name,
        appointment_date=shown,
        appointment_exist=shown is not None,
        iso_date=day.isoformat() if day else None,
    )


class MatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.countries = tvc.parse_countries(COUNTRY_HTML)

    def test_english_and_turkish_country_names(self) -> None:
        self.assertEqual(tvc.pick_country(self.countries, "france").id, "9890")
        self.assertEqual(tvc.pick_country(self.countries, "Fransa").id, "9890")
        self.assertEqual(tvc.pick_country(self.countries, "usa").name, "A.B.D.")
        self.assertEqual(tvc.pick_country(self.countries, "uk").id, "9985")
        self.assertEqual(tvc.pick_country(self.countries, "ingiltere").id, "9985")

    def test_guinea_does_not_swallow_guinea_bissau(self) -> None:
        self.assertEqual(tvc.pick_country(self.countries, "guinea").name, "Gine")
        self.assertEqual(tvc.pick_country(self.countries, "guinea-bissau").name, "Gine Bissau")

    def test_paris_and_city_aliases(self) -> None:
        france = tvc.Country("9890", "Fransa")
        self.assertEqual(tvc.pick_mission(FRANCE, "paris", france).id, "294")
        self.assertEqual(tvc.pick_mission(FRANCE, "294", france).id, "294")
        self.assertEqual(tvc.pick_mission(FRANCE, "lyon", france).id, "271")
        self.assertEqual(tvc.pick_mission(FRANCE, "nantes", france).id, "458")

    def test_ambiguous_prefix(self) -> None:
        missions = [
            tvc.Mission("1", "Paris Başkonsolosluğu"),
            tvc.Mission("2", "Parma Başkonsolosluğu"),
        ]
        with self.assertRaises(tvc.CLIError):
            tvc.pick_mission(missions, "par", tvc.Country("1", "X"))

    def test_alias_targets_are_unique_keys(self) -> None:
        folded = [tvc.norm(key).replace(" ", "") for key in tvc.COUNTRY_ALIASES]
        self.assertEqual(len(folded), len(set(folded)))


class ParseTests(unittest.TestCase):
    def test_ignores_moving_timestamp(self) -> None:
        row = {
            "MissionId": "271",
            "MissionName": "Liyon Başkonsolosluğu",
            "AppointmentDate": "28.09.2026",
            "AppointmentExist": True,
            "DateFormatAppointment": "2026-09-28T17:23:26.3089756+03:00",
        }
        parsed = tvc.appointment_from(
            row,
            tvc.Country("9890", "Fransa"),
            tvc.Mission("271", "Liyon Başkonsolosluğu"),
        )
        self.assertEqual(parsed.appointment_date, "28.09.2026")
        self.assertEqual(parsed.iso_date, "2026-09-28")

    def test_appointment_blob(self) -> None:
        rows = tvc.parse_appointment_blob(APPOINTMENT_HTML)
        self.assertIsNotNone(rows)
        assert rows is not None
        self.assertEqual(rows[0]["MissionId"], "294")

    def test_agency_page_names_the_agency(self) -> None:
        self.assertIsNone(tvc.parse_appointment_blob(AGENCY_HTML))
        self.assertEqual(tvc.parse_page_note(AGENCY_HTML), "via VfT GmbH-Berlin")

    def test_interval_and_dates(self) -> None:
        self.assertEqual(tvc.parse_interval("2h"), 7200)
        self.assertEqual(tvc.parse_interval("2"), 7200)
        self.assertEqual(tvc.parse_interval("90m"), 5400)
        self.assertEqual(tvc.parse_interval("15m"), 900)
        with self.assertRaises(tvc.CLIError):
            tvc.parse_interval("1m")
        self.assertEqual(tvc.parse_user_date("2026-11-01"), date(2026, 11, 1))
        self.assertEqual(tvc.parse_user_date("01.11.2026"), date(2026, 11, 1))


class NoticeTests(unittest.TestCase):
    def test_first_check_is_quiet_notice(self) -> None:
        paris = appointment("294", "Paris Başkonsolosluğu", "02.12.2026")
        notices, state = tvc.plan_notices({"missions": {}}, [paris], None)
        self.assertEqual([notice.title for notice in notices], ["Visa appointment"])
        self.assertFalse(notices[0].sound)
        self.assertEqual(state["missions"]["294"]["appointment_date"], "02.12.2026")

    def test_same_date_is_silent_even_if_old_timestamp_differed(self) -> None:
        paris = appointment("294", "Paris Başkonsolosluğu", "02.12.2026")
        state = {
            "missions": {
                "294": {
                    "appointment_date": "02.12.2026",
                    "appointment_exist": True,
                    "iso_date": "2026-12-02T00:00:00",
                }
            }
        }
        notices, _new_state = tvc.plan_notices(state, [paris], None)
        self.assertEqual(notices, [])

    def test_date_change(self) -> None:
        paris = appointment("294", "Paris Başkonsolosluğu", "15.10.2026")
        state = {
            "missions": {
                "294": {"appointment_date": "02.12.2026", "appointment_exist": True}
            }
        }
        notices, _new_state = tvc.plan_notices(state, [paris], None)
        self.assertEqual(notices[0].title, "Visa appointment changed")
        self.assertIn("02.12.2026 → 15.10.2026", notices[0].body)
        self.assertFalse(notices[0].sound)

    def test_alert_sounds_once_until_the_date_changes(self) -> None:
        paris = appointment("294", "Paris Başkonsolosluğu", "15.10.2026")
        threshold = date(2026, 11, 1)
        notices, state = tvc.plan_notices({"missions": {}}, [paris], threshold)
        self.assertTrue(notices[0].sound)
        again, _state = tvc.plan_notices(state, [paris], threshold)
        self.assertEqual(again, [])
        moved = appointment("294", "Paris Başkonsolosluğu", "20.10.2026")
        third, _state = tvc.plan_notices(state, [moved], threshold)
        self.assertTrue(third[0].sound)

    def test_plain_notify_keeps_an_existing_alert_marker(self) -> None:
        paris = appointment("294", "Paris Başkonsolosluğu", "15.10.2026")
        state = {
            "missions": {
                "294": {
                    "appointment_date": "15.10.2026",
                    "appointment_exist": True,
                    "alerted_date": "15.10.2026",
                    "alerted_before": "2026-11-01",
                }
            }
        }
        _notices, updated = tvc.plan_notices(state, [paris], None)
        self.assertEqual(updated["missions"]["294"]["alerted_before"], "2026-11-01")

    def test_flat_state_file_migrates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(
                json.dumps(
                    {
                        "mission_id": "294",
                        "appointment_date": "02.12.2026",
                        "appointment_exist": True,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(tvc, "STATE_PATH", path):
                state = tvc.load_state()
        self.assertEqual(state["missions"]["294"]["appointment_date"], "02.12.2026")


class LegacyTests(unittest.TestCase):
    def test_old_flags_map_to_paris(self) -> None:
        self.assertEqual(check.legacy_argv([]), ["check", "france", "paris", "--notify"])
        self.assertEqual(
            check.legacy_argv(["--loop", "--interval-hours", "3"]),
            ["watch", "france", "paris", "--interval", "3h"],
        )
        self.assertEqual(
            check.legacy_argv(["--install"]),
            ["install", "france", "paris"],
        )

    def test_agent_plist_uses_ids(self) -> None:
        data = tvc.build_agent("com.turkey-visa-checker.9890.294", 7200, ["check", "9890", "294", "--notify"])
        self.assertEqual(data["StartInterval"], 7200)
        self.assertEqual(data["ProgramArguments"][-4:], ["check", "9890", "294", "--notify"])
        self.assertTrue(data["ProgramArguments"][1].endswith("tvc.py"))


if __name__ == "__main__":
    unittest.main()
