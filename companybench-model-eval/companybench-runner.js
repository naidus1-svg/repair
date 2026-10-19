/*
 * CompanyBench model runner for Data OS.
 *
 * Runs the same 40 CompanyBench tasks, 3 runs per task, on one model with the same settings used for
 * Gemini 4 Argon, Claude Fable 5.1, GPT 6.1 Sol and GPT 6 Astra, then exports the results as a CSV.
 *
 * HOW TO USE (see README.md for the full steps):
 *   1. Sign in at https://data-os.turing.com
 *   2. Open DevTools (F12) -> Console, paste this whole file, press Enter.
 *   3. Call the functions on the CB object, for example:  await CB.preflight(65)
 *
 * Every function is safe to run twice: launching only tops up the runs that are missing.
 * The access token is read from the page on every request, so it never expires mid-run.
 * Nothing here deletes or cancels anything.
 *
 * Also runs under Node 18+ for testing: set DATAOS_TOKEN to a current access token.
 */
var CB = (() => {
  const CFG = {
    api: 'https://api.data-os.turing.com',
    agent: 3,                 // Terminus 2
    effort: 'high',           // every model in the comparison ran at high
    internet: true,
    webSearch: false,
    runsPerTask: 3,           // counted runs per task and model
    gapMs: 450,               // pause between calls; the API rate-limits bursts
    stallText: 'sent nothing for',        // provider stall, retried and not counted
    timeoutText: 'AgentTimeoutError',     // ran out of the per-run time limit, counted as a run
  };
  const TASKS = [{"alias": "T01", "task": 252614, "long": 243708}, {"alias": "T02", "task": 252615, "long": 243709}, {"alias": "T03", "task": 252616, "long": 243710}, {"alias": "T04", "task": 252618, "long": 243712}, {"alias": "T05", "task": 252619, "long": 243713}, {"alias": "T06", "task": 252622, "long": 243716}, {"alias": "T07", "task": 252623, "long": 243717}, {"alias": "T08", "task": 252624, "long": 243718}, {"alias": "T09", "task": 252626, "long": 243720}, {"alias": "T10", "task": 252629, "long": 243723}, {"alias": "T11", "task": 252631, "long": 243726}, {"alias": "T12", "task": 252632, "long": 243727}, {"alias": "T13", "task": 252594, "long": 243729}, {"alias": "T14", "task": 252595, "long": 243730}, {"alias": "T15", "task": 252596, "long": 243731}, {"alias": "T16", "task": 252597, "long": 243732}, {"alias": "T17", "task": 252598, "long": 243733}, {"alias": "T18", "task": 252599, "long": 243734}, {"alias": "T19", "task": 252600, "long": 243735}, {"alias": "T20", "task": 252601, "long": 243736}, {"alias": "T21", "task": 252602, "long": 243737}, {"alias": "T22", "task": 252603, "long": 243738}, {"alias": "T23", "task": 252604, "long": 243739}, {"alias": "T24", "task": 252605, "long": 243740}, {"alias": "T25", "task": 252606, "long": 243741}, {"alias": "T26", "task": 252607, "long": 243742}, {"alias": "T27", "task": 252608, "long": 243743}, {"alias": "T28", "task": 252609, "long": 243744}, {"alias": "T29", "task": 252610, "long": 243745}, {"alias": "T30", "task": 252611, "long": 243748}, {"alias": "T31", "task": 252612, "long": 243749}, {"alias": "T32", "task": 252613, "long": 243706}, {"alias": "T33", "task": 252617, "long": 243711}, {"alias": "T34", "task": 252620, "long": 243714}, {"alias": "T35", "task": 252621, "long": 243715}, {"alias": "T36", "task": 252625, "long": 243719}, {"alias": "T37", "task": 252627, "long": 243721}, {"alias": "T38", "task": 252628, "long": 243722}, {"alias": "T39", "task": 252630, "long": 243725}, {"alias": "T40", "task": 252593, "long": 243728}];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const isNode = typeof window === 'undefined';
  const token = () => (isNode ? process.env.DATAOS_TOKEN : sessionStorage.getItem('data-os.access-token'));

  async function call(method, path, body) {
    for (let i = 0; i < 6; i++) {
      const t = token();
      if (!t) throw new Error('No access token. Sign in at https://data-os.turing.com in this tab first.');
      const res = await fetch(CFG.api + path, {
        method,
        headers: { Authorization: 'Bearer ' + t, Accept: 'application/json', 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      await sleep(CFG.gapMs);
      if (res.status === 429 || res.status === 502 || res.status === 503) { await sleep(4000 * (i + 1)); continue; }
      if (res.status === 401) { await sleep(3000); continue; }          // token rotating, read it again
      const text = await res.text();
      let data; try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
      if (!res.ok) throw new Error(method + ' ' + path + ' -> HTTP ' + res.status + ' ' + String(text).slice(0, 300));
      return data;
    }
    throw new Error(method + ' ' + path + ' kept failing (rate limit or sign-in expired)');
  }

  const idOf = (x) => (x && typeof x === 'object' ? x.id : x);

  // All evaluations of one model on one task, oldest first, with the run summary attached.
  async function evals(modelId, taskId) {
    const out = [];
    let path = '/api/evaluations/?task=' + taskId + '&page_size=100';
    while (path) {
      const d = await call('GET', path);
      for (const e of d.results || []) {
        if (idOf(e.model) !== Number(modelId) || idOf(e.agent) !== CFG.agent) continue;
        const s = e.latest_run_summary || {};
        if (s.status === 'CANCELED' || s.status === 'CANCELLED') continue;
        out.push({ eval_id: e.id, run_id: s.id || null, status: s.status || 'PENDING', reward: s.aggregate_reward,
          exc: s.exception_info || '', steps: s.total_steps, tools: s.total_tool_calls,
          tok: s.model_token_usage || {} });
      }
      path = d.next ? d.next.replace(CFG.api, '') : null;
    }
    return out.sort((a, b) => a.eval_id - b.eval_id);
  }

  // One run is "counted" when it ended with a score or ran out of time. Provider stalls and other
  // exceptions are not counted and get replaced. Runs still going count as "in flight".
  function classify(r) {
    // A run that ran out of the per-run time limit ends FAILED (or EXCEPTION) with an AgentTimeoutError note.
    if (r.exc.includes(CFG.timeoutText)) return 'timeout';
    const done = r.status === 'PASSED' || r.status === 'FAILED';
    if (done && r.reward !== null && r.reward !== undefined) return 'counted';
    if (r.status === 'EXCEPTION' || r.status === 'ERROR') return r.exc.includes(CFG.stallText) ? 'stall' : 'error';
    return 'inflight';
  }

  async function preflight(modelId) {
    const d = await call('GET', '/api/llm-engine/models/?page_size=200');
    const m = (d.results || d).find((x) => x.id === Number(modelId));
    if (!m) throw new Error('Model ' + modelId + ' is not in the Data OS model list.');
    const ok = m.is_active && (m.supported_reasoning_efforts || []).includes(CFG.effort) && m.backend === 'litellm';
    if (m.backend !== 'litellm') console.log('WARNING: backend is "' + m.backend + '". Runs on a non-litellm backend failed at start with Terminus 2 ("Invalid kwargs for agent terminus-2", evaluation 964336, Inkling id 74). Use the litellm version of the model.');
    console.log(`${m.display_name} (id ${m.id}, ${m.provider}) active=${m.is_active} context=${m.context_length} efforts=${(m.supported_reasoning_efforts || []).join('/')}`);
    console.log(ok ? 'OK: active and supports effort "' + CFG.effort + '".' : 'STOP: model is inactive or does not support effort "' + CFG.effort + '". Ask Khiem.');
    const ag = await call('GET', '/api/llm-engine/agents/');
    const a = (ag.results || ag).find((x) => x.id === CFG.agent);
    console.log('Agent ' + CFG.agent + ': ' + (a ? a.display_name + ' active=' + a.is_active : 'NOT FOUND'));
    return { model: m, ok };
  }

  // view 'main' = the 80 minute tasks, 'long' = the 5 hour copies.
  async function state(modelId, view) {
    const rows = [];
    for (const t of TASKS) {
      const taskId = view === 'long' ? t.long : t.task;
      const list = (await evals(modelId, taskId)).map((r) => ({ ...r, cls: classify(r), alias: t.alias, task_id: taskId }));
      rows.push({ alias: t.alias, task_id: taskId, list });
    }
    return rows;
  }

  // Top up to the target number of runs per task. Counted, timed-out and in-flight runs all count toward the target.
  async function launch(modelId, opts = {}) {
    const view = opts.view || 'main';
    const dry = !!opts.dry;
    const rows = await state(modelId, view);
    let want = 0, made = 0;
    for (const row of rows) {
      let target = CFG.runsPerTask;
      if (view === 'long') {
        // one 5 hour rerun for every run that timed out at the 80 minute limit
        const main = (await evals(modelId, TASKS.find((t) => t.alias === row.alias).task)).map((r) => classify(r));
        const counted = main.filter((c) => c === 'counted' || c === 'timeout').slice(0, CFG.runsPerTask);
        target = counted.filter((c) => c === 'timeout').length;
      }
      const have = row.list.filter((r) => ['counted', 'timeout', 'inflight'].includes(r.cls)).length;
      const missing = Math.max(0, target - have);
      want += missing;
      for (let i = 0; i < missing; i++) {
        const body = { task: row.task_id, agent: CFG.agent, model: Number(modelId), trained_model: null,
          internet_access: CFG.internet, web_search: CFG.webSearch, reasoning_effort: CFG.effort };
        if (dry) { console.log('DRY RUN would launch', JSON.stringify(body)); continue; }
        const e = await call('POST', '/api/evaluations/', body);
        made++;
        console.log(`launched ${row.alias} -> evaluation ${e.id}`);
      }
    }
    console.log(dry ? `DRY RUN: ${want} runs would be launched.` : `Done. Launched ${made} runs.`);
    return { want, made };
  }

  async function status(modelId, view) {
    view = view || 'main';
    const rows = await state(modelId, view);
    const tot = { counted: 0, timeout: 0, inflight: 0, stall: 0, error: 0 };
    const lines = rows.map((r) => {
      const c = { counted: 0, timeout: 0, inflight: 0, stall: 0, error: 0 };
      r.list.forEach((x) => { c[x.cls]++; tot[x.cls]++; });
      return { task: r.alias, counted: c.counted, timed_out: c.timeout, in_flight: c.inflight, stalled: c.stall, errored: c.error };
    });
    console.table(lines);
    console.log(`Totals (${view}): counted ${tot.counted}, timed out ${tot.timeout}, in flight ${tot.inflight}, stalled ${tot.stall}, other errors ${tot.error}.`);
    if (view === 'main') console.log(`Finished when every task has ${CFG.runsPerTask} counted or timed out and nothing is in flight. Stalled and errored runs are replaced by CB.launch(modelId).`);
    return tot;
  }

  const minutes = (a, b) => (a && b ? Math.round(((new Date(b) - new Date(a)) / 60000) * 10) / 10 : '');

  async function exportCsv(modelId, view) {
    view = view || 'main';
    const rows = await state(modelId, view);
    const out = [['model_id', 'view', 'alias', 'task_id', 'slot', 'eval_id', 'run_id', 'status', 'reward', 'timed_out',
      'minutes', 'agent_minutes', 'steps', 'tool_calls', 'input_tokens', 'cache_tokens', 'output_tokens', 'cost_usd', 'exception']];
    let missing = 0;
    for (const r of rows) {
      const counted = r.list.filter((x) => x.cls === 'counted' || x.cls === 'timeout').slice(0, CFG.runsPerTask);
      if (view === 'main' && counted.length < CFG.runsPerTask) missing += CFG.runsPerTask - counted.length;
      let slot = 0;
      for (const x of counted) {
        slot++;
        let mins = '', amins = '';
        if (x.run_id) {
          const run = await call('GET', '/api/evaluations/runs/' + x.run_id + '/');
          const p = run.execution_profile || {};
          mins = minutes(p.started_at, p.finished_at);
          amins = minutes((p.agent_execution || {}).started_at, (p.agent_execution || {}).finished_at);
        }
        const u = x.tok || {};
        out.push([modelId, view, x.alias, x.task_id, slot, x.eval_id, x.run_id, x.status,
          (x.reward === null || x.reward === undefined) ? 0 : x.reward, x.cls === 'timeout' ? 1 : 0, mins, amins, x.steps, x.tools,
          u.input_tokens, u.cache_tokens, u.output_tokens, u.cost_usd, (x.exc || '').slice(0, 120).replace(/[\r\n,]/g, ' ')]);
      }
    }
    const csv = out.map((r) => r.map((v) => (v === undefined || v === null ? '' : String(v))).join(',')).join('\n');
    if (missing) console.warn(`Export is incomplete: ${missing} counted runs are still missing. Run CB.status(${modelId}) first.`);
    if (!isNode) {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
      a.download = `companybench_model${modelId}_${view}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      console.log('Downloaded ' + a.download + ' (' + (out.length - 1) + ' runs).');
    }
    return csv;
  }

  return { CFG, TASKS, preflight, launch, status, exportCsv, state, evals, classify };
})();
if (typeof window !== 'undefined') window.CB = CB;
