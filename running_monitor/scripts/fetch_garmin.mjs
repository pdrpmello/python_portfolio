#!/usr/bin/env node
/**
 * Puxa o historico do Garmin Connect para data/raw/.
 *
 * Por que Playwright e nao requests/fetch direto: desde marco/2026 o Garmin
 * bloqueia clientes HTTP por TLS fingerprinting (Cloudflare). A unica via que
 * funciona e disparar as chamadas de dentro de uma pagina do Chromium, herdando
 * o fingerprint de um Chrome real. Mesma tecnica do garmin-connect-mcp.
 *
 * A sessao vem de ~/.garmin-connect-mcp/session.json (cookies + csrf token) e
 * expira em poucas horas -> este script puxa TUDO de uma vez e persiste local,
 * para a analise rodar offline depois.
 *
 * Uso:  node scripts/fetch_garmin.mjs [--days=90] [--splits=15]
 */

import { createRequire } from "node:module";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const require = createRequire(import.meta.url);

const PLAYWRIGHT_PATH =
  process.env.GARMIN_PLAYWRIGHT_PATH ??
  "C:/Users/pedro/AppData/Roaming/npm/node_modules/@etweisberg/garmin-connect-mcp/node_modules/playwright";

const SESSION_FILE = join(homedir(), ".garmin-connect-mcp", "session.json");
const OUT_DIR = join(process.cwd(), "data", "raw");

const args = Object.fromEntries(
  process.argv.slice(2).map((a) => {
    const [k, v] = a.replace(/^--/, "").split("=");
    return [k, v ?? "true"];
  }),
);
const DAYS = Number(args.days ?? 90); // janela de wellness dia-a-dia
const SPLITS_N = Number(args.splits ?? 15); // parciais das N corridas mais recentes
const PAGE_SIZE = 100;
const MAX_PAGES = 20;
const THROTTLE_MS = 120;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const isoDate = (d) => d.toISOString().slice(0, 10);
const daysAgo = (n) => isoDate(new Date(Date.now() - n * 86400_000));

// ── sessao / browser ────────────────────────────────────────────────────────

const session = JSON.parse(readFileSync(SESSION_FILE, "utf-8").replace(/^\uFEFF/, ""));
const { chromium } = require(PLAYWRIGHT_PATH);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
await context.addCookies(
  session.cookies.map((c) => ({ name: c.name, value: c.value, domain: c.domain, path: "/" })),
);
const page = await context.newPage();
// Endpoint estatico so para fixar a origem em connect.garmin.com sem passar
// pelo SSO (as rotas /app/* redirecionam e levam rate-limit do Cloudflare).
await page.goto("https://connect.garmin.com/site-status/garmin-connect-status.json", {
  waitUntil: "domcontentloaded",
  timeout: 30_000,
});

const errors = [];

/** GET em /gc-api/<path> de dentro da pagina. Retorna null em qualquer falha. */
async function get(path, params) {
  let url = `/gc-api/${path}`;
  if (params) url += `?${new URLSearchParams(params).toString()}`;
  await sleep(THROTTLE_MS);
  try {
    const res = await page.evaluate(
      async ({ url, csrf }) => {
        const resp = await fetch(url, {
          headers: { "connect-csrf-token": csrf, Accept: "*/*" },
        });
        return { status: resp.status, body: await resp.text() };
      },
      { url, csrf: session.csrf_token },
    );
    if (res.status === 401) throw new Error("401 — sessao expirou, refaca o login");
    if (res.status !== 200 || !res.body) {
      errors.push({ path, status: res.status });
      return null;
    }
    return JSON.parse(res.body);
  } catch (e) {
    if (String(e.message).startsWith("401")) throw e; // sessao morta: aborta tudo
    errors.push({ path, error: String(e.message).slice(0, 200) });
    return null;
  }
}

function save(name, data) {
  const file = join(OUT_DIR, `${name}.json`);
  writeFileSync(file, JSON.stringify(data, null, 2), "utf-8");
  const n = Array.isArray(data) ? data.length : Object.keys(data ?? {}).length;
  console.log(`  ${name}.json  (${n} ${Array.isArray(data) ? "itens" : "chaves"})`);
  return file;
}

// ── coleta ─────────────────────────────────────────────────────────────────

