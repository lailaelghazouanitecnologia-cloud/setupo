"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Wallet, ArrowUpRight, ArrowDownRight, Plus,
  Loader, AlertCircle, CreditCard, Receipt,
  DollarSign, Clock, Check, Zap, Star, Crown,
  ChevronRight, X, ExternalLink, Trash2,
  FileText, Shield, CircleDot, Tag, RefreshCw,
  BarChart3, Percent, Activity, Gift,
} from "lucide-react";
import {
  getBalance, getTransactions, topUp,
  listBillingPlans, getSubscription, subscribe, cancelSubscription,
  pauseSubscription, resumeSubscription,
  createCheckout, createTopUpCheckout,
  listInvoices, listPaymentMethods, removePaymentMethod,
  applyCoupon, listAppliedCoupons, removeAppliedCoupon,
  listCreditNotes,
  getUsageSummary,
  listBillingWallets, createBillingWallet, topUpBillingWallet,
  listBillingEvents,
  type Transaction, type BillingPlan, type BillingSubscription,
  type Invoice, type PaymentMethod, type AppliedCoupon,
  type CreditNote, type BillingWallet, type BillingEvent,
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
  const [tab, setTab] = useState<"overview" | "plans" | "invoices" | "wallet" | "coupons" | "usage">("overview");
  const [balance, setBalance] = useState<number | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [subscription, setSub] = useState<BillingSubscription | null>(null);
  const [currentPlan, setCurrentPlan] = useState<BillingPlan | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [appliedCoupons, setAppliedCoupons] = useState<AppliedCoupon[]>([]);
  const [creditNotes, setCreditNotes] = useState<CreditNote[]>([]);
  const [wallets, setWallets] = useState<BillingWallet[]>([]);
  const [usage, setUsage] = useState<Record<string, number>>({});
  const [events, setEvents] = useState<BillingEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [balRes, txRes, plansRes, subRes, invRes, pmRes, cpnRes, cnRes, walRes, usageRes, evtRes] = await Promise.allSettled([
        getBalance(),
        getTransactions(),
        listBillingPlans(),
        getSubscription(),
        listInvoices(),
        listPaymentMethods(),
        listAppliedCoupons(),
        listCreditNotes(),
        listBillingWallets(),
        getUsageSummary(),
        listBillingEvents(),
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
      if (cpnRes.status === "fulfilled") setAppliedCoupons(cpnRes.value.applied_coupons || []);
      if (cnRes.status === "fulfilled") setCreditNotes(cnRes.value.credit_notes || []);
      if (walRes.status === "fulfilled") setWallets(walRes.value.wallets || []);
      if (usageRes.status === "fulfilled") setUsage(usageRes.value.usage || {});
      if (evtRes.status === "fulfilled") setEvents(evtRes.value.events || []);
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
    { id: "coupons" as const, label: "Coupons", icon: Tag },
    { id: "usage" as const, label: "Usage", icon: BarChart3 },
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
              appliedCoupons={appliedCoupons}
              creditNotes={creditNotes}
              wallets={wallets}
              usage={usage}
              events={events}
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
          {tab === "invoices" && <InvoicesTab invoices={invoices} creditNotes={creditNotes} />}
          {tab === "wallet" && (
            <WalletTab
              balance={balance}
              transactions={transactions}
              wallets={wallets}
              onReload={loadAll}
            />
          )}
          {tab === "coupons" && (
            <CouponsTab
              appliedCoupons={appliedCoupons}
              onReload={loadAll}
            />
          )}
          {tab === "usage" && (
            <UsageTab
              usage={usage}
              subscription={subscription}
              currentPlan={currentPlan}
              events={events}
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
  balance, currentPlan, subscription, paymentMethods, transactions,
  appliedCoupons, creditNotes, wallets, usage, events, onReload,
}: {
  balance: number | null;
  currentPlan: BillingPlan | null;
  subscription: BillingSubscription | null;
  paymentMethods: PaymentMethod[];
  transactions: Transaction[];
  appliedCoupons: AppliedCoupon[];
  creditNotes: CreditNote[];
  wallets: BillingWallet[];
  usage: Record<string, number>;
  events: BillingEvent[];
  onReload: () => void;
}) {
  const walletTotal = wallets.reduce((sum, w) => sum + (w.status === "active" ? w.balance_cents : 0), 0);
  const cnBalance = creditNotes.reduce((sum, cn) => sum + (cn.status === "available" ? cn.balance_cents : 0), 0);

  return (
    <div className="billing-overview">
      {/* Balance + Plan + Credits row */}
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
        <div className="billing-card">
          <div className="billing-card-label">Credits Available</div>
          <div className="billing-card-value">{formatCents(walletTotal + cnBalance)}</div>
          <div className="billing-card-sub">
            {wallets.length > 0 ? `${wallets.length} wallet(s)` : ""}{cnBalance > 0 ? ` + ${formatCents(cnBalance)} credit notes` : ""}
          </div>
        </div>
      </div>

      {/* Subscription status */}
      {subscription && subscription.status !== "active" && (
        <div className="billing-status-banner" data-status={subscription.status}>
          <CircleDot className="h-3.5 w-3.5" />
          <span>Subscription status: <strong>{subscription.status}</strong></span>
        </div>
      )}

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

      {/* Current period usage */}
      {Object.keys(usage).length > 0 && (
        <div className="billing-section">
          <div className="billing-section-title">
            <BarChart3 className="h-3.5 w-3.5" style={{ display: "inline", marginRight: 6, verticalAlign: "middle" }} />
            Current Period Usage
          </div>
          <div className="billing-usage-grid">
            {Object.entries(usage).map(([metric, value]) => {
              const limit = currentPlan?.features?.[metric.replace("_hour", "s").replace("_gb", "_gb")] ?? 0;
              const pct = limit > 0 && limit !== -1 ? Math.min(100, (value / limit) * 100) : 0;
              return (
                <div key={metric} className="billing-usage-item">
                  <div className="billing-usage-label">{metric.replace(/_/g, " ")}</div>
                  <div className="billing-usage-bar-container">
                    <div className="billing-usage-bar" style={{ width: `${pct}%` }} data-level={pct > 90 ? "danger" : pct > 70 ? "warn" : "ok"} />
                  </div>
                  <div className="billing-usage-value">
                    {value.toFixed(1)} {limit > 0 && limit !== -1 ? `/ ${limit}` : ""}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Active coupons */}
      {appliedCoupons.length > 0 && (
        <div className="billing-section">
          <div className="billing-section-title">
            <Tag className="h-3.5 w-3.5" style={{ display: "inline", marginRight: 6, verticalAlign: "middle" }} />
            Active Discounts ({appliedCoupons.length})
          </div>
          <div className="billing-coupon-list">
            {appliedCoupons.map((ac) => (
              <div key={ac.id} className="billing-coupon-badge">
                <Percent className="h-3 w-3" />
                <span>Coupon applied</span>
                {ac.periods_remaining > 0 && <span className="billing-coupon-periods">{ac.periods_remaining} period(s) left</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Payment methods */}
      <div className="billing-section">
        <div className="billing-section-title">Payment Methods</div>
        {paymentMethods.length === 0 ? (
          <div className="billing-empty-sm">No payment methods configured. Pay with Stripe or Google Pay at checkout.</div>
        ) : (
          <div className="billing-pm-list">
            {paymentMethods.map((pm) => (
              <div key={pm.id} className="billing-pm-row">
                <CreditCard className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />
                <span className="billing-pm-label">{pm.label}</span>
                <span className="billing-pm-type">{pm.type.replace(/_/g, " ")} via {pm.provider}</span>
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

      {/* Recent billing events */}
      {events.length > 0 && (
        <div className="billing-section">
          <div className="billing-section-title">
            <Activity className="h-3.5 w-3.5" style={{ display: "inline", marginRight: 6, verticalAlign: "middle" }} />
            Recent Billing Events
          </div>
          <div className="billing-events-list">
            {events.slice(0, 8).map((evt) => (
              <div key={evt.id} className="billing-event-row">
                <span className="billing-event-type">{evt.event_type.replace(/\./g, " ")}</span>
                <span className="billing-event-date">{formatDateShort(evt.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

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
          ["card"],
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

  const handlePause = async () => {
    setBusy("pause");
    setError("");
    try {
      await pauseSubscription();
      onReload();
    } catch (e: any) {
      setError(e.message);
    }
    setBusy(null);
  };

  const handleResume = async () => {
    setBusy("resume");
    setError("");
    try {
      await resumeSubscription();
      onReload();
    } catch (e: any) {
      setError(e.message);
    }
    setBusy(null);
  };

  const isUpgrade = (plan: BillingPlan) => {
    if (!currentPlan) return true;
    return plan.amount_cents > currentPlan.amount_cents;
  };

  return (
    <div>
      {error && (
        <div className="billing-error" style={{ marginBottom: 12 }}>
          <AlertCircle className="h-3.5 w-3.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Subscription controls */}
      {subscription && subscription.status === "paused" && (
        <div className="billing-status-banner" data-status="paused" style={{ marginBottom: 12 }}>
          <CircleDot className="h-3.5 w-3.5" />
          <span>Subscription is paused.</span>
          <button className="billing-inline-btn" onClick={handleResume} disabled={busy === "resume"}>
            {busy === "resume" ? <Loader className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
            Resume
          </button>
        </div>
      )}

      <div className="billing-plans-grid">
        {plans.map((plan) => {
          const isCurrent = currentPlan?.code === plan.code;
          const Icon = PLAN_ICONS[plan.code] || Zap;
          const upgrade = isUpgrade(plan);

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
                  <div className="billing-plan-current-actions">
                    {subscription?.status === "active" && (
                      <button
                        className="billing-plan-btn secondary"
                        onClick={handlePause}
                        disabled={busy === "pause"}
                      >
                        {busy === "pause" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : "Pause"}
                      </button>
                    )}
                    <button
                      className="billing-plan-btn current"
                      onClick={handleCancel}
                      disabled={busy === "cancel"}
                    >
                      {busy === "cancel" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : "Cancel Plan"}
                    </button>
                  </div>
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
                      <>{upgrade ? "Upgrade" : "Switch"} <ChevronRight className="h-3.5 w-3.5" /></>
                    )}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {currentPlan && currentPlan.amount_cents > 0 && (
        <div className="billing-proration-note">
          Switching plans mid-cycle will generate a proration credit for unused time on your current plan.
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════
//  INVOICES TAB (with credit notes)
// ══════════════════════════════════════════════

function InvoicesTab({ invoices, creditNotes }: { invoices: Invoice[]; creditNotes: CreditNote[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showCN, setShowCN] = useState(false);

  return (
    <div>
      {/* Toggle between invoices and credit notes */}
      <div className="billing-sub-tabs">
        <button className={`billing-sub-tab ${!showCN ? "active" : ""}`} onClick={() => setShowCN(false)}>
          <FileText className="h-3 w-3" /> Invoices ({invoices.length})
        </button>
        <button className={`billing-sub-tab ${showCN ? "active" : ""}`} onClick={() => setShowCN(true)}>
          <RefreshCw className="h-3 w-3" /> Credit Notes ({creditNotes.length})
        </button>
      </div>

      {showCN ? (
        <CreditNotesView creditNotes={creditNotes} />
      ) : (
        <InvoicesView invoices={invoices} expanded={expanded} setExpanded={setExpanded} />
      )}
    </div>
  );
}

function InvoicesView({
  invoices, expanded, setExpanded,
}: {
  invoices: Invoice[];
  expanded: string | null;
  setExpanded: (id: string | null) => void;
}) {
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
                <div key={item.id} className={`billing-invoice-item ${item.type === "discount" ? "discount" : ""} ${item.type === "tax" ? "tax" : ""}`}>
                  <span className="billing-invoice-item-desc">
                    {item.type === "discount" && <Tag className="h-2.5 w-2.5" style={{ display: "inline", marginRight: 4 }} />}
                    {item.type === "tax" && <Percent className="h-2.5 w-2.5" style={{ display: "inline", marginRight: 4 }} />}
                    {item.description}
                  </span>
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

function CreditNotesView({ creditNotes }: { creditNotes: CreditNote[] }) {
  if (creditNotes.length === 0) {
    return (
      <div className="panel-empty">
        <RefreshCw className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <div className="panel-empty-title">No credit notes</div>
        <div className="panel-empty-sub">Credit notes are issued for refunds, proration adjustments, and corrections</div>
      </div>
    );
  }

  return (
    <div className="billing-credit-notes-list">
      {creditNotes.map((cn) => (
        <div key={cn.id} className="billing-cn-card">
          <div className="billing-cn-row">
            <div className="billing-cn-left">
              <RefreshCw className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />
              <span className="billing-cn-number">{cn.number}</span>
            </div>
            <div className="billing-cn-center">
              <span className={`billing-cn-status ${cn.status}`}>{cn.status}</span>
              <span className="billing-cn-type">{cn.credit_type}</span>
            </div>
            <div className="billing-cn-right">
              <div className="billing-cn-amounts">
                <span className="billing-cn-total">{formatCents(cn.total_cents)}</span>
                {cn.balance_cents < cn.total_cents && (
                  <span className="billing-cn-remaining">{formatCents(cn.balance_cents)} remaining</span>
                )}
              </div>
              <span className="billing-cn-date">{formatDate(cn.created_at)}</span>
            </div>
          </div>
          {cn.reason && <div className="billing-cn-reason">{cn.reason}</div>}
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════
//  WALLET TAB (with multiple wallets)
// ══════════════════════════════════════════════

function WalletTab({
  balance, transactions, wallets, onReload,
}: {
  balance: number | null;
  transactions: Transaction[];
  wallets: BillingWallet[];
  onReload: () => void;
}) {
  const [showTopUp, setShowTopUp] = useState(false);
  const [showNewWallet, setShowNewWallet] = useState(false);

  return (
    <div>
      {/* Legacy balance card */}
      <div className="billing-balance-card">
        <div className="billing-balance-left">
          <div className="billing-balance-label">Account Balance</div>
          <div className="billing-balance-amount">${(balance ?? 0).toFixed(2)}</div>
          <div className="billing-balance-currency">USD — legacy balance</div>
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

      {/* Prepaid wallets (Lago-style) */}
      <div className="billing-section">
        <div className="billing-section-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>
            <Wallet className="h-3.5 w-3.5" style={{ display: "inline", marginRight: 6, verticalAlign: "middle" }} />
            Prepaid Wallets ({wallets.length}/5)
          </span>
          {wallets.length < 5 && (
            <button className="billing-inline-btn" onClick={() => setShowNewWallet(true)}>
              <Plus className="h-3 w-3" /> New Wallet
            </button>
          )}
        </div>

        {showNewWallet && (
          <NewWalletForm
            onClose={() => setShowNewWallet(false)}
            onSuccess={() => { setShowNewWallet(false); onReload(); }}
          />
        )}

        {wallets.length === 0 ? (
          <div className="billing-empty-sm">No prepaid wallets. Create one to use credits for invoice payments.</div>
        ) : (
          <div className="billing-wallets-grid">
            {wallets.map((w) => (
              <WalletCard key={w.id} wallet={w} onReload={onReload} />
            ))}
          </div>
        )}
      </div>

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

function WalletCard({ wallet, onReload }: { wallet: BillingWallet; onReload: () => void }) {
  const [showTopUp, setShowTopUp] = useState(false);
  const [busy, setBusy] = useState(false);
  const [topUpAmount, setTopUpAmount] = useState("");

  const handleTopUp = async () => {
    const num = parseFloat(topUpAmount);
    if (isNaN(num) || num <= 0) return;
    setBusy(true);
    try {
      await topUpBillingWallet(wallet.id, num);
      setShowTopUp(false);
      setTopUpAmount("");
      onReload();
    } catch { }
    setBusy(false);
  };

  return (
    <div className={`billing-wallet-card ${wallet.status !== "active" ? "inactive" : ""}`}>
      <div className="billing-wallet-header">
        <Wallet className="h-3.5 w-3.5" />
        <span className="billing-wallet-name">{wallet.name}</span>
        <span className={`billing-wallet-status ${wallet.status}`}>{wallet.status}</span>
      </div>
      <div className="billing-wallet-balance">{formatCents(wallet.balance_cents)}</div>
      <div className="billing-wallet-meta">
        <span>{wallet.credits_balance.toFixed(2)} credits</span>
        <span>Priority: {wallet.priority}</span>
        {wallet.expiration_at && <span>Expires: {formatDate(wallet.expiration_at)}</span>}
      </div>
      {wallet.status === "active" && (
        <div className="billing-wallet-actions">
          {showTopUp ? (
            <div className="billing-wallet-topup-inline">
              <input
                className="settings-input"
                type="number" min="1" step="0.01"
                placeholder="Credits"
                value={topUpAmount}
                onChange={(e) => setTopUpAmount(e.target.value)}
                style={{ width: 80, fontSize: 12 }}
              />
              <button className="billing-inline-btn" onClick={handleTopUp} disabled={busy}>
                {busy ? <Loader className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
              </button>
              <button className="billing-inline-btn" onClick={() => setShowTopUp(false)}>
                <X className="h-3 w-3" />
              </button>
            </div>
          ) : (
            <button className="billing-inline-btn" onClick={() => setShowTopUp(true)}>
              <Plus className="h-3 w-3" /> Add Credits
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function NewWalletForm({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [name, setName] = useState("Primary");
  const [credits, setCredits] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const handleCreate = async () => {
    setBusy(true);
    setError("");
    try {
      await createBillingWallet({
        name: name.trim() || "Primary",
        paid_credits: parseFloat(credits) || 0,
      });
      onSuccess();
    } catch (e: any) {
      setError(e.message);
    }
    setBusy(false);
  };

  return (
    <div className="billing-topup-form" style={{ marginBottom: 12 }}>
      <div className="billing-topup-header">
        <span style={{ fontSize: 13, fontWeight: 600 }}>New Wallet</span>
        <button className="ibtn" onClick={onClose}><X className="h-3.5 w-3.5" /></button>
      </div>
      {error && <div className="billing-error" style={{ marginBottom: 10 }}>{error}</div>}
      <div className="billing-topup-fields">
        <div className="billing-topup-field">
          <label className="settings-label">Name</label>
          <input className="settings-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Wallet name" />
        </div>
        <div className="billing-topup-field">
          <label className="settings-label">Initial Credits</label>
          <input className="settings-input" type="number" min="0" step="0.01" value={credits} onChange={(e) => setCredits(e.target.value)} placeholder="0.00" />
        </div>
      </div>
      <div className="billing-topup-actions">
        <button className="billing-topup-cancel" onClick={onClose}>Cancel</button>
        <button className="billing-topup-submit" onClick={handleCreate} disabled={busy}>
          {busy ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          <span>Create Wallet</span>
        </button>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════
//  COUPONS TAB
// ══════════════════════════════════════════════

function CouponsTab({
  appliedCoupons, onReload,
}: {
  appliedCoupons: AppliedCoupon[];
  onReload: () => void;
}) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleApply = async () => {
    if (!code.trim()) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await applyCoupon(code.trim().toUpperCase());
      setSuccess("Coupon applied successfully!");
      setCode("");
      onReload();
    } catch (e: any) {
      setError(e.message);
    }
    setBusy(false);
  };

  const handleRemove = async (appliedId: string) => {
    try {
      await removeAppliedCoupon(appliedId);
      onReload();
    } catch { }
  };

  return (
    <div>
      {/* Apply coupon code */}
      <div className="billing-coupon-form">
        <div className="billing-coupon-form-header">
          <Gift className="h-4 w-4" />
          <span style={{ fontWeight: 600, fontSize: 13 }}>Have a promo code?</span>
        </div>
        {error && <div className="billing-error" style={{ marginBottom: 10 }}><AlertCircle className="h-3 w-3" /> {error}</div>}
        {success && <div className="billing-success" style={{ marginBottom: 10 }}><Check className="h-3 w-3" /> {success}</div>}
        <div className="billing-coupon-input-row">
          <input
            className="settings-input"
            placeholder="Enter coupon code"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && handleApply()}
            style={{ flex: 1, textTransform: "uppercase", letterSpacing: 1 }}
          />
          <button className="billing-topup-submit" onClick={handleApply} disabled={busy || !code.trim()}>
            {busy ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Tag className="h-3.5 w-3.5" />}
            <span>Apply</span>
          </button>
        </div>
      </div>

      {/* Active coupons */}
      <div className="billing-section">
        <div className="billing-section-title">Active Coupons ({appliedCoupons.length})</div>
        {appliedCoupons.length === 0 ? (
          <div className="panel-empty">
            <Tag className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
            <div className="panel-empty-title">No active coupons</div>
            <div className="panel-empty-sub">Enter a promo code above to get a discount</div>
          </div>
        ) : (
          <div className="billing-applied-list">
            {appliedCoupons.map((ac) => (
              <div key={ac.id} className="billing-applied-row">
                <div className="billing-applied-info">
                  <Tag className="h-3.5 w-3.5" style={{ color: "var(--color-teal)" }} />
                  <div>
                    <div className="billing-applied-id">Coupon Applied</div>
                    <div className="billing-applied-meta">
                      Applied {formatDate(ac.applied_at)}
                      {ac.periods_remaining > 0 && ` · ${ac.periods_remaining} period(s) remaining`}
                      {ac.amount_cents_used > 0 && ` · ${formatCents(ac.amount_cents_used)} used`}
                    </div>
                  </div>
                </div>
                <button className="billing-pm-remove" onClick={() => handleRemove(ac.id)}>
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════
//  USAGE TAB
// ══════════════════════════════════════════════

function UsageTab({
  usage, subscription, currentPlan, events,
}: {
  usage: Record<string, number>;
  subscription: BillingSubscription | null;
  currentPlan: BillingPlan | null;
  events: BillingEvent[];
}) {
  const usageEvents = events.filter((e) => e.event_type === "usage.recorded");

  return (
    <div>
      {/* Usage summary */}
      <div className="billing-section">
        <div className="billing-section-title">
          <BarChart3 className="h-3.5 w-3.5" style={{ display: "inline", marginRight: 6, verticalAlign: "middle" }} />
          Current Period Usage
        </div>
        {subscription && (
          <div className="billing-usage-period">
            {formatDate(subscription.current_period_start)} — {formatDate(subscription.current_period_end)}
          </div>
        )}

        {Object.keys(usage).length === 0 ? (
          <div className="panel-empty">
            <BarChart3 className="h-10 w-10" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
            <div className="panel-empty-title">No usage recorded</div>
            <div className="panel-empty-sub">Usage events will appear here as you use resources</div>
          </div>
        ) : (
          <div className="billing-usage-detail-grid">
            {Object.entries(usage).map(([metric, value]) => {
              const features = currentPlan?.features || {};
              const limitKey = metric.replace("_hour", "s").replace("_gb", "_gb");
              const limit = features[limitKey] ?? 0;
              const pct = limit > 0 && limit !== -1 ? Math.min(100, (value / limit) * 100) : 0;
              const rate = ({"compute_hour": 0.007, "storage_gb": 0.05, "bandwidth_gb": 0.10} as Record<string, number>)[metric] || 0;
              const overage = limit > 0 && limit !== -1 ? Math.max(0, value - limit) : 0;
              const overageCost = overage * rate;

              return (
                <div key={metric} className="billing-usage-detail-card">
                  <div className="billing-usage-detail-header">
                    <span className="billing-usage-detail-name">{metric.replace(/_/g, " ")}</span>
                    <span className={`billing-usage-detail-pct ${pct > 90 ? "danger" : pct > 70 ? "warn" : ""}`}>
                      {limit > 0 && limit !== -1 ? `${pct.toFixed(0)}%` : "Unlimited"}
                    </span>
                  </div>
                  <div className="billing-usage-bar-container" style={{ height: 6 }}>
                    <div className="billing-usage-bar" style={{ width: `${pct}%` }} data-level={pct > 90 ? "danger" : pct > 70 ? "warn" : "ok"} />
                  </div>
                  <div className="billing-usage-detail-stats">
                    <span>Used: {value.toFixed(2)}</span>
                    {limit > 0 && limit !== -1 && <span>Limit: {limit}</span>}
                    {overage > 0 && <span className="billing-usage-overage">Overage: {overage.toFixed(2)} (${overageCost.toFixed(2)})</span>}
                    {rate > 0 && <span>Rate: ${rate}/unit</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Usage events */}
      {usageEvents.length > 0 && (
        <div className="billing-section">
          <div className="billing-section-title">
            <Activity className="h-3.5 w-3.5" style={{ display: "inline", marginRight: 6, verticalAlign: "middle" }} />
            Recent Usage Events
          </div>
          <div className="billing-events-list">
            {usageEvents.slice(0, 20).map((evt) => (
              <div key={evt.id} className="billing-event-row">
                <span className="billing-event-type">{evt.data?.metric || "usage"}</span>
                <span className="billing-event-detail">{evt.data?.units?.toFixed(2) || "—"} units</span>
                <span className="billing-event-date">{formatDateShort(evt.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
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
          ["card"],
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
          <CreditCard className="h-3 w-3" /> Stripe / Google Pay
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
