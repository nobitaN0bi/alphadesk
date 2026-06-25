"use client";

// ApprovalModal.tsx — Tech-Luxe HiTL gate (Phase 3.2 of AgentQuant Apex).
//
// Two-step confirmation designed for high-stakes execution:
//
//   Step 1: Capital Impact review
//     - Required Margin (sum of order notional)
//     - Available Margin (from LivePortfolio)
//     - Utilization After (color-coded: green <60%, amber 60-80%, red >80%)
//     - Per-order breakdown: symbol, qty, limit price, notional
//
//   Step 2: Final EXECUTE confirmation
//     - Requires deliberate click on a red-600 button (live) or
//       emerald-600 button (paper mode).
//     - Button label: "EXECUTE on Dhan" vs "CONFIRM Paper".
//
// Aesthetic constraints (prime architect directive):
//   - Deep obsidian background, border-white/10, monospace numbers, NO purple.
//   - Uses existing shadcn/ui Dialog primitives — no visual style regression
//     for the rest of the app, but a thicker "this is real money" treatment
//     for the live-execute button.
//
// Backward compat: the legacy prop shape is preserved
// (open, onOpenChange, actionId, items, onResolved). New capital-impact
// props are optional and gracefully degrade to the original simple flow
// when missing.

import { useMemo, useState } from "react";
import { Check, X, ShieldCheck, AlertTriangle, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ActionBadge, RiskBadge } from "@/components/StatusBadge";
import {
  approve,
  type AnalystRecommendation,
  type ApproveResult,
  type RiskAssessment,
} from "@/lib/api";

// --------------------------------------------------------------------------- //
// Types
// --------------------------------------------------------------------------- //
interface ApprovalModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actionId: string | null;
  items: { rec: AnalystRecommendation; risk?: RiskAssessment }[];
  onResolved: (approved: boolean, result: ApproveResult) => void;
  /** Available margin in INR — surfaced as the "Capital Impact" KPI. */
  availableMargin?: number;
  /**
   * Whether the run is in live-trading mode (Dhan broker configured) or
   * paper mode. Defaults to false (paper). Controls the colour and label
   * of the EXECUTE button.
   */
  isLive?: boolean;
  /**
   * Detected market regime. When present, the modal surfaces a regime pill
   * so the human can see *why* the system thinks it's safe (or not) to trade.
   */
  regime?: { label: string; confidence: number } | null;
}

// --------------------------------------------------------------------------- //
// Formatters
// --------------------------------------------------------------------------- //
const inr = (n: number, frac = 0): string =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: frac,
    maximumFractionDigits: frac,
  }).format(n);

