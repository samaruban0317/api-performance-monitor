"use strict";

const $ = (sel) => document.querySelector(sel);
const fmt = (v, suffix = "") => (v === null || v === undefined ? "—" : `${v}${suffix}`);

let autoTimer = null;

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function statusClass(target) {
  if (!target.samples) return "idle";
  const last = target.last_check;
  return last && last.success ? "up" : "down";
}

function renderCards(totals) {
  const cards = [
    { label: "Endpoints", value: totals.targets, sub: `${totals.active} active` },
    {
      label: "Global Avg Latency",
      value: fmt(totals.global_avg_ms),
      sub: "ms",
      raw: true,
    },
    {
      label: "Error Rate",
      value: fmt(totals.global_error_rate),
      sub: "%",
      raw: true,
    },
    { label: "Samples", value: totals.samples.toLocaleString(), sub: "in window" },
  ];
  $("#summary-cards").innerHTML = cards
    .map(
      (c) => `
      <div class="card">
        <div class="label">${c.label}</div>
        <div class="value">${c.value}${c.raw && c.value !== "—" ? ` <small>${c.sub}</small>` : ""}</div>
        ${!c.raw ? `<div class="label" style="margin-top:.3rem">${c.sub}</div>` : ""}
      </div>`
    )
    .join("");
}

function renderInsights(insights) {
  $("#insights").innerHTML = insights
    .map(
      (i) => `
      <li class="insight ${i.severity}">
        <span class="tag">${i.severity}</span>
        <span>${i.message}</span>
      </li>`
    )
    .join("");
}

function renderTargets(targets) {
  $("#targets-body").innerHTML = targets
    .map((t) => {
      const cls = statusClass(t);
      return `
      <tr data-id="${t.id}" data-name="${t.name}">
        <td><span class="dot ${cls}"></span></td>
        <td>
          <div class="endpoint-name">${t.name}</div>
          <div class="endpoint-url">${t.url}</div>
        </td>
        <td class="num">${fmt(t.avg_ms)}</td>
        <td class="num">${fmt(t.p95_ms)}</td>
        <td class="num">${fmt(t.p99_ms)}</td>
        <td class="num">${fmt(t.uptime_pct, "%")}</td>
        <td class="num">${fmt(t.errors)}</td>
        <td class="num">${fmt(t.samples)}</td>
      </tr>`;
    })
    .join("");

  document.querySelectorAll("#targets-body tr").forEach((row) => {
    row.addEventListener("click", () =>
      showDetail(row.dataset.id, row.dataset.name)
    );
  });
}

async function showDetail(id, name) {
  const data = await fetchJSON(`/api/targets/${id}`);
  $("#detail-title").textContent = `Recent latency · ${name}`;
  $("#detail-panel").classList.remove("hidden");
  drawChart(data.recent || []);
  $("#detail-panel").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function drawChart(samples) {
  const canvas = $("#latency-chart");
  const ctx = canvas.getContext("2d");
  const W = (canvas.width = canvas.clientWidth);
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const points = samples
    .filter((s) => s.response_time_ms !== null)
    .map((s) => ({ v: s.response_time_ms, ok: s.success }));
  if (!points.length) {
    ctx.fillStyle = "#8b949e";
    ctx.font = "14px sans-serif";
    ctx.fillText("No latency data yet.", 12, H / 2);
    return;
  }

  const max = Math.max(...points.map((p) => p.v)) * 1.15 || 1;
  const pad = 30;
  const stepX = (W - pad * 2) / Math.max(points.length - 1, 1);
  const y = (v) => H - pad - (v / max) * (H - pad * 2);

  // axis
  ctx.strokeStyle = "#2a313c";
  ctx.beginPath();
  ctx.moveTo(pad, H - pad);
  ctx.lineTo(W - pad, H - pad);
  ctx.stroke();

  // line
  ctx.strokeStyle = "#58a6ff";
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const px = pad + i * stepX;
    const py = y(p.v);
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  });
  ctx.stroke();

  // points (red if failed)
  points.forEach((p, i) => {
    ctx.fillStyle = p.ok ? "#3fb950" : "#f85149";
    ctx.beginPath();
    ctx.arc(pad + i * stepX, y(p.v), 2.5, 0, Math.PI * 2);
    ctx.fill();
  });

  // max label
  ctx.fillStyle = "#8b949e";
  ctx.font = "11px sans-serif";
  ctx.fillText(`${Math.round(max)} ms`, 2, pad);
}

async function load() {
  const window = $("#window").value;
  try {
    const data = await fetchJSON(`/api/overview?window=${window}`);
    renderCards(data.totals);
    renderInsights(data.insights);
    renderTargets(data.targets);
    $("#updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    $("#updated").textContent = `Error: ${err.message}`;
  }
}

$("#refresh").addEventListener("click", load);
$("#window").addEventListener("change", load);
$("#close-detail").addEventListener("click", () =>
  $("#detail-panel").classList.add("hidden")
);

load();
autoTimer = setInterval(load, 15000);
