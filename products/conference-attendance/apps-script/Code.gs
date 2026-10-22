/**
 * 출결·방문 등록 — 구글 시트 연동 서버 (Google Apps Script)
 *
 * 설치 (README «구글 시트 연동» 참고)
 *   1. 새 구글 시트 → 확장 프로그램 → Apps Script → 이 파일 내용을 통째로 붙여넣고 저장
 *   2. 위 함수 선택에서 setup 을 골라 ▶ 실행 (권한 허용) → «설정» 시트에 직원코드가 생김
 *   3. 배포 → 새 배포 → 유형 «웹 앱», 실행 사용자 «나», 액세스 «모든 사용자» → 웹 앱 주소 복사
 *   4. 출결 앱 «명단·설정 → 여러 기기 연동» 에 웹 앱 주소와 직원코드 입력
 *
 * 시트
 *   설정 — 행사명·운영방식·직원코드·개인정보 문구 등
 *   명단 — 참석자/방문자 (출결 앱에서 올린 명단 + 현장 등록)
 *   기록 — 입실·퇴실·취소 기록. 행을 중간만 지우지 말 것(지우려면 제목 줄만 남기고 전부)
 *
 * 요청 (POST 본문 JSON, Content-Type text/plain)
 *   info                 — 누구나. 행사명·운영방식·등록 화면 문구
 *   register             — 누구나. 현장 등록 → QR코드ID 발급
 *   pull  {key, since}   — 직원. 명단 전체 + since 번째 이후 기록
 *   push  {key, events, attendees} — 직원. 기록 추가(ID 중복 무시), 명단 추가·갱신
 */

const SHEET_CONF = '설정';
const SHEET_LIST = '명단';
const SHEET_LOG = '기록';
const LIST_HEAD = ['QR코드ID', '이름', '소속', '전화번호', '면허번호', '이메일', '등록경로', '등록시각', '개인정보동의', '마케팅동의', '갱신시각'];
const LOG_HEAD = ['ID', '시각', '구분', 'QR코드ID', '이름', '전화뒷자리', '장소', '방식', '기기', '대상ID', '받은시각', '시각(ms)'];
const CONF_ROWS = [
  ['행사명', '학술대회', '등록 화면과 출결 앱 위에 나오는 이름'],
  ['운영방식', '학술대회', '학술대회 또는 팝업'],
  ['직원코드', '', '출결 앱 연결용 비밀번호. 외부에 알리지 마세요'],
  ['주최', '', '개인정보 수집 주체 (기관·회사명)'],
  ['문의', '', '등록 화면에 보일 문의처'],
  ['보유기간', '행사 종료 후 1년', '개인정보 보유·이용 기간'],
  ['현장등록 열기', '예', '예 / 아니오'],
  ['등록 즉시 입장', '아니오', '예: 등록하면 바로 입장(방문) 기록. 팝업은 «예» 권장'],
  ['면허번호 받기', '예', '예 / 아니오 (학술대회 평점용)'],
];
const EVENT_TYPES = ['입실', '퇴실', '취소'];

/* ---------- 설치 ---------- */

function setup() {
  const ss = SpreadsheetApp.getActive();
  const conf = ensureSheet_(ss, SHEET_CONF, ['항목', '값', '설명']);
  const have = readConf_();
  const missing = CONF_ROWS.filter(function (r) { return !(r[0] in have); });
  if (missing.length) appendRows_(conf, missing);
  const list = ensureSheet_(ss, SHEET_LIST, LIST_HEAD);
  const log = ensureSheet_(ss, SHEET_LOG, LOG_HEAD);
  // 0으로 시작하는 번호·코드가 숫자로 바뀌지 않게 글자 서식
  list.getRange(1, 1, list.getMaxRows(), LIST_HEAD.length).setNumberFormat('@');
  log.getRange(1, 1, log.getMaxRows(), LOG_HEAD.length - 1).setNumberFormat('@');
  if (!readConf_()['직원코드']) setConf_('직원코드', randomCode_(8));
  const code = readConf_()['직원코드'];
  Logger.log('직원코드: ' + code);
  return code;
}

/* ---------- 요청 처리 ---------- */

function doGet(e) {
  return handle_((e && e.parameter) || {});
}

function doPost(e) {
  let p = {};
  try { p = JSON.parse((e && e.postData && e.postData.contents) || '{}'); } catch (err) { p = {}; }
  return handle_(p);
}

function handle_(p) {
  try {
    switch (p.action) {
      case 'info': return out_(info_());
      case 'register': return out_(locked_(function () { return register_(p); }));
      case 'pull': auth_(p); return out_(pull_(p));
      case 'push': auth_(p); return out_(locked_(function () { return push_(p); }));
      default: return out_({ ok: false, error: '알 수 없는 요청입니다' });
    }
  } catch (err) {
    return out_({ ok: false, error: String((err && err.message) || err) });
  }
}

