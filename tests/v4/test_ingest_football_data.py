"""football-data CSV 下载器的四道闸(owner 2026-08-06)。

## 为什么会有这个 CLI

训练链条 `下载 → ingest → 重训` 的**第一步一直是手动的** —— 代码里一个下载
入口都没有(grep 零命中),CSV 全靠人往 `data/historical_sources/` 里放。
artifact 因此冻在 2026-07-15。

## 四道闸,每道对应一次真踩过的坑

1. **404 伪装成空结果**:football-data 的 404 返回 **1271 字节的 HTML 错误页**,
   不是空 body。只判「有没有内容」会把错误页存成 CSV,下游报的是
   「missing 'Div' column」—— 和「这个联赛没数据」长得完全不一样。
2. **空 body 静默冲好数据**(clubelo 自毁式覆盖):远端抽风给半截文件,覆盖
   过去就永久少一截 ⇒ 行数变少默认拒绝写。
3. **抓空集也叫成功**:报告说的是「+N 行」,不是「✓ 完成」。
4. **404 ≠ 失败**:新赛季文件还没出就是 404(实测 2026-08-06 当天 `2627/D2`
   还是 404,而 `2627/SP1` 已有 5 行)。把它算失败会训练出忽略报警的习惯。

## 还钉住一个我自己写错的地方

第一版 `season_codes_for` 返回「当前+**下一**赛季」,而「下一赛季」要等整整
一年才存在 ⇒ 每次跑白打 13 个 404。正确的是「**上一**季+当前」(上季补录还在
写、新季刚出现)。是靠干跑输出里那一屏 `2728/*` 全 404 看出来的 —— 干跑先行
的价值。
"""
from __future__ import annotations

import datetime as dt

import pytest

from nutmeg.v4.cli import ingest_football_data as mod
from nutmeg.v4.cli.ingest_football_data import (
    TRAINED_DIVS,
    _data_rows,
    _looks_like_csv,
    season_codes_for,
    sync_season,
)

_HEADER = b"\xef\xbb\xbfDiv,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"


def _csv(n: int) -> bytes:
    rows = b"".join(f"D2,0{i%9+1}/08/2026,18:30,H{i},A{i},1,0,H\n".encode() for i in range(n))
    return _HEADER + rows


#: football-data 404 时真实返回的东西(形状抄自实测:200-ish 字节的 HTML,不是空)
_HTML_404 = (b"<!DOCTYPE html><html><head><title>404 Not Found</title></head>"
             b"<body><h1>Not Found</h1><p>The requested URL was not found.</p></body></html>")


class TestSeasonCodes:
    def test_august_gives_prev_and_current(self):
        """⭐ 钉住我写错过的那一处:8 月要的是「上一季 + 当前季」。"""
        assert season_codes_for(dt.date(2026, 8, 6)) == ["2526", "2627"]

    def test_spring_still_gives_prev_and_current(self):
        """3 月还在赛季中:当前是 2526,上一季 2425。"""
        assert season_codes_for(dt.date(2026, 3, 1)) == ["2425", "2526"]

    def test_never_asks_for_a_season_that_cannot_exist_yet(self):
        """「下一赛季」要等一年才存在 —— 出现在结果里就是每次白打 13 个 404。"""
        for d in (dt.date(2026, 8, 6), dt.date(2026, 12, 31), dt.date(2027, 1, 1)):
            assert "2728" not in season_codes_for(d), d


class TestCsvSniff:
    def test_rejects_the_html_404_page(self):
        """⭐ 承重条:404 页是**有内容**的,只判长度必中招。"""
        assert _looks_like_csv(_HTML_404) is False

    def test_accepts_the_real_header_with_bom(self):
        assert _looks_like_csv(_csv(3)) is True

    def test_rejects_empty_and_whitespace(self):
        assert _looks_like_csv(b"") is False
        assert _looks_like_csv(b"   \n\n") is False

    def test_row_count_excludes_header_and_blanks(self):
        assert _data_rows(_csv(7)) == 7
        assert _data_rows(_HEADER) == 0


def _stub(monkeypatch, table: dict[tuple[str, str], tuple[bytes | None, str]]):
    """把 HTTP 边界换掉,其余(比对/闸/写盘)全走真实代码。"""
    def fake(season, div, *, timeout=30.0):
        return table.get((season, div), (None, "· 尚未发布(404)"))
    monkeypatch.setattr(mod, "fetch_one", fake)


