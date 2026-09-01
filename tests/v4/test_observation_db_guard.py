"""🚨 `tests/conftest.py` 那三层护栏的**空包弹**。

护栏「一直绿」不是它在保护你的证据 —— 本仓已经吃过一次:判闸钉子实测只盖
3/39,钱路裸奔,而它从没红过。所以护栏自己必须有一组**会红的**断言:
把病因原样重演一遍,看它拦不拦。

⛔ 这里全是**行为断言**(真调 `sqlite3.connect`、真读环境变量),
不查源码字符串 —— 语法代理测语义属性在本仓已经翻车四次。
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_GUARDED = (_ROOT / "data" / "v4_observation.db").resolve()

#: 🚨 人口非平凡断言:先证明护栏**真的装上了**。
#: 找不到就 StopIteration ⇒ 本文件整片红,而不是底下那些断言空洞为真。
_CONFTEST = next(
    m for m in list(sys.modules.values())
    if getattr(m, "__file__", None) == str(_ROOT / "tests" / "conftest.py")
)


def _forget_offenses() -> list[str]:
    """取走并清空记账本。

    不清的话,conftest 的 autouse teardown 会把**本文件里故意触发的**那几次
    当成真违规,反过来把自检判红。
    """
    taken = list(_CONFTEST._OFFENSES)
    _CONFTEST._OFFENSES.clear()
    return taken


# ── ① 预防层:环境变量必须已经被挪走 ──────────────────────────────────

def test_observation_env_var_points_away_from_the_repo_db() -> None:
    """⭐ 本文件里最承重的一条 —— 病因就是这个值曾是**相对路径**。

    `/Users/ninoo/Nutmeg/.env` 里写的是 `data/v4_observation.db`,
    `load_dotenv()` 原样塞进 `os.environ`,消费方按 CWD 解析:
    worktree 里造残桩,主 checkout 里**写活生产库**。
    """
    val = os.environ.get("NUTMEG_V4_OBSERVATION_DB")
    assert val, "环境变量没设 ⇒ observation_routes 会退回相对路径默认值"
    p = Path(val)
    assert p.is_absolute(), f"仍是相对路径({val})—— 含义取决于 CWD,病因原样还在"
    assert p.resolve() != _GUARDED, f"仍指着生产观测库:{p}"


# ── ② 连接层:可写拦、只读放 ─────────────────────────────────────────

def test_writable_connect_to_the_production_db_is_blocked() -> None:
    """真调一次 `sqlite3.connect`,拦不拦。顺便验它**没有**把文件造出来。"""
    existed = _GUARDED.exists()
    with pytest.raises(RuntimeError, match="可写"):
        sqlite3.connect(str(_GUARDED))
    assert _forget_offenses(), "拦是拦了,但没记账 ⇒ 调用点一 except 就能吞掉它"
    if not existed:
        assert not _GUARDED.exists(), "拦截发生在建文件之后 ⇒ 残桩照留"


def test_the_relative_path_from_dotenv_is_what_gets_blocked() -> None:
    """🚨 病因原样重演:**相对**路径 + CWD=仓库根,正是 `.env` 那个值的形状。

    只拦绝对路径的话,这条会绿 —— 而真正咬人的从来是相对的那个。
    """
    os.chdir(_ROOT)
    with pytest.raises(RuntimeError, match="可写"):
        sqlite3.connect(os.path.join("data", "v4_observation.db"))
    assert _forget_offenses()


def test_readonly_connect_is_not_blocked() -> None:
    """哨兵读实库走的就是这条路 —— 拦了它 = 把四个数据驱动哨兵全打死。

    库不在时 sqlite 自己会抛 `OperationalError`,那**恰好证明**调用穿过了护栏
    (护栏抛的是 `RuntimeError`)。
    """
    try:
        sqlite3.connect(f"file:{_GUARDED}?mode=ro", uri=True).close()
    except sqlite3.OperationalError:
        pass                                  # 库不在 —— 说明放行了
    except RuntimeError as e:                 # pragma: no cover
        pytest.fail(f"只读被拦了:{e}")
    assert not _forget_offenses(), "只读被记成违规了"


def test_other_databases_are_untouched(tmp_path: Path) -> None:
    """负对照:别的库照常能写。没有这条,一个「什么都拦」的 bug 照样全绿。"""
    db = tmp_path / "v4_observation.db"       # 同名、不同目录 ⇒ 必须放行
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE t(x)")
    assert db.exists()
    assert not _forget_offenses()


@pytest.mark.parametrize(
    ("value", "expect_redirect"),
    [
        (None, True),                                    # 没设 ⇒ 退回相对默认值
        ("", True),
        ("data/v4_observation.db", True),                # ⭐ `.env` 里那个值
        ("./data/v4_observation.db", True),
        (str(_GUARDED), True),                           # 绝对但正是被守的那个
        ("/tmp/somewhere/obs.db", False),                # 明确指向别处 ⇒ 不动
    ],
)
def test_redirect_rule_covers_every_shape_of_the_bad_value(
    value: str | None, expect_redirect: bool
) -> None:
    assert _CONFTEST._needs_redirect(value) is expect_redirect


# ── ③ 残桩层:扫除动作本身 ───────────────────────────────────────────

def test_sweep_removes_the_stub_and_its_sidecars() -> None:
    """`-wal` 不一起扫掉的话,下一次 open 会把残桩复活。"""
    if _GUARDED.exists():
        pytest.skip("这里有真库 —— 不拿它做实验")
    made = []
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(_GUARDED) + suffix)
        p.write_bytes(b"")
        made.append(p.name)
    gone = _CONFTEST._sweep()
    assert set(gone) == set(made), f"扫漏了:{set(made) - set(gone)}"
    assert not any(Path(str(_GUARDED) + s).exists() for s in ("", "-wal", "-shm"))


#: 仓库根 —— 内层用例要拷真的 tests/conftest.py 过去。
REPO = Path(__file__).resolve().parents[2]


# ── 第 ③ 层的触发判据(2026-09-02 补:空包弹发现它零覆盖)────────────────────
#
# 🚨 第 ③ 层(跑完查文件 + 扫残桩)在 **owner 的主 checkout 上恒哑** ——
#    实库会话开始就在 ⇒ `_EXISTED_AT_START = True` ⇒ `created` 恒 False。
#    也就是说:唯一需要它的机器(没有实库的 worktree / CI)上它从没被测过,
#    而有实库的机器上它永远不会跑。空包弹实测:把那一整段判据删掉,全套照绿。
# ⇒ 造一个**没有实库的根**,起内层 pytest 真跑一遍。

def _inner_root(tmp_path: Path) -> Path:
    """搭一个最小的假仓库根:<tmp>/tests/conftest.py,且 <tmp>/data/ 不存在。

    ⚠️ `_ROOT = Path(__file__).resolve().parents[1]` ⇒ conftest 必须落在
    `<tmp>/tests/` 下,`_ROOT` 才会解析成 `<tmp>`(而不是真仓库)。
    """
    import shutil
    (tmp_path / "tests").mkdir()
    shutil.copy(REPO / "tests" / "conftest.py", tmp_path / "tests" / "conftest.py")
    return tmp_path


def _run_inner(root: Path, body: str) -> "subprocess.CompletedProcess":
    import os
    import subprocess
    import sys
    import textwrap
    (root / "tests" / "test_probe.py").write_text(textwrap.dedent(body), encoding="utf-8")
    env = {**os.environ,
           "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": str(REPO / "apps" / "api" / "src")}
    # ⛔ 不带 -p no:cacheprovider 之外的花样;rootdir 就让它落在 <tmp>。
    return subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "tests/test_probe.py", "-q", "--no-header",
         "-p", "no:randomly", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=root, timeout=300, env=env)


def test_layer_three_fires_when_the_db_did_not_exist_at_start(tmp_path: Path) -> None:
    """🚨 没有实库的根上:测试造出残桩 ⇒ 必须判红,**并且扫掉**。

    扫掉是判据的一部分不只是打扫:不删的话,第一个造它的测试之后所有同病测试
    都看到「文件已存在」⇒ 只抓得到一个,抓不到人口。
    """
    root = _inner_root(tmp_path)
    # 🚨 造残桩必须**绕开 sqlite3** —— 空包弹抓到过:第一版用 `sqlite3.connect(db)`,
    #    而那正好触发**第 ② 层**(可写拦截)⇒ 内层是被 ② 判红的,③ 根本没上场。
    #    于是「把 ③ 的触发判据整个删掉」这发变异照样绿。⇒ 用纯文件写。
    r = _run_inner(root, '''
        from pathlib import Path

        def test_probe():
            db = Path("data/v4_observation.db")
            db.parent.mkdir(exist_ok=True)
            db.write_bytes(b"SQLite format 3\\x00")   # 纯文件写:不经 sqlite3.connect
    ''')
    assert r.returncode != 0, (
        f"造出了残桩却没红 —— 第 ③ 层的触发判据失效了:\n{r.stdout[-2500:]}")
    assert "残桩" in r.stdout, f"红了但不是第 ③ 层报的:\n{r.stdout[-2500:]}"
    # ⛔ 并且必须是 ③ 报的,不是 ② —— ② 报的是「以可写方式打开」
    assert "可写" not in r.stdout, (
        f"红的是第 ② 层(可写拦截),③ 仍未被覆盖:\n{r.stdout[-2500:]}")
    assert not (root / "data" / "v4_observation.db").exists(), (
        "红了但残桩没被扫掉 —— 下一轮它会让数据驱动哨兵改去量那个空壳")
    # ⚠️ 「文件没了」不足以钉住**第 ③ 层自己**的扫除:`pytest_sessionfinish` 有
    #    兜底扫除,把 ③ 里的 `_sweep()` 换成 `[]`,文件最终照样没有(空包弹实测
    #    那发仍绿)。⇒ 判据改成「③ 的判红消息里点名扫了哪个文件」——
    #    那是只有 ③ 自己走到才会有的东西。
    import re
    m = re.search(r"已自动扫除:([^)\n]*)", r.stdout)
    assert m and "v4_observation.db" in m.group(1), (
        f"③ 的判红没有点名它扫掉的残桩 ⇒ 扫除那步没走到(兜底层在替它擦屁股):"
        f"\n{r.stdout[-2500:]}")


def test_layer_three_stays_quiet_when_the_db_was_already_there(tmp_path: Path) -> None:
    """⭐ 负对照:实库**会话开始就在** ⇒ 第 ③ 层一个字都不许说,更不许删。

    这条钉的是 owner 主 checkout 上的行为 —— 那里躺着 111MB 的活生产库,
    第 ③ 层要是把「本来就在」也当成残桩,就会把它 unlink 掉。
    """
    root = _inner_root(tmp_path)
    (root / "data").mkdir()
    import sqlite3
    sqlite3.connect(root / "data" / "v4_observation.db").close()
    before = (root / "data" / "v4_observation.db").stat().st_size
    r = _run_inner(root, '''
        def test_probe():
            assert True
    ''')
    assert r.returncode == 0, f"库本来就在,不该红:\n{r.stdout[-2500:]}"
    assert (root / "data" / "v4_observation.db").exists(), "🚨 把本来就在的库删了"
    assert (root / "data" / "v4_observation.db").stat().st_size == before


# ── 纵深防御:主判据被改坏的那一天(2026-09-02 血的教训)────────────────────

def test_a_production_sized_db_is_never_deleted_even_if_the_main_guard_is_broken(
        tmp_path: Path) -> None:
    """🚨 这条钉的是**已经发生过一次**的事故。

    2026-09-02:为了验证「保险失效会删生产库」这发空包弹,主判据被改成
    `created = _guarded_exists()`(去掉 `and not _EXISTED_AT_START`),
    然后在主仓跑了一次 pytest —— 那一轮自己的 autouse fixture 就用这份被改坏的
    conftest 执行了 `_sweep()`,**把 111MB 的生产观测库 unlink 了**。
    已从 daily_backup 恢复,丢了约 21 小时的 forward-only 采集
    (polymarket_gaps 1,672 行等,point-in-time,补不回来)。

    ⇒ 主判据是**对的**,但它可以被改坏,而改坏的代价不可逆。
      这条测试**故意把主判据改坏**,断言体量闸仍然兜得住 ——
      本条要是绿不了,那道兜底就等于不存在。

    ⭐ 判据是「文件还在、且逐字节没变」,不是「没报错」。
    """
    import re as _re
    root = _inner_root(tmp_path)
    cf = root / "tests" / "conftest.py"
    src = cf.read_text(encoding="utf-8")
    broken = src.replace(
        "created = _guarded_exists() and not _EXISTED_AT_START",
        "created = _guarded_exists()")
    assert broken != src, "没能把主判据改坏 ⇒ 本条什么都没验"
    cf.write_text(broken, encoding="utf-8")

    # 造一个「生产体量」的库(> _MAX_STUB_BYTES)
    m = _re.search(r"_MAX_STUB_BYTES = (.+)", src)
    assert m, "找不到 _MAX_STUB_BYTES"
    cap = eval(m.group(1))                                    # noqa: S307
    (root / "data").mkdir()
    prod = root / "data" / "v4_observation.db"
    prod.write_bytes(b"SQLite format 3\x00" + b"x" * (cap + 1024))
    before = prod.read_bytes()

    r = _run_inner(root, '''
        def test_probe():
            assert True
    ''')
    assert prod.exists(), (
        "🚨 主判据被改坏时,体量闸没兜住 —— 生产库会被删。这正是 2026-09-02 那次事故")
    assert prod.read_bytes() == before, "文件还在但内容变了"
    assert "拒绝删除" in r.stdout, (
        f"没有大声说出来 —— 主判据失效必须可见,不能静默跳过:\n{r.stdout[-2000:]}")


def test_the_backstop_still_lets_a_real_stub_be_swept(tmp_path: Path) -> None:
    """⭐ 负对照:真正的残桩(小)照样被扫掉。

    没有这条,把体量闸写成「一律不删」也能让上面那条绿 ——
    而那样第 ③ 层就废了(残桩不删 ⇒ 只抓得到第一个造它的测试,抓不到人口)。
    """
    root = _inner_root(tmp_path)
    r = _run_inner(root, '''
        from pathlib import Path

        def test_probe():
            db = Path("data/v4_observation.db")
            db.parent.mkdir(exist_ok=True)
            db.write_bytes(b"SQLite format 3\\x00")     # 小残桩
    ''')
    assert r.returncode != 0, f"残桩没被判红:\n{r.stdout[-2000:]}"
    assert not (root / "data" / "v4_observation.db").exists(), (
        "小残桩没被扫掉 —— 体量闸把第 ③ 层一起废了")
