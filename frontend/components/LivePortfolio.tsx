"use client";

/**
 * LivePortfolio.tsx — Tech-Luxe obsidian + monospace terminal panel.
 *
 * Phase 3.1 of the AgentQuant Apex migration. Displays the live Dhan
 * account snapshot polled from the backend's `/portfolio` endpoint:
 *
 *   - Top KPI row: Available Margin, Used Margin, Day P&L, Position Count.
 *   - Holdings table: symbol, qty, avg, LTP, P&L, day change (color-coded).
 *   - Auto-refresh every 5 seconds via SWR-like fetch loop.
 *
 * Aesthetic constraints (from the project directive):
 *   - Deep obsidian / slate background (border-white/10, bg-zinc-950).
 *   - Monospace font (JetBrains Mono) for all financial numbers.
 *   - High data density, subtle borders, no glassmorphism.
 *   - NO purple.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

// --------------------------------------------------------------------------- //
// Types — mirror backend/graph/state.py (QuantState)
// --------------------------------------------------------------------------- //
export type RegimeLabel =
  | "LowVol-Bull"
  | "LowVol-Bear"
  | "HighVol-Bull"
  | "HighVol-Bear"
  | "Crisis"
  | "Unknown";

export interface Holding {
  symbol: string;
  security_id?: string | null;
  quantity: number;
  avg_price: number;
  current_price: number;
  pnl: number;
  pnl_pct: number;
  day_change_pct: number;
}

export interface PortfolioSnapshot {
  available_margin: number;
  used_margin: number;
  current_holdings: Holding[];
  portfolio_synced_at?: string | null;
  regime_context?: { label: RegimeLabel; confidence: number } | null;
}

interface LivePortfolioProps {
  apiBase: string;
  refreshMs?: number;
}

// --------------------------------------------------------------------------- //
// Number formatters
// --------------------------------------------------------------------------- //
const inr = (n: number, frac = 0): string =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: frac,
    maximumFractionDigits: frac,
  }).format(n);

const pct = (n: number, frac = 2): string =>
  `${n >= 0 ? "+" : ""}${n.toFixed(frac)}%`;

// --------------------------------------------------------------------------- //
// Component
// --------------------------------------------------------------------------- //
export function LivePortfolio({
  apiBase,
  refreshMs = 5_000,
}: LivePortfolioProps) {
  const [snap, setSnap] = useState<PortfolioSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchSnap = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/portfolio`, { cache: "no-store" });
      if (!res.ok) {
        setError(`HTTP ${res.status}`);
        return;
      }
      const data: PortfolioSnapshot = await res.json();
      setSnap(data);
      setError(null);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    fetchSnap();
    const id = setInterval(fetchSnap, refreshMs);
    return () => clearInterval(id);
  }, [fetchSnap, refreshMs]);

  // ---- Derived KPIs ----
  const deployedNotional = useMemo(
    () => snap?.current_holdings.reduce((s, h) => s + h.quantity * h.avg_price, 0) ?? 0,
    [snap]
  );
  const currentNotional = useMemo(
    () => snap?.current_holdings.reduce((s, h) => s + h.quantity * h.current_price, 0) ?? 0,
    [snap]
  );
  const totalPnl = currentNotional - deployedNotional;
  const totalPnlPct =
    deployedNotional > 0 ? (totalPnl / deployedNotional) * 100 : 0;

  // ---- Loading / error shell ----
  if (loading && !snap) {
    return (
      <div className="rounded-lg border border-white/10 bg-zinc-950 p-6 font-mono text-sm text-zinc-400">
        Loading live portfolio…
      </div>
    );
  }

  // ---- Render ----
  return (
    <section
      aria-label="Live Portfolio"
      className="rounded-lg border border-white/10 bg-zinc-950 text-zinc-100"
    >
      {/* Header */}
      <header className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold tracking-widest text-zinc-200 uppercase">
            Live Portfolio
          </h2>
          <p className="font-mono text-xs text-zinc-500">
            {snap?.portfolio_synced_at
              ? `Synced ${new Date(snap.portfolio_synced_at).toLocaleString("en-IN")}`
              : "Awaiting first sync"}
            {snap?.regime_context ? (
              <>
                {" · "}
                <span
                  className={
                    snap.regime_context.label === "Crisis"
                      ? "text-rose-400"
                      : snap.regime_context.label.includes("Bull")
                        ? "text-emerald-400"
                        : "text-amber-400"
                  }
                >
                  {snap.regime_context.label} ·{" "}
                  {(snap.regime_context.confidence * 100).toFixed(0)}%
                </span>
              </>
            ) : null}
          </p>
        </div>
        <div className="flex items-center gap-3 font-mono text-[10px] text-zinc-500">
          {lastRefresh ? (
            <span>last {lastRefresh.toLocaleTimeString("en-IN")}</span>
          ) : null}
          <button
            type="button"
            onClick={fetchSnap}
            className="rounded border border-white/10 px-2 py-1 text-zinc-300 hover:bg-white/5"
          >
            refresh
          </button>
        </div>
      </header>

      {/* KPI grid */}
      <div className="grid grid-cols-2 gap-px border-b border-white/10 bg-white/5 md:grid-cols-4">
        <KpiCell
          label="Available Margin"
          value={inr(snap?.available_margin ?? 0, 0)}
          accent="emerald"
        />
        <KpiCell
          label="Deployed"
          value={inr(deployedNotional, 0)}
          sub={`${inr(snap?.used_margin ?? 0, 0)} from Dhan`}
        />
        <KpiCell
          label="Unrealised P&L"
          value={inr(totalPnl, 0)}
          sub={pct(totalPnlPct)}
          accent={totalPnl >= 0 ? "emerald" : "rose"}
        />
        <KpiCell
          label="Positions"
          value={String(snap?.current_holdings.length ?? 0)}
          sub={
            snap?.current_holdings && snap.current_holdings.length
              ? `${(snap.current_holdings.reduce((s, h) => s + h.quantity, 0)).toLocaleString("en-IN")} shares`
              : "—"
          }
        />
      </div>

      {/* Error / no broker banner */}
      {error ? (
        <div className="border-b border-rose-500/30 bg-rose-500/5 px-4 py-2 font-mono text-xs text-rose-300">
          ⚠ {error} — Dhan may not be configured. Set BROKER=dhan + DHAN_* env vars
          in <code>backend/.env</code>.
        </div>
      ) : null}

      {/* Holdings table */}
      <div className="overflow-x-auto">
        <table className="w-full font-mono text-xs">
          <thead className="text-zinc-500 uppercase tracking-widest">
            <tr className="border-b border-white/10">
              <th className="px-4 py-2 text-left">Symbol</th>
              <th className="px-4 py-2 text-right">Qty</th>
              <th className="px-4 py-2 text-right">Avg</th>
              <th className="px-4 py-2 text-right">LTP</th>
              <th className="px-4 py-2 text-right">P&L</th>
              <th className="px-4 py-2 text-right">Day Δ</th>
            </tr>
          </thead>
          <tbody>
            {snap?.current_holdings.length ? (
              snap.current_holdings.map((h) => (
                <tr
                  key={h.symbol}
                  className="border-b border-white/5 hover:bg-white/[0.03]"
                >
                  <td className="px-4 py-2 font-semibold text-zinc-200">
                    {h.symbol}
                  </td>
                  <td className="px-4 py-2 text-right text-zinc-300">
                    {h.quantity.toLocaleString("en-IN")}
                  </td>
                  <td className="px-4 py-2 text-right text-zinc-400">
                    {inr(h.avg_price, 2)}
                  </td>
                  <td className="px-4 py-2 text-right text-zinc-300">
                    {inr(h.current_price, 2)}
                  </td>
                  <td
                    className={`px-4 py-2 text-right ${
                      h.pnl >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {inr(h.pnl, 0)} <span className="text-[10px]">({pct(h.pnl_pct)})</span>
                  </td>
                  <td
                    className={`px-4 py-2 text-right ${
                      h.day_change_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {pct(h.day_change_pct)}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-6 text-center text-zinc-500"
                >
                  No live positions. Start a research run, approve a sized order,
                  and the portfolio will populate once Dhan confirms execution.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------- //
// Sub-components
// --------------------------------------------------------------------------- //
function KpiCell({
  label,
  value,
  sub,
  accent = "zinc",
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: "zinc" | "emerald" | "rose";
}) {
  const accentClass =
    accent === "emerald"
      ? "text-emerald-400"
      : accent === "rose"
        ? "text-rose-400"
        : "text-zinc-100";
  return (
    <div className="bg-zinc-950 px-4 py-3">
      <p className="text-[10px] tracking-widest text-zinc-500 uppercase">
        {label}
      </p>
      <p className={`mt-1 font-mono text-lg ${accentClass}`}>{value}</p>
      {sub ? <p className="font-mono text-[10px] text-zinc-500">{sub}</p> : null}
    </div>
  );
}

export default LivePortfolio;
