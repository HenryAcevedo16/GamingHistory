import type { Metadata } from "next";
import { BackupView } from "@/components/backup/backup-view";

export const metadata: Metadata = { title: "Respaldo | Gaming History Studio" };

export default function BackupPage() {
  return <BackupView />;
}
