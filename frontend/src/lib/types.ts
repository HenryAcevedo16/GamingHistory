export type PricingModel = "free" | "freemium" | "paid" | "unknown";
export type DisplayStatus = "available" | "installed" | "connected" | "disabled" | "error";
export type CapabilityStatus = "declared" | "verified" | "unsupported";
export type CheckStatus = "pass" | "fail" | "warn" | "skip";

export interface PluginRequirement {
  id: string;
  label: string;
  kind: string;
  identifier: string;
  optional: boolean;
  notes?: string | null;
  check_id?: string | null;
}

export interface PluginPermission {
  id: string;
  label: string;
  description: string;
  risk: "low" | "medium" | "high";
  requires_confirmation: boolean;
}

export interface PluginTool {
  name: string;
  description: string;
  destructive: boolean;
}

export interface PluginCapability {
  id: string;
  label: string;
  description?: string | null;
  status: CapabilityStatus;
}

export interface KnownCosts {
  pricing: PricingModel;
  currency?: string | null;
  notes: string;
  limits?: string | null;
}

export interface DiagnosticCheck {
  id: string;
  label: string;
  kind: string;
  target: string;
  args: string[];
  optional: boolean;
  hint?: string | null;
  timeout_seconds: number;
}

export interface DiagnosisSummary {
  ran_at?: string | null;
  ok?: boolean | null;
}

export interface PluginView {
  id: string;
  name: string;
  version: string;
  description: string;
  category: string;
  connection_type: string;
  mcp_command_or_endpoint?: string | null;
  icon?: string | null;
  accent?: string | null;
  optional: boolean;
  documentation_url?: string | null;
  install_status: string;
  enabled: boolean;
  connected: boolean;
  display_status: DisplayStatus;
  installed_at?: string | null;
  connected_at?: string | null;
  last_error?: string | null;
  last_diagnosis?: DiagnosisSummary | null;
  checks_total: number;
  requirements: PluginRequirement[];
  permissions: PluginPermission[];
  tools: PluginTool[];
  capabilities: PluginCapability[];
  known_costs: KnownCosts;
  diagnostics: DiagnosticCheck[];
}

export interface PluginCounts {
  total: number;
  available: number;
  installed: number;
  connected: number;
  disabled: number;
  error: number;
}

export interface ManifestErrorView {
  path: string;
  error: string;
}

export interface PluginListResponse {
  items: PluginView[];
  total: number;
  counts: PluginCounts;
  manifest_errors: ManifestErrorView[];
  generated_at: string;
}

export interface CheckResult {
  id: string;
  label: string;
  kind: string;
  status: CheckStatus;
  optional: boolean;
  evidence: string;
  hint?: string | null;
  version?: string | null;
  duration_ms: number;
}

export interface DiagnosticReport {
  plugin_id: string;
  ran_at: string;
  ok: boolean;
  checks: CheckResult[];
  summary: {
    passed: number;
    failed: number;
    warnings: number;
    skipped: number;
  };
  duration_ms: number;
}

export interface DiagnosticResponse extends DiagnosticReport {
  plugin_state: PluginView;
}

export interface RequirementStatus {
  id: string;
  label: string;
  kind: string;
  identifier: string;
  optional: boolean;
  check_id?: string | null;
  satisfied?: boolean | null;
  check_status?: CheckStatus | null;
  evidence?: string | null;
  notes?: string | null;
}

export interface RequirementReport {
  plugin_id: string;
  ok: boolean;
  requirements: RequirementStatus[];
  checks: CheckResult[];
  ran_at: string;
}

export interface ActionResponse {
  success: boolean;
  message: string;
  plugin: PluginView;
}

export type RouterOperation =
  | "auto_assembly"
  | "editable_draft"
  | "professional_edit"
  | "transcript_edit";

export interface RouterCandidate {
  plugin_id: string;
  name: string;
  eligible: boolean;
  selected: boolean;
  reason: string;
  enabled: boolean;
  installed: boolean;
  connected: boolean;
  adapter_registered: boolean;
  pricing: PricingModel;
  missing_capabilities: string[];
}

export interface RouterSelection {
  plugin_id: string;
  name: string;
  reason: string;
  score: number;
  adapter_registered: boolean;
  executable: boolean;
}

export interface RouterDecision {
  operation: RouterOperation;
  label: string;
  description: string;
  required_capabilities: string[];
  adapter_operation: string;
  capability_source: string;
  selected?: RouterSelection | null;
  candidates: RouterCandidate[];
  discarded: RouterCandidate[];
  explanation: string;
  generated_at: string;
}

export interface RouterDecisionsResponse {
  cloud_authorized: boolean;
  decisions: RouterDecision[];
  generated_at: string;
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  database: string;
  plugins_dir: string;
  plugins_found: number;
  manifest_errors: number;
  details: Record<string, unknown>;
}