mkdirSync(OUT_DIR, { recursive: true });
mkdirSync(join(OUT_DIR, "splits"), { recursive: true });
console.log(`Gravando em ${OUT_DIR}`);

// 1. perfil e zonas
const settings = await get("userprofile-service/userprofile/settings");
const displayName = settings?.displayName;
if (!displayName) throw new Error("nao consegui resolver displayName");
save("user_settings", settings);
save("hr_zones", await get("biometric-service/heartRateZones/"));
save("vo2max", await get(`metrics-service/metrics/maxmet/latest/${isoDate(new Date())}`));
save("personal_records", await get(`personalrecord-service/personalrecord/prs/${displayName}`));

// 2. historico completo de atividades (paginado ate esvaziar)
const activities = [];
for (let p = 0; p < MAX_PAGES; p++) {
  const batch = await get("activitylist-service/activities/search/activities", {
    limit: PAGE_SIZE,
    start: p * PAGE_SIZE,
  });
  if (!Array.isArray(batch) || batch.length === 0) break;
  activities.push(...batch);
  console.log(`  ...pagina ${p + 1}: +${batch.length} (total ${activities.length})`);
  if (batch.length < PAGE_SIZE) break;
}
save("activities", activities);

const oldest = activities.at(-1)?.startTimeLocal?.slice(0, 10);
const newest = activities[0]?.startTimeLocal?.slice(0, 10);

// 3. series agregadas (endpoints de range: 1 request cada)
const rangeStart = oldest ?? daysAgo(365);
const rangeEnd = isoDate(new Date());
save("sleep_stats", await get(`sleep-service/stats/sleep/daily/${daysAgo(DAYS)}/${rangeEnd}`));
save("weight", await get(`weight-service/weight/range/${daysAgo(DAYS)}/${rangeEnd}`));
for (const metric of ["distance", "duration"]) {
  save(
    `fitness_stats_weekly_${metric}`,
    await get("fitnessstats-service/activity", {
      aggregation: "weekly",
      startDate: rangeStart,
      endDate: rangeEnd,
      groupByActivityType: "true",
      standardizedUnits: "true",
      groupByParentActivityType: "false",
      userFirstDay: "sunday",
      metric,
    }),
  );
}

// 4. wellness dia-a-dia na janela recente (resumo diario + HRV)
const dailySummary = {};
const hrv = {};
for (let i = 0; i < DAYS; i++) {
  const d = daysAgo(i);
  const [sum, h] = [
    await get(`usersummary-service/usersummary/daily/${displayName}`, { calendarDate: d }),
    await get(`hrv-service/hrv/${d}`),
  ];
  if (sum) dailySummary[d] = sum;
  if (h) hrv[d] = h;
  if (i % 15 === 14) console.log(`  ...wellness ${i + 1}/${DAYS} dias`);
}
save("daily_summary", dailySummary);
save("hrv", hrv);

// prontidao de treino so faz sentido nos ultimos dias
const readiness = {};
for (let i = 0; i < Math.min(DAYS, 14); i++) {
  const d = daysAgo(i);
  const r = await get(`metrics-service/metrics/trainingreadiness/${d}`);
  if (r) readiness[d] = r;
}
save("readiness", readiness);

// 5. parciais das corridas mais recentes (deriva de FC e disciplina de pace)
const runs = activities.filter((a) => String(a.activityType?.typeKey ?? "").includes("running"));
let splitsOk = 0;
for (const a of runs.slice(0, SPLITS_N)) {
  const s = await get(`activity-service/activity/${a.activityId}/splits`);
  if (!s) continue;
  writeFileSync(
    join(OUT_DIR, "splits", `${a.activityId}.json`),
    JSON.stringify(s, null, 2),
    "utf-8",
  );
  splitsOk++;
}
console.log(`  splits/  (${splitsOk} corridas)`);

// 6. metadados da coleta
save("meta", {
  fetchedAt: new Date().toISOString(),
  displayName,
  activities: activities.length,
  runs: runs.length,
  oldestActivity: oldest,
  newestActivity: newest,
  wellnessDays: DAYS,
  splitsFetched: splitsOk,
  errors,
});

await browser.close();
console.log(
  `\nOK — ${activities.length} atividades (${runs.length} corridas) de ${oldest} a ${newest}` +
    (errors.length ? `; ${errors.length} endpoints falharam (ver meta.json)` : ""),
);
