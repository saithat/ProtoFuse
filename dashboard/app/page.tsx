import type { Metadata } from "next";
import { EvaluationDashboard } from "./evaluation-dashboard";

export const metadata: Metadata = {
  title: "ProtoFuse / Evaluation Readout",
  description: "An evidence-first view of ProtoFuse traces, surrogates, splits, and benchmarks.",
};

export default function Home() {
  return <EvaluationDashboard />;
}
