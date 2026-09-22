/**
 * 나눠 붙이는 판 — 모아 놓으면 한 장짜리 판과 **똑같이 돈다**.
 *
 * 왜 이 시험이 있나
 *   한 장짜리 판(61KB)이 붙여넣기에서 잘리는 일이 있었다. 어디서 잘리는지는
 *   붙이는 사람 쪽 사정이라 여기서 알 길이 없어, 작게 잘라 여러 장으로 낸다.
 *
 *   나누는 순간 새로 생기는 위험이 있다. 함수 한가운데서 잘리면 그 장만으로는
 *   문법이 깨지고, 화면 글을 `A1 + A2` 로 이어 붙이다 차례가 틀리면 화면에
 *   `undefined` 가 찍힌다. 그래서 **실제로 모아서 돌려 본다.**
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { makeServer, BUNDLE_PATH } = require('./harness');

const PARTS_DIR = path.join(__dirname, '..', '나눠붙이기');
const 한계 = 13000;   // 만드는 쪽 한계 12,000 + 머리말 어림

function 장들() {
  return fs.readdirSync(PARTS_DIR)
    .filter((f) => f.endsWith('.gs'))
    .sort((a, b) => parseInt(a, 10) - parseInt(b, 10))
    .map((f) => path.join(PARTS_DIR, f));
}

/** 앱스 스크립트가 여러 `.gs` 를 한 덩어리로 읽는 것과 같게 모은다. */
function 모은것() {
  return 장들().map((p) => fs.readFileSync(p, 'utf8')).join('\n');
}

test('장이 있고, 차례대로 번호가 붙어 있다', () => {
  const 목록 = 장들();
  assert.ok(목록.length >= 2, '나눈 판이 없습니다');
  목록.forEach((p, i) => {
    assert.equal(path.basename(p), `${i + 1}.gs`, '번호가 건너뜁니다');
  });
});

test('한 장도 한계를 넘지 않는다', () => {
  for (const p of 장들()) {
    const 크기 = fs.statSync(p).size;
    assert.ok(크기 <= 한계, `${path.basename(p)} 가 ${크기}바이트입니다`);
  }
});

test('장마다 끝 표가 있다 — 잘렸는지 눈으로 알 수 있게', () => {
  const 목록 = 장들();
  목록.forEach((p, i) => {
    const 글 = fs.readFileSync(p, 'utf8');
    assert.match(글, new RegExp(`⛳ ${i + 1}/${목록.length} 끝`),
                 `${path.basename(p)} 에 끝 표가 없습니다`);
  });
});

test('모아 놓으면 **실제로 돈다**', () => {
  const 임시 = path.join(os.tmpdir(), `parts-${process.pid}.gs`);
  fs.writeFileSync(임시, 모은것(), 'utf8');
  try {
    const s = makeServer({}, 임시);
    const 답 = s.call({ action: 'ping' });
    assert.equal(답.ok, true, 'ping 이 안 돕니다');
  } finally { fs.unlinkSync(임시); }
});

test('화면 글이 **온전히** 이어 붙는다', () => {
  const 임시 = path.join(os.tmpdir(), `parts-html-${process.pid}.gs`);
  fs.writeFileSync(임시, 모은것(), 'utf8');
  try {
    const s = makeServer({}, 임시);
    const 화면 = s.sandbox.adminHtml();
    assert.ok(화면.startsWith('<!DOCTYPE html>'), '화면 머리가 없습니다');
    assert.ok(화면.trimEnd().endsWith('</html>'), '화면 꼬리가 잘렸습니다');
    assert.ok(!화면.includes('undefined'),
              '조각 차례가 틀려 undefined 가 섞였습니다');

    // 한 장짜리 판과 **같은 글**이어야 한다. 한쪽만 고쳐지는 일이 없게.
    const 하나 = makeServer({}, BUNDLE_PATH);
    assert.equal(화면, 하나.sandbox.adminHtml());
  } finally { fs.unlinkSync(임시); }
});

test('한 장짜리 판과 코드가 같다', () => {
  // 머리말·끝표만 걷어내면 남는 것이 같아야 한다.
  const 씻기 = (글) => 글
    .replace(/^\/\/[^\n]*\n/gm, '')
    .replace(/\s+/g, ' ')
    .trim();
  assert.equal(씻기(모은것()), 씻기(fs.readFileSync(BUNDLE_PATH, 'utf8')));
});
