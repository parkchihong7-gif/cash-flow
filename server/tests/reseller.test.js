/**
 * 산 사람(관리자키를 산 분)이 자기 고객에게 키를 파는 길.
 *
 * 왜 따로 필요한가
 *   관리자 화면은 **마스터 비밀번호 하나**로 열린다. 그것을 넘기면 산
 *   사람이 관리자키도 찍어 내고(끝없는 재판매), 남의 키도 지우고, 전체
 *   초기화까지 할 수 있다. 한 번 넘기면 되돌릴 수도 없다.
 *
 *   그래서 파는 분은 **비밀번호가 아니라 자기 키로** 들어온다.
 *   그 표로는 자기가 준 고객키만 다룰 수 있다.
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { makeServer } = require('./harness');

const PW = '주인비밀번호7';
const PROPS = { ADMIN_PASSWORD: PW, DEFAULT_PROGRAM: 'exam-drill' };

/** 주인이 관리자키 한 벌을 판다. */
function 팔기(srv, 이름) {
  return srv.call({ action: 'adminCreateInvite', token: PW, role: 'admin',
                    name: 이름, email: 이름 + '@example.com' });
}

/** 산 사람이 자기 키로 들어온다. */
function 들어오기(srv, 한벌) {
  return srv.call({ action: 'resellerLogin',
                    key1: 한벌.primaryKey, key2: 한벌.secondaryKeys['PC'] });
}

// ── 들어오기 ────────────────────────────────────────────────────────

test('산 사람은 자기 키로 들어온다', () => {
  const srv = makeServer(PROPS);
  const 학원장 = 팔기(srv, '김학원장');
  const 표 = 들어오기(srv, 학원장);
  assert.strictEqual(표.ok, true, JSON.stringify(표));
  assert.ok(표.token, '표가 안 나왔습니다');
  assert.strictEqual(표.name, '김학원장');
});

test('고객용 키로는 발급 화면이 안 열린다', () => {
  const srv = makeServer(PROPS);
  const 수강생 = srv.call({ action: 'adminCreateInvite', token: PW, role: 'client',
                            name: '이수강생', email: 'lee@example.com' });
  const 표 = 들어오기(srv, 수강생);
  assert.strictEqual(표.ok, false);
  assert.strictEqual(표.reason, 'not_admin');
});

test('1차키만으로는 못 들어온다', () => {
  const srv = makeServer(PROPS);
  const 학원장 = 팔기(srv, '김학원장');
  const 표 = srv.call({ action: 'resellerLogin', key1: 학원장.primaryKey });
  assert.strictEqual(표.ok, false);
  assert.strictEqual(표.reason, 'need_pair');
});

test('정지된 관리자키로는 못 들어온다', () => {
  const srv = makeServer(PROPS);
  const 학원장 = 팔기(srv, '김학원장');
  srv.call({ action: 'adminSuspendKey', token: PW, key: 학원장.primaryKey });
  assert.strictEqual(들어오기(srv, 학원장).reason, 'suspended');
});

// ── 할 수 있는 일 ───────────────────────────────────────────────────

test('산 사람이 자기 고객에게 키를 준다', () => {
  const srv = makeServer(PROPS);
  const 학원장 = 팔기(srv, '김학원장');
  const 표 = 들어오기(srv, 학원장).token;

  const 수강생 = srv.call({ action: 'adminCreateInvite', token: 표,
                            name: '이수강생', email: 'lee@example.com' });
  assert.strictEqual(수강생.ok, true, JSON.stringify(수강생));
  assert.ok(수강생.primaryKey);
  // 그 키로 실제로 들어가진다.
  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', key1: 수강생.primaryKey,
               key2: 수강생.secondaryKeys['PC'] }).ok, true);
});

test('산 사람은 자기가 준 것만 본다', () => {
  const srv = makeServer(PROPS);
  const A = 팔기(srv, 'A학원');
  const B = 팔기(srv, 'B학원');
  const A표 = 들어오기(srv, A).token;
  const B표 = 들어오기(srv, B).token;

  srv.call({ action: 'adminCreateInvite', token: A표, name: 'A의학생', email: 'a1@example.com' });
  srv.call({ action: 'adminCreateInvite', token: B표, name: 'B의학생', email: 'b1@example.com' });

  const A가본다 = srv.call({ action: 'adminList', token: A표 }).rows;
  assert.strictEqual(A가본다.length, 4);
  assert.ok(A가본다.every((r) => r.assignedName === 'A의학생'),
            'A 화면에 남의 고객이 보입니다');
  // 주인은 전부 본다 — 관리자 두 벌(8) + 학생 두 벌(8).
  assert.strictEqual(srv.call({ action: 'adminList', token: PW }).rows.length, 16);
});

