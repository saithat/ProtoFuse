import type { Metadata } from "next";
import { EvaluationDashboard } from "./evaluation-dashboard";

export const metadata: Metadata = {
  title: "ProtoFuse / Evaluation Readout",
  description: "Current workload-specific evidence, protocol-separated cohorts, and independent ProtoFuse audit outcomes.",
};

export default function Home() {
  return <EvaluationDashboard />;
}
