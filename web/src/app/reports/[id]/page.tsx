import type { Metadata } from "next";
import { ReportScreen } from "@/components/report/report-screen";

export const metadata: Metadata = { title: "Report" };

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReportScreen id={id} />;
}