test('산 사람이 자기 고객키를 정지·삭제한다', () => {
  const srv = makeServer(PROPS);
  const A = 팔기(srv, 'A학원');
  const A표 = 들어오기(srv, A).token;
  const 학생 = srv.call({ action: 'adminCreateInvite', token: A표,
                          name: 'A의학생', email: 'a1@example.com' });

  assert.strictEqual(
    srv.call({ action: 'adminSuspendKey', token: A표, key: 학생.primaryKey }).ok, true);
  assert.strictEqual(
    srv.call({ action: 'adminDeleteKey', token: A표, key: 학생.primaryKey }).ok, true);
  assert.strictEqual(srv.call({ action: 'adminList', token: A표 }).rows.length, 0);
});

// ── 못 하는 일 ──────────────────────────────────────────────────────

test('산 사람은 관리자키를 못 찍어 낸다 — 주소를 고쳐 보내도', () => {
  // 이게 뚫리면 한 번 판 것이 끝없이 재판매된다.
  const srv = makeServer(PROPS);
  const 학원장 = 팔기(srv, '김학원장');
  const 표 = 들어오기(srv, 학원장).token;

  const out = srv.call({ action: 'adminCreateInvite', token: 표, role: 'admin',
                         name: '다른학원', email: 'x@example.com' });
  assert.strictEqual(out.ok, true, '만들어지긴 해야 합니다');
  const 그줄 = srv.call({ action: 'adminList', token: PW }).rows
    .find((r) => r.key === out.primaryKey);
  assert.strictEqual(그줄.role, 'client', 'role=admin 으로 보냈더니 관리자가 됐습니다');
});

test('산 사람은 발급자를 남의 것으로 바꿔치기 못 한다', () => {
  const srv = makeServer(PROPS);
  const A = 팔기(srv, 'A학원');
  const B = 팔기(srv, 'B학원');
  const A표 = 들어오기(srv, A).token;

  // A 가 "B 가 준 것" 처럼 꾸며 보낸다.
  const out = srv.call({ action: 'adminCreateInvite', token: A표,
                         issuedBy: B.primaryKey,
                         name: '끼워넣기', email: 'x@example.com' });
  assert.strictEqual(out.ok, true);
  const 그줄 = srv.call({ action: 'adminList', token: PW }).rows
    .find((r) => r.key === out.primaryKey);
  assert.strictEqual(그줄.issuedBy, A.primaryKey, '발급자가 바꿔치기 됐습니다');
  assert.strictEqual(srv.call({ action: 'adminList', token: A표 }).rows.length, 4);
});

test('산 사람은 남의 키를 못 만진다', () => {
  const srv = makeServer(PROPS);
  const A = 팔기(srv, 'A학원');
  const B = 팔기(srv, 'B학원');
  const A표 = 들어오기(srv, A).token;
  const B표 = 들어오기(srv, B).token;
  const B학생 = srv.call({ action: 'adminCreateInvite', token: B표,
                           name: 'B의학생', email: 'b1@example.com' });

  for (const 짓 of ['adminSuspendKey', 'adminDeleteKey']) {
    const out = srv.call({ action: 짓, token: A표, key: B학생.primaryKey });
    assert.strictEqual(out.reason, 'not_yours', 짓);
  }
  // 주인의 키(A 자신의 관리자키)도 못 만진다 — 자기가 준 것이 아니다.
  assert.strictEqual(
    srv.call({ action: 'adminDeleteKey', token: A표, key: A.primaryKey }).reason, 'not_yours');
  // B 의 학생은 그대로 들어갈 수 있어야 한다.
  assert.strictEqual(
    srv.call({ action: 'validateKeyPair', key1: B학생.primaryKey,
               key2: B학생.secondaryKeys['PC'] }).ok, true);
});

test('산 사람은 전체 초기화를 못 한다', () => {
  // 부르면 **남이 판 키까지** 통째로 날아간다.
  const srv = makeServer(PROPS);
  const A = 팔기(srv, 'A학원');
  const A표 = 들어오기(srv, A).token;
  const out = srv.call({ action: 'adminResetAll', token: A표, confirm: '초기화' });
  assert.strictEqual(out.ok, false);
  assert.strictEqual(out.reason, 'owner_only');
  assert.strictEqual(srv.call({ action: 'adminList', token: PW }).rows.length, 4);
});

test('산 사람은 레거시 단일키를 못 만든다', () => {
  // 그 키에는 발급자가 안 붙어, 누구 것인지 가릴 수 없다.
  const srv = makeServer(PROPS);
  const A = 팔기(srv, 'A학원');
  const A표 = 들어오기(srv, A).token;
  assert.strictEqual(
    srv.call({ action: 'adminCreateKeys', token: A표, count: 5 }).reason, 'owner_only');
});

// ── 표 자체 ─────────────────────────────────────────────────────────

test('산 사람의 표를 손대면 안 먹는다', () => {
  const srv = makeServer(PROPS);
  const A = 팔기(srv, 'A학원');
  const B = 팔기(srv, 'B학원');
  const A표 = 들어오기(srv, A).token;

  // 표 안의 키만 B 것으로 바꿔 본다. 서명이 안 맞아야 한다.
  const 위조 = A표.split('.')[0].split('~')[0] + '~' + B.primaryKey
             + '.' + A표.split('.').slice(1).join('.');
  assert.strictEqual(srv.call({ action: 'adminList', token: 위조 }).ok, false);
});

