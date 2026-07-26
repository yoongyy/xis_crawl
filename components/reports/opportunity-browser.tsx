"use client";

import { useEffect, useState } from "react";
import {
  Building2,
  Clock3,
  ExternalLink,
  MapPin,
  MessageSquareText,
  PackageSearch,
  ShieldAlert,
  X,
} from "lucide-react";
import { DemoLabel } from "@/components/reports/report-ui";
import type {
  InsuranceOpportunity,
  OpportunityLevel,
} from "@/data/sample-insurance-report";
import { useLanguage } from "@/lib/language-context";

const levelStyles: Record<OpportunityLevel, string> = {
  very_high: "border-rose-200 bg-rose-50 text-rose-700",
  high: "border-amber-200 bg-amber-50 text-amber-800",
  medium: "border-sky-200 bg-sky-50 text-sky-700",
  low: "border-slate-200 bg-slate-50 text-slate-600",
};

const levelLabels: Record<OpportunityLevel, { en: string; zh: string }> = {
  very_high: { en: "Very high", zh: "极高" },
  high: { en: "High", zh: "高" },
  medium: { en: "Medium", zh: "中" },
  low: { en: "Low", zh: "低" },
};

function Detail({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-slate-400">
        {icon}
        {label}
      </dt>
      <dd className="mt-1 truncate text-xs font-semibold text-slate-700" title={value}>
        {value}
      </dd>
    </div>
  );
}
export function OpportunityCard({
  opportunity,
  compact = false,
  onOpen,
}: {
  opportunity: InsuranceOpportunity;
  compact?: boolean;
  onOpen?: () => void;
}) {
  const { language } = useLanguage();
  const isEnglish = language === "en";

  return (
    <article className="flex h-full min-w-0 flex-col rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <DemoLabel />
        <span className="rounded border border-teal-200 bg-teal-50 px-2 py-1 text-[10px] font-bold uppercase text-teal-800">
          {opportunity.opportunityType}
        </span>
      </div>

      <h3 className="text-base font-bold leading-6 text-navy">
        {opportunity.title}
      </h3>
      <blockquote
        className={`mt-3 border-l-2 border-primary pl-3 text-sm leading-6 text-slate-700 ${
          compact ? "line-clamp-3" : ""
        }`}
      >
        &ldquo;{opportunity.quote}&rdquo;
      </blockquote>

      <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4 border-y border-slate-100 py-4">
        <Detail
          icon={<MapPin className="h-3.5 w-3.5" />}
          label={isEnglish ? "Location" : "地点"}
          value={opportunity.location}
        />
        <Detail
          icon={<PackageSearch className="h-3.5 w-3.5" />}
          label={isEnglish ? "Product" : "产品"}
          value={opportunity.product}
        />
        <Detail
          icon={<Building2 className="h-3.5 w-3.5" />}
          label={isEnglish ? "Insurer" : "保险公司"}
          value={opportunity.insurer ?? (isEnglish ? "Not specified" : "未注明")}
        />
        <Detail
          icon={<Clock3 className="h-3.5 w-3.5" />}
          label={isEnglish ? "Posted" : "发布时间"}
          value={opportunity.postedAt}
        />
      </dl>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span
          className={`rounded border px-2 py-1 text-[10px] font-bold uppercase ${levelStyles[opportunity.level]}`}
        >
          {levelLabels[opportunity.level][language]}{" "}
          {isEnglish ? "opportunity" : "机会"}
        </span>
        <span className="text-[11px] font-semibold text-slate-500">
          {opportunity.confidence}% {isEnglish ? "confidence" : "可信度"}
        </span>
      </div>

      <div className="mt-4 rounded-md bg-slate-50 p-3">
        <p className="text-[10px] font-bold uppercase text-slate-400">
          {isEnglish ? "Why it matters" : "为什么值得关注"}
        </p>
        <p className="mt-1 text-xs leading-5 text-slate-600">
          {opportunity.whyItMatters}
        </p>
      </div>

      <div className="mt-auto grid gap-2 pt-5 sm:grid-cols-2">
        <a
          href={opportunity.sourceUrl ?? "#demo-source"}
          className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700 hover:border-primary hover:text-primary"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          {isEnglish ? "View Demo Source" : "查看演示来源"}
        </a>
        <button
          type="button"
          onClick={onOpen}
          className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-bold text-white hover:bg-primary-dark"
        >
          <MessageSquareText className="h-3.5 w-3.5" />
          {isEnglish ? "See Suggested Response" : "查看建议回复"}
        </button>
      </div>
    </article>
  );
}

