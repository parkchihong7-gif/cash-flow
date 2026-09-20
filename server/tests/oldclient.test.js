/**
 * 공인중개사 화면(gongin-jungsagsa-exam)이 **이 서버에 그대로 붙는가.**
 *
 * 그 화면은 이미 팔려 나갈 물건이고, 소스는 다른 저장소에 있어 여기서
 * 고칠 수 없다. 고칠 수 있는 것은 `APPS_SCRIPT_URL` 한 줄뿐이다.
 * 그러니 **이 서버가 그 화면의 규약을 그대로 받아 줘야** 한다.
 *
 * 아래는 그 화면이 실제로 보내는 요청을 그대로 옮긴 것이다.
 * (index.html 의 adminApi() · tryRedeem() · startSessionHeartbeat() 에서)
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { makeServer } = require('./harness');

const PW = '주인비밀번호7';
/** 옛 화면은 program 을 안 보낸다. 기본 프로그램으로 받아 줘야 한다. */
const PROPS = { ADMIN_PASSWORD: PW, DEFAULT_PROGRAM: 'exam' };

/** 옛 화면의 adminApi(action, params) — token 은 **비밀번호 그 자체**다. */
function adminApi(srv, action, params) {
  return srv.call(Object.assign({ action: action, token: PW }, params || {}));
}

test('옛 화면: 비밀번호만으로 로그인된다 (adminList 성공 = 로그인 성공)', () => {
  const srv = makeServer(PROPS);
  assert.strictEqual(adminApi(srv, 'adminList').ok, true);
  assert.strictEqual(srv.call({ action: 'adminList', token: '틀린것' }).ok, false);
});

test('옛 화면: 이메일 배포가 그대로 된다', () => {
  const srv = makeServer(PROPS);
  const data = adminApi(srv, 'adminCreateInvite', {
    name: '홍길동', email: 'hong@example.com',
    baseUrl: 'https://parkchihong7-gif.github.io/gongin-jungsagsa-exam/',
  });
  assert.strictEqual(data.ok, true);
  // 그 화면은 이 세 칸을 그대로 꺼내 쓴다. 이름이 다르면 화면이 깨진다.
  assert.ok(data.primaryKey, 'primaryKey 가 없습니다');
  assert.ok(data.secondaryKeys['PC'], '2차 PC 가 없습니다');
  assert.ok(data.secondaryKeys['노트북'], '2차 노트북이 없습니다');
  assert.ok(data.secondaryKeys['휴대폰'], '2차 휴대폰이 없습니다');
  assert.strictEqual(typeof data.url, 'string', 'url 이 없습니다');
});

test('옛 화면: 레거시 일괄 생성이 그대로 된다', () => {
  const srv = makeServer(PROPS);
  const data = adminApi(srv, 'adminCreateKeys', { count: '10', expiryDays: '' });
  assert.strictEqual(data.ok, true);
  assert.strictEqual(data.keys.length, 10);
});

test('옛 화면: 문 열기와 하트비트가 그대로 된다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = adminApi(srv, 'adminCreateInvite', { name: '홍', email: 'h@example.com' });

  // tryRedeem(): key1 만, 또는 key1+key2
  const 만 = srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey });
  assert.strictEqual(만.reason, 'no_secondary');

  const 열림 = srv.call({ action: 'validateKeyPair',
                          key1: 한벌.primaryKey, key2: 한벌.secondaryKeys['PC'] });
  assert.strictEqual(열림.ok, true);
  assert.ok(열림.sessionToken, 'sessionToken 이 없습니다');

  // startSessionHeartbeat(): 1분마다 checkSession
  const 확인 = srv.call({ action: 'checkSession',
                          key: 한벌.secondaryKeys['PC'], sessionToken: 열림.sessionToken });
  assert.strictEqual(확인.ok, true);

  // 다른 기기가 같은 2차키로 들어오면 → session_replaced
  srv.call({ action: 'validateKeyPair', key1: 한벌.primaryKey, key2: 한벌.secondaryKeys['PC'] });
  const 쫓김 = srv.call({ action: 'checkSession',
                          key: 한벌.secondaryKeys['PC'], sessionToken: 열림.sessionToken });
  assert.strictEqual(쫓김.ok, false);
  assert.strictEqual(쫓김.reason, 'session_replaced', '그 화면은 이 말만 알아듣는다');
});

