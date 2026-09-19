"""Dependency-free Node smoke checks for the inline frontend presentation code."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NODE_SMOKE = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {spawnSync} = require('node:child_process');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const script = html.split('<script type="module">')[1].split('</script>')[0];
const syntax = spawnSync(process.execPath, ['--check', '--input-type=module'],
  {input: script, encoding: 'utf8'});
assert.equal(syntax.status, 0, syntax.stderr);
assert.equal((script.match(/\bfetch\(/g) || []).length, 1, 'Only the api helper may fetch');
assert(!script.includes('addLabel(obj.id'));
assert(script.includes('nameInput.dataset.displayed'), 'Canonical names must survive English property edits');

function section(start, end) { return script.slice(script.indexOf(start), script.indexOf(end)); }
class Element {
  constructor() {
    this.children = []; this.style = {}; this.dataset = {}; this.value = '';
    this.innerHTML = ''; this.textContent = ''; this.isConnected = true;
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren() { this.children = []; this.innerHTML = ''; }
  querySelector(selector) {
    if (selector === '.cand-wrap') return this.children.find(x => x.className === 'cand-wrap') || null;
    this.queries ||= {};
    return this.queries[selector] ||= new Element();
  }
  remove() { this.isConnected = false; }
  setAttribute() {}
  focus() {}
}
const elements = new Map();
const document = {
  getElementById(id) {
    if (id === 'report-overlay') return null;
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  },
  createElement: () => new Element(),
  querySelectorAll: () => [],
  documentElement: {}, body: new Element(),
};
const window = {location: {origin: 'http://localhost'}};
const localStorage = {getItem: () => null, setItem: () => {}};
let response = {}, requests = [];
let fetch = async url => {
  requests.push(url);
  return {ok: true, json: async () => response};
};
let sceneData = null;
let previewed = false;
const previewCandidate = () => { previewed = true; };
const clearGhosts = () => {};
const applyCandidate = () => {};
const refresh = async () => {};
const commitEdit = async () => {};
const select = () => {};
const nextId = () => 'bed_1';
const TYPE_SIZES = {bed: [2, 1.1, .5]};

const code = [
  section('// ---------- Presentation-only localization', '// ---------- Renderer / Scene'),
  section('async function toggleCandidates(', "document.getElementById('reset-btn').onclick"),
  section('async function showReport()', '// ---------- Natural-language commands'),
  section('async function sendCommand()', "document.getElementById('cmd-send').onclick"),
  section("document.getElementById('add-obj').onclick", "document.getElementById('del-obj').onclick"),
].join('\n');
const checks = `
assert.equal(lang, 'ko');
const bed = {id: 'bed', type: 'bed', name: '침대 (침실)'};
assert.equal(displayName(bed), '침대 (침실)');
assert.equal(shortName(bed), '침대');
assert.equal(codeName('HARD_CLASH'), '가구 충돌');
lang = 'en';
assert.equal(displayName(bed), 'Bed (Bedroom)');
assert.equal(shortName(bed), 'Bed');
assert.equal(displayName({id: 'bed_2', type: 'bed', name: '침대 2'}), 'Bed 2');
assert.equal(displayName({id: 'bed_8', type: 'bed', name: 'bed_8'}), 'Bed 8');
assert.equal(bed.name, '침대 (침실)');
assert.equal(esc('<img src=x onerror="x">\\'&'), '&lt;img src=x onerror=&quot;x&quot;&gt;&#39;&amp;');
await api('/api/chat?existing=1', {method: 'POST'});
assert.equal(requests.at(-1).searchParams.get('lang'), 'en');
assert.equal(requests.at(-1).searchParams.get('existing'), '1');
sceneData = {meta: {room: {min: [0,0,0], max: [9,6,3]}}, equipment: [bed]};
document.getElementById('add-type').value = 'bed';
await document.getElementById('add-obj').onclick();
assert.equal(sceneData.equipment.at(-1).name, '침대 2');
assert.equal(sceneData.equipment.at(-1).id, 'bed_1');

const malicious = '<img src=x onerror=alert(1)>';
response = {reply: malicious, applied: [malicious], errors: [malicious]};
document.getElementById('cmd-input').value = 'Move desk';
await sendCommand();
assert(!document.getElementById('cmd-reply').innerHTML.includes('<img'));
assert(document.getElementById('cmd-reply').innerHTML.includes('&lt;img'));
response = {blocked: true, token: 'pending-token', reply: '1 new violation', applied: []};
document.getElementById('cmd-input').value = 'Unsafe command';
await sendCommand();
const forceButton = document.getElementById('cmd-reply').children.at(-1);
assert.equal(forceButton.textContent, 'Apply anyway');
response = {applied: true};
await forceButton.onclick();
assert.equal(requests.at(-1).pathname, '/api/command/apply');
response = {error: malicious};
document.getElementById('cmd-input').value = 'Another command';
await sendCommand();
assert(!document.getElementById('cmd-reply').innerHTML.includes('<img'));
assert(document.getElementById('cmd-reply').innerHTML.includes('&lt;img'));

response = {candidates: [{option: malicious, description: malicious, impact: malicious,
  recommended: true, verified: true, violations_after: 1, displacement_mm: 20}]};
const card = new Element();
await toggleCandidates(card, {id: 'DE-1'});
const wrap = card.children[0];
assert(previewed);
assert(wrap.children[0].innerHTML.includes('Recommended'));
assert(!wrap.children[0].innerHTML.includes('<img'));
response = {analysis: {why: malicious, impact: [malicious], recommendation: malicious,
  past_case: malicious, knowledge_used: {rules: [malicious], cases: [malicious]}, llm: true}};
await wrap.children[1].onclick();
assert(!wrap.children.at(-1).innerHTML.includes('<img'));
assert(wrap.children.at(-1).innerHTML.includes('Expected impact'));

response = {summary: {score: 34, checks_run: 10, passed: 4, violations: 6},
  scene_name: malicious, generated: malicious,
  violations: [{id: 'DE-1', severity: 'HIGH', code: 'HARD_CLASH', detail: malicious,
    measured_mm: -250, required_mm: 0}],
  history: [{time: '10:00', kind: 'copilot', text: malicious}]};
await showReport();
let report = document.body.children.at(-1).queries['#report-frame'].srcdoc;
assert(report.includes('<html lang="en">'));
assert(report.includes('Layout score'));
assert(report.includes('History entries are shown in the language originally recorded.'));
assert(!report.includes('<img'));
lang = 'ko';
await showReport();
report = document.body.children.at(-1).queries['#report-frame'].srcdoc;
assert(report.includes('<html lang="ko">'));
assert(report.includes('가구 충돌'));
assert(report.includes('배치 점수'));

let release;
fetch = url => new Promise(resolve => {
  release = () => resolve({ok: true, json: async () => ({reply: 'stale reply'})});
});
document.getElementById('cmd-input').value = 'Move desk';
const pending = sendCommand();
languageRevision++;
document.getElementById('cmd-reply').innerHTML = '';
release();
await pending;
assert.equal(document.getElementById('cmd-reply').innerHTML, '');
console.log('Frontend localization, API language, names, escaping, report, and stale-response checks passed');
`;
eval(`(async () => {${code}\n${checks}})()`).catch(error => {
  console.error(error);
  process.exitCode = 1;
});
"""


def test_frontend_i18n_smoke():
    node = shutil.which("node") or shutil.which("node.exe")
    if node is None:
        pytest.skip("Node.js is required for frontend JavaScript smoke checks")
    result = subprocess.run(
        [node, "-"], input=NODE_SMOKE, text=True, encoding="utf-8",
        capture_output=True, cwd=ROOT, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
