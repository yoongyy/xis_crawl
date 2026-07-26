"use client";

import Link from "next/link";
import {
  ArrowRight,
  ExternalLink,
  MessageCircleQuestion,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";
import { OpportunityBrowser } from "@/components/reports/opportunity-browser";
import { DemoLabel } from "@/components/reports/report-ui";
import { opportunities } from "@/data/sample-insurance-report";
import { useLanguage } from "@/lib/language-context";

const homepageOpportunityIds = [
  "parents-medical-card",
  "considering-switch",
  "trusted-agent-request",
];

export default function InsuranceProof() {
  const { language } = useLanguage();
  const isEnglish = language === "en";
  const homepageOpportunities = homepageOpportunityIds
    .map((id) => opportunities.find((item) => item.id === id))
    .filter((item): item is (typeof opportunities)[number] => Boolean(item));

  const insightItems = [
    "Premium-increase discussions",
    "Medical-card comparison requests",
    "Customers looking for trusted agents",
    "Parents' coverage questions",
    "Claim-help requests",
  ];

  const proofItems = [
    { icon: ExternalLink, label: "Original public context" },
    { icon: ScanSearch, label: "Opportunity classification" },
    { icon: ShieldCheck, label: "Source transparency" },
    { icon: ShieldCheck, label: "No hidden contact harvesting" },
    { icon: MessageCircleQuestion, label: "Built for helpful engagement" },
  ];

  return (
    <section
      id="insurance-sample"
      className="scroll-mt-20 border-y border-slate-200 bg-slate-50 py-20"
      aria-labelledby="insurance-proof-title"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div className="max-w-3xl">
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <p className="text-xs font-bold uppercase text-primary">
                {isEnglish ? "Malaysia insurance sample" : "马来西亚保险样本"}
              </p>
              <DemoLabel text={isEnglish ? "Sample data" : "样本数据"} />
            </div>
            <h2
              id="insurance-proof-title"
              className="text-3xl font-extrabold text-navy sm:text-4xl"
            >
              {isEnglish
                ? "See what CariLead finds for insurance agents"
                : "查看 CariLead 为保险代理人发现的机会"}
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
              {isEnglish
                ? "A real opportunity is more than a name and phone number. CariLead shows what the person publicly asked, why the conversation matters, and whether the signal is strong enough to act on."
                : "真正的机会不只是姓名和电话号码。CariLead 展示对方公开提出的问题、对话为何重要，以及信号是否足够强，值得采取行动。"}
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row md:justify-end">
            <Link
              href="/reports/malaysia-insurance"
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-bold text-white hover:bg-primary-dark"
            >
              {isEnglish
                ? "View Full Sample Insurance Report"
                : "查看完整保险样本报告"}
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/#free-report"
              className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-bold text-navy hover:border-primary hover:text-primary"
            >
              {isEnglish ? "Get Free Weekly Report" : "获取免费周报"}
            </Link>
          </div>
        </div>

        <div className="mt-10">
          <OpportunityBrowser
            opportunities={homepageOpportunities}
            compact
          />
        </div>

        <div className="mt-10 grid overflow-hidden rounded-lg border border-slate-200 bg-white lg:grid-cols-[0.85fr_1.15fr]">
          <div className="border-b border-slate-200 p-6 lg:border-b-0 lg:border-r">
            <DemoLabel />
            <h3 className="mt-4 text-lg font-bold text-navy">
              {isEnglish
                ? "Malaysia Insurance This Week - Sample"
                : "本周马来西亚保险 - 样本"}
            </h3>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              {isEnglish
                ? "A compact preview of the discussion clusters included in the free intelligence layer."
                : "免费情报层所包含讨论主题的简洁预览。"}
            </p>
          </div>
          <ul className="grid gap-px bg-slate-200 sm:grid-cols-2">
            {insightItems.map((item) => (
              <li
                key={item}
                className="flex items-center gap-3 bg-white p-4 text-xs font-semibold text-slate-700"
              >
                <ScanSearch className="h-4 w-4 shrink-0 text-teal" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-6 grid gap-px overflow-hidden rounded-lg border border-slate-200 bg-slate-200 sm:grid-cols-2 lg:grid-cols-5">
          {proofItems.map(({ icon: Icon, label }) => (
            <div
              key={label}
              className="flex items-center gap-2 bg-slate-50 p-4 text-[11px] font-bold text-slate-600"
            >
              <Icon className="h-4 w-4 shrink-0 text-primary" />
              {label}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
