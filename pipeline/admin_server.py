"""
Local admin server for the jobs classification pipeline.

Start with:
    python -m pipeline.admin_server

Then visit jobs.html?admin=1 to use the admin UI.

Endpoints:
    GET  /health      — liveness check (used by UI to detect server)
    POST /save_rule   — append a correction to data/rules.json
    POST /rerun       — trigger python -m pipeline.reclassify
    POST /reset_rule  — remove a rule from data/rules.json

Dependencies: flask, flask-cors (pip install flask flask-cors)
"""
import json
import os
import re
import subprocess
import sys

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
# Allow all origins — this server only binds to localhost, so any
# browser tab (including the deployed GitHub Pages site) can call it.
CORS(app)

RULES_PATH = os.path.join('data', 'rules.json')

_EMPTY_RULES = {
    "manual": {},
    "employers": {},
    "keywords": {
        s: {"boost": [], "penalize": []}
        for s in ["Healthcare", "Education", "Logistics", "Public Sector", "Building Trades", "Manufacturing"]
    },
    "role_keywords": {
        r: [] for r in [
            "Internal organizer", "External organizer", "Communications", "Legal",
            "Research", "Political/electoral", "Admin/operations", "Apprenticeship", "Union job"
        ]
    },
    "hide_keywords": [],
}


def _load_rules() -> dict:
    if not os.path.exists(RULES_PATH):
        return dict(_EMPTY_RULES)
    with open(RULES_PATH, encoding='utf-8') as f:
        return json.load(f)


def _save_rules(rules: dict) -> None:
    with open(RULES_PATH, 'w', encoding='utf-8') as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)


def sanity_check(new_rule: dict, existing_rules: dict) -> dict:
    """
    Validate a new rule against existing rules.
    Stub — real conflict detection logic added in Build 5.
    Returns {"ok": bool, "warnings": [...], "blocks": [...]}.
    """
    blocks = []
    warnings = []

    # Block: hide + boost on the same manual rule
    if new_rule.get('hide') and new_rule.get('boost'):
        blocks.append("A job can't be both hidden and boosted. Uncheck one before saving.")

    return {"ok": len(blocks) == 0, "warnings": warnings, "blocks": blocks}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/save_rule', methods=['POST'])
def save_rule():
    data = request.get_json(force=True) or {}
    rules = _load_rules()

    check = sanity_check(data, rules)
    if not check['ok']:
        return jsonify({"ok": False, "blocks": check['blocks'], "warnings": check['warnings']}), 400

    scope = data.get('scope', 'manual')
    rule_added = {}

    if scope == 'manual':
        job_id = (data.get('job_id') or '').strip()
        if not job_id:
            return jsonify({"ok": False, "error": "job_id required for manual scope"}), 400
        rule = {}
        for field in ('sector', 'role_type', 'exp_level', 'special_requirements', 'location_override'):
            val = data.get(field)
            if val not in (None, '', 'no_change'):
                rule[field] = val
        if 'hide' in data and data['hide'] is not None:
            rule['hide'] = bool(data['hide'])
        if data.get('boost'):
            rule['boost'] = True
        rules.setdefault('manual', {})[job_id] = rule
        rule_added = {'manual': {job_id: rule}}

    elif scope == 'employer':
        employer = (data.get('employer') or '').strip()
        if not employer:
            return jsonify({"ok": False, "error": "employer required for employer scope"}), 400
        rule = {}
        for field in ('sector', 'role_type', 'exp_level'):
            val = data.get(field)
            if val not in (None, '', 'no_change'):
                rule[field] = val
        rules.setdefault('employers', {})[employer] = rule
        rule_added = {'employers': {employer: rule}}

    elif scope == 'keyword':
        keyword = (data.get('keyword') or '').strip()
        sector  = (data.get('sector') or '').strip()
        if not keyword:
            return jsonify({"ok": False, "error": "keyword required for keyword scope"}), 400
        kw_rules = rules.setdefault('keywords', {})
        if sector and sector in kw_rules:
            lst = kw_rules[sector].setdefault('boost', [])
            if keyword not in lst:
                lst.append(keyword)
        rule_added = {'keywords': {sector: {'boost': [keyword]}}}

    elif scope == 'role_keyword':
        keyword   = (data.get('keyword') or '').strip()
        role_type = (data.get('role_type') or '').strip()
        if not keyword or not role_type:
            return jsonify({"ok": False, "error": "keyword and role_type required"}), 400
        rk = rules.setdefault('role_keywords', {})
        lst = rk.setdefault(role_type, [])
        if keyword not in lst:
            lst.append(keyword)
        rule_added = {'role_keywords': {role_type: [keyword]}}

    elif scope == 'hide':
        keyword = (data.get('keyword') or '').strip()
        if not keyword:
            return jsonify({"ok": False, "error": "keyword required for hide scope"}), 400
        lst = rules.setdefault('hide_keywords', [])
        if keyword not in lst:
            lst.append(keyword)
        rule_added = {'hide_keywords': [keyword]}

    else:
        return jsonify({"ok": False, "error": f"unknown scope: {scope}"}), 400

    _save_rules(rules)
    return jsonify({"ok": True, "warnings": check['warnings'], "rule_added": rule_added})


