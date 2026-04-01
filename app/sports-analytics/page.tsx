import type { Metadata } from "next";
import { SportsAnalyticsWorkbench } from "@/components/sports/SportsAnalyticsWorkbench";

export const metadata: Metadata = {
  title: "Sports Analytics Workbench",
  description:
    "Interactive frontend for the FastAPI + LangGraph sports analytics MVP, including natural-language query execution and structured result inspection.",
};

export default function SportsAnalyticsPage() {
  return <SportsAnalyticsWorkbench />;
}
