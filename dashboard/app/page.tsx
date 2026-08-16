import type { Metadata } from "next";
import { EvaluationDashboard } from "./evaluation-dashboard";

export const metadata: Metadata = {
  title: "ProtoFuse / Evaluation Readout",
  description: "Confirmed CUSTOM MFE results, failed joint-surrogate audits, and current ProtoFuse benchmark evidence.",
};

export default function Home() {
  return <EvaluationDashboard />;
}
