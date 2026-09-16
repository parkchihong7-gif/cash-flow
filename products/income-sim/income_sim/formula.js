// 계산식 해석기 — 파이썬의 income_sim/expr.py 와 같은 규칙을 따른다.
//
// 모델의 매출·비용 식은 models/*.yaml 에 글자로 한 번만 적혀 있고,
// 터미널(파이썬)과 이 화면(자바스크립트)이 그 같은 글자를 각자 계산한다.
// 식을 두 군데 적으면 언젠가 어긋나고, 그때 어느 숫자가 맞는지 알 수 없게 된다.
//
// eval() 이나 new Function() 을 쓰지 않고 직접 해석한다.
// 브라우저 보안 정책이 그 둘을 막는 곳에서도 돌아가야 하기 때문이다.
//
// 파이썬과 맞춰 둔 것
//   - 0 으로 나누면 오류가 아니라 0
//   - 결과가 무한대·NaN 이면 0
//   - ** 는 오른쪽 우선, 단항 마이너스보다 먼저 (파이썬과 같이 -2**2 === -4)

(function (global) {
  "use strict";

  function tokenize(source) {
    var tokens = [];
    var i = 0;
    while (i < source.length) {
      var ch = source[i];
      if (ch === " " || ch === "\t" || ch === "\n") { i += 1; continue; }
      if (source.startsWith("**", i)) { tokens.push({ t: "op", v: "**" }); i += 2; continue; }
      if ("+-*/(),".indexOf(ch) !== -1) { tokens.push({ t: "op", v: ch }); i += 1; continue; }
      var number = /^\d+(\.\d+)?([eE][+-]?\d+)?/.exec(source.slice(i));
      if (number) {
        tokens.push({ t: "num", v: parseFloat(number[0]) });
        i += number[0].length;
        continue;
      }
      var name = /^[A-Za-z_][A-Za-z0-9_]*/.exec(source.slice(i));
      if (name) { tokens.push({ t: "name", v: name[0] }); i += name[0].length; continue; }
      throw new Error("읽을 수 없는 글자입니다: " + ch + " (식: " + source + ")");
    }
    return tokens;
  }

  function parse(source) {
    var tokens = tokenize(source);
    var pos = 0;

    function peek() { return tokens[pos]; }
    function eat(value) {
      var token = tokens[pos];
      if (!token || token.v !== value) {
        throw new Error("'" + value + "' 가 있어야 합니다 (식: " + source + ")");
      }
      pos += 1;
      return token;
    }

    function atom() {
      var token = tokens[pos];
      if (!token) { throw new Error("식이 도중에 끝났습니다: " + source); }
      if (token.t === "num") { pos += 1; return { k: "num", v: token.v }; }
      if (token.t === "name") {
        pos += 1;
        if (peek() && peek().v === "(") {
          eat("(");
          var args = [];
          if (peek() && peek().v !== ")") {
            args.push(expr());
            while (peek() && peek().v === ",") { eat(","); args.push(expr()); }
          }
          eat(")");
          if (token.v !== "min" && token.v !== "max") {
            throw new Error("쓸 수 있는 함수는 min, max 뿐입니다: " + token.v);
          }
          return { k: "call", fn: token.v, args: args };
        }
        return { k: "name", v: token.v };
      }
      if (token.v === "(") { pos += 1; var inner = expr(); eat(")"); return inner; }
      throw new Error("쓸 수 없는 표현입니다: " + token.v + " (식: " + source + ")");
    }

    function power() {
      var left = atom();
      if (peek() && peek().v === "**") {
        pos += 1;
        return { k: "bin", op: "**", l: left, r: unary() };   // 오른쪽 우선
      }
      return left;
    }

    function unary() {
      var token = peek();
      if (token && (token.v === "-" || token.v === "+")) {
        pos += 1;
        return { k: "un", op: token.v, x: unary() };
      }
      return power();
    }

    function term() {
      var node = unary();
      while (peek() && (peek().v === "*" || peek().v === "/")) {
        var op = tokens[pos].v;
        pos += 1;
        node = { k: "bin", op: op, l: node, r: unary() };
      }
      return node;
    }

    function expr() {
      var node = term();
      while (peek() && (peek().v === "+" || peek().v === "-")) {
        var op = tokens[pos].v;
        pos += 1;
        node = { k: "bin", op: op, l: node, r: term() };
      }
      return node;
    }

    var tree = expr();
    if (pos !== tokens.length) {
      throw new Error("식 뒤에 남는 것이 있습니다: " + source);
    }
    return tree;
  }

  function walk(node, scope, source) {
    switch (node.k) {
      case "num":
        return node.v;
      case "name":
        if (!(node.v in scope)) {
          throw new Error("값을 찾지 못했습니다: " + node.v + " (식: " + source + ")");
        }
        return Number(scope[node.v]);
      case "un":
        return node.op === "-" ? -walk(node.x, scope, source) : walk(node.x, scope, source);
      case "call": {
        var args = node.args.map(function (a) { return walk(a, scope, source); });
        return node.fn === "min" ? Math.min.apply(null, args) : Math.max.apply(null, args);
      }
      case "bin": {
        var l = walk(node.l, scope, source);
        var r = walk(node.r, scope, source);
        if (node.op === "+") { return l + r; }
        if (node.op === "-") { return l - r; }
        if (node.op === "*") { return l * r; }
        if (node.op === "/") { return r === 0 ? 0 : l / r; }  // 파이썬과 맞춘다
        return Math.pow(l, r);
      }
      default:
        throw new Error("알 수 없는 마디입니다");
    }
  }

  var cache = {};

  function evaluate(source, scope) {
    if (!(source in cache)) { cache[source] = parse(source); }
    var value = walk(cache[source], scope, source);
    if (!isFinite(value)) { return 0; }       // 파이썬과 맞춘다
    return value;
  }

  // ------------------------------------------------ 12개월 계산 (engine.py 와 같은 순서)
  function simulate(model, values, months) {
    months = months || 12;
    var rows = [];
    var carried = {};
    var cumulative = -(Number(values.initial_cost) || 0);

    for (var month = 1; month <= months; month += 1) {
      var scope = Object.assign({}, values, { month: month });

      (model.state || []).forEach(function (spec) {
        if (month === 1) {
          carried[spec.key] = evaluate(spec.initial, scope);
        } else {
          var withPrev = Object.assign({}, scope, { prev: carried[spec.key] });
          carried[spec.key] = evaluate(spec.next, withPrev);
        }
        scope[spec.key] = carried[spec.key];
      });

      var revenue = evaluate(model.formulas.revenue, scope);
      var cost = evaluate(model.formulas.cost, scope);
      var hours = evaluate(model.formulas.hours, scope);
      var profit = revenue - cost;
      cumulative += profit;

      rows.push({
        month: month, revenue: revenue, cost: cost, profit: profit,
        cumulative: cumulative, hours: hours, state: Object.assign({}, carried),
      });
    }

    var sum = function (key) {
      return rows.reduce(function (acc, row) { return acc + row[key]; }, 0);
    };
    var totalHours = sum("hours");
    var totalProfit = sum("profit");
    var firstMonthly = rows.find(function (row) { return row.profit > 0; });
    var firstCumulative = rows.find(function (row) { return row.cumulative > 0; });

    return {
      rows: rows,
      total_revenue: sum("revenue"),
      total_cost: sum("cost"),
      total_profit: totalProfit,
      total_hours: totalHours,
      initial_cost: Number(values.initial_cost) || 0,
      net_after_initial: totalProfit - (Number(values.initial_cost) || 0),
      monthly_breakeven: firstMonthly ? firstMonthly.month : null,
      cumulative_breakeven: firstCumulative ? firstCumulative.month : null,
      hourly: totalHours > 0 ? totalProfit / totalHours : null,
    };
  }

  var api = { evaluate: evaluate, simulate: simulate, parse: parse };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
  global.IncomeSim = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
