/**
 * 앱스 스크립트 흉내 장치.
 *
 * 왜 이렇게 하나
 *   keyserver.gs 는 구글 서버에서만 돈다. 여기서 못 돌리니 시험을 못 한다고
 *   하면, 사장님이 올린 뒤에야 잘못을 아신다. 그래서 구글이 주는 것들
 *   (SpreadsheetApp·MailApp·LockService·Utilities·CacheService) 을 흉내 내고
 *   **올릴 파일 그대로**를 읽어 돌린다.
 *
 *   다시 만든 사본을 시험하면 사본만 옳아진다. 반드시 올라갈 파일 자체여야
 *   한다. 그래서 여기서는 .gs 를 문자열로 읽어 vm 에 넣는다.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');

const GS_PATH = path.join(__dirname, '..', 'keyserver.gs');

/** 아주 작은 구글 시트 흉내. 값은 전부 문자열로 둔다. */
class FakeSheet {
  constructor(name) { this.name = name; this.values = []; }
  appendRow(row) { this.values.push(row.map((v) => (v == null ? '' : String(v)))); }
  getLastRow() { return this.values.length; }
  getDataRange() {
    const values = this.values.map((r) => r.slice());
    return { getValues: () => values };
  }
  clear() { this.values = []; }
  getRange(row, col, numRows, numCols) {
    const sheet = this;
    return {
      setValues(block) {
        for (let i = 0; i < numRows; i++) {
          const at = row - 1 + i;
          while (sheet.values.length <= at) { sheet.values.push([]); }
          const line = sheet.values[at];
          for (let j = 0; j < numCols; j++) {
            line[col - 1 + j] = block[i][j] == null ? '' : String(block[i][j]);
          }
        }
      },
    };
  }
}

class FakeBook {
  constructor(id = 'sheet-1', title = '장부') {
    this.sheets = new Map();
    this.id = id;
    this.title = title;
  }
  getId() { return this.id; }
  getUrl() { return `https://docs.google.com/spreadsheets/d/${this.id}/edit`; }
  getName() { return this.title; }
  getSheetByName(name) { return this.sheets.get(name) || null; }
  insertSheet(name) {
    const sheet = new FakeSheet(name);
    this.sheets.set(name, sheet);
    return sheet;
  }
}

function pad(n, width) { return String(n).padStart(width, '0'); }

/** `Utilities.formatDate` 중 이 파일이 쓰는 모양만 흉내 낸다. */
function formatDate(date, tz, pattern) {
  // 서울 시각으로 옮긴다. 시험은 고정 시각을 쓰므로 이걸로 충분하다.
  const seoul = new Date(date.getTime() + 9 * 3600 * 1000);
  const y = seoul.getUTCFullYear();
  const mo = pad(seoul.getUTCMonth() + 1, 2);
  const d = pad(seoul.getUTCDate(), 2);
  const h = pad(seoul.getUTCHours(), 2);
  const mi = pad(seoul.getUTCMinutes(), 2);
  const s = pad(seoul.getUTCSeconds(), 2);
  return pattern
    .replace("yyyy-MM-dd'T'HH:mm:ss", `${y}-${mo}-${d}T${h}:${mi}:${s}`)
    .replace('yyyy-MM-dd', `${y}-${mo}-${d}`);
}

/**
 * 장치 하나를 새로 차린다.
 *
 * @param {object} props 스크립트 속성 (ADMIN_PASSWORD 등)
 * @returns 서버를 부르는 도구들
 */