test('옛 화면: reason 값이 그 화면이 아는 것들이다', () => {
  // index.html 이 분기하는 값들: no_secondary / pair_mismatch /
  // secondary_not_found / session_replaced / suspended
  const srv = makeServer(PROPS);
  const 갑 = adminApi(srv, 'adminCreateInvite', { name: '갑', email: 'a@example.com' });
  const 을 = adminApi(srv, 'adminCreateInvite', { name: '을', email: 'b@example.com' });

  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', key1: 갑.primaryKey }).reason, 'no_secondary');
  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', key1: 갑.primaryKey,
               key2: 을.secondaryKeys['PC'] }).reason, 'pair_mismatch');
  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', key1: 갑.primaryKey,
               key2: 'ZZZZ-ZZZZ-ZZZZ' }).reason, 'secondary_not_found');

  adminApi(srv, 'adminSuspendKey', { key: 갑.primaryKey });
  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', key1: 갑.primaryKey,
               key2: 갑.secondaryKeys['PC'] }).reason, 'suspended');
});

test('옛 화면: 목록 표가 그 화면이 읽는 칸을 갖고 있다', () => {
  const srv = makeServer(PROPS);
  adminApi(srv, 'adminCreateInvite', { name: '홍길동', email: 'hong@example.com' });
  const rows = adminApi(srv, 'adminList').rows;
  assert.ok(rows.length, '목록이 비었습니다');

  // index.html 의 renderAdminKeyTable() 이 r.* 로 읽는 칸들
  for (const 칸 of ['key', 'type', 'status', 'issuedDate', 'expiryDate',
                    'assignedName', 'assignedEmail', 'usedDate']) {
    assert.ok(칸 in rows[0], `목록에 ${칸} 칸이 없습니다`);
  }
  const 이차 = rows.find((r) => r.type === 'secondary');
  assert.ok('deviceLabel' in 이차 && 'parentKey' in 이차);
  // primary/secondary 로 갈라 보여 주는 화면이라 이 두 값이 그대로여야 한다
  assert.ok(rows.some((r) => r.type === 'primary'));
});

test('옛 화면: 정지·삭제가 그대로 된다', () => {
  const srv = makeServer(PROPS);
  const 한벌 = adminApi(srv, 'adminCreateInvite', { name: '홍', email: 'h@example.com' });
  assert.strictEqual(adminApi(srv, 'adminSuspendKey', { key: 한벌.primaryKey }).ok, true);
  assert.strictEqual(adminApi(srv, 'adminDeleteKey', { key: 한벌.primaryKey }).ok, true);
  assert.strictEqual(adminApi(srv, 'adminList').rows.length, 0);
});

// ── 여기부터는 **다른 점**이다. 그대로는 안 된다 ──────────────────

test('다른 점 ①: 모든 키 초기화는 confirm 이 있어야 움직인다', () => {
  // 옛 화면은 confirm 을 안 보낸다. 그러니 그 버튼은 안 먹는다.
  // 막는 쪽이 옳다 — 버튼 한 번에 판 키가 통째로 날아가면 안 된다.
  const srv = makeServer(PROPS);
  adminApi(srv, 'adminCreateInvite', { name: '홍', email: 'h@example.com' });
  const out = adminApi(srv, 'adminResetAll');
  assert.strictEqual(out.ok, false);
  assert.strictEqual(out.reason, 'need_confirm');
  assert.strictEqual(adminApi(srv, 'adminList').rows.length, 4, '안 지운다더니 지웠습니다');
});

test('다른 점 ②: 옛 화면이 만든 키는 판매(관리자) 키가 된다', () => {
  // 옛 화면은 role 을 안 보내고, 이 서버의 기본값은 admin 이다.
  // 그 화면으로 수강생 키를 주시면 그 수강생이 관리자가 된다.
  const srv = makeServer(PROPS);
  const 한벌 = adminApi(srv, 'adminCreateInvite', { name: '수강생', email: 's@example.com' });
  const 일차 = adminApi(srv, 'adminList').rows.find((r) => r.type === 'primary');
  assert.strictEqual(일차.role, 'admin',
    '기본값이 바뀌었으면 이 시험을 고치고 안내도 함께 고쳐야 합니다');
  // 고치는 법: 주소에 &role=client 를 붙이면 고객용이 된다.
  const 고객 = adminApi(srv, 'adminCreateInvite',
                        { name: '수강생2', email: 's2@example.com', role: 'client' });
  const 그줄 = adminApi(srv, 'adminList').rows
    .find((r) => r.key === 고객.primaryKey);
  assert.strictEqual(그줄.role, 'client');
});

test('들어가는 곳이 메일 본문에 실린다', () => {
  // 이게 빠지면 고객은 키만 받고 **어디로 가야 하는지 모른다.**
  // 실제로 그 일이 있었다.
  const srv = makeServer(PROPS);
  const 문 = 'https://parkchihong7-gif.github.io/gongin-jungsagsa-exam/';
  adminApi(srv, 'adminCreateInvite', { name: '홍', email: 'h@example.com', baseUrl: 문 });
  assert.strictEqual(srv.mails.length, 1);
  assert.ok(srv.mails[0].body.includes(문), '메일에 들어가는 곳이 없습니다');
  assert.ok(srv.mails[0].body.includes('들어가는 곳'), '무슨 주소인지 안 적혀 있습니다');
});