function OpportunityModal({
  opportunity,
  onClose,
}: {
  opportunity: InsuranceOpportunity;
  onClose: () => void;
}) {
  const { language } = useLanguage();
  const isEnglish = language === "en";

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[70] flex items-end justify-center bg-navy/60 sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="opportunity-title"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="max-h-[94vh] w-full max-w-4xl overflow-y-auto rounded-t-lg bg-white shadow-2xl sm:rounded-lg">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-5 py-4">
          <div className="flex items-center gap-2">
            <DemoLabel />
            <span
              className={`rounded border px-2 py-1 text-[10px] font-bold uppercase ${levelStyles[opportunity.level]}`}
            >
              {levelLabels[opportunity.level][language]}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={isEnglish ? "Close opportunity details" : "关闭机会详情"}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-navy"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 sm:p-7">
          <p className="text-xs font-bold uppercase text-primary">
            {opportunity.opportunityType}
          </p>
          <h2
            id="opportunity-title"
            className="mt-2 text-xl font-extrabold text-navy sm:text-2xl"
          >
            {opportunity.title}
          </h2>
          <blockquote className="mt-4 border-l-4 border-primary bg-slate-50 p-4 text-sm leading-6 text-slate-700">
            &ldquo;{opportunity.quote}&rdquo;
          </blockquote>

          <div className="mt-7 grid gap-6 lg:grid-cols-2">
            <section>
              <h3 className="text-sm font-bold text-navy">
                {isEnglish ? "Public context" : "公开语境"}
              </h3>
              <p className="mt-2 text-xs leading-5 text-slate-600">
                {opportunity.publicContext}
              </p>
            </section>
            <section>
              <h3 className="text-sm font-bold text-navy">
                {isEnglish ? "Opportunity classification" : "机会分类"}
              </h3>
              <dl className="mt-2 grid grid-cols-2 gap-3 text-xs">
                <div>
                  <dt className="text-slate-400">{isEnglish ? "Product" : "产品"}</dt>
                  <dd className="mt-1 font-semibold text-slate-700">
                    {opportunity.product}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">{isEnglish ? "Location" : "地点"}</dt>
                  <dd className="mt-1 font-semibold text-slate-700">
                    {opportunity.location}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">{isEnglish ? "Score" : "评分"}</dt>
                  <dd className="mt-1 font-semibold text-slate-700">
                    {levelLabels[opportunity.level][language]}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">{isEnglish ? "Confidence" : "可信度"}</dt>
                  <dd className="mt-1 font-semibold text-slate-700">
                    {opportunity.confidence}%
                  </dd>
                </div>
              </dl>
            </section>
          </div>

          <div className="mt-7 grid gap-7 md:grid-cols-2">
            <section>
              <h3 className="text-sm font-bold text-navy">
                {isEnglish ? "What is known" : "已知事实"}
              </h3>
              <ul className="mt-3 space-y-2 text-xs leading-5 text-slate-600">
                {opportunity.knownFacts.map((fact) => (
                  <li key={fact}>• {fact}</li>
                ))}
              </ul>
            </section>
            <section>
              <h3 className="text-sm font-bold text-navy">
                {isEnglish ? "What is unknown" : "未知信息"}
              </h3>
              <ul className="mt-3 space-y-2 text-xs leading-5 text-slate-600">
                {opportunity.unknownFacts.map((fact) => (
                  <li key={fact}>• {fact}</li>
                ))}
              </ul>
            </section>
          </div>

          <section className="mt-7 rounded-md border border-amber-200 bg-amber-50 p-4">
            <h3 className="flex items-center gap-2 text-sm font-bold text-amber-900">
              <ShieldAlert className="h-4 w-4" />
              {isEnglish ? "Risk notes" : "风险提示"}
            </h3>
            <ul className="mt-2 space-y-2 text-xs leading-5 text-amber-900/80">
              {opportunity.riskNotes.map((note) => (
                <li key={note}>• {note}</li>
              ))}
            </ul>
          </section>

          <section className="mt-6 border-l-4 border-primary bg-emerald-50 p-4">
            <h3 className="text-sm font-bold text-navy">
              {isEnglish ? "Suggested public response" : "建议公开回复"}
            </h3>
            <p className="mt-2 text-xs leading-5 text-slate-700">
              {opportunity.suggestedResponse}
            </p>
          </section>

          <section className="mt-6">
            <h3 className="text-sm font-bold text-navy">
              {isEnglish ? "What not to say" : "不应使用的说法"}
            </h3>
            <ul className="mt-2 grid gap-2 text-xs leading-5 text-slate-600 sm:grid-cols-2">
              {opportunity.responseWarnings.map((warning) => (
                <li key={warning} className="rounded-md border border-rose-100 bg-rose-50 p-3">
                  &ldquo;{warning}&rdquo;
                </li>
              ))}
            </ul>
          </section>

          <p className="mt-7 border-t border-slate-200 pt-5 text-[11px] leading-5 text-slate-500">
            {isEnglish
              ? "CariLead suggests a helpful opening, not personalised financial advice. Agents remain responsible for proper fact-finding, suitability assessment, disclosure, and regulatory compliance."
              : "CariLead 仅建议有帮助的开场方式，并非个性化财务建议。代理人仍须负责适当的事实调查、适合性评估、披露及监管合规。"}
          </p>
        </div>
      </div>
    </div>
  );
}

export function OpportunityBrowser({
  opportunities,
  compact = false,
}: {
  opportunities: InsuranceOpportunity[];
  compact?: boolean;
}) {
  const [selected, setSelected] = useState<InsuranceOpportunity | null>(null);

  return (
    <>
      <div className={`grid gap-5 ${compact ? "lg:grid-cols-3" : "lg:grid-cols-2"}`}>
        {opportunities.map((opportunity) => (
          <OpportunityCard
            key={opportunity.id}
            opportunity={opportunity}
            compact={compact}
            onOpen={() => setSelected(opportunity)}
          />
        ))}
      </div>
      {selected ? (
        <OpportunityModal
          opportunity={selected}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </>
  );
}
