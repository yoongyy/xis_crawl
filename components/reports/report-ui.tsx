"use client";

import Link from "next/link";
import { ArrowRight, BarChart3 } from "lucide-react";
import type {
  ConcernTrend,
  MentionTheme,
} from "@/data/sample-insurance-report";
import { useLanguage } from "@/lib/language-context";

export function DemoLabel({ text }: { text?: string }) {
  const { language } = useLanguage();

  return (
    <span className="inline-flex rounded border border-amber-300 bg-amber-50 px-2 py-1 text-[10px] font-bold uppercase text-amber-800">
      {text ?? (language === "en" ? "Demo example" : "演示示例")}
    </span>
  );
}
export function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-8 max-w-3xl">
      <p className="mb-2 text-xs font-bold uppercase text-primary">{eyebrow}</p>
      <h2 className="text-2xl font-extrabold text-navy sm:text-3xl">{title}</h2>
      {description ? (
        <p className="mt-3 text-sm leading-6 text-slate-600">{description}</p>
      ) : null}
    </div>
  );
}

export function ConcernChart({ data }: { data: ConcernTrend[] }) {
  const { language } = useLanguage();
  const max = Math.max(...data.map((item) => item.mentions));

  return (
    <div
      role="img"
      aria-label={
        language === "en"
          ? "Demo volume of customer concerns in a targeted public-conversation sample"
          : "目标公开对话样本中的客户关注主题演示数量"
      }
      className="space-y-4"
    >
      {data.map((item) => (
        <div key={item.name}>
          <div className="mb-1.5 flex items-center justify-between gap-4 text-xs">
            <span className="font-semibold text-slate-700">{item.name}</span>
            <span className="shrink-0 text-slate-500">
              {item.mentions} {language === "en" ? "demo mentions" : "次演示提及"}
            </span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-sm bg-slate-100">
            <div
              className="h-full rounded-sm bg-teal"
              style={{ width: `${(item.mentions / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function MentionBars({
  title,
  data,
}: {
  title: string;
  data: MentionTheme[];
}) {
  const max = Math.max(...data.map((item) => item.mentions));

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-teal" />
        <h3 className="text-sm font-bold text-navy">{title}</h3>
      </div>
      <div className="mt-5 space-y-4">
        {data.map((item) => (
          <div key={item.name}>
            <div className="mb-1.5 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-700">{item.name}</p>
                <p className="truncate text-[10px] text-slate-400">{item.note}</p>
              </div>
              <span className="shrink-0 text-xs font-bold text-teal">
                {item.mentions}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-sm bg-slate-100">
              <div
                className="h-full rounded-sm bg-primary"
                style={{ width: `${(item.mentions / max) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ReportCta() {
  const { language } = useLanguage();

  return (
    <section className="bg-navy py-14 text-white">
      <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-7 px-4 sm:px-6 md:flex-row md:items-center lg:px-8">
        <div className="max-w-2xl">
          <p className="mb-2 text-xs font-bold uppercase text-primary-light">
            {language === "en" ? "Weekly market intelligence" : "每周市场情报"}
          </p>
          <h2 className="text-2xl font-extrabold sm:text-3xl">
            {language === "en"
              ? "Receive the next Malaysia insurance report."
              : "订阅下一期马来西亚保险市场报告。"}
          </h2>
          <p className="mt-2 text-sm text-slate-300">
            {language === "en"
              ? "The free report tells you what customers are talking about."
              : "免费报告告诉您客户正在讨论什么。"}
          </p>
        </div>
        <Link
          href="/#free-report"
          className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-bold text-white hover:bg-primary-dark"
        >
          {language === "en" ? "Get Free Insurance Report" : "获取免费保险报告"}
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </section>
  );
}
