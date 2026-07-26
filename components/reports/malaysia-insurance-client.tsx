"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarDays,
  Clock3,
  FileText,
  Search,
  ShieldCheck,
} from "lucide-react";
import EarlyAccessForm from "@/components/early-access-form";
import Footer from "@/components/footer";
import Navbar from "@/components/navbar";
import {
  ExecutiveSummary,
  FreeVsPro,
  MethodologySection,
  TrendAndMentionSections,
} from "@/components/reports/insurance-report-sections";
import { OpportunityBrowser } from "@/components/reports/opportunity-browser";
import {
  DemoLabel,
  ReportCta,
  SectionHeading,
} from "@/components/reports/report-ui";
import { opportunities, reportMeta } from "@/data/sample-insurance-report";
import { useLanguage } from "@/lib/language-context";

export default function MalaysiaInsuranceReportClient() {
  const [isEarlyAccessOpen, setIsEarlyAccessOpen] = useState(false);
  const { language } = useLanguage();
  const isEnglish = language === "en";

  return (
    <>
      <Navbar onOpenEarlyAccess={() => setIsEarlyAccessOpen(true)} />
      <main className="min-h-screen bg-slate-50 pt-20">
        <section className="border-b border-slate-200 bg-white py-12 sm:py-16">
          <div className="mx-auto grid max-w-7xl gap-10 px-4 sm:px-6 lg:grid-cols-[1.2fr_0.8fr] lg:px-8">
            <div className="max-w-3xl">
              <div className="mb-5 flex flex-wrap items-center gap-3">
                <DemoLabel text={isEnglish ? "Sample CariLead Report" : "CariLead 样本报告"} />
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500">
                  <CalendarDays className="h-3.5 w-3.5" />
                  {reportMeta.edition}
                </span>
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500">
                  <Clock3 className="h-3.5 w-3.5" />
                  {reportMeta.updatedAt}
                </span>
              </div>
              <p className="mb-2 text-xs font-bold uppercase text-primary">
                {isEnglish ? "Malaysia insurance intelligence" : "马来西亚保险情报"}
              </p>
              <h1 className="text-4xl font-extrabold leading-tight text-navy sm:text-5xl">
                {isEnglish
                  ? reportMeta.title
                  : "马来西亚保险客户声音报告"}
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600">
                {isEnglish
                  ? reportMeta.subtitle
                  : "马来西亚客户目前正在询问、投诉、比较和考虑的保险议题。"}
              </p>
              <p className="mt-4 max-w-2xl text-xs leading-5 text-slate-500">
                {isEnglish
                  ? "This page demonstrates the type of analysis CariLead can produce. Demo records are clearly labelled and do not represent guaranteed sales opportunities."
                  : "本页面展示 CariLead 可生成的分析类型。演示记录均有明确标注，不代表保证成交的销售机会。"}
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link
                  href="/#free-report"
                  className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-bold text-white hover:bg-primary-dark"
                >
                  {isEnglish ? "Get Free Weekly Report" : "获取免费周报"}
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <a
                  href="#sample-opportunities"
                  className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-bold text-navy hover:border-primary hover:text-primary"
                >
                  <Search className="h-4 w-4" />
                  {isEnglish ? "View Sample Opportunities" : "查看样本机会"}
                </a>
              </div>
            </div>

            <aside className="rounded-lg border border-slate-200 bg-slate-50 p-6">
              <div className="flex items-center justify-between border-b border-slate-200 pb-4">
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-primary" />
                  <span className="text-sm font-bold text-navy">
                    {isEnglish ? "Report snapshot" : "报告快照"}
                  </span>
                </div>
                <DemoLabel text={isEnglish ? "Demo dataset" : "演示数据集"} />
              </div>
              <dl className="mt-5 grid grid-cols-2 gap-5">
                <div>
                  <dt className="text-[11px] text-slate-500">
                    {isEnglish
                      ? "Customer conversations analysed"
                      : "分析的客户对话"}
                  </dt>
                  <dd className="mt-1 text-2xl font-extrabold text-navy">
                    {reportMeta.conversations}
                  </dd>
                  <span className="text-[10px] text-amber-700">
                    {isEnglish ? "demo conversations" : "演示对话"}
                  </span>
                </div>
                <div>
                  <dt className="text-[11px] text-slate-500">
                    {isEnglish
                      ? "High-intent opportunities detected"
                      : "检测到的高意向机会"}
                  </dt>
                  <dd className="mt-1 text-2xl font-extrabold text-navy">
                    {reportMeta.highIntent}
                  </dd>
                  <span className="text-[10px] text-amber-700">
                    {isEnglish ? "demo high-intent signals" : "演示高意向信号"}
                  </span>
                </div>
                <div>
                  <dt className="text-[11px] text-slate-500">
                    {isEnglish ? "Most discussed product" : "讨论最多的产品"}
                  </dt>
                  <dd className="mt-1 text-sm font-bold text-navy">
                    {reportMeta.leadingProduct}
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] text-slate-500">
                    {isEnglish ? "Fastest-growing concern" : "增长最快的关注点"}
                  </dt>
                  <dd className="mt-1 text-sm font-bold text-navy">
                    {reportMeta.fastestGrowing}
                  </dd>
                </div>
              </dl>
              <p className="mt-6 border-t border-slate-200 pt-4 text-[11px] leading-5 text-slate-500">
                {isEnglish
                  ? `${reportMeta.dateRange}. Values are illustrative and are not audited market measurements.`
                  : `${reportMeta.dateRange}。数值仅供演示，并非经审计的市场统计。`}
              </p>
            </aside>
          </div>
        </section>

        <ExecutiveSummary />
        <TrendAndMentionSections />

        <section
          id="sample-opportunities"
          className="scroll-mt-20 border-y border-slate-200 bg-white py-16"
        >
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <SectionHeading
              eyebrow={isEnglish ? "Opportunity feed" : "机会信息流"}
              title={
                isEnglish
                  ? "Example public insurance opportunities"
                  : "公开保险机会示例"
              }
              description={
                isEnglish
                  ? "CariLead identifies public conversations that may show a need for insurance guidance. Not every complaint is a lead, so each opportunity is classified by context and intent."
                  : "CariLead 识别可能需要保险指导的公开对话。并非每条投诉都是线索，因此每个机会都会按语境和意图分类。"
              }
            />

            <div className="mb-8 grid gap-px overflow-hidden rounded-lg border border-slate-200 bg-slate-200 sm:grid-cols-3">
              {[
                {
                  title: isEnglish ? "Free intelligence" : "免费情报",
                  body: isEnglish
                    ? "Anonymised themes and opportunity examples"
                    : "匿名主题与机会示例",
                },
                {
                  title: "CariLead Pro",
                  body: isEnglish
                    ? "Source-linked context and scoring"
                    : "来源链接语境与评分",
                },
                {
                  title: isEnglish ? "Human review" : "人工审核",
                  body: isEnglish
                    ? "Verify context before responding"
                    : "回复前核实语境",
                },
              ].map((item) => (
                <div key={item.title} className="bg-slate-50 p-4">
                  <p className="flex items-center gap-2 text-xs font-bold text-navy">
                    <ShieldCheck className="h-4 w-4 text-teal" />
                    {item.title}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">{item.body}</p>
                </div>
              ))}
            </div>

            <OpportunityBrowser opportunities={opportunities} />
          </div>
        </section>

        <FreeVsPro onOpenEarlyAccess={() => setIsEarlyAccessOpen(true)} />
        <MethodologySection />
        <ReportCta />
      </main>
      <Footer />
      <EarlyAccessForm
        isOpen={isEarlyAccessOpen}
        onClose={() => setIsEarlyAccessOpen(false)}
      />
    </>
  );
}