// --------------------------------------------------------------------------- //
// Capital Impact sub-panel
// --------------------------------------------------------------------------- //
function CapitalImpact({
  required,
  available,
  isLive,
}: {
  required: number;
  available: number;
  isLive: boolean;
}) {
  const utilization = available > 0 ? (required / available) * 100 : 0;
  const tone =
    utilization > 80
      ? "border-down/30 text-down"
      : utilization > 60
        ? "border-warning/30 text-warning"
        : "border-up/30 text-up";
  return (
    <div
      className={`border ${tone} bg-card/40 p-3 font-mono text-xs`}
      data-testid="capital-impact"
    >
      <div className="flex items-center gap-1.5">
        {isLive ? (
          <AlertTriangle className="h-3.5 w-3.5 text-down" />
        ) : (
          <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />
        )}
        <span className="eyebrow">Capital Impact</span>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2">
        <div>
          <p className="eyebrow text-muted-foreground">Required</p>
          <p className="text-base text-foreground tabular-nums">
            {inr(required, 0)}
          </p>
        </div>
        <div>
          <p className="eyebrow text-muted-foreground">Available</p>
          <p className="text-base text-foreground tabular-nums">
            {inr(available, 0)}
          </p>
        </div>
        <div>
          <p className="eyebrow text-muted-foreground">Utilization</p>
          <p className="text-base tabular-nums">{utilization.toFixed(1)}%</p>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Order detail row (capital impact table)
// --------------------------------------------------------------------------- //
function OrderDetailRow({
  symbol,
  qty,
  price,
  notional,
  correlationId,
}: {
  symbol: string;
  qty: number;
  price: number;
  notional: number;
  correlationId?: string;
}) {
  return (
    <tr className="border-b border-border font-mono text-[11px]">
      <td className="px-2 py-1.5 font-semibold text-primary">{symbol}</td>
      <td className="px-2 py-1.5 text-right text-foreground tabular-nums">
        {qty.toLocaleString("en-IN")}
      </td>
      <td className="px-2 py-1.5 text-right text-foreground tabular-nums">
        {inr(price, 2)}
      </td>
      <td className="px-2 py-1.5 text-right text-foreground tabular-nums">
        {inr(notional, 0)}
      </td>
      <td className="px-2 py-1.5 text-right text-muted-foreground">
        {correlationId?.slice(0, 10) ?? "—"}
      </td>
    </tr>
  );
}

// --------------------------------------------------------------------------- //
// Main component
// --------------------------------------------------------------------------- //
export function ApprovalModal({
  open,
  onOpenChange,
  actionId,
  items,
  onResolved,
  availableMargin = 0,
  isLive = false,
  regime = null,
}: ApprovalModalProps) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<"review" | "confirm">("review");

  // Aggregate capital impact across the staged orders. We pull per-symbol
  // quantity and limit price from the risk manager's sized_order when present,
  // otherwise fall back to a 1-share placeholder so the original flow works.
  const aggregated = useMemo(() => {
    let totalNotional = 0;
    const rows: {
      symbol: string;
      qty: number;
      price: number;
      notional: number;
      correlationId?: string;
    }[] = [];
    for (const { rec, risk } of items) {
      const sized = risk?.sized_order;
      const qty =
        sized?.quantity && sized.quantity > 0
          ? sized.quantity
          : risk?.proposed_quantity && risk.proposed_quantity > 0
            ? risk.proposed_quantity
            : 1; // paper fallback
      const price =
        sized?.price && sized.price > 0
          ? sized.price
          : risk?.proposed_price && risk.proposed_price > 0
            ? risk.proposed_price
            : 0;
      const notional = qty * price;
      totalNotional += notional;
      rows.push({
        symbol: rec.symbol,
        qty,
        price,
        notional,
        correlationId: sized?.correlation_id,
      });
    }
    return { totalNotional, rows };
  }, [items]);

  async function decide(approved: boolean) {
    if (!actionId) return;
    setBusy(approved ? "approve" : "reject");
    setError(null);
    try {
      const result = await approve(actionId, approved);
      onResolved(approved, result);
      onOpenChange(false);
      setStep("review"); // reset for the next opening
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !busy && onOpenChange(o)}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-flag">
              <ShieldCheck className="h-4 w-4" />
              <span className="eyebrow text-flag">Human approval required</span>
            </div>
            {regime ? (
              <span
                className="eyebrow text-muted-foreground"
                title="Detected market regime at run start"
              >
                regime · {regime.label} · {(regime.confidence * 100).toFixed(0)}%
              </span>
            ) : null}
          </div>
          <DialogTitle>
            {step === "review"
              ? isLive
                ? `Deploy ${items.length} live order${items.length === 1 ? "" : "s"} on Dhan?`
                : `Add ${items.length} stock${items.length === 1 ? "" : "s"} to the paper watchlist?`
              : isLive
                ? "Confirm live execution"
                : "Confirm paper addition"}
          </DialogTitle>
          <DialogDescription>
            {step === "review"
              ? isLive
                ? "These orders cleared the risk guardrails and have been sized against your available margin. Approving will fire them on Dhan with the correlation_ids shown. Re-submitting this run (e.g. after a graph resume) will NOT duplicate these orders."
                : "These cleared the risk guardrails. Approving stages them into the paper watchlist. No real order is placed unless a broker is configured."
              : isLive
                ? "You are about to commit real capital. This action is logged in the audit trail. Pressing EXECUTE is final."
                : "This will add the symbols to your paper watchlist (no live orders). You can re-run the research at any time."}
          </DialogDescription>
        </DialogHeader>

        {/* Step 1: Capital Impact + Order Detail */}
        {step === "review" ? (
          <>
            {aggregated.totalNotional > 0 ? (
              <CapitalImpact
                required={aggregated.totalNotional}
                available={availableMargin}
                isLive={isLive}
              />
            ) : null}

            <div className="max-h-64 space-y-1.5 overflow-y-auto">
              {items.map(({ rec, risk }) => {
                const sized = risk?.sized_order;
                const row = aggregated.rows.find((r) => r.symbol === rec.symbol);
                return (
                  <div
                    key={rec.symbol}
                    className="flex items-center justify-between gap-3 border border-border bg-card px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-primary">
                        {rec.symbol}
                      </span>
                      {risk?.sector && (
                        <span className="eyebrow">{risk.sector}</span>
                      )}
                      {row && row.notional > 0 ? (
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {row.qty} × ₹{row.price.toFixed(2)} · {inr(row.notional, 0)}
                        </span>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs tabular-nums text-muted-foreground">
                        {Math.round(rec.confidence * 100)}%
                      </span>
                      <ActionBadge action={rec.action} />
                      {risk && <RiskBadge decision={risk.decision} />}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Per-order notional table (only when live sizing data is present) */}
            {aggregated.totalNotional > 0 ? (
              <div className="overflow-x-auto border border-border">
                <table className="w-full">
                  <thead className="bg-card/60 text-muted-foreground uppercase">
                    <tr>
                      <th className="px-2 py-1.5 text-left text-[10px] tracking-widest">
                        Symbol
                      </th>
                      <th className="px-2 py-1.5 text-right text-[10px] tracking-widest">
                        Qty
                      </th>
                      <th className="px-2 py-1.5 text-right text-[10px] tracking-widest">
                        Limit ₹
                      </th>
                      <th className="px-2 py-1.5 text-right text-[10px] tracking-widest">
                        Notional
                      </th>
                      <th className="px-2 py-1.5 text-right text-[10px] tracking-widest">
                        Corr-ID
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {aggregated.rows.map((r) => (
                      <OrderDetailRow
                        key={r.symbol}
                        symbol={r.symbol}
                        qty={r.qty}
                        price={r.price}
                        notional={r.notional}
                        correlationId={r.correlationId}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </>
        ) : (
          /* Step 2: Final confirmation */
          <div className="border border-border bg-card/40 p-4 font-mono text-xs">
            <p className="text-foreground">
              {isLive ? "EXECUTE" : "CONFIRM"} {items.length} order
              {items.length === 1 ? "" : "s"}
              {aggregated.totalNotional > 0
                ? ` totalling ${inr(aggregated.totalNotional, 0)}`
                : null}
              {isLive ? " on Dhan." : " on the paper watchlist."}
            </p>
            {isLive ? (
              <p className="mt-2 text-down">
                Real capital will be deployed. Pressing EXECUTE is final.
              </p>
            ) : (
              <p className="mt-2 text-muted-foreground">
                Paper mode — no live orders will be placed.
              </p>
            )}
          </div>
        )}

        {error && (
          <p className="font-mono text-xs text-down">{error}</p>
        )}

        <DialogFooter>
          {step === "review" ? (
            <>
              <Button
                variant="outline"
                onClick={() => decide(false)}
                disabled={busy !== null}
              >
                {busy === "reject" ? <Loader2 className="animate-spin" /> : <X />}
                Reject
              </Button>
              <Button onClick={() => setStep("confirm")} disabled={busy !== null}>
                I understand, proceed →
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={() => setStep("review")}
                disabled={busy !== null}
              >
                ← Back
              </Button>
              <Button
                onClick={() => decide(true)}
                disabled={busy !== null}
                className={
                  isLive
                    ? "bg-down text-white hover:bg-down/90 font-mono uppercase tracking-widest"
                    : "bg-up text-white hover:bg-up/90 font-mono uppercase tracking-widest"
                }
              >
                {busy === "approve" ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Check />
                )}
                {isLive ? "EXECUTE on Dhan" : "CONFIRM Paper"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
