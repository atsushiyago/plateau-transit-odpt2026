"""
ODPT（公共交通オープンデータチャレンジ2026）の神奈川中央交通データから
藤沢市周辺エリアのバス停別・時間帯別の運行本数データを集計し、
public/data/bus-stop-frequencies.json を生成する。

- バス停位置は既存の analysis-facilities.json（P11ベース）を維持しつつ、
  NFKC名寄せ＋系統番号（odpt:busroutePattern と P11 routes の一致数）により
  他市の同名バス停との混同を防いで正確に紐付ける。
- 江ノ電バスなど ODPT 時刻表が非公開の事業者は hasOdptTimetable=False として保持する。
"""

from __future__ import annotations

import json
import os
import pathlib
import unicodedata
import urllib.request

SCRIPT_DIR = pathlib.Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
CACHE_DIR = SCRIPT_DIR / "cache" / "odpt"
FACILITIES_JSON = REPO_ROOT / "public" / "data" / "analysis-facilities.json"
OUTPUT_JSON = REPO_ROOT / "public" / "data" / "bus-stop-frequencies.json"

MAJOR_OPERATORS = ("神奈川中央交通", "江ノ電バス")

ODPT_POLE_ENDPOINT = (
    "https://api-challenge.odpt.org/api/v4/odpt:BusstopPole"
    "?odpt:operator=odpt.Operator:Kanachu&acl:consumerKey={token}"
)
ODPT_TIMETABLE_DUMP_ENDPOINT = (
    "https://api-challenge.odpt.org/api/v4/odpt:BusTimetable.json"
    "?odpt:operator=odpt.Operator:Kanachu&acl:consumerKey={token}"
)


def load_challenge_token() -> str | None:
    if os.environ.get("ODPT_CHALLENGE_TOKEN"):
        return os.environ["ODPT_CHALLENGE_TOKEN"]
    env_local = REPO_ROOT / ".env.local"
    if env_local.exists():
        for line in env_local.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, val = stripped.split("=", 1)
            if key.strip() == "ODPT_CHALLENGE_TOKEN":
                return val.strip().strip("\"'")
    return None


def ensure_odpt_cache() -> tuple[list[dict], list[dict]]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pole_path = CACHE_DIR / "kanachu_busstop_pole.json"
    tt_path = CACHE_DIR / "kanachu_bus_timetable_full.json"

    token = None
    if not pole_path.exists() or not tt_path.exists():
        token = load_challenge_token()
        if not token:
            raise RuntimeError(
                "ODPT_CHALLENGE_TOKEN が見つかりません。.env.local または環境変数に設定してください。"
            )

    if not pole_path.exists():
        print("Downloading Kanachu odpt:BusstopPole...", flush=True)
        with urllib.request.urlopen(ODPT_POLE_ENDPOINT.format(token=token), timeout=60) as resp:
            pole_path.write_bytes(resp.read())

    if not tt_path.exists():
        print("Downloading Kanachu odpt:BusTimetable.json (full dump)...", flush=True)
        with urllib.request.urlopen(ODPT_TIMETABLE_DUMP_ENDPOINT.format(token=token), timeout=180) as resp:
            tt_path.write_bytes(resp.read())

    poles = json.loads(pole_path.read_text(encoding="utf-8"))
    timetables = json.loads(tt_path.read_text(encoding="utf-8"))
    return poles, timetables


def norm_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip()


def round2(value: float) -> float:
    return round(value, 2)


