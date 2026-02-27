"use client";

import { useState, useEffect } from "react";
import {
  Wallet, ArrowUpRight, ArrowDownRight, Plus,
  Loader, AlertCircle, CreditCard, Receipt,
  DollarSign, Clock,
} from "lucide-react";
import {
  getBalance, getTransactions, topUp,
  type Transaction,
} from "@/lib/api/client";

const MAX_TOPUP = 1000;
const MIN_TOPUP = 5;

export function BillingPanel() {
  const [balance, setBalance] = useState<number | null>(null);
  const [currency, setCurrency] = useState("USD");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showTopUp, setShowTopUp] = useState(false);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    setError("");
    try {
      const [balRes, txRes] = await Promise.allSettled([
        getBalance(),
        getTransactions(),
      ]);

      if (balRes.status === "fulfilled") {
        setBalance(balRes.value.balance);
        setCurrency(balRes.value.currency || "USD");
      }
      if (txRes.status === "fulfilled") {
        setTransactions(txRes.value.transactions || []);
      }

      if (balRes.status === "rejected" && txRes.status === "rejected") {
        setError("Failed to load billing data");
      }
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  const formatAmount = (amount: number) => {
    const prefix = amount >= 0 ? "+" : "";
    return `${prefix}$${Math.abs(amount).toFixed(2)}`;
  };

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch {
      return dateStr;
    }
  };

  return (
    <div>
      {error && (
        <div style={{ padding: "8px 12px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <AlertCircle className="h-3.5 w-3.5" style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 40, gap: 8, color: "var(--muted-foreground)" }}>
          <Loader className="h-4 w-4 animate-spin" />
          <span style={{ fontSize: "var(--font-xs)" }}>Loading billing...</span>
        </div>
      ) : (
        <>
          {/* Balance card */}
          <div style={{
            padding: 20,
            background: "linear-gradient(135deg, var(--sidebar-bg), var(--background))",
            borderRadius: 10,
            border: "1px solid var(--border)",
            marginBottom: 20,
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div>
                <div style={{ fontSize: "var(--font-xs)", color: "var(--muted-foreground)", marginBottom: 4 }}>Current Balance</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: "var(--foreground)", fontFamily: "monospace" }}>
                  ${(balance ?? 0).toFixed(2)}
                </div>
                <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginTop: 4 }}>{currency}</div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn-primary" onClick={() => setShowTopUp(true)}>
                  <Plus className="h-3.5 w-3.5" />
                  <span>Top Up</span>
                </button>
              </div>
            </div>
          </div>

          {showTopUp && (
            <TopUpForm
              onClose={() => setShowTopUp(false)}
              onSuccess={() => { setShowTopUp(false); loadData(); }}
            />
          )}

          {/* Transactions */}
          <div className="settings-section">
            <div className="settings-section-title">
              <Receipt className="h-3.5 w-3.5" style={{ display: "inline", marginRight: 6, verticalAlign: "middle" }} />
              Transactions ({transactions.length})
            </div>

            {transactions.length === 0 ? (
              <div className="panel-empty">
                <CreditCard className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
                <div className="panel-empty-title">No transactions</div>
                <div className="panel-empty-sub">Top up your balance to get started</div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {transactions.map((tx) => (
                  <div key={tx.id} style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "8px 10px",
                    borderRadius: 6,
                    fontSize: "var(--font-xs)",
                  }}>
                    <div style={{
                      width: 28,
                      height: 28,
                      borderRadius: 6,
                      background: tx.amount >= 0 ? "rgba(20,184,166,0.1)" : "rgba(239,68,68,0.08)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}>
                      {tx.amount >= 0 ? (
                        <ArrowDownRight className="h-3.5 w-3.5" style={{ color: "var(--color-teal)" }} />
                      ) : (
                        <ArrowUpRight className="h-3.5 w-3.5" style={{ color: "var(--color-red)" }} />
                      )}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 500 }}>{tx.description || tx.type}</div>
                      <div style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", display: "flex", alignItems: "center", gap: 4, marginTop: 1 }}>
                        <Clock className="h-2.5 w-2.5" />
                        {formatDate(tx.created_at)}
                        {tx.reference && <span>· {tx.reference}</span>}
                      </div>
                    </div>
                    <div style={{
                      fontWeight: 600,
                      fontFamily: "monospace",
                      color: tx.amount >= 0 ? "var(--color-teal)" : "var(--color-red)",
                    }}>
                      {formatAmount(tx.amount)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function TopUpForm({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const presets = [10, 25, 50, 100];

  const handleSubmit = async () => {
    const num = parseFloat(amount);
    if (isNaN(num) || num < MIN_TOPUP) { setError(`Minimum top-up is $${MIN_TOPUP}`); return; }
    if (num > MAX_TOPUP) { setError(`Maximum top-up is $${MAX_TOPUP}`); return; }

    setBusy(true);
    setError("");
    try {
      await topUp(num, reference.trim());
      onSuccess();
    } catch (e: any) {
      setError(e.message);
    }
    setBusy(false);
  };

  return (
    <div style={{ padding: 16, background: "var(--sidebar-bg)", borderRadius: 8, marginBottom: 16, border: "1px solid var(--border)" }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Top Up Balance</div>

      {error && (
        <div style={{ padding: "6px 10px", fontSize: "var(--font-xs)", color: "var(--color-red)", background: "rgba(239,68,68,0.08)", borderRadius: 6, marginBottom: 10 }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        {presets.map((p) => (
          <button
            key={p}
            className={amount === String(p) ? "btn-primary" : "btn-secondary"}
            onClick={() => setAmount(String(p))}
            style={{ flex: 1 }}
          >
            ${p}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 3, display: "block" }}>Amount ($)</label>
          <input
            className="deploy-select"
            type="number"
            min={MIN_TOPUP}
            max={MAX_TOPUP}
            step="0.01"
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            style={{ width: "100%" }}
          />
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: "var(--font-xxs)", color: "var(--muted-foreground)", marginBottom: 3, display: "block" }}>Reference (optional)</label>
          <input
            className="deploy-select"
            placeholder="e.g. invoice #123"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            style={{ width: "100%" }}
          />
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={handleSubmit} disabled={busy}>
          {busy ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <DollarSign className="h-3.5 w-3.5" />}
          <span>{busy ? "Processing..." : `Top Up $${amount || "0"}`}</span>
        </button>
      </div>
    </div>
  );
}