@app.route('/rerun', methods=['POST'])
def rerun():
    result = subprocess.run(
        [sys.executable, '-m', 'pipeline.reclassify'],
        capture_output=True, text=True,
        cwd=os.getcwd(),
    )
    output = (result.stdout or '') + (result.stderr or '')
    m = re.search(r'Classified:\s*(\d+)', output)
    job_count = int(m.group(1)) if m else None
    return jsonify({
        "ok": result.returncode == 0,
        "output": output,
        "job_count": job_count,
    })


@app.route('/reset_rule', methods=['POST'])
def reset_rule():
    data = request.get_json(force=True) or {}
    scope = data.get('scope', '')
    key   = data.get('key', '')
    rules = _load_rules()

    if scope == 'manual':
        rules.get('manual', {}).pop(key, None)
    elif scope == 'employer':
        rules.get('employers', {}).pop(key, None)

    _save_rules(rules)
    return jsonify({"ok": True})


def _parse_int_from_output(text, key):
    """Extract integer from machine-parseable lines like 'INGEST_NEW=5'."""
    import re
    m = re.search(rf'{re.escape(key)}=(\d+)', text)
    return int(m.group(1)) if m else None


@app.route('/ingest_url', methods=['POST'])
def ingest_url():
    data = request.get_json(force=True) or {}
    url  = (data.get('url') or '').strip()
    mode = (data.get('mode') or 'auto').strip()

    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    if mode not in ('auto', 'single', 'board'):
        return jsonify({"ok": False, "error": "mode must be auto, single, or board"}), 400

    result = subprocess.run(
        [sys.executable, '-m', 'pipeline.ingest_url', '--url', url, '--mode', mode],
        capture_output=True, text=True,
        cwd=os.getcwd(),
    )
    output = (result.stdout or '') + (result.stderr or '')

    new_count   = _parse_int_from_output(output, 'INGEST_NEW')
    skipped     = _parse_int_from_output(output, 'INGEST_SKIPPED')
    total_count = _parse_int_from_output(output, 'INGEST_TOTAL')

    return jsonify({
        "ok":          result.returncode == 0,
        "output":      output,
        "new_count":   new_count,
        "skipped":     skipped,
        "total_count": total_count,
    })


@app.route('/supported_boards')
def supported_boards():
    from pipeline.ingestors.router import SUPPORTED_BOARDS
    return jsonify({"ok": True, "boards": SUPPORTED_BOARDS})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Admin server starting on http://localhost:5001")
    print("Visit jobs.html?admin=1 to use the admin UI.")
    print("Press Ctrl+C to stop.\n")
    app.run(host='127.0.0.1', port=5001, debug=False)


if __name__ == '__main__':
    main()