def main() -> None:
    poles, timetables = ensure_odpt_cache()
    facilities = json.loads(FACILITIES_JSON.read_text(encoding="utf-8"))
    major_stops = [
        s for s in facilities["busStops"] if any(op in s.get("operator", "") for op in MAJOR_OPERATORS)
    ]

    # 1. busroutePattern -> 系統名（例: "藤03", "湘19"）マップを作成
    pat_to_route_name: dict[str, str] = {}
    for tt in timetables:
        pat = tt.get("odpt:busroutePattern")
        title = (tt.get("dc:title") or "").strip()
        if pat and title and pat not in pat_to_route_name:
            pat_to_route_name[pat] = norm_text(title.split()[0])

    # 2. BusstopPole を (正規化名称, 停留所グループコード) ごとにまとめる
    by_title_group: dict[str, dict[str, list[dict]]] = {}
    pole_id_to_group: dict[str, tuple[str, str]] = {}
    for p in poles:
        title = norm_text(p.get("dc:title") or "")
        same_as = p.get("owl:sameAs") or ""
        parts = same_as.split(".")
        if not title or len(parts) < 3:
            continue
        group_code = parts[-2]
        by_title_group.setdefault(title, {}).setdefault(group_code, []).append(p)
        pole_id_to_group[same_as] = (title, group_code)

    # 3. 平日ダイヤの乗車可能便数（canGetOn != False）を時間別(0..23)で集計
    weekday_hourly: dict[tuple[str, str], list[int]] = {}
    for tt in timetables:
        if tt.get("odpt:calendar") != "odpt.Calendar:Weekday":
            continue
        for obj in tt.get("odpt:busTimetableObject", []):
            if obj.get("odpt:canGetOn") is False:
                continue
            pid = obj.get("odpt:busstopPole")
            key = pole_id_to_group.get(pid)
            if key is None:
                continue
            dep = obj.get("odpt:departureTime") or obj.get("odpt:arrivalTime")
            if not dep or ":" not in dep:
                continue
            hour = int(dep.split(":")[0]) % 24
            arr = weekday_hourly.get(key)
            if arr is None:
                arr = [0] * 24
                weekday_hourly[key] = arr
            arr[hour] += 1

    # 4. major_stops（analysis-facilities の主要事業者877件）と1対1で照合
    output_stops: list[dict] = []
    matched_kanachu = 0
    total_kanachu = 0
    enoden_count = 0

    for idx, stop in enumerate(major_stops):
        operator = stop.get("operator", "")
        is_kanachu = "神奈川中央交通" in operator
        if is_kanachu:
            total_kanachu += 1
        elif "江ノ電バス" in operator:
            enoden_count += 1

        entry: dict = {
            "index": idx,
            "name": stop["name"],
            "operator": operator,
            "lat": stop["lat"],
            "lng": stop["lng"],
            "hasOdptTimetable": False,
            "weekday": None,
        }

        if is_kanachu:
            title = norm_text(stop["name"])
            groups = by_title_group.get(title, {})
            chosen_group: str | None = None
            if len(groups) == 1:
                chosen_group = next(iter(groups))
            elif len(groups) > 1:
                p11_routes = {norm_text(r["name"]) for r in stop.get("routes", []) if r.get("name")}
                chosen_group = max(
                    groups.items(),
                    key=lambda kv: (
                        len(
                            p11_routes
                            & {
                                pat_to_route_name[pat]
                                for pole in kv[1]
                                for pat in pole.get("odpt:busroutePattern", [])
                                if pat in pat_to_route_name
                            }
                        ),
                        sum(weekday_hourly.get((title, kv[0]), [0] * 24)),
                    ),
                )[0]

            if chosen_group is not None:
                hours = weekday_hourly.get((title, chosen_group), [0] * 24)
                total = sum(hours)
                # 運行時間帯を概ね 5:00〜22:59 (18時間) として終日平均本数/時を算出
                all_day_per_hour = total / 18.0
                morning_per_hour = sum(hours[7:10]) / 3.0   # 7:00-9:59 (3時間)
                daytime_per_hour = sum(hours[10:17]) / 7.0  # 10:00-16:59 (7時間)
                evening_per_hour = sum(hours[19:23]) / 4.0  # 19:00-22:59 (4時間)
                entry["hasOdptTimetable"] = True
                entry["weekday"] = {
                    "total": total,
                    "allDayPerHour": round2(all_day_per_hour),
                    "morningPerHour": round2(morning_per_hour),
                    "daytimePerHour": round2(daytime_per_hour),
                    "eveningPerHour": round2(evening_per_hour),
                    "hourly": hours,
                }
                matched_kanachu += 1

        output_stops.append(entry)

    payload = {
        "metadata": {
            "source": "公共交通オープンデータセンター（ODPT）チャレンジ2026 神奈川中央交通 バス時刻表・バス停情報",
            "calendar": "Weekday",
            "timeBands": {
                "allDay": "終日平均 (5:00-22:59)",
                "morning": "朝 (7:00-9:59)",
                "daytime": "日中 (10:00-16:59)",
                "evening": "夜 (19:00-22:59)",
            },
            "totalMajorStops": len(output_stops),
            "matchedKanachuStops": matched_kanachu,
            "totalKanachuStops": total_kanachu,
            "enodenPositionOnlyStops": enoden_count,
        },
        "stops": output_stops,
    }

    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size_kb = OUTPUT_JSON.stat().st_size / 1024
    print(
        f"Wrote {OUTPUT_JSON.name}: {len(output_stops)} stops "
        f"(Kanachu ODPT matched {matched_kanachu}/{total_kanachu}, Enoden {enoden_count}), "
        f"size={size_kb:.1f}KB",
        flush=True,
    )


if __name__ == "__main__":
    main()