test('산 사람의 표도 기한이 지나면 안 먹는다', () => {
  const srv = makeServer(PROPS);
  const A = 팔기(srv, 'A학원');
  const 과거 = String(Date.now() - 1000) + '~' + A.primaryKey;
  const 표 = 과거 + '.' + srv.sandbox.signature(과거);   // 서명은 맞다
  assert.strictEqual(srv.call({ action: 'adminList', token: 표 }).ok, false);
});

test('주인 표와 산 사람 표가 섞이지 않는다', () => {
  const srv = makeServer(PROPS);
  const A = 팔기(srv, 'A학원');
  // 주인 표에 ~키 를 붙여 산 사람인 척, 또는 그 반대로 해 본다.
  const 주인표 = srv.call({ action: 'adminLogin', password: PW }).token;
  const 섞음 = 주인표.split('.')[0] + '~' + A.primaryKey + '.' + 주인표.split('.')[1];
  assert.strictEqual(srv.call({ action: 'adminList', token: 섞음 }).ok, false);
  // 제대로 된 주인 표는 전부 본다.
  assert.strictEqual(srv.call({ action: 'adminResetAll', token: 주인표, confirm: '초기화' }).ok, true);
});

// ── 표에 프로그램이 묶여 있다 ───────────────────────────────────────
//
// 처음엔 표에 '누구인지' 만 담았다. 그랬더니 산 분이 요청에 program 을
// 바꿔 보내면 **사지도 않은 프로그램**의 키를 발급하고 목록까지 볼 수
// 있었다. 브라우저로 돌려 보다가 발급한 키가 엉뚱한 프로그램으로 들어가는
// 것을 보고 알았다.

test('산 사람은 자기가 산 프로그램에서만 발급한다', () => {
  const srv = makeServer(PROPS);
  const A = srv.call({ action: 'adminCreateInvite', token: PW, program: 'exam-drill',
                       role: 'admin', name: 'A학원', email: 'a@example.com' });
  const 표 = srv.call({ action: 'resellerLogin', program: 'exam-drill',
                        key1: A.primaryKey, key2: A.secondaryKeys['PC'] }).token;

  // 다른 프로그램으로 발급해 보려 한다.
  const out = srv.call({ action: 'adminCreateInvite', token: 표, program: 'agency-kit',
                         name: '끼워넣기', email: 'x@example.com' });
  assert.strictEqual(out.ok, true, '만들어지긴 해야 합니다');

  // 산 프로그램으로 들어갔어야 한다.
  const 남의것 = srv.call({ action: 'adminList', token: PW, program: 'agency-kit' }).rows;
  assert.strictEqual(남의것.length, 0, '사지도 않은 프로그램에 키가 생겼습니다');
  const 자기것 = srv.call({ action: 'adminList', token: PW, program: 'exam-drill' }).rows;
  assert.strictEqual(자기것.length, 8, '산 프로그램에 안 들어갔습니다');
});

test('산 사람은 다른 프로그램 목록을 못 본다', () => {
  const srv = makeServer(PROPS);
  const A = srv.call({ action: 'adminCreateInvite', token: PW, program: 'exam-drill',
                       role: 'admin', name: 'A학원', email: 'a@example.com' });
  srv.call({ action: 'adminCreateInvite', token: PW, program: 'agency-kit',
             role: 'client', name: '남의고객', email: 'z@example.com' });
  const 표 = srv.call({ action: 'resellerLogin', program: 'exam-drill',
                        key1: A.primaryKey, key2: A.secondaryKeys['PC'] }).token;

  const 본것 = srv.call({ action: 'adminList', token: 표, program: 'agency-kit' }).rows;
  assert.ok(본것.every((r) => r.program === 'exam-drill'),
            '다른 프로그램 줄이 보입니다');
  assert.ok(!본것.some((r) => r.assignedName === '남의고객'));
});

test('표에서 프로그램만 바꿔치기 못 한다', () => {
  const srv = makeServer(PROPS);
  const A = srv.call({ action: 'adminCreateInvite', token: PW, program: 'exam-drill',
                       role: 'admin', name: 'A학원', email: 'a@example.com' });
  const 표 = srv.call({ action: 'resellerLogin', program: 'exam-drill',
                        key1: A.primaryKey, key2: A.secondaryKeys['PC'] }).token;
  const 몸통 = 표.slice(0, 표.lastIndexOf('.'));
  const 위조 = 몸통.replace('~exam-drill', '~agency-kit') + 표.slice(표.lastIndexOf('.'));
  assert.strictEqual(srv.call({ action: 'adminList', token: 위조 }).ok, false);
});

test('프로그램이 빠진 옛 모양 표는 안 먹는다', () => {
  // 표 모양이 바뀌었다. 예전 두 칸짜리는 거절해야 한다.
  const srv = makeServer(PROPS);
  const 몸통 = (Date.now() + 3600000) + '~AAAA-BBBB-CCCC';
  const 표 = 몸통 + '.' + srv.sandbox.signature(몸통);
  assert.strictEqual(srv.call({ action: 'adminList', token: 표 }).ok, false);
});
