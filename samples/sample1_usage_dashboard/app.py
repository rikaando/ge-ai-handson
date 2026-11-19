"""サブテーマ 1 参考実装: 部署・ユーザー別の生成 AI 利用量可視化ダッシュボード (Python 標準ライブラリのみ)."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import py_compile
import sys
import threading
import time
from typing import Any
import unicodedata
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent.parent / "data"
USERS_CSV = DATA_DIR / "users.csv"
LOGS_CSV = DATA_DIR / "ai_audit_logs.csv"

MODEL_ORDER = [
    "gemini-3.8-flash",
    "gemini-4-argon",
    "claude-sonnet-5-5",
    "claude-opus-5-5",
]

SURFACE_ORDER = [
    "Gemini Enterprise Chat",
    "Antigravity",
    "BigQuery Data Agent",
    "Gemini Enterprise Search",
]


def _sorted_by_order(items: set[str], preferred_order: list[str]) -> list[str]:
    order_index = {name: idx for idx, name in enumerate(preferred_order)}
    return sorted(items, key=lambda x: (order_index.get(x, 999), x))


def _pick_top_key(counter: Counter[str]) -> str:
    if not counter:
        return "-"
    return max(counter.items(), key=lambda kv: (kv[1], kv[0]))[0]


def load_users(users_path: Path = USERS_CSV) -> dict[str, dict[str, str]]:
    """users.csv を読み込み、user_id をキーとした辞書を返す."""
    users: dict[str, dict[str, str]] = {}
    with users_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            uid = row["user_id"].strip()
            users[uid] = {
                "user_id": uid,
                "user_email": row["user_email"].strip(),
                "user_name": row["user_name"].strip(),
                "department": row["department"].strip(),
                "job_role": row["job_role"].strip(),
            }
    return users


def load_joined_logs(
    users: dict[str, dict[str, str]],
    logs_path: Path = LOGS_CSV,
) -> list[dict[str, Any]]:
    """ai_audit_logs.csv を読み込み、user_id で users と結合したレコード一覧を返す."""
    joined: list[dict[str, Any]] = []
    with logs_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            uid = row["user_id"].strip()
            user = users.get(
                uid,
                {
                    "user_id": uid,
                    "user_email": "",
                    "user_name": uid,
                    "department": "未登録部署",
                    "job_role": "-",
                },
            )
            in_tok = int(row["input_tokens"])
            out_tok = int(row["output_tokens"])
            joined.append(
                {
                    "event_timestamp": row["event_timestamp"].strip(),
                    "log_id": row["log_id"].strip(),
                    "user_id": uid,
                    "user_name": user["user_name"],
                    "user_email": user["user_email"],
                    "department": user["department"],
                    "job_role": user["job_role"],
                    "tool_surface": row["tool_surface"].strip(),
                    "model_name": row["model_name"].strip(),
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "total_tokens": in_tok + out_tok,
                    "latency_ms": int(row["latency_ms"]),
                }
            )
    return joined


def load_and_aggregate(
    users_path: Path = USERS_CSV,
    logs_path: Path = LOGS_CSV,
    department_filter: str = "",
    model_filter: str = "",
) -> dict[str, Any]:
    """users.csv と ai_audit_logs.csv を結合し、部署・モデル・日別・ユーザー別の利用量を集計する."""
    users = dict(load_users(users_path))
    all_logs = load_joined_logs(users, logs_path)

    for log in all_logs:
        uid = log["user_id"]
        if uid not in users:
            users[uid] = {
                "user_id": uid,
                "user_email": "",
                "user_name": uid,
                "department": "未登録部署",
                "job_role": "-",
            }

    all_departments = sorted({u["department"] for u in users.values()})
    all_models = _sorted_by_order({log["model_name"] for log in all_logs}, MODEL_ORDER)
    all_surfaces = _sorted_by_order({log["tool_surface"] for log in all_logs}, SURFACE_ORDER)

    filtered_users = {
        uid: u
        for uid, u in users.items()
        if not department_filter or u["department"] == department_filter
    }
    filtered_logs = [
        log
        for log in all_logs
        if (not department_filter or log["department"] == department_filter)
        and (not model_filter or log["model_name"] == model_filter)
    ]

    total_requests = len(filtered_logs)
    total_input = sum(log["input_tokens"] for log in filtered_logs)
    total_output = sum(log["output_tokens"] for log in filtered_logs)
    total_tokens = total_input + total_output
    avg_latency_ms = (
        round(sum(log["latency_ms"] for log in filtered_logs) / total_requests)
        if total_requests
        else 0
    )

    dept_user_counts: Counter[str] = Counter(u["department"] for u in filtered_users.values())
    dept_logs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for log in filtered_logs:
        dept_logs[log["department"]].append(log)

    target_depts = (
        [department_filter]
        if department_filter and department_filter in dept_user_counts
        else sorted(dept_user_counts.keys())
    )

    departments: list[dict[str, Any]] = []
    for dept in target_depts:
        logs = dept_logs.get(dept, [])
        req_count = len(logs)
        in_tok = sum(item["input_tokens"] for item in logs)
        out_tok = sum(item["output_tokens"] for item in logs)
        tot_tok = in_tok + out_tok
        licensed_cnt = dept_user_counts[dept]
        active_cnt = len({item["user_id"] for item in logs})

        model_breakdown: dict[str, dict[str, int]] = {}
        for m in all_models:
            m_logs = [item for item in logs if item["model_name"] == m]
            if m_logs:
                model_breakdown[m] = {
                    "requests": len(m_logs),
                    "total_tokens": sum(item["total_tokens"] for item in m_logs),
                }

        surface_breakdown: dict[str, dict[str, int]] = {}
        for s in all_surfaces:
            s_logs = [item for item in logs if item["tool_surface"] == s]
            if s_logs:
                surface_breakdown[s] = {
                    "requests": len(s_logs),
                    "total_tokens": sum(item["total_tokens"] for item in s_logs),
                }

        departments.append(
            {
                "department": dept,
                "licensed_users": licensed_cnt,
                "active_users": active_cnt,
                "inactive_users": licensed_cnt - active_cnt,
                "requests": req_count,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": tot_tok,
                "requests_per_user": round(req_count / licensed_cnt, 1) if licensed_cnt else 0.0,
                "tokens_per_user": round(tot_tok / licensed_cnt) if licensed_cnt else 0,
                "avg_latency_ms": round(sum(item["latency_ms"] for item in logs) / req_count)
                if req_count
                else 0,
                "model_breakdown": model_breakdown,
                "surface_breakdown": surface_breakdown,
            }
        )
    departments.sort(key=lambda d: (d["total_tokens"], d["requests"], d["department"]), reverse=True)

    models: list[dict[str, Any]] = []
    for m in all_models:
        if model_filter and m != model_filter:
            continue
        m_logs = [item for item in filtered_logs if item["model_name"] == m]
        req_count = len(m_logs)
        in_tok = sum(item["input_tokens"] for item in m_logs)
        out_tok = sum(item["output_tokens"] for item in m_logs)
        tot_tok = in_tok + out_tok
        models.append(
            {
                "model_name": m,
                "requests": req_count,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": tot_tok,
                "avg_latency_ms": round(sum(item["latency_ms"] for item in m_logs) / req_count)
                if req_count
                else 0,
                "request_share_pct": round(req_count / total_requests * 100, 1)
                if total_requests
                else 0.0,
                "token_share_pct": round(tot_tok / total_tokens * 100, 1)
                if total_tokens
                else 0.0,
            }
        )
    models.sort(key=lambda m: (m["total_tokens"], m["requests"]), reverse=True)

    user_logs_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for log in filtered_logs:
        user_logs_map[log["user_id"]].append(log)

    users_list: list[dict[str, Any]] = []
    for uid, u in filtered_users.items():
        logs = user_logs_map.get(uid, [])
        req_count = len(logs)
        in_tok = sum(item["input_tokens"] for item in logs)
        out_tok = sum(item["output_tokens"] for item in logs)
        tot_tok = in_tok + out_tok
        m_counter: Counter[str] = Counter(item["model_name"] for item in logs)
        s_counter: Counter[str] = Counter(item["tool_surface"] for item in logs)
        model_breakdown = {
            m: {
                "requests": m_counter[m],
                "total_tokens": sum(
                    item["total_tokens"] for item in logs if item["model_name"] == m
                ),
            }
            for m in all_models
            if m_counter[m]
        }
        users_list.append(
            {
                "user_id": uid,
                "user_name": u["user_name"],
                "user_email": u["user_email"],
                "department": u["department"],
                "job_role": u["job_role"],
                "requests": req_count,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": tot_tok,
                "avg_latency_ms": round(sum(item["latency_ms"] for item in logs) / req_count)
                if req_count
                else 0,
                "top_model": _pick_top_key(m_counter),
                "top_surface": _pick_top_key(s_counter),
                "used_models": sorted(m_counter.keys()),
                "model_breakdown": model_breakdown,
            }
        )
    users_list.sort(key=lambda u: (-u["total_tokens"], -u["requests"], u["user_id"]))

    all_dates = sorted({log["event_timestamp"][:10] for log in all_logs if log["event_timestamp"]})
    daily_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"requests": 0, "total_tokens": 0}
    )
    for log in filtered_logs:
        day_str = log["event_timestamp"][:10]
        if day_str:
            daily_counts[day_str]["requests"] += 1
            daily_counts[day_str]["total_tokens"] += log["total_tokens"]

    daily_trends: list[dict[str, Any]] = []
    if all_dates:
        cur_day = date.fromisoformat(all_dates[0])
        end_day = date.fromisoformat(all_dates[-1])
        while cur_day <= end_day:
            ds = cur_day.isoformat()
            c = daily_counts[ds]
            daily_trends.append(
                {
                    "date": ds,
                    "requests": c["requests"],
                    "total_tokens": c["total_tokens"],
                }
            )
            cur_day += timedelta(days=1)

    active_total = sum(1 for u in users_list if u["requests"] > 0)
    licensed_total = len(users_list)
    return {
        "summary": {
            "total_requests": total_requests,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "total_tokens": total_tokens,
            "avg_latency_ms": avg_latency_ms,
            "licensed_users": licensed_total,
            "active_users": active_total,
            "inactive_users": licensed_total - active_total,
        },
        "departments": departments,
        "models": models,
        "daily_trends": daily_trends,
        "users": users_list,
        "filters": {
            "departments": all_departments,
            "models": all_models,
            "surfaces": all_surfaces,
            "selected_department": department_filter,
            "selected_model": model_filter,
        },
    }


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>生成AI利用量集計</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Google+Sans+Flex:wght@400;500&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+JP:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-white: #FFFFFF;
      --bg-band: #F8F9FC;
      --text-primary: #212226;
      --text-secondary: #4B5563;
      --border-line: #E3E7ED;
      --blue: #1A73E8;
      --track-bg: #EEF1F6;
      --series-1: #3186FF;
      --series-2: #FC413D;
      --series-3: #FEC700;
      --series-4: #00AF57;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg-white);
      color: var(--text-primary);
      font-family: 'Google Sans Flex', 'Noto Sans JP', sans-serif;
      font-size: 14px;
      line-height: 1.6;
      word-break: auto-phrase;
    }
    .mono { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
    .nowrap { white-space: nowrap; }
    .band { width: 100%; border-bottom: 1px solid var(--border-line); padding: 36px 32px; }
    .band-subtle { background: var(--bg-band); }
    .container { max-width: 1160px; margin: 0 auto; }
    .header-row { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; flex-wrap: wrap; }
    h1 { font-size: 28px; font-weight: 500; line-height: 1.3; }
    h2 { font-size: 20px; font-weight: 500; line-height: 1.4; margin-bottom: 8px; }
    .editorial-grid { display: grid; grid-template-columns: 320px 1fr; gap: 48px; align-items: start; }
    .hero-metric {
      font-size: 48px; font-weight: 500; line-height: 1.1; letter-spacing: -0.02em;
      font-variant-numeric: tabular-nums; margin: 6px 0 8px;
    }
    .hero-unit { font-size: 20px; font-weight: 500; margin-left: 4px; }
    .meta-note { font-size: 13px; color: var(--text-secondary); }
    .filter-toolbar { display: flex; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
    .filter-field { display: flex; flex-direction: column; gap: 4px; min-width: 168px; }
    .filter-field label { font-size: 13px; color: var(--text-secondary); }
    select, .btn-reset {
      font-family: inherit; font-size: 13px; color: var(--text-primary); background: var(--bg-white);
      border: 1px solid var(--border-line); border-radius: 6px; padding: 7px 12px;
    }
    .btn-reset { background: var(--track-bg); border-color: transparent; font-weight: 500; cursor: pointer; }
    .btn-reset:hover { background: #E3E7ED; }
    .segmented { display: inline-flex; flex-wrap: wrap; background: var(--track-bg); padding: 4px; border-radius: 8px; gap: 2px; }
    .segmented button {
      appearance: none; border: none; background: transparent; color: var(--text-secondary);
      font-family: inherit; font-size: 13px; font-weight: 500; padding: 6px 11px; border-radius: 6px;
      cursor: pointer; transition: background 220ms cubic-bezier(0.22, 1, 0.36, 1), color 220ms cubic-bezier(0.22, 1, 0.36, 1);
    }
    .segmented button[aria-selected="true"] {
      background: var(--bg-white); color: var(--text-primary);
      box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.03);
    }
    .segmented button:focus-visible, select:focus-visible, .btn-reset:focus-visible, .bar-row:focus-visible {
      outline: 2px solid var(--blue); outline-offset: 2px;
    }
    .legend { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 16px; font-size: 13px; color: var(--text-secondary); }
    .legend-item { display: inline-flex; align-items: center; gap: 6px; }
    .swatch {
      width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0;
      box-shadow: inset 0 0 0 1px rgba(33, 34, 38, 0.18);
    }
    .ser-1 { background-color: var(--series-1); }
    .ser-2 { background-color: var(--series-2); }
    .ser-3 { background-color: var(--series-3); }
    .ser-4 {
      background-color: var(--series-4);
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8'%3E%3Cpath d='M-2,2 l4,-4 M0,8 l8,-8 M6,10 l4,-4' stroke='%23ffffff' stroke-width='1.8' stroke-opacity='0.55'/%3E%3C/svg%3E");
    }
    .ser-other { background-color: #64748B; }
    .bar-list { display: flex; flex-direction: column; gap: 14px; }
    .bar-row {
      padding: 8px 10px 12px; border-bottom: 1px solid var(--border-line); border-radius: 6px;
      cursor: pointer; transition: background 180ms cubic-bezier(0.22, 1, 0.36, 1);
    }
    .bar-row:hover { background: rgba(26, 115, 232, 0.04); }
    .bar-row.selected { background: #E8F0FE; }
    .bar-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; gap: 12px; flex-wrap: wrap; }
    .item-title { font-size: 16px; font-weight: 500; }
    .bar-track { width: 100%; height: 12px; background: var(--track-bg); border-radius: 6px; overflow: hidden; display: flex; }
    .bar-group { height: 100%; display: flex; transition: width 280ms cubic-bezier(0.22, 1, 0.36, 1); }
    .stack-seg { height: 100%; border-right: 2px solid var(--bg-white); }
    .stack-seg:last-child { border-right: none; }
    .bar-fill { height: 100%; background: var(--blue); border-radius: 6px; transition: width 280ms cubic-bezier(0.22, 1, 0.36, 1); }
    .daily-wrap { display: grid; grid-template-columns: auto 1fr; gap: 6px 10px; align-items: stretch; margin-bottom: 28px; }
    .daily-y {
      height: 164px; padding-top: 8px; display: flex; flex-direction: column;
      justify-content: space-between; align-items: flex-end; font-size: 13px; color: var(--text-secondary);
    }
    .daily-plot { position: relative; height: 164px; padding-top: 8px; border-left: 1px solid var(--border-line); border-bottom: 1px solid var(--border-line); }
    .daily-lines { position: absolute; inset: 8px 0 0 0; pointer-events: none; display: flex; flex-direction: column; justify-content: space-between; }
    .daily-line { width: 100%; border-top: 1px dashed var(--border-line); }
    .daily-line:last-child { border-top: none; }
    .daily-bars { position: relative; z-index: 1; display: flex; align-items: flex-end; gap: 4px; height: 100%; padding: 0 4px; }
    .daily-col { flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; }
    .daily-bar { width: 100%; max-width: 20px; background: var(--blue); border-radius: 3px 3px 0 0; transition: height 260ms cubic-bezier(0.22, 1, 0.36, 1); }
    .daily-col:hover .daily-bar { background: var(--series-1); }
    .daily-x { grid-column: 2; display: flex; justify-content: space-between; font-size: 13px; color: var(--text-secondary); }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 11px 8px; border-bottom: 1px solid var(--border-line); font-size: 14px; vertical-align: top; }
    th { font-size: 13px; font-weight: 500; color: var(--text-secondary); }
    th.right, td.right { text-align: right; white-space: nowrap; }
    tbody tr.clickable { cursor: pointer; }
    tbody tr.clickable:hover { background: rgba(26, 115, 232, 0.04); }
    tbody tr.selected { background: #E8F0FE; }
    .inactive-row { color: var(--text-secondary); }
    .sub-line { display: block; font-size: 13px; color: var(--text-secondary); }
    .mini-stack { width: 116px; height: 8px; background: var(--track-bg); border-radius: 4px; overflow: hidden; display: flex; margin-bottom: 4px; }
    .empty-state { padding: 20px; text-align: center; color: var(--text-secondary); font-size: 13px; }
    footer { padding: 24px 32px; font-size: 13px; color: var(--text-secondary); }
    @media (max-width: 860px) {
      .band { padding: 24px 16px; }
      .editorial-grid { grid-template-columns: 1fr; gap: 24px; }
      .filter-field { min-width: 140px; flex: 1 1 auto; }
    }
    @media (max-width: 680px) {
      table.responsive-table thead { display: none; }
      table.responsive-table, table.responsive-table tbody, table.responsive-table tr, table.responsive-table td { display: block; width: 100%; }
      table.responsive-table tr { padding: 10px 0; border-bottom: 1px solid var(--border-line); }
      table.responsive-table td { border-bottom: none; padding: 4px 0; display: flex; justify-content: space-between; gap: 12px; text-align: right; white-space: normal; }
      table.responsive-table td::before { content: attr(data-label); font-size: 13px; font-weight: 500; color: var(--text-secondary); text-align: left; flex-shrink: 0; }
      table.responsive-table .mini-stack { margin-left: auto; }
    }
  </style>
</head>
<body>
  <header class="band">
    <div class="container header-row">
      <h1>生成AI利用量集計</h1>
      <div class="filter-toolbar" aria-label="表示条件">
        <div class="filter-field">
          <label for="dept-filter">部署</label>
          <select id="dept-filter"><option value="">すべての部署</option></select>
        </div>
        <div class="filter-field">
          <label for="model-filter">モデル</label>
          <select id="model-filter"><option value="">すべてのモデル</option></select>
        </div>
        <button type="button" class="btn-reset" id="reset-btn">リセット</button>
      </div>
    </div>
  </header>

  <section class="band band-subtle">
    <div class="container editorial-grid">
      <div>
        <h2>部署別内訳</h2>
        <div class="hero-metric" id="dept-hero">-</div>
        <p class="meta-note" id="dept-caption"></p>
        <p class="meta-note" id="dept-submeta" style="margin-top: 6px;"></p>
        <div class="segmented" role="tablist" aria-label="部署別表示指標" id="dept-tabs" style="margin-top: 16px;">
          <button type="button" role="tab" aria-selected="true" data-mode="total_tokens">合計トークン</button>
          <button type="button" role="tab" aria-selected="false" data-mode="tokens_per_user">1人あたり</button>
          <button type="button" role="tab" aria-selected="false" data-mode="surface_share">利用機能比率</button>
          <button type="button" role="tab" aria-selected="false" data-mode="avg_latency_ms">平均レイテンシ</button>
        </div>
        <div class="legend" id="dept-legend" aria-label="内訳凡例"></div>
      </div>
      <div class="bar-list" id="dept-bars"></div>
    </div>
  </section>

  <section class="band">
    <div class="container editorial-grid">
      <div>
        <h2>日別推移・モデル別内訳</h2>
        <div class="hero-metric" id="daily-hero">-</div>
        <p class="meta-note" id="daily-caption"></p>
        <div class="segmented" role="tablist" aria-label="日別推移指標" id="daily-tabs" style="margin-top: 16px;">
          <button type="button" role="tab" aria-selected="true" data-daily="requests">リクエスト数</button>
          <button type="button" role="tab" aria-selected="false" data-daily="total_tokens">合計トークン</button>
        </div>
      </div>
      <div>
        <div class="daily-wrap">
          <div class="daily-y mono" id="daily-y" aria-hidden="true"></div>
          <div class="daily-plot">
            <div class="daily-lines" aria-hidden="true">
              <div class="daily-line"></div><div class="daily-line"></div>
              <div class="daily-line"></div><div class="daily-line"></div><div class="daily-line"></div>
            </div>
            <div class="daily-bars" id="daily-bars"></div>
          </div>
          <div class="daily-x mono" id="daily-x"></div>
        </div>
        <table class="responsive-table">
          <thead>
            <tr>
              <th>モデル名</th>
              <th class="right">リクエスト数</th>
              <th class="right">合計トークン</th>
              <th class="right">トークン比率</th>
              <th class="right">平均レイテンシ</th>
            </tr>
          </thead>
          <tbody id="model-tbody"></tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="band band-subtle">
    <div class="container editorial-grid">
      <div>
        <h2>ユーザー別一覧</h2>
        <div class="hero-metric" id="user-hero">-</div>
        <p class="meta-note" id="user-caption"></p>
        <div style="margin-top: 16px;">
          <span class="meta-note" style="display:block; margin-bottom:6px;">並び順</span>
          <div class="segmented" role="tablist" aria-label="ユーザー並び順" id="user-tabs">
            <button type="button" role="tab" aria-selected="true" data-sort="total_tokens">トークン順</button>
            <button type="button" role="tab" aria-selected="false" data-sort="requests">件数順</button>
            <button type="button" role="tab" aria-selected="false" data-sort="avg_latency_ms">応答時間順</button>
          </div>
        </div>
        <div style="margin-top: 14px;">
          <label for="status-filter" class="meta-note" style="display:block; margin-bottom:6px;">利用状態</label>
          <select id="status-filter" style="width: 100%;">
            <option value="ALL">全員 (未利用を含む)</option>
            <option value="ACTIVE">利用ありのみ</option>
            <option value="INACTIVE">未利用 (0件) のみ</option>
          </select>
        </div>
      </div>
      <div>
        <table class="responsive-table">
          <thead>
            <tr>
              <th>順位</th>
              <th>氏名</th>
              <th>部署・職種</th>
              <th>モデル内訳</th>
              <th class="right">リクエスト数</th>
              <th class="right">合計トークン</th>
              <th class="right">平均応答</th>
            </tr>
          </thead>
          <tbody id="user-tbody"></tbody>
        </table>
      </div>
    </div>
  </section>

  <footer class="container mono" id="provenance"></footer>

  <script>
    const MODEL_CLASSES = {
      'gemini-3.8-flash': 'ser-1',
      'gemini-4-argon': 'ser-2',
      'claude-sonnet-5-5': 'ser-3',
      'claude-opus-5-5': 'ser-4'
    };
    const SURFACE_CLASSES = {
      'Gemini Enterprise Chat': 'ser-1',
      'Antigravity': 'ser-2',
      'BigQuery Data Agent': 'ser-3',
      'Gemini Enterprise Search': 'ser-4'
    };

    let DATA = null;
    let deptMode = 'total_tokens';
    let dailyMode = 'requests';
    let userSort = 'total_tokens';

    const fmt = n => Number(n || 0).toLocaleString('ja-JP');
    const esc = s => String(s ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const modelCls = m => MODEL_CLASSES[m] || 'ser-other';
    const surfaceCls = s => SURFACE_CLASSES[s] || 'ser-other';

    function calcNiceAxisMax(rawMax) {
      if (rawMax <= 4) return 4;
      const roughStep = rawMax / 4;
      const mag = Math.pow(10, Math.floor(Math.log10(roughStep)));
      const norm = roughStep / mag;
      let niceNorm = 1;
      if (norm > 5) niceNorm = 10;
      else if (norm > 3) niceNorm = 5;
      else if (norm > 2) niceNorm = 3;
      else if (norm > 1) niceNorm = 2;
      return niceNorm * mag * 4;
    }

    function syncFilterOptions(filters) {
      const deptSel = document.getElementById('dept-filter');
      const modelSel = document.getElementById('model-filter');
      if (deptSel.options.length <= 1) {
        filters.departments.forEach(d => deptSel.add(new Option(d, d)));
      }
      if (modelSel.options.length <= 1) {
        filters.models.forEach(m => modelSel.add(new Option(m, m)));
      }
      deptSel.value = filters.selected_department || '';
      modelSel.value = filters.selected_model || '';
    }

    function buildModelSegments(breakdown, denomTokens, models) {
      if (!denomTokens) return '';
      return models.map(m => {
        const item = (breakdown || {})[m];
        if (!item || !item.total_tokens) return '';
        const pct = (item.total_tokens / denomTokens) * 100;
        const tip = m + ': ' + fmt(item.total_tokens) + ' tokens (' + fmt(item.requests) + '件)';
        return '<div class="stack-seg ' + modelCls(m) + '" style="width:' + pct.toFixed(2) + '%" title="' + esc(tip) + '"></div>';
      }).join('');
    }

    function renderLegend(items, clsFn) {
      const el = document.getElementById('dept-legend');
      if (!items.length) { el.innerHTML = ''; return; }
      el.innerHTML = items.map(name =>
        '<span class="legend-item"><span class="swatch ' + clsFn(name) + '"></span><span>' + esc(name) + '</span></span>'
      ).join('');
    }

    function renderDeptSection() {
      const s = DATA.summary;
      const models = DATA.filters.models;
      const surfaces = DATA.filters.surfaces;
      const selectedDept = DATA.filters.selected_department;
      const activeRate = s.licensed_users ? Math.round((s.active_users / s.licensed_users) * 100) : 0;

      const heroEl = document.getElementById('dept-hero');
      const capEl = document.getElementById('dept-caption');
      if (deptMode === 'total_tokens') {
        heroEl.innerHTML = fmt(s.total_tokens) + '<span class="hero-unit">tokens</span>';
        capEl.textContent = '入力 ' + fmt(s.input_tokens) + ' / 出力 ' + fmt(s.output_tokens);
        renderLegend(models, modelCls);
      } else if (deptMode === 'tokens_per_user') {
        const perUser = s.licensed_users ? Math.round(s.total_tokens / s.licensed_users) : 0;
        heroEl.innerHTML = fmt(perUser) + '<span class="hero-unit">tokens/人</span>';
        capEl.textContent = 'ライセンス付与 ' + fmt(s.licensed_users) + ' 名あたりの平均トークン量';
        renderLegend(models, modelCls);
      } else if (deptMode === 'surface_share') {
        heroEl.innerHTML = fmt(s.total_requests) + '<span class="hero-unit">件</span>';
        capEl.textContent = '部署ごとの利用機能比率 (リクエスト件数ベース)';
        renderLegend(surfaces, surfaceCls);
      } else {
        heroEl.innerHTML = fmt(s.avg_latency_ms) + '<span class="hero-unit">ms</span>';
        capEl.textContent = '1リクエストあたりの平均応答時間';
        renderLegend([], modelCls);
      }
      document.getElementById('dept-submeta').textContent =
        '稼働 ' + s.active_users + '/' + s.licensed_users + ' 名 (' + activeRate + '%) ・ リクエスト ' + fmt(s.total_requests) + ' 件';

      const depts = [...DATA.departments].sort((a, b) => {
        if (deptMode === 'tokens_per_user') return (b.tokens_per_user - a.tokens_per_user) || (b.requests_per_user - a.requests_per_user);
        if (deptMode === 'avg_latency_ms') return (b.avg_latency_ms - a.avg_latency_ms) || (b.requests - a.requests);
        if (deptMode === 'surface_share') return (b.requests - a.requests) || (b.total_tokens - a.total_tokens);
        return (b.total_tokens - a.total_tokens) || (b.requests - a.requests);
      });

      const maxVal = Math.max(1, ...depts.map(d => {
        if (deptMode === 'tokens_per_user') return d.tokens_per_user;
        if (deptMode === 'avg_latency_ms') return d.avg_latency_ms;
        return d.total_tokens;
      }));

      const root = document.getElementById('dept-bars');
      root.innerHTML = depts.map(d => {
        const isSel = selectedDept === d.department;
        let meta = '';
        let barInner = '';
        if (deptMode === 'surface_share') {
          meta = fmt(d.requests) + ' 件 ・ 稼働 ' + d.active_users + '/' + d.licensed_users + ' 名';
          const segs = d.requests ? surfaces.map(sf => {
            const item = (d.surface_breakdown || {})[sf];
            if (!item || !item.requests) return '';
            const pct = (item.requests / d.requests) * 100;
            const tip = sf + ': ' + item.requests + '件 (' + pct.toFixed(1) + '%)';
            return '<div class="stack-seg ' + surfaceCls(sf) + '" style="width:' + pct.toFixed(2) + '%" title="' + esc(tip) + '"></div>';
          }).join('') : '';
          barInner = '<div class="bar-group" style="width:' + (d.requests ? 100 : 0) + '%">' + segs + '</div>';
        } else if (deptMode === 'avg_latency_ms') {
          const w = d.avg_latency_ms ? (d.avg_latency_ms / maxVal) * 100 : 0;
          meta = (d.requests ? fmt(d.avg_latency_ms) + ' ms' : '-') + ' ・ ' + fmt(d.requests) + ' 件';
          barInner = '<div class="bar-fill" style="width:' + w.toFixed(1) + '%"></div>';
        } else {
          const val = deptMode === 'tokens_per_user' ? d.tokens_per_user : d.total_tokens;
          const unit = deptMode === 'tokens_per_user' ? ' tokens/人' : ' tokens';
          const reqPart = deptMode === 'tokens_per_user' ? d.requests_per_user + ' 件/人' : fmt(d.requests) + ' 件';
          const w = (val / maxVal) * 100;
          meta = fmt(val) + unit + ' (' + reqPart + ' ・ 稼働 ' + d.active_users + '/' + d.licensed_users + ' 名)';
          barInner = '<div class="bar-group" style="width:' + w.toFixed(1) + '%">' + buildModelSegments(d.model_breakdown, d.total_tokens, models) + '</div>';
        }
        return (
          '<div class="bar-row' + (isSel ? ' selected' : '') + '" tabindex="0" role="button" data-dept="' + esc(d.department) + '">' +
            '<div class="bar-head">' +
              '<span class="item-title">' + esc(d.department) + '</span>' +
              '<span class="mono meta-note">' + esc(meta) + '</span>' +
            '</div>' +
            '<div class="bar-track">' + barInner + '</div>' +
          '</div>'
        );
      }).join('');

      root.querySelectorAll('.bar-row').forEach(el => {
        const toggle = () => {
          const deptSel = document.getElementById('dept-filter');
          deptSel.value = deptSel.value === el.dataset.dept ? '' : el.dataset.dept;
          fetchAndRender();
        };
        el.addEventListener('click', toggle);
        el.addEventListener('keydown', e => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
        });
      });
    }

    function renderDailyAndModels() {
      const trends = DATA.daily_trends || [];
      const isTokens = dailyMode === 'total_tokens';
      const unit = isTokens ? 'tokens' : '件';
      const heroEl = document.getElementById('daily-hero');
      const capEl = document.getElementById('daily-caption');
      const yEl = document.getElementById('daily-y');
      const barsEl = document.getElementById('daily-bars');
      const xEl = document.getElementById('daily-x');

      if (!trends.length) {
        heroEl.textContent = '-';
        capEl.textContent = '';
        yEl.innerHTML = '';
        barsEl.innerHTML = '<div class="empty-state" style="width:100%;">該当データがありません</div>';
        xEl.innerHTML = '';
      } else {
        const vals = trends.map(t => isTokens ? t.total_tokens : t.requests);
        const maxVal = Math.max(1, ...vals);
        const yMax = calcNiceAxisMax(maxVal);
        const peak = trends.reduce((best, cur) =>
          (isTokens ? cur.total_tokens > best.total_tokens : cur.requests > best.requests) ? cur : best
        , trends[0]);
        const peakVal = isTokens ? peak.total_tokens : peak.requests;
        const sumVal = vals.reduce((a, b) => a + b, 0);
        const avgVal = isTokens ? fmt(Math.round(sumVal / trends.length)) : (sumVal / trends.length).toFixed(1);

        heroEl.innerHTML = fmt(peakVal) + '<span class="hero-unit">' + unit + '</span>';
        capEl.textContent = 'ピーク日 ' + peak.date + ' ・ 日平均 ' + avgVal + ' ' + unit + '/日';

        yEl.innerHTML = [1, 0.75, 0.5, 0.25, 0].map(r => '<span>' + fmt(Math.round(yMax * r)) + '</span>').join('');
        barsEl.innerHTML = trends.map(t => {
          const v = isTokens ? t.total_tokens : t.requests;
          const h = v ? Math.max(2, (v / yMax) * 100) : 0;
          const tip = t.date + ': ' + t.requests + '件 / ' + fmt(t.total_tokens) + ' tokens';
          return '<div class="daily-col" title="' + esc(tip) + '"><div class="daily-bar" style="height:' + h.toFixed(1) + '%"></div></div>';
        }).join('');
        const mid = trends[Math.floor(trends.length / 2)].date;
        xEl.innerHTML = '<span>' + esc(trends[0].date) + '</span><span>' + esc(mid) + '</span><span>' + esc(trends[trends.length - 1].date) + '</span>';
      }

      const selectedModel = DATA.filters.selected_model;
      const tbody = document.getElementById('model-tbody');
      if (!DATA.models.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">該当データがありません</td></tr>';
        return;
      }
      tbody.innerHTML = DATA.models.map(m => {
        const isSel = selectedModel === m.model_name;
        return (
          '<tr class="clickable' + (isSel ? ' selected' : '') + '" data-model="' + esc(m.model_name) + '">' +
            '<td data-label="モデル名" class="mono">' + esc(m.model_name) + '</td>' +
            '<td data-label="リクエスト数" class="right mono">' + fmt(m.requests) + ' (' + m.request_share_pct + '%)</td>' +
            '<td data-label="合計トークン" class="right mono">' + fmt(m.total_tokens) + '</td>' +
            '<td data-label="トークン比率" class="right mono">' + m.token_share_pct + '%</td>' +
            '<td data-label="平均レイテンシ" class="right mono">' + (m.requests ? fmt(m.avg_latency_ms) + ' ms' : '-') + '</td>' +
          '</tr>'
        );
      }).join('');

      tbody.querySelectorAll('tr.clickable').forEach(tr => {
        tr.addEventListener('click', () => {
          const modelSel = document.getElementById('model-filter');
          modelSel.value = modelSel.value === tr.dataset.model ? '' : tr.dataset.model;
          fetchAndRender();
        });
      });
    }

    function renderUsers() {
      const s = DATA.summary;
      const models = DATA.filters.models;
      const status = document.getElementById('status-filter').value;
      const rate = s.licensed_users ? Math.round((s.active_users / s.licensed_users) * 1000) / 10 : 0;

      document.getElementById('user-hero').innerHTML =
        fmt(s.active_users) + ' / ' + fmt(s.licensed_users) + '<span class="hero-unit">名</span>';

      const list = [...DATA.users]
        .filter(u => status === 'ACTIVE' ? u.requests > 0 : (status === 'INACTIVE' ? u.requests === 0 : true))
        .sort((a, b) => (b[userSort] - a[userSort]) || (b.total_tokens - a.total_tokens) || a.user_id.localeCompare(b.user_id));

      document.getElementById('user-caption').textContent =
        'アクティブ率 ' + rate + '% (未利用 ' + s.inactive_users + ' 名) ・ 表示 ' + list.length + ' 名';

      const tbody = document.getElementById('user-tbody');
      if (!list.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">該当するユーザーがいません</td></tr>';
        return;
      }

      tbody.innerHTML = list.map((u, idx) => {
        const inactiveNote = u.requests === 0 ? ' (未利用)' : '';
        const segs = buildModelSegments(u.model_breakdown, u.total_tokens, models);
        return (
          '<tr class="' + (u.requests === 0 ? 'inactive-row' : '') + '">' +
            '<td data-label="順位" class="mono">' + (idx + 1) + '</td>' +
            '<td data-label="氏名">' +
              '<span>' + esc(u.user_name) + inactiveNote + '</span>' +
              '<span class="sub-line mono">' + esc(u.user_id) + '</span>' +
            '</td>' +
            '<td data-label="部署・職種">' +
              '<span>' + esc(u.department) + '</span>' +
              '<span class="sub-line">' + esc(u.job_role) + '</span>' +
            '</td>' +
            '<td data-label="モデル内訳">' +
              '<div class="mini-stack">' + segs + '</div>' +
              '<span class="sub-line mono">' + esc(u.top_model) + '</span>' +
            '</td>' +
            '<td data-label="リクエスト数" class="right mono">' + fmt(u.requests) + '</td>' +
            '<td data-label="合計トークン" class="right mono">' +
              fmt(u.total_tokens) +
              '<span class="sub-line">入 ' + fmt(u.input_tokens) + ' / 出 ' + fmt(u.output_tokens) + '</span>' +
            '</td>' +
            '<td data-label="平均応答" class="right mono">' + (u.requests ? fmt(u.avg_latency_ms) + ' ms' : '-') + '</td>' +
          '</tr>'
        );
      }).join('');
    }

    function bindSegmented(containerId, onSelect) {
      const buttons = Array.from(document.querySelectorAll('#' + containerId + ' button'));
      buttons.forEach((btn, idx) => {
        btn.addEventListener('click', () => {
          buttons.forEach(b => b.setAttribute('aria-selected', 'false'));
          btn.setAttribute('aria-selected', 'true');
          onSelect(btn);
        });
        btn.addEventListener('keydown', e => {
          if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
            e.preventDefault();
            const next = e.key === 'ArrowRight' ? (idx + 1) % buttons.length : (idx - 1 + buttons.length) % buttons.length;
            buttons[next].focus();
            buttons[next].click();
          }
        });
      });
    }

    async function fetchAndRender() {
      const dept = document.getElementById('dept-filter').value;
      const model = document.getElementById('model-filter').value;
      const params = new URLSearchParams();
      if (dept) params.set('department', dept);
      if (model) params.set('model', model);
      const qs = params.toString();
      const res = await fetch('/api/usage' + (qs ? '?' + qs : ''), { cache: 'no-store' });
      DATA = await res.json();
      syncFilterOptions(DATA.filters);
      renderDeptSection();
      renderDailyAndModels();
      renderUsers();
      document.getElementById('provenance').textContent =
        'Source: data/users.csv (25 rows) + data/ai_audit_logs.csv (100 rows) | Join key: user_id';
    }

    bindSegmented('dept-tabs', btn => { deptMode = btn.dataset.mode; if (DATA) renderDeptSection(); });
    bindSegmented('daily-tabs', btn => { dailyMode = btn.dataset.daily; if (DATA) renderDailyAndModels(); });
    bindSegmented('user-tabs', btn => { userSort = btn.dataset.sort; if (DATA) renderUsers(); });

    document.getElementById('dept-filter').addEventListener('change', fetchAndRender);
    document.getElementById('model-filter').addEventListener('change', fetchAndRender);
    document.getElementById('status-filter').addEventListener('change', () => { if (DATA) renderUsers(); });
    document.getElementById('reset-btn').addEventListener('click', () => {
      document.getElementById('dept-filter').value = '';
      document.getElementById('model-filter').value = '';
      document.getElementById('status-filter').value = 'ALL';
      fetchAndRender();
    });

    fetchAndRender();
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    """利用量ダッシュボード配信ハンドラ."""

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/api/usage", "/api/dashboard"):
            qs = parse_qs(parsed.query)
            dept = qs.get("department", [""])[0]
            model = qs.get("model", [""])[0]
            payload = load_and_aggregate(department_filter=dept, model_filter=model)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(HTTPStatus.OK, "application/json; charset=utf-8", body)
            return
        if parsed.path in ("/", "/index.html"):
            self._send_bytes(HTTPStatus.OK, "text/html; charset=utf-8", DASHBOARD_HTML.encode("utf-8"))
            return
        if parsed.path == "/health":
            self._send_bytes(HTTPStatus.OK, "application/json; charset=utf-8", b'{"status":"ok"}')
            return
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self._send_bytes(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not Found")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def _pad_east_asian(text: str, width: int) -> str:
    disp_len = sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in text)
    return text + " " * max(0, width - disp_len)


def print_cli_summary() -> None:
    """ターミナル向けに部署別・モデル別・ユーザー上位の集計結果を表示する."""
    data = load_and_aggregate()
    s = data["summary"]
    print(
        f"=== 生成AI利用量サマリー (全 {s['total_requests']} 件 / 合計 {s['total_tokens']:,} tokens / 平均 {s['avg_latency_ms']:,} ms) ==="
    )
    print(f"アクティブ人数: {s['active_users']} / {s['licensed_users']} 名 (未利用 {s['inactive_users']} 名)\n")
    print("[部署別ランキング]")
    for d in data["departments"]:
        dept_col = _pad_east_asian(d["department"], 14)
        print(
            f"  - {dept_col} | {d['requests']:>3} 件 | {d['total_tokens']:>8,} tokens "
            f"({d['tokens_per_user']:>6,}/人) | 平均 {d['avg_latency_ms']:>5,} ms | 稼働 {d['active_users']}/{d['licensed_users']} 名"
        )
    print("\n[モデル別内訳]")
    for m in data["models"]:
        print(
            f"  - {m['model_name']:<18} | {m['requests']:>3} 件 ({m['request_share_pct']:>4.1f}%) "
            f"| {m['total_tokens']:>8,} tokens ({m['token_share_pct']:>4.1f}%) | 平均 {m['avg_latency_ms']:>5,} ms"
        )
    print("\n[ユーザー別 上位5名]")
    for u in data["users"][:5]:
        print(
            f"  - {u['user_id']} ({u['user_name']} / {u['department']}) | {u['requests']:>2} 件 | {u['total_tokens']:>7,} tokens | {u['top_model']}"
        )


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    """ポート再利用と即時停止を有効化したマルチスレッド HTTP サーバー."""

    allow_reuse_address = True
    daemon_threads = True


def _start_auto_reloader(interval: float = 1.0) -> None:
    """スクリプト自身の更新を検知し、構文確認のうえで同一プロセスを再実行する."""
    script = Path(__file__).resolve()
    try:
        initial_mtime = script.stat().st_mtime
    except OSError:
        return

    def _watch() -> None:
        nonlocal initial_mtime
        while True:
            time.sleep(interval)
            try:
                current_mtime = script.stat().st_mtime
                if current_mtime != initial_mtime:
                    initial_mtime = current_mtime
                    py_compile.compile(str(script), doraise=True)
                    os.execv(sys.executable, [sys.executable, *sys.argv])
            except Exception:
                continue

    threading.Thread(target=_watch, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="サブテーマ1: 生成AI利用量可視化ダッシュボード")
    parser.add_argument("--port", type=int, default=8080, help="待ち受けポート番号 (既定: 8080)")
    parser.add_argument("--cli", action="store_true", help="Webサーバーを起動せずターミナルに集計結果を表示")
    args = parser.parse_args()

    if not USERS_CSV.exists() or not LOGS_CSV.exists():
        print(f"CSVファイルが見つかりません: {USERS_CSV}, {LOGS_CSV}", file=sys.stderr)
        sys.exit(1)

    if args.cli:
        print_cli_summary()
        return

    _start_auto_reloader()
    server = ReusableThreadingHTTPServer(("0.0.0.0", args.port), DashboardHandler)
    print(f"Usage Dashboard running at http://localhost:{args.port} (Press Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
