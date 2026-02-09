import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional


ROOT = Path(__file__).resolve().parents[1]
ENDPOINTS_DIR = ROOT / "app" / "api" / "v1" / "endpoints"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PERM_RE = re.compile(
    r"PermissionChecker\(\s*(?P<arg>\[[^\]]*\]|\"[^\"]*\"|'[^']*')\s*(?:,\s*require_all\s*=\s*(?P<all>True|False))?\s*\)"
)

ROUTE_RE = re.compile(r"@router\.(get|post|put|delete|patch|websocket)\(\s*([\"'])(?P<path>.+?)\\2")


def _extract_permission_codes(arg: str) -> List[str]:
    s = str(arg or "").strip()
    if not s:
        return []
    if s.startswith("["):
        codes = re.findall(r"['\"]([^'\"]+)['\"]", s)
        return [c.strip() for c in codes if str(c).strip()]
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return [s[1:-1].strip()]
    return []


def _find_last_route_decorator(lines: List[str], before_idx: int) -> Optional[str]:
    for i in range(before_idx, max(-1, before_idx - 30), -1):
        m = ROUTE_RE.search(lines[i])
        if m:
            return f"{m.group(1).upper()} {m.group('path')}"
    return None


def scan_file(path: Path) -> List[Dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    results: List[Dict] = []
    for idx, line in enumerate(lines):
        if "PermissionChecker" not in line:
            continue
        m = PERM_RE.search(line)
        if not m:
            continue
        arg = m.group("arg")
        require_all = (m.group("all") == "True")
        codes = _extract_permission_codes(arg)
        route = _find_last_route_decorator(lines, idx)
        results.append(
            {
                "file": str(path.relative_to(ROOT)),
                "line": idx + 1,
                "route": route or "-",
                "permissions": codes,
                "mode": "ALL" if require_all else "ANY",
            }
        )
    return results


def load_backend_dependencies() -> Dict[str, List[str]]:
    from app.services.rbac_service import RbacService

    out: Dict[str, List[str]] = {}
    for k, v in (RbacService.PERMISSION_DEPENDENCIES or {}).items():
        kk = str(k).strip()
        if not kk:
            continue
        out[kk] = [str(x).strip() for x in (v or []) if str(x).strip()]
    return out


def implied_closure(codes: List[str], deps: Dict[str, List[str]]) -> List[str]:
    selected = {str(c).strip() for c in (codes or []) if str(c).strip()}
    changed = True
    while changed:
        changed = False
        for code in list(selected):
            for dep in deps.get(code, []):
                if dep and dep not in selected:
                    selected.add(dep)
                    changed = True
    return sorted(selected)


def main():
    deps = load_backend_dependencies()
    rows: List[Dict] = []
    for py in sorted(ENDPOINTS_DIR.glob("*.py")):
        rows.extend(scan_file(py))

    print("# API 权限清单（从 PermissionChecker 静态扫描）")
    print()
    print("说明：")
    print("- mode=ANY 表示满足任一权限即可；mode=ALL 表示必须同时具备。")
    print("- implied 表示按后端依赖表展开后，实际会隐含的权限集合（用于识别“授权面扩大”）。")
    print()
    print("| Route | mode | perms | implied | Source |")
    print("|---|---:|---|---|---|")
    for r in rows:
        perms = r["permissions"] or []
        implied = implied_closure(perms, deps) if perms else []
        route = str(r["route"])
        src = f"{r['file']}:{r['line']}"
        print(
            f"| {route} | {r['mode']} | {', '.join(perms) if perms else '-'} | {', '.join(implied) if implied else '-'} | {src} |"
        )


if __name__ == "__main__":
    main()