function info_() {
  const c = readConf_();
  return {
    ok: true,
    event: {
      name: c['행사명'] || '행사',
      mode: String(c['운영방식'] || '').indexOf('팝업') >= 0 ? 'popup' : 'conference',
      host: c['주최'] || '',
      contact: c['문의'] || '',
      retention: c['보유기간'] || '행사 종료 후 1년',
      open: isYes_(c['현장등록 열기'], true),
      license: isYes_(c['면허번호 받기'], false),
      autoCheckin: isYes_(c['등록 즉시 입장'], false),
    },
  };
}

function auth_(p) {
  const code = readConf_()['직원코드'];
  if (!code || String(p.key || '') !== code) throw new Error('직원코드가 맞지 않습니다');
}

function pull_(p) {
  const log = sheet_(SHEET_LOG);
  const total = Math.max(0, log.getLastRow() - 1);
  const since = Math.max(0, Number(p.since) || 0);
  const reset = since > total; // 기록 시트를 비웠으면 처음부터 다시
  const from = reset ? 0 : since;
  const rows = total > from ? log.getRange(2 + from, 1, total - from, LOG_HEAD.length).getValues() : [];
  return {
    ok: true,
    event: info_().event,
    attendees: listRows_().map(rowToAttendee_),
    events: rows.filter(function (r) { return r[0]; }).map(rowToEvent_),
    next: total,
    reset: reset,
  };
}

function push_(p) {
  const now = Date.now();
  const log = sheet_(SHEET_LOG);
  const last = log.getLastRow();
  const ids = {};
  if (last > 1) log.getRange(2, 1, last - 1, 1).getValues().forEach(function (r) { ids[String(r[0])] = true; });

  const newRows = [];
  (Array.isArray(p.events) ? p.events : []).slice(0, 2000).forEach(function (e) {
    const id = clean_(e.id, 64);
    const t = Number(e.t);
    if (!id || ids[id] || EVENT_TYPES.indexOf(e.type) < 0 || !isFinite(t)) return;
    ids[id] = true;
    newRows.push([id, fmtTime_(t), e.type, safe_(clean_(e.qr, 64)), safe_(clean_(e.name, 40)), clean_(e.p4, 4),
      safe_(clean_(e.loc, 40)), safe_(clean_(e.by, 20)), safe_(clean_(e.device, 40)), clean_(e.ref, 64), fmtTime_(now), t]);
  });
  appendRows_(log, newRows);

  const list = sheet_(SHEET_LIST);
  const rows = listRows_();
  const at = {};
  rows.forEach(function (r, i) { at[String(r[0]).toLowerCase()] = i + 2; });
  const add = [];
  let updated = 0;
  (Array.isArray(p.attendees) ? p.attendees : []).slice(0, 5000).forEach(function (a) {
    const qr = clean_(a.qr, 64);
    const name = clean_(a.name, 40);
    if (!qr || !name) return;
    const vals = [safe_(name), safe_(clean_(a.org, 80)), safe_(clean_(a.phone, 20)), safe_(clean_(a.license, 20)), safe_(clean_(a.email, 80))];
    const row = at[qr.toLowerCase()];
    if (row) {
      list.getRange(row, 2, 1, 5).setValues([vals]);
      list.getRange(row, 11).setValue(fmtTime_(now));
      updated++;
    } else {
      at[qr.toLowerCase()] = -1;
      add.push([safe_(qr)].concat(vals, [safe_(clean_(a.source, 20)) || '명단', fmtTime_(now), '', '', fmtTime_(now)]));
    }
  });
  appendRows_(list, add);
  return { ok: true, accepted: newRows.length, added: add.length, updated: updated };
}

