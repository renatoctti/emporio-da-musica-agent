"use strict";
// Test runner for cards.js: reads the trace of one answer (JSON) from stdin and prints the cards
// and the follow-up questions. tests/test_cards.py runs it and checks the output.
const path = require("path");
const cards = require(path.join(__dirname, "..", "..", "src", "emporio", "web", "static", "cards.js"));

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const trace = JSON.parse(input);
  const list = cards.cardsFromTrace(trace);
  process.stdout.write(JSON.stringify({ cards: list, followUps: cards.followUps(list) }));
});
