import { StudySynopsis } from "../types";

const API_BASE = import.meta.env.VITE_API_URL || "";

const request = async (path: string, options: RequestInit) => {
  const response = await fetch(`${API_BASE}${path}`, options);
  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const body = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const message =
      typeof body === "string"
        ? body
        : body?.detail || body?.message || "Ошибка запроса";
    throw new Error(message);
  }
  return body;
};

export const chatWithAssistant = async (
  message: string,
  history: any[] = []
): Promise<string> => {
  const data = (await request("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  })) as { text?: string };
  return data.text || "Нет ответа.";
};

export const getReferenceOptions = async (
  inn: string,
  dosage: string,
  form: string
): Promise<{
  default_trade_name: string;
  options: Array<{
    trade_name: string;
    reg_no: string;
    reg_date: string;
    forms: string;
    inn: string;
    score?: number;
  }>;
}> => {
  const q = new URLSearchParams({ inn, dosage, form }).toString();
  return (await request(`/api/reference-options?${q}`, {
    method: "GET",
  })) as any;
};

export const grlsSearch = async (params: {
  q: string;
  dosage?: string;
  form?: string;
  limit?: number;
}): Promise<{
  items: Array<{ trade_name: string; reg_no: string; reg_date: string; forms: string; inn: string; score: number }>;
}> => {
  const q = new URLSearchParams({
    q: params.q,
    dosage: params.dosage || "",
    form: params.form || "",
    limit: String(params.limit || 20),
  }).toString();
  return request(`/api/grls-search?${q}`, { method: "GET" }) as Promise<any>;
};

export type DesignFiles = { docx?: string; pdf?: string; json?: string; md?: string; yaml?: string };

export type DesignResponse = {
  synopsis: StudySynopsis;
  rag: any;
  ragSummary: any;
  decision: any;
  stats: any;
  timeline: any;
  docxId?: string;
  files?: DesignFiles;
};

export const designProtocol = async (params: {
  inn: string;
  form: string;
  dosage: string;
  cvIntra: string;
  rsabe: boolean;
  design: string;
  regimen: string;
  studyType: string;
  constraints: string;
  dropOut: string;
  screenFail: string;
  refTradeName: string;
  file?: File | null;
}): Promise<DesignResponse> => {
  const form = new FormData();
  form.append("inn", params.inn);
  form.append("form", params.form);
  form.append("dosage", params.dosage);
  form.append("cvIntra", params.cvIntra);
  form.append("rsabe", String(params.rsabe));
  form.append("design", params.design);
  form.append("regimen", params.regimen);
  form.append("studyType", params.studyType);
  form.append("constraints", params.constraints || "");
  form.append("dropOut", params.dropOut || "0");
  form.append("screenFail", params.screenFail || "0");
  form.append("refTradeName", params.refTradeName || "");
  if (params.file) form.append("file", params.file);

  return (await request("/api/design", {
    method: "POST",
    body: form,
  })) as DesignResponse;
};

export const designProtocolAsync = async (params: {
  inn: string;
  form: string;
  dosage: string;
  cvIntra: string;
  rsabe: boolean;
  design: string;
  regimen: string;
  studyType: string;
  constraints: string;
  dropOut: string;
  screenFail: string;
  refTradeName: string;
  mode: "fast" | "enrich";
  file?: File | null;
}): Promise<{ jobId: string }> => {
  const form = new FormData();
  form.append("inn", params.inn);
  form.append("form", params.form);
  form.append("dosage", params.dosage);
  form.append("cvIntra", params.cvIntra);
  form.append("rsabe", String(params.rsabe));
  form.append("design", params.design);
  form.append("regimen", params.regimen);
  form.append("studyType", params.studyType);
  form.append("constraints", params.constraints || "");
  form.append("dropOut", params.dropOut || "0");
  form.append("screenFail", params.screenFail || "0");
  form.append("refTradeName", params.refTradeName || "");
  form.append("mode", params.mode || "fast");
  if (params.file) form.append("file", params.file);

  return (await request("/api/design-async", {
    method: "POST",
    body: form,
  })) as { jobId: string };
};

export const getJobStatus = async (jobId: string): Promise<any> => {
  return request(`/api/jobs/${jobId}`, { method: "GET" });
};

export const exportSynopsis = async (payload: {
  synopsis: any;
  decision?: any;
  stats?: any;
  timeline?: any;
  ragSummary?: any;
  rag?: any;
}): Promise<DesignResponse> => {
  return (await request("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })) as DesignResponse;
};

export const getHistory = async (limit = 20): Promise<any[]> => {
  const data = (await request(`/api/history?limit=${limit}`, {
    method: "GET",
  })) as { items?: any[] };
  return data.items || [];
};

export const getHistoryItem = async (id: number): Promise<any> => {
  return request(`/api/history/${id}`, { method: "GET" });
};