function register_(p) {
  const ev = info_().event;
  if (!ev.open) throw new Error('현장 등록이 닫혀 있습니다. 등록데스크에 문의해 주세요.');
  const name = clean_(p.name, 40);
  const phone = String(p.phone || '').replace(/\D/g, '');
  if (!name) throw new Error('이름을 입력해 주세요');
  if (!/^01[016789]\d{7,8}$/.test(phone)) throw new Error('휴대폰 번호를 확인해 주세요');
  if (p.privacy !== true) throw new Error('개인정보 수집·이용에 동의해야 등록할 수 있습니다');
  if (p.age14 !== true) throw new Error('만 14세 미만은 보호자 동의가 필요합니다. 등록데스크에 문의해 주세요.');
  const email = clean_(p.email, 80);
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('이메일 주소를 확인해 주세요');

  const rows = listRows_();
  const same = rows.filter(function (r) { return String(r[3]).replace(/\D/g, '') === phone; })[0];
  if (same) {
    if (ev.mode === 'conference') throw new Error('이미 등록된 번호입니다. 문자로 받은 QR을 쓰시거나 등록데스크에 문의해 주세요.');
    if (String(same[1]).replace(/\s/g, '') !== name.replace(/\s/g, '')) throw new Error('이미 다른 이름으로 등록된 번호입니다. 등록데스크에 문의해 주세요.');
    return { ok: true, qr: String(same[0]), name: String(same[1]), existing: true, checkedIn: false, event: ev };
  }

  const taken = {};
  rows.forEach(function (r) { taken[String(r[0]).toLowerCase()] = true; });
  let qr;
  do { qr = 'W' + randomCode_(6); } while (taken[qr.toLowerCase()]);

  const now = Date.now();
  const stamp = fmtTime_(now);
  const fmtPhone = phone.length === 11 ? phone.slice(0, 3) + '-' + phone.slice(3, 7) + '-' + phone.slice(7) : phone.slice(0, 3) + '-' + phone.slice(3, 6) + '-' + phone.slice(6);
  appendRows_(sheet_(SHEET_LIST), [[qr, safe_(name), safe_(clean_(p.org, 80)), fmtPhone, ev.license ? safe_(clean_(p.license, 20)) : '',
    safe_(email), '현장등록', stamp, '동의 ' + stamp, p.marketing === true ? '동의 ' + stamp : '미동의', stamp]]);

  if (ev.autoCheckin) {
    appendRows_(sheet_(SHEET_LOG), [['reg-' + qr, stamp, '입실', qr, safe_(name), phone.slice(-4), '현장등록', '현장등록', '등록페이지', '', stamp, now]]);
  }
  return { ok: true, qr: qr, name: name, existing: false, checkedIn: ev.autoCheckin, event: ev };
}

/* ---------- 시트 도우미 ---------- */

function sheet_(name) {
  const sh = SpreadsheetApp.getActive().getSheetByName(name);
  if (!sh) throw new Error('«' + name + '» 시트가 없습니다. Apps Script 에서 setup 을 먼저 실행하세요.');
  return sh;
}

function ensureSheet_(ss, name, head) {
  const sh = ss.getSheetByName(name) || ss.insertSheet(name);
  if (sh.getLastRow() === 0) sh.getRange(1, 1, 1, head.length).setValues([head]);
  sh.setFrozenRows(1);
  return sh;
}

function appendRows_(sh, rows) {
  if (!rows.length) return;
  const last = sh.getLastRow();
  const need = last + rows.length - sh.getMaxRows();
  if (need > 0) sh.insertRowsAfter(sh.getMaxRows(), need + 50);
  sh.getRange(last + 1, 1, rows.length, rows[0].length).setValues(rows);
}

function listRows_() {
  const sh = sheet_(SHEET_LIST);
  const n = sh.getLastRow() - 1;
  if (n < 1) return [];
  return sh.getRange(2, 1, n, LIST_HEAD.length).getValues().filter(function (r) { return r[0] && r[1]; });
}

function rowToAttendee_(r) {
  return {
    qr: String(r[0]), name: String(r[1]), org: String(r[2]), phone: String(r[3]), license: String(r[4]),
    email: String(r[5]), source: String(r[6]), regAt: String(r[7]), marketing: String(r[9]).indexOf('동의') === 0,
  };
}

function rowToEvent_(r) {
  const e = {
    id: String(r[0]), t: Number(r[11]) || 0, type: String(r[2]), qr: String(r[3]), name: String(r[4]),
    p4: String(r[5]), loc: String(r[6]), by: String(r[7]), device: String(r[8]),
  };
  if (r[9]) e.ref = String(r[9]);
  return e;
}

function readConf_() {
  const sh = SpreadsheetApp.getActive().getSheetByName(SHEET_CONF);
  const map = {};
  if (!sh || sh.getLastRow() < 2) return map;
  sh.getRange(2, 1, sh.getLastRow() - 1, 2).getValues().forEach(function (r) {
    if (r[0]) map[String(r[0]).trim()] = String(r[1]).trim();
  });
  return map;
}

function setConf_(key, value) {
  const sh = sheet_(SHEET_CONF);
  const keys = sh.getRange(2, 1, Math.max(1, sh.getLastRow() - 1), 1).getValues();
  for (let i = 0; i < keys.length; i++) {
    if (String(keys[i][0]).trim() === key) { sh.getRange(i + 2, 2).setValue(value); return; }
  }
  appendRows_(sh, [[key, value, '']]);
}

/* ---------- 작은 도우미 ---------- */

function locked_(fn) {
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try { return fn(); } finally { lock.releaseLock(); }
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function isYes_(v, def) {
  if (v === undefined || v === '') return def;
  return /^(예|네|y|yes|true|o|1|on)$/i.test(String(v).trim());
}

function clean_(s, max) {
  return String(s === undefined || s === null ? '' : s).replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, max);
}

// 시트에서 수식으로 실행되지 않게
function safe_(s) {
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

function fmtTime_(t) {
  return Utilities.formatDate(new Date(t), Session.getScriptTimeZone() || 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
}

function randomCode_(n) {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let s = '';
  for (let i = 0; i < n; i++) s += chars.charAt(Math.floor(Math.random() * chars.length));
  return s;
}
