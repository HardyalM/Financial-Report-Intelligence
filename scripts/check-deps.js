#!/usr/bin/env node
// M7.1 gate: no charting library in web/package.json (docs/UI.md section 11, ARCHITECTURE).
// Two periods are compared as numbers inside each ratio card; a chart would invite trend reading
// that two data points cannot support. Run from the repository root: node scripts/check-deps.js
"use strict";
const fs = require("node:fs");
const path = require("node:path");

const BANNED = [
  /^recharts$/, /^chart\.js$/, /^react-chartjs/, /^d3(-|$)/, /^@visx\//, /^victory/, /^nivo$/,
  /^@nivo\//, /^echarts/, /^highcharts/, /^apexcharts$/, /^react-apexcharts$/, /^plotly/,
  /^react-plotly/, /^@tremor\//, /^chartist/, /^vega/, /^@observablehq\/plot$/, /^billboard\.js$/,
  /^c3$/, /^lightweight-charts$/, /^@mui\/x-charts$/, /^@antv\//, /^uplot/, /^frappe-charts$/,
];

const file = path.resolve(__dirname, "..", "web", "package.json");
const pkg = JSON.parse(fs.readFileSync(file, "utf8"));
const names = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies, ...pkg.peerDependencies,
  ...pkg.optionalDependencies });
const found = names.filter((n) => BANNED.some((re) => re.test(n)));
if (found.length) {
  console.error(`charting libraries are not allowed in v1: ${found.join(", ")}`);
  process.exit(1);
}
console.log(`check-deps: ${names.length} dependencies, no charting library`);