function makeServer(props = {}, gsPath = GS_PATH) {
  // 시트를 스스로 만드는지 보려고, 처음에는 **아무것도 없는** 상태로 둔다.
  const books = new Map();
  const made = [];
  const cache = new Map();
  let bookSeq = 0;
  const 붙은시트 = props.__ATTACHED_SHEET__ ? new FakeBook('sheet-붙음') : null;
  if (붙은시트) { books.set(붙은시트.getId(), 붙은시트); }
  const mails = [];
  const logged = [];
  let lockHeld = 0;
  let uuidSeq = 0;
  let slept = 0;

  const sandbox = {
    console,
    Math,
    Date,
    JSON,
    Object,
    Number,
    String,
    Array,
    Error,
    RegExp,
    isNaN,

    SpreadsheetApp: {
      // 따로 만든 프로젝트에는 '붙어 있는 시트' 가 없다. 그 경우가 기본이다.
      getActiveSpreadsheet: () => 붙은시트,
      openById: (id) => {
        const found = books.get(id);
        if (!found) { throw new Error(`그런 시트가 없습니다: ${id}`); }
        return found;
      },
      create: (title) => {
        const fresh = new FakeBook(`sheet-새로-${++bookSeq}`, title);
        books.set(fresh.getId(), fresh);
        made.push(fresh);
        return fresh;
      },
    },
    PropertiesService: {
      getScriptProperties: () => ({
        getProperty: (k) => (k in props ? props[k] : null),
        setProperty: (k, v) => { props[k] = String(v); },
      }),
    },
    HtmlService: {
      createHtmlOutput: (html) => ({
        html,
        setTitle() { return this; },
        addMetaTag() { return this; },
        getContent: () => html,
      }),
    },
    Logger: { log: (text) => { logged.push(String(text)); } },
    LockService: {
      getScriptLock: () => ({
        waitLock() {
          // 실제로는 기다렸다 잡는다. 여기서는 겹쳐 잡히면 시험이 알아채야 한다.
          if (lockHeld > 0) { throw new Error('자물쇠가 겹쳤습니다'); }
          lockHeld++;
        },
        releaseLock() { lockHeld--; },
      }),
    },
    CacheService: {
      getScriptCache: () => ({
        get: (k) => (cache.has(k) ? cache.get(k) : null),
        put: (k, v) => { cache.set(k, String(v)); },
      }),
    },
    Utilities: {
      // 진짜 앱스 스크립트는 36글자 UUID 를 준다. 짧은 가짜를 주면
      // 길이에 기대는 잘못을 시험이 못 잡는다.
      getUuid: () => { uuidSeq++; return crypto.randomUUID(); },
      formatDate,
      sleep: (ms) => { slept += ms; },
      computeHmacSha256Signature: (text, secret) => {
        const buf = crypto.createHmac('sha256', String(secret)).update(String(text)).digest();
        // 앱스 스크립트는 부호 있는 바이트 배열을 준다. 그 모양까지 맞춘다.
        return Array.from(buf).map((b) => (b > 127 ? b - 256 : b));
      },
    },
    MailApp: {
      sendEmail: (to, subject, body, options) => {
        if (props.__MAIL_FAILS__) { throw new Error('메일 한도를 넘었습니다'); }
        mails.push({ to, subject, body, options });
      },
      // 하루 한도. 실제로는 개인 100통 / 워크스페이스 1,500통.
      // `__QUOTA__` 를 0 으로 두면 «오늘 다 썼다» 를 흉내 낼 수 있다.
      getRemainingDailyQuota: () =>
        (props.__QUOTA__ === undefined ? 100 : Number(props.__QUOTA__)),
    },
    ContentService: {
      MimeType: { JSON: 'application/json' },
      createTextOutput: (text) => ({
        setMimeType() { return this; },
        getContent: () => text,
        text,
      }),
    },
  };
  sandbox.globalThis = sandbox;

  const code = fs.readFileSync(gsPath, 'utf8');
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: 'keyserver.gs' });

  /** 서버를 한 번 부른다. GET 처럼 인자를 보낸다. */
  function call(params) {
    const out = sandbox.handle({ parameter: Object.assign({}, params) });
    return JSON.parse(out.text);
  }

  /** POST 로도 같은 값이 나오는지 볼 때 쓴다. */
  function post(params) {
    const out = sandbox.handle({ postData: { contents: JSON.stringify(params) } });
    return JSON.parse(out.text);
  }

  /** 서버가 지금 쓰고 있는 장부. 없으면 아직 안 만든 것이다. */
  function book() {
    const id = props.SHEET_ID;
    return (id && books.get(id)) || 붙은시트 || null;
  }

  return {
    call, post, mails, logged, cache, sandbox, props,
    book,
    madeSheets: () => made.slice(),
    lockLeaked: () => lockHeld !== 0,
    sheet: (name) => {
      const b = book();
      return b ? b.getSheetByName(name) : null;
    },
  };
}

module.exports = { makeServer, FakeSheet, FakeBook, GS_PATH,
                   BUNDLE_PATH: path.join(__dirname, '..', 'keyserver.bundle.gs') };
