"""
Generate standalone HTML reference files from step*_reference.py and pipeline_reference.py.

Output files (same directory as this script):
  pipeline_reference.html
  step1_reference.html … step4_reference.html

Also extracts pipeline_reference.svg from pipeline_reference.py.

Run from any directory:
    python notebook/z_references/generate_html.py
"""
import re
import sys
import importlib.util
from pathlib import Path

HERE = Path(__file__).parent.resolve()

_WRAPPER = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
</head>
<body style="margin:24px auto;max-width:900px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
{body}
</body>
</html>
"""


def _load_html_content(py_file: Path) -> str:
    """Import a reference .py and return its HTML_CONTENT string."""
    spec = importlib.util.spec_from_file_location("_ref", py_file)
    mod = importlib.util.module_from_spec(spec)
    # Stub out IPython so the module-level display() call is a no-op
    import types
    fake_ipython = types.ModuleType("IPython")
    fake_display = types.ModuleType("IPython.display")
    fake_display.HTML = lambda x: x
    fake_display.display = lambda *a, **kw: None
    fake_ipython.display = fake_display
    sys.modules.setdefault("IPython", fake_ipython)
    sys.modules.setdefault("IPython.display", fake_display)
    spec.loader.exec_module(mod)
    return getattr(mod, "HTML_CONTENT", "")


def generate_step_html(step_num: int) -> None:
    py = HERE / f"step{step_num}_reference.py"
    if not py.exists():
        print(f"  [skip] {py.name} not found")
        return
    html_content = _load_html_content(py)
    out = HERE / f"step{step_num}_reference.html"
    out.write_text(_WRAPPER.format(title=f"Step {step_num} reference", body=html_content))
    print(f"  [ok]   {out.name}")


def generate_pipeline_html() -> None:
    py = HERE / "pipeline_reference.py"
    if not py.exists():
        print("  [skip] pipeline_reference.py not found")
        return
    html_content = _load_html_content(py)
    out = HERE / "pipeline_reference.html"
    out.write_text(_WRAPPER.format(title="TUS pipeline reference", body=html_content))
    print(f"  [ok]   {out.name}")


def generate_pipeline_svg() -> None:
    py = HERE / "pipeline_reference.py"
    if not py.exists():
        return
    content = py.read_text()
    m = re.search(r'(<svg[\s\S]*?</svg>)', content)
    if m:
        out = HERE / "pipeline_reference.svg"
        out.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + m.group(1))
        print(f"  [ok]   {out.name}")


def generate_pipeline_png() -> None:
    """Screenshot pipeline_reference.html → pipeline_reference_card.png using Playwright."""
    html_file = HERE / "pipeline_reference.html"
    out = HERE / "pipeline_reference_card.png"
    if not html_file.exists():
        print("  [skip] pipeline_reference.html not found (run generate_pipeline_html first)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [skip] pipeline_reference_card.png — playwright not installed")
        return
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 960, "height": 800}, device_scale_factor=2)
        page.goto(html_file.as_uri())
        page.wait_for_timeout(300)
        # Capture only the content div, not the full viewport
        content = page.query_selector(".pip-wrap")
        if content:
            content.screenshot(path=str(out))
        else:
            page.screenshot(path=str(out), full_page=True)
        browser.close()
    print(f"  [ok]   {out.name}")


if __name__ == "__main__":
    print("Generating reference HTML files...")
    generate_pipeline_html()
    generate_pipeline_svg()
    generate_pipeline_png()
    for n in range(1, 6):
        generate_step_html(n)
    print("Done.")
