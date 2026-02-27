"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Wallet, ArrowUpRight, ArrowDownRight, Plus,
  Loader, AlertCircle, CreditCard, Receipt,
  DollarSign, Clock, Check, Zap, Star, Crown,
  ChevronRight, X, ExternalLink, Trash2,
  FileText, Shield, CircleDot,
} from "lucide-react";
import {
  getBalance, getTransactions, topUp,
  listBillingPlans, getSubscription, subscribe, cancelSubscription,
  createCheckout, createTopUpCheckout,
  listInvoices, listPaymentMethods, removePaymentMethod,
  type Transaction, type BillingPlan, type BillingSubscription,
  type Invoice, type PaymentMethod,
} from "@/lib/api/client";

const MAX_TOPUP = 1000;
const MIN_TOPUP = 5;

const PLAN_ICONS: Record<string, typeof Star> = {
  free: Zap,
  starter: Star,
  pro: Crown,
  scale: Shield,
};

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return dateStr;
  }
}

function formatDateShort(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return dateStr;
  }
}

// ══════════════════════════════════════════════
//  MAIN BILLING PANEL
// ══════════════════════════════════════════════

export function BillingPanel() {
  const [tab, setTab] = useState<"overview" | "plans" | "invoices" | "wallet">("overview");
  const [balance, setBalance] = useState<number | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [subscription, setSub] = useState<BillingSubscription | null>(null);
  const [currentPlan, setCurrentPlan] = useState<BillingPlan | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [balRes, txRes, plansRes, subRes, invRes, pmRes] = await Promise.allSettled([
        getBalance(),
        getTransactions(),
        listBillingPlans(),
        getSubscription(),
        listInvoices(),
        listPaymentMethods(),
      ]);

      if (balRes.status === "fulfilled") setBalance(balRes.value.balance);
      if (txRes.status === "fulfilled") setTransactions(txRes.value.transactions || []);
      if (plansRes.status === "fulfilled") setPlans(plansRes.value.plans || []);
      if (subRes.status === "fulfilled") {
        setSub(subRes.value.subscription);
        setCurrentPlan(subRes.value.plan);
      }
      if (invRes.status === "fulfilled") setInvoices(invRes.value.invoices || []);
      if (pmRes.status === "fulfilled") setPaymentMethods(pmRes.value.payment_methods || []);
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const tabs = [
    { id: "overview" as const, label: "Overview", icon: Wallet },
    { id: "plans" as const, label: "Plans", icon: Zap },
    { id: "invoices" as const, label: "Invoices", icon: FileText },
    { id: "wallet" as const, label: "Wallet", icon: DollarSign },
  ];

  return (
    <div>
      {/* Tab bar */}
      <div className="tab-bar">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`tab-item ${tab === id ? "active" : ""}`}
            onClick={() => setTab(id)}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="billing-error">
          <AlertCircle className="h-3.5 w-3.5" style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="billing-loading">
          <Loader className="h-4 w-4 animate-spin" />
          <span>Loading billing...</span>
        </div>
      ) : (
        <>
          {tab === "overview" && (
            <OverviewTab
              balance={balance}
              currentPlan={currentPlan}
              subscription={subscription}
              paymentMethods={paymentMethods}
              transactions={transactions}
              onReload={loadAll}
            />
          )}
          {tab === "plans" && (
            <PlansTab
              plans={plans}
              currentPlan={currentPlan}
              subscription={subscription}
              onReload={loadAll}
            />
          )}
          {tab === "invoices" && <InvoicesTab invoices={invoices} />}
          {tab === "wallet" && (
            <WalletTab
              balance={balance}
              transactions={transactions}
              onReload={loadAll}
            />
          )}
        </>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════
//  OVERVIEW TAB
// ══════════════════════════════════════════════

function OverviewTab({
  balance, currentPlan, subscription, paymentMethods, transactions, onReload,
}: {
  balance: number | null;
  currentPlan: BillingPlan | null;
  subscription: BillingSubscription | null;
  paymentMethods: PaymentMethod[];
  transactions: Transaction[];
  onReload: () => void;
}) {
  return (
    <div className="billing-overview">
      {/* Balance + Plan row */}
      <div className="billing-overview-cards">
        <div className="billing-card">
          <div className="billing-card-label">Wallet Balance</div>
          <div className="billing-card-value">${(balance ?? 0).toFixed(2)}</div>
          <div className="billing-card-sub">USD</div>
        </div>
        <div className="billing-card">
          <div className="billing-card-label">Current Plan</div>
          <div className="billing-card-value">{currentPlan?.name || "No plan"}</div>
          <div className="billing-card-sub">
            {currentPlan ? (
              currentPlan.amount_cents === 0 ? "Free" : `${formatCents(currentPlan.amount_cents)}/${currentPlan.interval}`
            ) : "Subscribe to get started"}
          </div>
        </div>
        <div className="billing-card">
          <div className="billing-card-label">Billing Period</div>
          <div className="billing-card-value">
            {subscription ? formatDate(subscription.current_period_end) : "—"}
          </div>
          <div className="billing-card-sub">
            {subscription ? `Since ${formatDate(subscription.current_period_start)}` : "No active period"}
          </div>
        </div>
      </div>

      {/* Plan features */}
      {currentPlan && currentPlan.features && (
        <div className="billing-section">
          <div className="billing-section-title">Plan Limits</div>
          <div className="billing-features">
            {Object.entries(currentPlan.features).map(([key, val]) => (
              <div key={key} className="billing-feature-row">
                <span className="billing-feature-key">{key.replace(/_/g, " ")}</span>
                <span className="billing-feature-val">
                  {val === -1 ? "Unlimited" : typeof val === "number" ? val.toLocaleString() : val}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Payment methods */}
      <div className="billing-section">
        <div className="billing-section-title">Payment Methods</div>
        {paymentMethods.length === 0 ? (
          <div className="billing-empty-sm">No payment methods configured. Pay with Stripe at checkout.</div>
        ) : (
          <div className="billing-pm-list">
            {paymentMethods.map((pm) => (
              <div key={pm.id} className="billing-pm-row">
                <CreditCard className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />
                <span className="billing-pm-label">{pm.label}</span>
                <span className="billing-pm-type">{pm.type} via {pm.provider}</span>
                {pm.is_default && <span className="billing-pm-default">Default</span>}
                <button
                  className="billing-pm-remove"
                  onClick={async () => {
                    await removePaymentMethod(pm.id);
                    onReload();
                  }}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent transactions */}
      <div className="billing-section">
        <div className="billing-section-title">Recent Activity</div>
        {transactions.length === 0 ? (
          <div className="billing-empty-sm">No transactions yet.</div>
        ) : (
          <div className="billing-txn-list">
            {transactions.slice(0, 5).map((tx) => (
              <TxnRow key={tx.id} tx={tx} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════
//  PLANS TAB
// ══════════════════════════════════════════════

function PlansTab({
  plans, currentPlan, subscription, onReload,
}: {
  plans: BillingPlan[];
  currentPlan: BillingPlan | null;
  subscription: BillingSubscription | null;
  onReload: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const handleSubscribe = async (planCode: string, amountCents: number) => {
    setBusy(planCode);
    setError("");
    try {
      if (amountCents === 0) {
        await subscribe(planCode);
        onReload();
      } else {
        const res = await createCheckout(
          planCode,
          window.location.origin + "/dashboard?billing=success",
          window.location.origin + "/dashboard?billing=cancelled",
        );
        if (res.free) {
          onReload();
        } else if (res.url) {
          window.open(res.url, "_blank");
        }
      }
    } catch (e: any) {
      setError(e.message);
    }
    setBusy(null);
  };

  const handleCancel = async () => {
    setBusy("cancel");
    setError("");
    try {
      await cancelSubscription();
      onReload();
    } catch (e: any) {
      setError(e.message);
    }
    setBusy(null);
  };

  return (
    <div>
      {error && (
        <div className="billing-error" style={{ marginBottom: 12 }}>
          <AlertCircle className="h-3.5 w-3.5" />
          <span>{error}</span>
        </div>
      )}

      <div className="billing-plans-grid">
        {plans.map((plan) => {
          const isCurrent = currentPlan?.code === plan.code;
          const Icon = PLAN_ICONS[plan.code] || Zap;

          return (
            <div key={plan.code} className={`billing-plan-card ${isCurrent ? "current" : ""}`}>
              <div className="billing-plan-header">
                <div className="billing-plan-icon">
                  <Icon className="h-5 w-5" />
                </div>
                <div className="billing-plan-name">{plan.name}</div>
                {isCurrent && <span className="billing-plan-badge">Current</span>}
              </div>

              <div className="billing-plan-price">
                {plan.amount_cents === 0 ? (
                  <span className="billing-plan-amount">Free</span>
                ) : (
                  <>
                    <span className="billing-plan-amount">{formatCents(plan.amount_cents)}</span>
                    <span className="billing-plan-interval">/{plan.interval}</span>
                  </>
                )}
              </div>

              <div className="billing-plan-desc">{plan.description}</div>

              <div className="billing-plan-features">
                {plan.features && Object.entries(plan.features).map(([key, val]) => (
                  <div key={key} className="billing-plan-feature">
                    <Check className="h-3 w-3" style={{ color: "var(--color-teal)", flexShrink: 0 }} />
                    <span>
                      {val === -1 ? "Unlimited" : val} {key.replace(/_/g, " ")}
                    </span>
                  </div>
                ))}
              </div>

              <div className="billing-plan-actions">
                {isCurrent ? (
                  <button
                    className="billing-plan-btn current"
                    onClick={handleCancel}
                    disabled={busy === "cancel"}
                  >
                    {busy === "cancel" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : "Cancel Plan"}
                  </button>
                ) : (
                  <button
                    className="billing-plan-btn"
                    onClick={() => handleSubscribe(plan.code, plan.amount_cents)}
                    disabled={busy === plan.code}
                  >
                    {busy === plan.code ? (
                      <Loader className="h-3.5 w-3.5 animate-spin" />
                    ) : plan.amount_cents === 0 ? (
                      "Get Started"
                    ) : (
                      <>Subscribe <ChevronRight className="h-3.5 w-3.5" /></>
                    )}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════
//  INVOICES TAB
// ══════════════════════════════════════════════

function InvoicesTab({ invoices }: { invoices: Invoice[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (invoices.length === 0) {
    return (
      <div className="panel-empty">
        <Receipt className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">No invoices</div>
        <div className="panel-empty-sub">Invoices will appear here after billing cycles</div>
      </div>
    );
  }

  return (
    <div className="billing-invoices-list">
      {invoices.map((inv) => (
        <div key={inv.id} className="billing-invoice-card">
          <div className="billing-invoice-row" onClick={() => setExpanded(expanded === inv.id ? null : inv.id)}>
            <div className="billing-invoice-left">
              <FileText className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />
              <span className="billing-invoice-number">{inv.number}</span>
            </div>
            <div className="billing-invoice-center">
              <span className={`billing-invoice-status ${inv.status}`}>{inv.status}</span>
              <span className={`billing-invoice-payment ${inv.payment_status}`}>{inv.payment_status}</span>
            </div>
            <div className="billing-invoice-right">
              <span className="billing-invoice-amount">{formatCents(inv.total_cents)}</span>
              <span className="billing-invoice-date">{formatDate(inv.created_at)}</span>
            </div>
          </div>

          {expanded === inv.id && inv.items && inv.items.length > 0 && (
            <div className="billing-invoice-details">
              {inv.items.map((item) => (
                <div key={item.id} className="billing-invoice-item">
                  <span className="billing-invoice-item-desc">{item.description}</span>
                  <span className="billing-invoice-item-amount">{formatCents(item.amount_cents)}</span>
                </div>
              ))}
              {inv.credits_applied_cents > 0 && (
                <div className="billing-invoice-item credits">
                  <span className="billing-invoice-item-desc">Credits applied</span>
                  <span className="billing-invoice-item-amount">-{formatCents(inv.credits_applied_cents)}</span>
                </div>
              )}
              <div className="billing-invoice-item total">
                <span className="billing-invoice-item-desc">Total due</span>
                <span className="billing-invoice-item-amount">{formatCents(inv.total_cents)}</span>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════
//  WALLET TAB
// ══════════════════════════════════════════════

function WalletTab({
  balance, transactions, onReload,
}: {
  balance: number | null;
  transactions: Transaction[];
  onReload: () => void;
}) {
  const [showTopUp, setShowTopUp] = useState(false);

  return (
    <div>
      {/* Balance card */}
      <div className="billing-balance-card">
        <div className="billing-balance-left">
          <div className="billing-balance-label">Wallet Balance</div>
          <div className="billing-balance-amount">${(balance ?? 0).toFixed(2)}</div>
          <div className="billing-balance-currency">USD — prepaid credits</div>
        </div>
        <div className="billing-balance-right">
          <button className="billing-topup-btn" onClick={() => setShowTopUp(true)}>
            <Plus className="h-3.5 w-3.5" />
            Top Up
          </button>
        </div>
      </div>

      {showTopUp && (
        <TopUpForm
          onClose={() => setShowTopUp(false)}
          onSuccess={() => { setShowTopUp(false); onReload(); }}
        />
      )}

      {/* Transactions */}
      <div className="billing-section">
        <div className="billing-section-title">
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
          <div className="billing-txn-list">
            {transactions.map((tx) => <TxnRow key={tx.id} tx={tx} />)}
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════
//  SHARED COMPONENTS
// ══════════════════════════════════════════════

function TxnRow({ tx }: { tx: Transaction }) {
  return (
    <div className="billing-txn-row">
      <div className={`billing-txn-icon ${tx.amount >= 0 ? "in" : "out"}`}>
        {tx.amount >= 0 ? (
          <ArrowDownRight className="h-3.5 w-3.5" />
        ) : (
          <ArrowUpRight className="h-3.5 w-3.5" />
        )}
      </div>
      <div className="billing-txn-info">
        <div className="billing-txn-desc">{tx.description || tx.type}</div>
        <div className="billing-txn-meta">
          <Clock className="h-2.5 w-2.5" />
          {formatDateShort(tx.created_at)}
          {tx.reference && <span>· {tx.reference}</span>}
        </div>
      </div>
      <div className={`billing-txn-amount ${tx.amount >= 0 ? "in" : "out"}`}>
        {tx.amount >= 0 ? "+" : ""}${Math.abs(tx.amount).toFixed(2)}
      </div>
    </div>
  );
}

function TopUpForm({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [useStripe, setUseStripe] = useState(false);

  const presets = [10, 25, 50, 100];

  const handleSubmit = async () => {
    const num = parseFloat(amount);
    if (isNaN(num) || num < MIN_TOPUP) { setError(`Minimum top-up is $${MIN_TOPUP}`); return; }
    if (num > MAX_TOPUP) { setError(`Maximum top-up is $${MAX_TOPUP}`); return; }

    setBusy(true);
    setError("");
    try {
      if (useStripe) {
        const res = await createTopUpCheckout(
          Math.round(num * 100),
          window.location.origin + "/dashboard?topup=success",
          window.location.origin + "/dashboard?topup=cancelled",
        );
        if (res.url) {
          window.open(res.url, "_blank");
          onClose();
        }
      } else {
        await topUp(num, reference.trim());
        onSuccess();
      }
    } catch (e: any) {
      setError(e.message);
    }
    setBusy(false);
  };

  return (
    <div className="billing-topup-form">
      <div className="billing-topup-header">
        <span style={{ fontSize: 13, fontWeight: 600 }}>Top Up Balance</span>
        <button className="ibtn" onClick={onClose}><X className="h-3.5 w-3.5" /></button>
      </div>

      {error && <div className="billing-error" style={{ marginBottom: 10 }}>{error}</div>}

      <div className="billing-topup-presets">
        {presets.map((p) => (
          <button
            key={p}
            className={`billing-topup-preset ${amount === String(p) ? "active" : ""}`}
            onClick={() => setAmount(String(p))}
          >
            ${p}
          </button>
        ))}
      </div>

      <div className="billing-topup-fields">
        <div className="billing-topup-field">
          <label className="settings-label">Amount ($)</label>
          <input
            className="settings-input"
            type="number"
            min={MIN_TOPUP}
            max={MAX_TOPUP}
            step="0.01"
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <div className="billing-topup-field">
          <label className="settings-label">Reference (optional)</label>
          <input
            className="settings-input"
            placeholder="e.g. invoice #123"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
        </div>
      </div>

      {/* Payment method toggle */}
      <div className="billing-topup-method">
        <button
          className={`billing-topup-method-btn ${!useStripe ? "active" : ""}`}
          onClick={() => setUseStripe(false)}
        >
          <Wallet className="h-3 w-3" /> Wallet Credits
        </button>
        <button
          className={`billing-topup-method-btn ${useStripe ? "active" : ""}`}
          onClick={() => setUseStripe(true)}
        >
          <CreditCard className="h-3 w-3" /> Stripe
        </button>
      </div>

      <div className="billing-topup-actions">
        <button className="billing-topup-cancel" onClick={onClose}>Cancel</button>
        <button className="billing-topup-submit" onClick={handleSubmit} disabled={busy}>
          {busy ? <Loader className="h-3.5 w-3.5 animate-spin" /> : useStripe ? <ExternalLink className="h-3.5 w-3.5" /> : <DollarSign className="h-3.5 w-3.5" />}
          <span>{busy ? "Processing..." : useStripe ? `Pay $${amount || "0"} with Stripe` : `Top Up $${amount || "0"}`}</span>
        </button>
      </div>
    </div>
  );
}