class TestGuards:
    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        _stub(monkeypatch, {("2627", "D2"): (_csv(9), "ok")})
        added, fails, _ = sync_season("2627", tmp_path, divs=("D2",), apply=False)
        assert added == 9 and fails == 0
        assert not (tmp_path / "2627" / "D2.csv").exists(), "干跑写盘了"

    def test_apply_writes_and_reports_delta(self, tmp_path, monkeypatch):
        _stub(monkeypatch, {("2627", "D2"): (_csv(9), "ok")})
        added, fails, _ = sync_season("2627", tmp_path, divs=("D2",), apply=True)
        assert (added, fails) == (9, 0)
        assert _data_rows((tmp_path / "2627" / "D2.csv").read_bytes()) == 9

    def test_shrink_is_refused_and_counts_as_failure(self, tmp_path, monkeypatch):
        """🩹 clubelo 自毁式覆盖同族:远端半截文件不许覆盖好数据。"""
        dest = tmp_path / "2627"
        dest.mkdir()
        (dest / "D2.csv").write_bytes(_csv(300))
        _stub(monkeypatch, {("2627", "D2"): (_csv(12), "ok")})
        added, fails, lines = sync_season("2627", tmp_path, divs=("D2",), apply=True)
        assert fails == 1 and added == 0
        assert _data_rows((dest / "D2.csv").read_bytes()) == 300, "好数据被覆盖了"
        assert any("拒绝覆盖" in ln for ln in lines)

    def test_shrink_allowed_with_explicit_flag(self, tmp_path, monkeypatch):
        """真缩水(联赛缩编/远端重排)得有出口,但必须显式。"""
        dest = tmp_path / "2627"
        dest.mkdir()
        (dest / "D2.csv").write_bytes(_csv(300))
        _stub(monkeypatch, {("2627", "D2"): (_csv(12), "ok")})
        _, fails, _ = sync_season("2627", tmp_path, divs=("D2",), apply=True, allow_shrink=True)
        assert fails == 0
        assert _data_rows((dest / "D2.csv").read_bytes()) == 12

    def test_404_is_not_a_failure(self, tmp_path, monkeypatch):
        """⭐ 新赛季还没发布就是 404 —— 这是正确答案,不是故障。"""
        _stub(monkeypatch, {})
        added, fails, lines = sync_season("2728", tmp_path, divs=("D2",), apply=True)
        assert (added, fails) == (0, 0)
        assert any("尚未发布" in ln for ln in lines)

    def test_non_csv_body_is_a_failure_and_does_not_write(self, tmp_path, monkeypatch):
        _stub(monkeypatch, {("2627", "D2"): (None, "❌ 不是 CSV(首 40 字节 ...)")})
        added, fails, _ = sync_season("2627", tmp_path, divs=("D2",), apply=True)
        assert (added, fails) == (0, 1)
        assert not (tmp_path / "2627" / "D2.csv").exists()

    def test_unchanged_file_is_neither_added_nor_failed(self, tmp_path, monkeypatch):
        """整季已完结、远端逐字节相同 ⇒ +0 且不报错(实测 2526 全部如此)。"""
        dest = tmp_path / "2526"
        dest.mkdir()
        (dest / "D2.csv").write_bytes(_csv(306))
        _stub(monkeypatch, {("2526", "D2"): (_csv(306), "ok")})
        added, fails, lines = sync_season("2526", tmp_path, divs=("D2",), apply=True)
        assert (added, fails) == (0, 0)
        assert any("无变化" in ln for ln in lines)


class TestExitCode:
    def test_zero_new_rows_exits_zero(self, tmp_path, monkeypatch, capsys):
        """⭐ 「一行没新增」**不是**失败 —— 休赛期本来就是 0。把它当失败会训练出
        忽略报警的习惯(老误报的护栏最后会被删掉)。"""
        _stub(monkeypatch, {})
        rc = mod.main(["--out-dir", str(tmp_path), "--seasons", "2728", "--apply"])
        assert rc == 0
        assert "去看了、确实没有新数据" in capsys.readouterr().out

    def test_hard_failure_exits_one(self, tmp_path, monkeypatch):
        _stub(monkeypatch, {("2627", "E0"): (None, "❌ HTTP 503")})
        assert mod.main(["--out-dir", str(tmp_path), "--seasons", "2627", "--apply"]) == 1


def test_only_trained_divs_are_fetched():
    """别写成「把该站所有联赛都拉下来」—— 源树是训练语料,多出来的联赛会
    悄悄改变 `load_all_matches` 的口径。

    13 个 div = 生产训练集的**欧洲**部分。第 14 个训练联赛 JPN_J1 不在这里 ——
    它走 `japan/JPN.csv`,是另一棵子树、另一个 URL 模式,不归本 CLI 管。
    """
    from nutmeg.v4.data.ingest import LEAGUE_NAMES
    assert len(TRAINED_DIVS) == 13
    unknown = [d for d in TRAINED_DIVS if d not in LEAGUE_NAMES]
    assert not unknown, f"这些 div 不在 LEAGUE_NAMES 里:{unknown}"


@pytest.mark.parametrize("season,div", [("2526", "D2")])
def test_live_url_shape_still_holds(season, div):
    """拿真站核一次形状(联网才跑)。URL 模式变了这条会红。"""
    import httpx
    try:
        r = httpx.get(mod.BASE_URL.format(season=season, div=div), timeout=20)
    except httpx.HTTPError:
        pytest.skip("离线")
    assert r.status_code == 200
    assert _looks_like_csv(r.content), r.content[:80]
    assert _data_rows(r.content) > 200, "整季应有 300 行量级"
