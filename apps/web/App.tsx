import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Beaker,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Clipboard,
  Cpu,
  FileUp,
  Info,
  Loader2,
  MessageSquare,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sigma,
  X,
} from "lucide-react";
import { ChatMessage, StudySynopsis } from "./types";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Tooltip, Legend, Filler);

type SectionField = { label: string; value: any; key: keyof StudySynopsis; list?: boolean };

function SynopsisSection(props: {
  title: string;
  sectionKey: string;
  icon?: React.ReactNode;
  fields: SectionField[];
  editSection: string | null;
  setEditSection: (v: string | null) => void;
  safeText: (v: any) => string;
  updateSynopsisField: (key: keyof StudySynopsis, value: string, list?: boolean) => void;
  synopsisDraft: StudySynopsis | null;
}) {
  const { title, sectionKey, icon, fields, editSection, setEditSection, safeText, updateSynopsisField, synopsisDraft } = props;
  const isEdit = editSection === sectionKey;

  return (
    <details className="border border-slate-200 rounded-3xl overflow-hidden bg-white" open={isEdit}>
      <summary className="cursor-pointer list-none px-5 py-4 bg-slate-50 text-sm font-black text-slate-900 flex items-center justify-between">
        <span className="inline-flex items-center gap-2">
          {icon}
          {title}
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            setEditSection(isEdit ? null : sectionKey);
          }}
          className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-400 hover:text-emerald-600 transition-colors"
        >
          {isEdit ? "Свернуть" : "Редактировать"}
        </button>
      </summary>

      <div className="p-5 space-y-4 text-sm text-slate-700">
        {!isEdit ? (
          fields.map((f) => (
            <div key={String(f.key)}>
              <div className="text-[10px] uppercase tracking-[0.18em] font-extrabold text-slate-400">{f.label}</div>
              <div className="mt-1 whitespace-pre-wrap">{safeText(f.value)}</div>
            </div>
          ))
        ) : (
          <div className="space-y-4">
            {fields.map((f) => {
              const draftValue = synopsisDraft ? (synopsisDraft as any)[f.key] : f.value;
              const text = Array.isArray(draftValue) ? draftValue.join("\n") : (draftValue ?? "");
              return (
                <div key={String(f.key)}>
                  <div className="text-[10px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-1">{f.label}</div>
                  <textarea
                    value={String(text)}
                    onChange={(e) => updateSynopsisField(f.key, e.target.value, !!f.list)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-xs outline-none focus:border-emerald-400 min-h-[88px]"
                  />
                </div>
              );
            })}
            <div className="text-[11px] text-slate-500">
              Изменения применяются локально. Нажмите «Пересобрать файлы», чтобы обновить DOCX/PDF/JSON.
            </div>
          </div>
        )}
      </div>
    </details>
  );
}
import {
  chatWithAssistant,
  designProtocol,
  designProtocolAsync,
  getHistory,
  getHistoryItem,
  getReferenceOptions,
  getJobStatus,
  exportSynopsis,
  grlsSearch,
  DesignFiles,
  apiUrl,
  enrichProtocolAsync,
  deepOcrProtocolAsync,
} from "./services/apiService";

const App: React.FC = () => {
  // inputs
  const [inn, setInn] = useState("");
  const [dosage, setDosage] = useState("");
  const [form, setForm] = useState("Таблетки");
  const [cvIntra, setCvIntra] = useState("auto");
  const [rsabe, setRsabe] = useState(false);
  const [design, setDesign] = useState("auto");
  const [regimen, setRegimen] = useState<"Натощак" | "После еды" | "Оба варианта">("Натощак");
  const [studyType, setStudyType] = useState("Однофазное");
  const [constraints, setConstraints] = useState("");
  const [dropOut, setDropOut] = useState("20");
  const [screenFail, setScreenFail] = useState("10");
  const [parserFile, setParserFile] = useState<File | null>(null);
  const [deepMode, setDeepMode] = useState(false);
  const [refTradeName, setRefTradeName] = useState("");
  const [refManual, setRefManual] = useState(false);
  const [refManualValue, setRefManualValue] = useState("");
  const [refOptions, setRefOptions] = useState<
    Array<{ trade_name: string; reg_no: string; reg_date: string; forms: string; inn: string; score?: number }>
  >([]);
  const [refLoading, setRefLoading] = useState(false);
  const [refError, setRefError] = useState<string | null>(null);

  // output
  const [loading, setLoading] = useState(false);
  const [parserError, setParserError] = useState<string | null>(null);

  const [synopsis, setSynopsis] = useState<StudySynopsis | null>(null);
  const [synopsisDraft, setSynopsisDraft] = useState<StudySynopsis | null>(null);
  const [ragData, setRagData] = useState<any | null>(null);
  const [ragSummary, setRagSummary] = useState<any | null>(null);
  const [decision, setDecision] = useState<any | null>(null);
  const [stats, setStats] = useState<any | null>(null);
  const [timeline, setTimeline] = useState<any | null>(null);

  const [docxId, setDocxId] = useState<string | null>(null);
  const [files, setFiles] = useState<DesignFiles | null>(null);

  // right area
  const [rightTab, setRightTab] = useState<"synopsis" | "calc" | "sources" | "grls">("synopsis");
  const [editSection, setEditSection] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStage, setJobStage] = useState<string | null>(null);
  const [jobMessage, setJobMessage] = useState<string | null>(null);
  const [draftReady, setDraftReady] = useState(false);
  const draftReadyRef = useRef(false);
  const pollTokenRef = useRef<string | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const [synopsisDirty, setSynopsisDirty] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);

  const [grlsQuery, setGrlsQuery] = useState("");
  const [grlsResults, setGrlsResults] = useState<any[]>([]);
  const [grlsLoading, setGrlsLoading] = useState(false);
  const [grlsError, setGrlsError] = useState<string | null>(null);

  // history
  const [historyItems, setHistoryItems] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyKind, setHistoryKind] = useState<string>("all");
  const [historySelectedId, setHistorySelectedId] = useState<number | null>(null);

  // chat
  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // small UX
  const [toast, setToast] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const toastTimer = useRef<number | null>(null);

  const safeText = (value: any): string => {
    if (value === null || value === undefined) return "—";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  };

  const toList = (value: any): string[] => {
    if (Array.isArray(value)) return value.map((v) => String(v));
    if (!value) return [];
    return String(value)
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
  };

  const showToast = (kind: "ok" | "err", text: string) => {
    setToast({ kind, text });
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 2600);
  };

  const safeParse = (text?: string) => {
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch {
      return null;
    }
  };

  const formatDate = (iso?: string) => {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      return d.toLocaleString("ru-RU");
    } catch {
      return iso;
    }
  };

  useEffect(() => {
    if (chatEndRef.current) chatEndRef.current.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
      pollTokenRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (synopsis) setSynopsisDraft(synopsis);
  }, [synopsis]);

  useEffect(() => {
    const i = inn.trim();
    const d = dosage.trim();
    const f = form.trim();
    if (!i || !d || !f) return;

    const t = window.setTimeout(async () => {
      setRefLoading(true);
      setRefError(null);
      try {
        const res = await getReferenceOptions(i, d, f);
        if ((res as any).loading) {
          setRefOptions([]);
          setRefError("GRLS загружается… попробуйте ещё раз через несколько секунд");
          return;
        }
        const opts = res.options || [];
        setRefOptions(opts);
        if (!refTradeName && res.default_trade_name) {
          setRefTradeName(res.default_trade_name);
        }
        if (opts.length === 0) {
          setRefManual(true);
        } else if (refManual && !refManualValue) {
          setRefManual(false);
        }
      } catch (e: any) {
        const msg = e?.message || "Не удалось загрузить референты";
        setRefError(msg === "timeout" ? "Не удалось загрузить GRLS: превышено время ответа" : msg);
        setRefOptions([]);
      } finally {
        setRefLoading(false);
      }
    }, 500);

    return () => window.clearTimeout(t);
  }, [inn, dosage, form, refTradeName, refManual, refManualValue]);

  useEffect(() => {
    const q = grlsQuery.trim();
    if (!q) {
      setGrlsResults([]);
      return;
    }
    const t = window.setTimeout(async () => {
      setGrlsLoading(true);
      setGrlsError(null);
      try {
        const res = await grlsSearch({ q, dosage: dosage.trim(), form: form.trim(), limit: 20 });
        setGrlsResults(res.items || []);
      } catch (e: any) {
        setGrlsError(e?.message || "Не удалось загрузить справочник");
        setGrlsResults([]);
      } finally {
        setGrlsLoading(false);
      }
    }, 500);
    return () => window.clearTimeout(t);
  }, [grlsQuery, dosage, form]);

  const evidenceCount = useMemo(() => {
    const a = Array.isArray(ragData?.evidence) ? ragData.evidence.length : 0;
    const b = Array.isArray(synopsis?.bibliography) ? synopsis!.bibliography.length : 0;
    const c = Array.isArray(ragData?.be?.be_evidence) ? ragData.be.be_evidence.length : 0;
    const d = Array.isArray(ragData?.be?.html_sources) ? ragData.be.html_sources.length : 0;
    const e = Array.isArray(ragData?.evidence_docs) ? ragData.evidence_docs.length : 0;
    const f = Array.isArray(ragData?.be?.discovered) ? ragData.be.discovered.length : 0;
    return Math.max(a, b, c + d, e + f);
  }, [ragData, synopsis]);

  const confidence = useMemo(() => {
    if (evidenceCount >= 4) return "high";
    if (evidenceCount >= 2) return "medium";
    if (evidenceCount === 1) return "low";
    return "unknown";
  }, [evidenceCount]);

  const hasAnyResult = !!synopsis || !!decision || !!stats || !!timeline || !!ragSummary || !!ragData;
  const isEmpty = !inn.trim();
  const isDraft = !!inn.trim() && !hasAnyResult && !loading && !parserError;

  const warnings = useMemo(() => {
    if (!hasAnyResult) return [];
    const out: string[] = [];
    const t12 = ragSummary?.t12_h;
    const washout = decision?.washout_days;

    const hasCv =
      !!ragSummary?.cvintra_cmax ||
      !!ragSummary?.cvintra_auc ||
      (stats?.assumptions?.cv_intra && stats?.assumptions?.cv_intra !== "auto");

    if (!hasCv) out.push("CVintra не найден: задайте вручную или проверьте источники");

    if (t12 && washout) {
      const minWashoutDays = Math.ceil((5 * Number(t12)) / 24);
      if (Number(washout) < minWashoutDays) out.push("Washout меньше 5×T1/2");
    }

    if (rsabe && decision?.design !== "replicate") out.push("RSABE включён, но выбран не replicate дизайн");
    if (!rsabe && decision?.design === "replicate") out.push("Replicate при выключенном RSABE: проверьте CV");

    return out;
  }, [hasAnyResult, ragSummary, decision, rsabe, stats]);

  const statusOk = warnings.length === 0;

  const projectTitle = useMemo(() => {
    if (!inn.trim()) return "Проект";
    const d = dosage ? ` • ${dosage} mg` : "";
    return `${inn}${d} • ${regimen}`;
  }, [inn, dosage, regimen]);

  const hasArtifacts = (res: any) => {
    if (!res || typeof res !== "object") return false;
    if (res.docxId || res.docx_id) return true;
    const f = res.files;
    return !!(f && (f.docx || f.pdf || f.md || f.yaml || f.json));
  };

  const progressSteps = [
    { key: "draft", label: "Draft" },
    { key: "discover", label: "Поиск литературы" },
    { key: "instruction", label: "Инструкция/SmPC" },
    { key: "be", label: "BE источники" },
    { key: "llm", label: "LLM fallback" },
    { key: "synopsis", label: "Формирование синопсиса" },
    { key: "export", label: "Экспорт файлов" },
    { key: "done", label: "Готово" },
  ];
  const stageOrder = ["queued", "draft", "discover", "instruction", "be", "llm", "synopsis", "export", "done", "error"];
  const currentStageIndex = stageOrder.indexOf(jobStage || "");

  const runDesign = async (e?: React.FormEvent) => {
    e?.preventDefault?.();
    if (!inn.trim()) return;

    setLoading(true);
    setParserError(null);
    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
    const token =
      (crypto as any)?.randomUUID?.() ??
      String(Date.now());
    pollTokenRef.current = token;

    setJobId(null);
    setJobStage(null);
    setJobMessage(null);
    setDraftReady(false);
    draftReadyRef.current = false;

    try {
      const asyncStart = await designProtocolAsync({
        inn,
        form,
        dosage,
        cvIntra,
        rsabe,
        design,
        regimen,
        studyType,
        constraints,
        dropOut,
        screenFail,
        refTradeName: refManual ? refManualValue : refTradeName,
        mode: "fast",
        file: parserFile,
      });
      setJobId(asyncStart.jobId);

      let timeoutGraceTries = 0;

      const poll = async () => {
        if (!asyncStart.jobId) return;
        if (pollTokenRef.current !== token) return;
        try {
          const job = await getJobStatus(asyncStart.jobId);
          setJobStage(job.stage || null);
          setJobMessage(job.message || null);

          const result = job.result || null;
          const artifactsReady = Boolean(job.artifacts_ready) || hasArtifacts(result);

          if (result) {
            setSynopsis(result?.synopsis || null);
            setRagData(result?.rag || null);
            setRagSummary(result?.ragSummary || null);
            setDecision(result?.decision || null);
            setStats(result?.stats || null);
            setTimeline(result?.timeline || null);
            const newDocx = result?.docxId || result?.docx_id || null;
            if (newDocx) setDocxId(newDocx);
            setFiles(result?.files || null);
          }

          if (artifactsReady && !draftReadyRef.current) {
            draftReadyRef.current = true;
            setDraftReady(true);
            setLoading(false);
            showToast("ok", "Черновик готов — идёт поиск источников");
          }

          if (job.status === "done") {
            setRightTab("synopsis");
            setLoading(false);
            showToast("ok", "Синопсис обновлён");
            return;
          }

          if (job.status === "error") {
            const msg = job.message || "Обогащение прервано";
            const isTimeout = msg === "timeout" || job.error === "JOB_TIMEOUT";
            if (isTimeout && !artifactsReady && timeoutGraceTries < 8) {
              timeoutGraceTries += 1;
              pollTimerRef.current = window.setTimeout(poll, 1500);
              return;
            }
            if (artifactsReady) {
              setLoading(false);
              showToast("err", `${msg} (файлы сохранены)`);
              return;
            }
            setParserError(msg);
            setLoading(false);
            showToast("err", msg);
            return;
          }

          pollTimerRef.current = window.setTimeout(poll, 2000);
        } catch (e) {
          pollTimerRef.current = window.setTimeout(poll, 2000);
        }
      };

      pollTimerRef.current = window.setTimeout(poll, 800);
    } catch (err: any) {
      const msg = err?.message || "Ошибка проектирования";
      setParserError(msg);
      showToast("err", msg);
      setLoading(false);
    } finally {
      // loading will be turned off when job completes
    }
  };

  const runEnrich = async () => {
    if (!inn.trim()) return;
    setLoading(true);
    setParserError(null);

    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
    const token =
      (crypto as any)?.randomUUID?.() ??
      String(Date.now());
    pollTokenRef.current = token;

    try {
      const asyncStart = await enrichProtocolAsync({
        inn,
        form,
        dosage,
        cvIntra,
        rsabe,
        design,
        regimen,
        studyType,
        constraints,
        dropOut,
        screenFail,
        refTradeName: refManual ? refManualValue : refTradeName,
        deepMode,
        file: parserFile,
      });

      setJobId(asyncStart.jobId);

      let timeoutGraceTries = 0;

      const poll = async () => {
        if (!asyncStart.jobId) return;
        if (pollTokenRef.current !== token) return;
        try {
          const job = await getJobStatus(asyncStart.jobId);
          setJobStage(job.stage || null);
          setJobMessage(job.message || null);

          const result = job.result || null;
          const artifactsReady = Boolean(job.artifacts_ready) || hasArtifacts(result);

          if (result) {
            setSynopsis(result?.synopsis || null);
            setRagData(result?.rag || null);
            setRagSummary(result?.ragSummary || null);
            setDecision(result?.decision || null);
            setStats(result?.stats || null);
            setTimeline(result?.timeline || null);
            const newDocx = result?.docxId || result?.docx_id || null;
            if (newDocx) setDocxId(newDocx);
            setFiles(result?.files || null);
          }

          if (artifactsReady && !draftReadyRef.current) {
            draftReadyRef.current = true;
            setDraftReady(true);
            setLoading(false);
            showToast("ok", "Черновик готов — идёт поиск источников");
          }

          if (job.status === "done") {
            setRightTab("synopsis");
            setLoading(false);
            showToast("ok", "Источники обновлены");
            return;
          }

          if (job.status === "error") {
            const msg = job.message || "Обогащение прервано";
            const isTimeout = msg === "timeout" || job.error === "JOB_TIMEOUT";
            if (isTimeout && !artifactsReady && timeoutGraceTries < 8) {
              timeoutGraceTries += 1;
              pollTimerRef.current = window.setTimeout(poll, 1500);
              return;
            }
            if (artifactsReady) {
              setLoading(false);
              showToast("err", `${msg} (файлы сохранены)`);
              return;
            }
            setParserError(msg);
            setLoading(false);
            showToast("err", msg);
            return;
          }

          pollTimerRef.current = window.setTimeout(poll, 2000);
        } catch (e) {
          pollTimerRef.current = window.setTimeout(poll, 2000);
        }
      };

      pollTimerRef.current = window.setTimeout(poll, 800);
    } catch (err: any) {
      const msg = err?.message || "Ошибка обогащения";
      setParserError(msg);
      showToast("err", msg);
      setLoading(false);
    }
  };

  const runDeepOcr = async () => {
    if (!inn.trim()) return;
    setLoading(true);
    setParserError(null);

    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
    const token = (crypto as any)?.randomUUID?.() ?? String(Date.now());
    pollTokenRef.current = token;

    try {
      const asyncStart = await deepOcrProtocolAsync({
        inn,
        form,
        dosage,
        cvIntra,
        rsabe,
        design,
        regimen,
        studyType,
        constraints,
        dropOut,
        screenFail,
        refTradeName: refManual ? refManualValue : refTradeName,
        file: parserFile,
      });

      setJobId(asyncStart.jobId);

      let timeoutGraceTries = 0;

      const poll = async () => {
        if (!asyncStart.jobId) return;
        if (pollTokenRef.current !== token) return;
        try {
          const job = await getJobStatus(asyncStart.jobId);
          setJobStage(job.stage || null);
          setJobMessage(job.message || null);

          const result = job.result || null;
          const artifactsReady = Boolean(job.artifacts_ready) || hasArtifacts(result);

          if (result) {
            setSynopsis(result?.synopsis || null);
            setRagData(result?.rag || null);
            setRagSummary(result?.ragSummary || null);
            setDecision(result?.decision || null);
            setStats(result?.stats || null);
            setTimeline(result?.timeline || null);
            const newDocx = result?.docxId || result?.docx_id || null;
            if (newDocx) setDocxId(newDocx);
            setFiles(result?.files || null);
          }

          if (artifactsReady && !draftReadyRef.current) {
            draftReadyRef.current = true;
            setDraftReady(true);
            setLoading(false);
            showToast("ok", "Черновик готов — идёт Deep OCR");
          }

          if (job.status === "done") {
            setRightTab("synopsis");
            setLoading(false);
            showToast("ok", "Deep OCR завершён");
            return;
          }

          if (job.status === "error") {
            const msg = job.message || "Deep OCR прерван";
            const isTimeout = msg === "timeout" || job.error === "JOB_TIMEOUT";
            if (isTimeout && !artifactsReady && timeoutGraceTries < 8) {
              timeoutGraceTries += 1;
              pollTimerRef.current = window.setTimeout(poll, 1500);
              return;
            }
            if (artifactsReady) {
              setLoading(false);
              showToast("err", `${msg} (файлы сохранены)`);
              return;
            }
            setParserError(msg);
            setLoading(false);
            showToast("err", msg);
            return;
          }

          pollTimerRef.current = window.setTimeout(poll, 2000);
        } catch (e) {
          pollTimerRef.current = window.setTimeout(poll, 2000);
        }
      };

      pollTimerRef.current = window.setTimeout(poll, 800);
    } catch (err: any) {
      const msg = err?.message || "Ошибка Deep OCR";
      setParserError(msg);
      showToast("err", msg);
      setLoading(false);
    }
  };

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const items = await getHistory(30);
      setHistoryItems(items);
      if (items?.length) setHistorySelectedId(items[0].id);
    } finally {
      setHistoryLoading(false);
    }
  };

  const applyHistoryItem = async (id: number) => {
    const item = await getHistoryItem(id);
    const response = item?.response ? JSON.parse(item.response) : null;

    // поддержка старой и новой схемы (если response — укороченный)
    if (item?.kind === "design" && response) {
      setSynopsis(response.synopsis || synopsis || null);
      setRagData(response.rag || ragData || null);
      setRagSummary(response.ragSummary || ragSummary || null);
      setDecision(response.decision || decision || null);
      setStats(response.stats || stats || null);
      setTimeline(response.timeline || timeline || null);

      const newDocx = response.docxId || response?.docx_id || null;
      if (newDocx) setDocxId(newDocx);

      if (response.files) setFiles(response.files);
      setRightTab("synopsis");
      setHistoryOpen(false);
      showToast("ok", "Загружено из истории");
    }
  };

  const historyView = useMemo(() => {
    const q = historyQuery.trim().toLowerCase();
    return historyItems
      .map((item) => {
        const payload = safeParse(item.payload);
        const response = safeParse(item.response);
        return { ...item, payload, response };
      })
      .filter((item) => (historyKind === "all" ? true : item.kind === historyKind))
      .filter((item) => {
        if (!q) return true;
        const inn = (item.payload?.inn || item.payload?.name || "").toString().toLowerCase();
        const title = (item.response?.synopsis?.protocolTitle || "").toString().toLowerCase();
        const kind = (item.kind || "").toString().toLowerCase();
        return inn.includes(q) || title.includes(q) || kind.includes(q);
      })
      .sort((a, b) => {
        const da = new Date(a.created_at || 0).getTime();
        const db = new Date(b.created_at || 0).getTime();
        return db - da;
      });
  }, [historyItems, historyQuery, historyKind]);

  const historyStats = useMemo(() => {
    const counts: Record<string, number> = {};
    historyItems.forEach((h) => {
      counts[h.kind] = (counts[h.kind] || 0) + 1;
    });
    return counts;
  }, [historyItems]);

  const historySelected = useMemo(() => {
    if (!historySelectedId) return null;
    return historyView.find((h) => h.id === historySelectedId) || null;
  }, [historySelectedId, historyView]);

  useEffect(() => {
    if (!historyOpen) return;
    if (historySelectedId && historyView.find((h) => h.id === historySelectedId)) return;
    if (historyView.length) setHistorySelectedId(historyView[0].id);
  }, [historyOpen, historyView, historySelectedId]);

  const openUrl = (path?: string) => {
    if (!path) return;
    window.open(apiUrl(path), "_blank", "noopener,noreferrer");
  };

  const downloadDocx = () => {
    if (files?.docx) return openUrl(files.docx);
    if (docxId) return openUrl(`/api/design/${docxId}.docx`);
    showToast("err", "Нет DOCX для скачивания");
  };

  const downloadPdf = () => {
    if (files?.pdf) return openUrl(files.pdf);
    if (docxId) return openUrl(`/api/design/${docxId}.pdf`);
    showToast("err", "Нет PDF для скачивания");
  };

  const downloadJson = () => {
    if (files?.json) return openUrl(files.json);
    if (docxId) return openUrl(`/api/design/${docxId}.json`);
    showToast("err", "Нет JSON для скачивания");
  };

  const downloadMarkdown = () => {
    if (files?.md) return openUrl(files.md);
    if (docxId) return openUrl(`/api/design/${docxId}.md`);
    showToast("err", "Нет Markdown для скачивания");
  };

  const downloadYaml = () => {
    if (files?.yaml) return openUrl(files.yaml);
    if (docxId) return openUrl(`/api/design/${docxId}.yaml`);
    showToast("err", "Нет YAML для скачивания");
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showToast("ok", "Скопировано");
    } catch {
      showToast("err", "Не удалось скопировать");
    }
  };

  const updateSynopsisField = (key: keyof StudySynopsis, value: string, list = false) => {
    setSynopsisDraft((prev) => {
      const base = prev || synopsis;
      if (!base) return prev;
      const next: any = { ...base };
      next[key] = list ? toList(value) : value;
      return next;
    });
    setSynopsisDirty(true);
  };

  const applySynopsisDraft = () => {
    if (!synopsisDraft) return;
    setSynopsis(synopsisDraft);
    showToast("ok", "Изменения применены");
  };

  const resetSynopsisDraft = () => {
    if (!synopsis) return;
    setSynopsisDraft(synopsis);
    setSynopsisDirty(false);
  };

  const exportEditedSynopsis = async () => {
    const current = synopsisDraft || synopsis;
    if (!current) return;
    setExportLoading(true);
    try {
      const result = await exportSynopsis({
        synopsis: current,
        decision,
        stats,
        timeline,
        ragSummary,
        rag: ragData,
      });
      if (result?.docxId) setDocxId(result.docxId);
      if (result?.files) setFiles(result.files);
      setSynopsisDirty(false);
      showToast("ok", "Файлы пересобраны");
    } catch (err: any) {
      showToast("err", err?.message || "Не удалось пересобрать файлы");
    } finally {
      setExportLoading(false);
    }
  };

  const Card = ({
    title,
    icon,
    children,
    subtle,
  }: {
    title: string;
    icon?: React.ReactNode;
    children: React.ReactNode;
    subtle?: boolean;
  }) => (
    <div
      className={`rounded-3xl border border-slate-200/80 bg-white/80 backdrop-blur shadow-soft ${
        subtle ? "shadow-none bg-white/70" : ""
      }`}
    >
      <div className="px-5 pt-5 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500">
            {title}
          </div>
        </div>
      </div>
      <div className="px-5 pb-5">{children}</div>
    </div>
  );

  const Skeleton = ({ className }: { className: string }) => (
    <div className={`animate-pulse rounded-2xl bg-slate-100 ${className}`} />
  );

  const Segmented = ({
    options,
    value,
    onChange,
  }: {
    options: string[];
    value: string;
    onChange: (v: string) => void;
  }) => (
    <div className="grid grid-cols-3 gap-2">
      {options.map((v) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={`px-3 py-2.5 rounded-2xl text-xs font-extrabold border transition-all ${
            value === v
              ? "bg-slate-900 border-slate-900 text-white shadow"
              : "bg-white border-slate-200 text-slate-600 hover:border-emerald-300"
          }`}
        >
          {v}
        </button>
      ))}
    </div>
  );

  const renderDesignDiagram = () => {
    const isRep = decision?.design === "replicate";
    const sequences = isRep ? [["T", "R", "T", "R"], ["R", "T", "R", "T"]] : [["T", "R"], ["R", "T"]];

    return (
      <div className="space-y-4">
        {sequences.map((seq: string[], i: number) => (
          <div key={i} className="flex items-center gap-2">
            <div className="text-[10px] uppercase text-slate-400 w-10 font-extrabold">S{i + 1}</div>
            <div className="flex gap-2">
              {seq.map((s, idx) => (
                <div
                  key={idx}
                  className={`w-11 h-9 rounded-2xl flex items-center justify-center text-xs font-black ${
                    s === "T"
                      ? "bg-emerald-600 text-white shadow"
                      : "bg-slate-900 text-white shadow"
                  }`}
                  title={s === "T" ? "Test" : "Reference"}
                >
                  {s}
                </div>
              ))}
            </div>
          </div>
        ))}
        <div className="flex items-center gap-4 text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-2">
            <span className="w-3 h-3 rounded bg-emerald-600" />
            T — Test
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="w-3 h-3 rounded bg-slate-900" />
            R — Reference
          </span>
        </div>
      </div>
    );
  };

  const renderTimepoints = () => {
    const points = Array.isArray(timeline?.timepoints_h) ? timeline.timepoints_h : [];
    if (!points.length) return <div className="text-xs text-slate-400">Пока нет таймпоинтов.</div>;

    return (
      <div className="flex flex-wrap gap-2">
        {points.slice(0, 24).map((p: number, i: number) => (
          <span
            key={i}
            className="px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-[10px] font-extrabold"
          >
            {p}h
          </span>
        ))}
        {points.length > 24 && (
          <span className="px-2.5 py-1 rounded-full bg-white border border-slate-200 text-slate-500 text-[10px] font-extrabold">
            +{points.length - 24}
          </span>
        )}
      </div>
    );
  };


  const Funnel = () => {
    const sf = Math.max(0, Math.min(95, Number(String(screenFail).replace(",", ".")) || 0));
    const dof = Math.max(0, Math.min(95, Number(String(dropOut).replace(",", ".")) || 0));
    const screenRate = 100 - sf;
    const completeRate = Math.max(0, Math.round(screenRate * (1 - dof / 100)));
    const nScreen = Number(stats?.n_screening || 0);
    const nComplete = Number(stats?.n_required || 0);
    const nEligible = nScreen ? Math.round((screenRate / 100) * nScreen) : Math.round((screenRate / 100) * 100);

    return (
      <div className="space-y-3">
        <div className="text-xs text-slate-600">
          <span className="font-extrabold">Funnel</span>: screen-fail {sf}% → drop-out {dof}% → завершившие ~{completeRate}% от скрининга
        </div>
        <div className="space-y-2">
          <div>
            <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-400">
              <span>Скрининг</span>
              <span>{nScreen || "—"}</span>
            </div>
            <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
              <div className="h-2 bg-slate-900 transition-all" style={{ width: "100%" }} />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-400">
              <span>Допуск</span>
              <span>{nEligible || "—"}</span>
            </div>
            <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
              <div className="h-2 bg-emerald-600 transition-all" style={{ width: `${screenRate}%` }} />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-400">
              <span>Завершили</span>
              <span>{nComplete || "—"}</span>
            </div>
            <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
              <div className="h-2 bg-emerald-500 transition-all" style={{ width: `${completeRate}%` }} />
            </div>
          </div>
        </div>
      </div>
    );
  };

  const handleSendMessage = async () => {
    if (!chatInput.trim()) return;
    const userMsg: ChatMessage = { role: "user", content: chatInput, timestamp: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setChatInput("");
    setChatLoading(true);
    try {
      const response = await chatWithAssistant(chatInput, [...messages, userMsg]);
      setMessages((prev) => [...prev, { role: "assistant", content: response, timestamp: Date.now() }]);
    } catch (err) {
      showToast("err", "Чат недоступен");
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div className="min-h-screen relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-24 -left-24 h-[320px] w-[320px] rounded-full bg-emerald-200/40 blur-3xl" />
        <div className="absolute top-40 -right-24 h-[360px] w-[360px] rounded-full bg-cyan-200/40 blur-3xl" />
        <div className="absolute bottom-0 left-1/3 h-[260px] w-[260px] rounded-full bg-amber-200/30 blur-3xl" />
      </div>
      {/* Top bar */}
      <div className="sticky top-0 z-50 px-6 lg:px-10 py-5">
        <div className="rounded-3xl border border-black/10 bg-white/75 backdrop-blur-xl shadow-lift px-5 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-500 to-emerald-500 text-white flex items-center justify-center shadow">
              <Beaker size={26} />
            </div>
            <div>
              <div className="text-2xl font-black tracking-tight serif">
                Синопсис<span className="text-emerald-600">.Ассист</span>
              </div>
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-500">
                <Activity size={12} className="text-emerald-600" />
                Bioequivalence Workspace
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setHistoryOpen(true);
                loadHistory();
              }}
              className="hidden md:inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl border border-slate-200 bg-white text-slate-700 text-xs font-extrabold hover:border-emerald-300 transition-colors"
            >
              <BookOpen size={16} />
              История
            </button>

            <button
              type="button"
              onClick={(e) => runDesign(e as any)}
              disabled={loading || !inn.trim()}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-slate-900 text-white text-xs font-extrabold hover:bg-black transition-colors disabled:opacity-40"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
              Обновить
            </button>
          </div>
        </div>

        {/* History panel */}
        {historyOpen && (
          <div className="fixed inset-0 z-[70]">
            <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm" onClick={() => setHistoryOpen(false)} />
            <div className="absolute right-6 top-20 bottom-6 w-[960px] max-w-[94vw] rounded-[32px] bg-white shadow-lift border border-slate-200 flex flex-col overflow-hidden">
              <div className="p-5 border-b border-slate-200 bg-gradient-to-r from-slate-50 via-white to-emerald-50">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs uppercase tracking-[0.22em] font-extrabold text-slate-500">История синопсисов</div>
                    <div className="text-lg font-black text-slate-900">Журнал проектов и версий</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => loadHistory()}
                      className="px-3 py-2 rounded-2xl text-xs font-extrabold border border-slate-200 bg-white hover:border-emerald-300"
                    >
                      Обновить
                    </button>
                    <button
                      type="button"
                      className="text-xs font-extrabold text-slate-500 hover:text-slate-900"
                      onClick={() => setHistoryOpen(false)}
                    >
                      Закрыть
                    </button>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                  <input
                    value={historyQuery}
                    onChange={(e) => setHistoryQuery(e.target.value)}
                    placeholder="Поиск по INN, протоколу или типу"
                    className="md:col-span-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold outline-none focus:border-emerald-300 transition-colors"
                  />
                  <div className="flex flex-wrap gap-2">
                    {["all", "design", "synopsis", "parse-pdf", "chat"].map((k) => (
                      <button
                        key={k}
                        type="button"
                        onClick={() => setHistoryKind(k)}
                        className={`px-3 py-1.5 rounded-full text-[10px] font-extrabold uppercase tracking-[0.2em] border ${
                          historyKind === k
                            ? "bg-slate-900 text-white border-slate-900"
                            : "bg-white text-slate-500 border-slate-200"
                        }`}
                      >
                        {k === "all" ? "Все" : k}
                        {historyStats[k] ? ` • ${historyStats[k]}` : ""}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="flex flex-1 min-h-0">
                <div className="w-[360px] border-r border-slate-200 overflow-y-auto">
                  <div className="p-4 space-y-3">
                    {historyLoading && <div className="text-xs text-slate-500">Загрузка…</div>}
                    {!historyLoading && historyView.length === 0 && (
                      <div className="text-xs text-slate-500">История пуста.</div>
                    )}
                    {historyView.map((item) => {
                      const inn = item.payload?.inn || item.payload?.name || "—";
                      const dose = item.payload?.dosage || "";
                      const title = item.response?.synopsis?.protocolTitle || "Без заголовка";
                      const isActive = item.id === historySelectedId;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => setHistorySelectedId(item.id)}
                          className={`w-full text-left rounded-2xl border p-4 transition-all ${
                            isActive
                              ? "border-emerald-400 bg-emerald-50/70 shadow-soft"
                              : "border-slate-200 bg-white hover:border-emerald-300"
                          }`}
                        >
                          <div className="text-[10px] font-extrabold text-slate-500 uppercase tracking-[0.2em]">
                            {item.kind}
                          </div>
                          <div className="mt-1 text-sm font-black text-slate-900 line-clamp-2">{title}</div>
                          <div className="text-xs text-slate-500">{inn}{dose ? ` • ${dose} mg` : ""}</div>
                          <div className="text-[11px] text-slate-400 mt-2">{formatDate(item.created_at)}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto">
                  <div className="p-6 space-y-6">
                    {!historySelected && (
                      <div className="text-sm text-slate-500">Выберите запись слева, чтобы увидеть детали.</div>
                    )}
                    {historySelected && (() => {
                      const payload = historySelected.payload || {};
                      const response = historySelected.response || {};
                      const files = response?.files || {};
                      const synopsisTitle = response?.synopsis?.protocolTitle || "Без заголовка";
                      const cvUsed = response?.stats?.assumptions?.cv_intra || payload?.cvIntra || "—";
                      const designType = response?.decision?.design || payload?.design || "—";
                      const nRequired = response?.stats?.n_required ?? "—";
                      const nScreen = response?.stats?.n_screening ?? "—";

                      return (
                        <>
                          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-soft">
                            <div className="flex items-start justify-between gap-4">
                              <div>
                                <div className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-400">
                                  {historySelected.kind}
                                </div>
                                <div className="mt-1 text-xl font-black text-slate-900">{synopsisTitle}</div>
                                <div className="text-sm text-slate-600 mt-1">
                                  {payload.inn || payload.name || "—"} • {payload.dosage || "—"} mg • {payload.form || "—"} • {payload.regimen || "—"}
                                </div>
                                <div className="text-[11px] text-slate-400 mt-2">{formatDate(historySelected.created_at)}</div>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  onClick={() => applyHistoryItem(historySelected.id)}
                                  className="px-4 py-2 rounded-2xl text-xs font-extrabold bg-emerald-600 text-white hover:bg-emerald-700"
                                >
                                  Открыть
                                </button>
                                {files?.docx && (
                                  <button
                                    type="button"
                                    onClick={() => openUrl(files.docx)}
                                    className="px-3 py-2 rounded-2xl text-xs font-extrabold border border-slate-200 bg-white"
                                  >
                                    DOCX
                                  </button>
                                )}
                                {files?.pdf && (
                                  <button
                                    type="button"
                                    onClick={() => openUrl(files.pdf)}
                                    className="px-3 py-2 rounded-2xl text-xs font-extrabold border border-slate-200 bg-white"
                                  >
                                    PDF
                                  </button>
                                )}
                                {files?.md && (
                                  <button
                                    type="button"
                                    onClick={() => openUrl(files.md)}
                                    className="px-3 py-2 rounded-2xl text-xs font-extrabold border border-slate-200 bg-white"
                                  >
                                    MD
                                  </button>
                                )}
                                {files?.yaml && (
                                  <button
                                    type="button"
                                    onClick={() => openUrl(files.yaml)}
                                    className="px-3 py-2 rounded-2xl text-xs font-extrabold border border-slate-200 bg-white"
                                  >
                                    YAML
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                              <div className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-400">Дизайн</div>
                              <div className="mt-2 text-lg font-black text-slate-900">{designType}</div>
                              <div className="text-xs text-slate-500 mt-1">CVintra: {cvUsed}</div>
                            </div>
                            <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                              <div className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-400">Выборка</div>
                              <div className="mt-2 text-lg font-black text-slate-900">{nRequired}</div>
                              <div className="text-xs text-slate-500 mt-1">Скрининг: {nScreen}</div>
                            </div>
                            <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                              <div className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-400">Источники</div>
                              <div className="mt-2 text-lg font-black text-slate-900">
                                {Array.isArray(response?.rag?.evidence_docs) ? response.rag.evidence_docs.length : 0}
                              </div>
                              <div className="text-xs text-slate-500 mt-1">evidence docs</div>
                            </div>
                          </div>

                          <div className="rounded-3xl border border-slate-200 bg-white p-5">
                            <div className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-400">Сводка</div>
                            <div className="mt-2 text-sm text-slate-700 whitespace-pre-wrap">
                              {response?.synopsis?.objectives || response?.synopsis?.methodology || "Нет текста"}
                            </div>
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Main grid */}
      <main className="px-6 lg:px-10 pb-24 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left panel */}
        <aside className="lg:col-span-4">
          <div className="rounded-3xl border border-black/10 bg-white/80 backdrop-blur shadow-lift p-6">
            <div className="flex items-center gap-3 text-emerald-700 mb-5">
              <Search size={22} />
              <div className="text-lg font-black serif">Проектирование</div>
            </div>

            <form onSubmit={(e) => runDesign(e)} className="space-y-5">
              {/* Drug */}
              <div className="rounded-3xl border border-slate-200 bg-white p-4">
                <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500 mb-3">
                  Препарат
                </div>

                <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-1">
                  МНН (INN)
                </label>
                <input
                  value={inn}
                  onChange={(e) => setInn(e.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                  placeholder="Rosuvastatin"
                />

                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div>
                    <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-1">
                      Доза (mg)
                    </label>
                    <input
                      value={dosage}
                      onChange={(e) => setDosage(e.target.value)}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                      placeholder="20"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-1">
                      CVintra
                    </label>
                    <input
                      value={cvIntra}
                      onChange={(e) => setCvIntra(e.target.value)}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                      placeholder="auto или 0.24"
                    />
                  </div>
                </div>

                <div className="mt-3">
                  <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-1">
                    Форма
                  </label>
                  <input
                    value={form}
                    onChange={(e) => setForm(e.target.value)}
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                  />
                </div>

                <div className="mt-3">
                  <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-2">
                    Референтный препарат (GRLS)
                  </label>
                  {!refManual && (
                    <select
                      value={refTradeName}
                      onChange={(e) => setRefTradeName(e.target.value)}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                      disabled={refLoading}
                    >
                      <option value="">Авто (по умолчанию)</option>
                      {refOptions.map((o, idx) => (
                        <option key={`${o.trade_name}-${idx}`} value={o.trade_name}>
                          {o.trade_name} • {o.reg_date || "—"} • score {o.score ?? "—"}
                        </option>
                      ))}
                    </select>
                  )}

                  {refManual && (
                    <input
                      value={refManualValue}
                      onChange={(e) => setRefManualValue(e.target.value)}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                      placeholder="Введите торговое название вручную"
                    />
                  )}
                  {refLoading && <div className="mt-2 text-xs text-slate-500">Загрузка списка референтов…</div>}
                  {refError && <div className="mt-2 text-xs text-red-600">{refError}</div>}

                  <div className="mt-2 flex items-center gap-2 text-xs text-slate-600">
                    <input
                      id="ref-manual"
                      type="checkbox"
                      checked={refManual}
                      onChange={(e) => setRefManual(e.target.checked)}
                    />
                    <label htmlFor="ref-manual">Ввести вручную</label>
                  </div>
                </div>
              </div>

              {/* Conditions */}
              <div className="rounded-3xl border border-slate-200 bg-white p-4">
                <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500 mb-3">
                  Условия
                </div>

                <div className="flex items-center justify-between gap-3 p-3 rounded-2xl bg-emerald-50 border border-emerald-100">
                  <div className="flex items-center gap-2">
                    <Sigma className="text-emerald-700" size={18} />
                    <div>
                      <div className="text-xs font-extrabold text-emerald-900">RSABE (HVD)</div>
                      <div className="text-[11px] text-emerald-700">использовать при CV &gt; 30%</div>
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={rsabe}
                    onChange={(e) => setRsabe(e.target.checked)}
                    className="w-6 h-6 accent-emerald-600"
                  />
                </div>

                <div className="mt-3">
                  <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-2">
                    Дизайн
                  </label>
                  <select
                    value={design}
                    onChange={(e) => setDesign(e.target.value)}
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                  >
                    <option value="auto">Авто</option>
                    <option value="2x2">2×2 Cross-over</option>
                    <option value="replicate">Replicate</option>
                    <option value="parallel">Параллельный</option>
                  </select>
                </div>

                <div className="mt-3">
                  <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-2">
                    Режим
                  </label>
                  <Segmented
                    options={["Натощак", "После еды", "Оба варианта"]}
                    value={regimen}
                    onChange={(v) => setRegimen(v as any)}
                  />
                </div>

                <div className="mt-3">
                  <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-2">
                    Тип исследования
                  </label>
                  <select
                    value={studyType}
                    onChange={(e) => setStudyType(e.target.value)}
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                  >
                    <option>Однофазное</option>
                    <option>Двухфазное</option>
                    <option>Пилотное</option>
                  </select>
                </div>

                
              </div>

              {/* Losses */}
              <div className="rounded-3xl border border-slate-200 bg-white p-4">
                <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500 mb-3">
                  Потери и импорт
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-1">
                      Drop-out %
                    </label>
                    <input
                      value={dropOut}
                      onChange={(e) => setDropOut(e.target.value)}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                      placeholder="20"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-1">
                      Screen-fail %
                    </label>
                    <input
                      value={screenFail}
                      onChange={(e) => setScreenFail(e.target.value)}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                      placeholder="10"
                    />
                  </div>
                </div>

                <div className="mt-3">
                  <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-2">
                    PDF (опционально)
                  </label>
                  <div className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                    <div className="flex items-center gap-2 text-sm text-slate-700">
                      <FileUp size={18} className="text-emerald-700" />
                      <span className="font-semibold">
                        {parserFile ? parserFile.name : "Загрузить файл"}
                      </span>
                    </div>
                    <input
                      type="file"
                      accept=".pdf"
                      onChange={(e) => setParserFile(e.target.files?.[0] || null)}
                      className="text-xs text-slate-600"
                    />
                  </div>
                  <label className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-slate-600">
                    <input
                      type="checkbox"
                      checked={deepMode}
                      onChange={(e) => setDeepMode(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    Deep OCR (медленно, для сканов)
                  </label>
                </div>

                <div className="mt-3">
                  <label className="block text-[11px] uppercase tracking-[0.18em] font-extrabold text-slate-400 mb-2">
                    Доп. требования
                  </label>
                  <textarea
                    value={constraints}
                    onChange={(e) => setConstraints(e.target.value)}
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none focus:bg-white focus:border-emerald-300 transition-colors min-h-[92px]"
                    placeholder="Пол, возраст, BMI и т.п."
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3">
                <button
                  type="submit"
                  disabled={loading || !inn.trim()}
                  className="w-full rounded-3xl bg-emerald-600 text-white py-4 font-black text-sm shadow hover:bg-emerald-700 active:scale-[0.99] transition-all disabled:opacity-40"
                >
                  {loading ? (
                    <span className="inline-flex items-center gap-2">
                      <Loader2 size={18} className="animate-spin" />
                      {jobMessage || "Генерация…"}
                    </span>
                  ) : (
                    "Сгенерировать (Draft)"
                  )}
                </button>
                <button
                  type="button"
                  disabled={loading || !inn.trim() || !synopsis}
                  onClick={() => runEnrich()}
                  className="w-full rounded-3xl border border-emerald-200 text-emerald-700 py-3 font-bold text-sm hover:bg-emerald-50 transition-all disabled:opacity-40"
                >
                  Обогатить источниками
                </button>
                <button
                  type="button"
                  disabled={loading || !inn.trim() || !synopsis}
                  onClick={() => runDeepOcr()}
                  className="w-full rounded-3xl border border-slate-200 text-slate-700 py-3 font-bold text-sm hover:bg-slate-50 transition-all disabled:opacity-40"
                >
                  Deep OCR (сканы)
                </button>
              </div>

              {loading && (
                <div className="text-[11px] text-slate-500">
                  {jobId ? `Задача: ${jobId.slice(0, 8)} • ${jobStage || "ожидание"}` : "Запуск задачи…"}
                </div>
              )}

              {parserError && (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {parserError}
                </div>
              )}
            </form>
          </div>
        </aside>

        {/* Right board */}
        <section className="lg:col-span-8 space-y-6">
          {/* Project header */}
          <div className="rounded-3xl border border-black/10 bg-white/80 backdrop-blur shadow-lift p-6">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div>
                <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500">
                  {isEmpty ? "Готов к проектированию" : "Проект"}
                </div>
                <div className="mt-1 text-2xl font-black serif">{projectTitle}</div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-slate-200 bg-white text-[11px] font-extrabold text-slate-600">
                    <BookOpen size={14} className="text-emerald-700" />
                    Evidence: {evidenceCount}
                  </span>
                  <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-slate-200 bg-white text-[11px] font-extrabold text-slate-600">
                    <ShieldCheck size={14} className="text-slate-800" />
                    Confidence: {confidence}
                  </span>
                  <span className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border bg-white text-[11px] font-extrabold ${
                    statusOk ? "border-emerald-200 text-emerald-700" : "border-amber-200 text-amber-700"
                  }`}>
                    {statusOk ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                    {statusOk ? "OK" : `Warnings: ${warnings.length}`}
                  </span>
                </div>
              </div>

              {/* Downloads */}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={downloadDocx}
                  disabled={!docxId && !files?.docx}
                  className="px-4 py-2.5 rounded-2xl bg-slate-900 text-white text-xs font-extrabold hover:bg-black transition-colors disabled:opacity-40"
                >
                  DOCX
                </button>
                <button
                  type="button"
                  onClick={downloadPdf}
                  disabled={!docxId && !files?.pdf}
                  className="px-4 py-2.5 rounded-2xl bg-white border border-slate-200 text-slate-800 text-xs font-extrabold hover:border-emerald-300 transition-colors disabled:opacity-40"
                >
                  PDF
                </button>
                <button
                  type="button"
                  onClick={downloadJson}
                  disabled={!docxId && !files?.json}
                  className="px-4 py-2.5 rounded-2xl bg-white border border-slate-200 text-slate-800 text-xs font-extrabold hover:border-emerald-300 transition-colors disabled:opacity-40"
                >
                  JSON
                </button>
              </div>
            </div>

            {!statusOk && (
              <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                <div className="font-extrabold mb-1">Предупреждения</div>
                <ul className="list-disc pl-5 space-y-1">
                  {warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {(isEmpty || isDraft) && (
              <div className="mt-5 rounded-3xl border border-slate-200 bg-slate-50 p-5">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-2xl bg-white border border-slate-200 flex items-center justify-center">
                    <Info size={18} className="text-emerald-700" />
                  </div>
                  <div>
                    <div className="font-black text-slate-900">
                      {isEmpty ? "Введите МНН слева" : "Черновик готов — нажмите «Сгенерировать (Draft)»"}
                    </div>
                    <div className="mt-1 text-sm text-slate-600">
                      Справа появятся выбранный дизайн, расчёт выборки, таймпоинты, источники и секции синопсиса.
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Summary row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card title="Дизайн" icon={<Activity size={16} className="text-emerald-700" />}>
              {loading ? (
                <div className="space-y-2">
                  <Skeleton className="h-5 w-24" />
                  <Skeleton className="h-3 w-40" />
                  <Skeleton className="h-3 w-32" />
                </div>
              ) : (
                <div className="space-y-1">
                  <div className="text-lg font-black text-slate-900 mono">{safeText(decision?.design)}</div>
                  <div className="text-sm text-slate-600">Периоды: <span className="font-bold">{safeText(decision?.periods)}</span></div>
                  <div className="text-sm text-slate-600">Последовательности: <span className="font-bold">{safeText(decision?.sequences)}</span></div>
                  <div className="text-sm text-slate-600">Washout: <span className="font-bold">{safeText(decision?.washout_days)}</span> дней</div>
                </div>
              )}
            </Card>

            <Card title="Выборка" icon={<Sigma size={16} className="text-emerald-700" />}>
              {loading ? (
                <div className="space-y-2">
                  <Skeleton className="h-5 w-44" />
                  <Skeleton className="h-3 w-36" />
                  <Skeleton className="h-3 w-28" />
                </div>
              ) : (
                <div className="space-y-1">
                  <div className="text-lg font-black text-slate-900 mono">N: {safeText(stats?.n_required)}</div>
                  <div className="text-sm text-slate-600">К скринингу: <span className="font-bold">{safeText(stats?.n_screening)}</span></div>
                  <div className="text-sm text-slate-600">CV использован: <span className="font-bold">{safeText(stats?.assumptions?.cv_intra)}</span></div>
                  <div className="text-sm text-slate-600">α 0.05 · Power 80%</div>
                </div>
              )}
            </Card>

            <Card title="Потери" icon={<ShieldCheck size={16} className="text-emerald-700" />}>
              <Funnel />
            </Card>
          </div>

          {/* Diagram + timepoints */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title="Схема исследования" icon={<Activity size={16} className="text-emerald-700" />}>
              {loading ? (
                <div className="space-y-3">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-5/6" />
                </div>
              ) : (
                renderDesignDiagram()
              )}
            </Card>

            <Card title="Сетка отбора" icon={<Search size={16} className="text-emerald-700" />}>
              <div className="text-xs text-slate-500 mb-3">
                Уплотнение вокруг Tmax + хвост по t1/2
              </div>
              {loading ? (
                <div className="flex flex-wrap gap-2">
                  {Array.from({ length: 14 }).map((_, i) => (
                    <Skeleton key={i} className="h-6 w-12 rounded-full" />
                  ))}
                </div>
              ) : (
                renderTimepoints()
              )}
            </Card>
          </div>

          <Card title="Progress Board" icon={<Loader2 size={16} className="text-emerald-700" />}>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
              {progressSteps.map((s, idx) => {
                const isActive = idx === Math.max(0, currentStageIndex - 1);
                const isDone = currentStageIndex > idx;
                const isError = jobStage === "error";
                const state = isError && isActive ? "error" : isDone ? "done" : isActive ? "active" : "idle";
                return (
                  <div
                    key={s.key}
                    className={`rounded-2xl border px-3 py-3 text-xs font-extrabold uppercase tracking-[0.2em] ${
                      state === "done"
                        ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                        : state === "active"
                        ? "bg-slate-900 border-slate-900 text-white"
                        : state === "error"
                        ? "bg-red-50 border-red-200 text-red-700"
                        : "bg-white border-slate-200 text-slate-500"
                    }`}
                  >
                    {s.label}
                  </div>
                );
              })}
            </div>
            <div className="mt-3 text-xs text-slate-500">
              {jobMessage || "Ожидание задачи"}
            </div>
          </Card>

          {/* Tabs */}
          <Card title="Рабочая область" icon={<Cpu size={16} className="text-emerald-700" />}>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              {(["synopsis", "calc", "sources", "grls"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setRightTab(t)}
                  className={`px-4 py-2.5 rounded-2xl text-xs font-extrabold border transition-all ${
                    rightTab === t
                      ? "bg-emerald-600 border-emerald-600 text-white"
                      : "bg-white border-slate-200 text-slate-600 hover:border-emerald-300"
                  }`}
                >
                  {t === "synopsis"
                    ? "Синопсис"
                    : t === "calc"
                    ? "Расчёты"
                    : t === "sources"
                    ? "Источники"
                    : "Справочник GRLS"}
                </button>
              ))}

              <div className="ml-auto flex items-center gap-2">
                {rightTab === "synopsis" && (
                  <button
                    type="button"
                    onClick={() => exportEditedSynopsis()}
                    disabled={!synopsisDirty || exportLoading}
                    className={`inline-flex items-center gap-2 px-3 py-2.5 rounded-2xl border text-xs font-extrabold transition-colors ${
                      synopsisDirty
                        ? "bg-slate-900 border-slate-900 text-white hover:bg-black"
                        : "bg-white border-slate-200 text-slate-400"
                    }`}
                  >
                    {exportLoading ? "Сборка…" : "Пересобрать файлы"}
                  </button>
                )}
                {synopsis?.markdown && (
                  <button
                    type="button"
                    onClick={() => copyToClipboard(synopsis.markdown)}
                    className="inline-flex items-center gap-2 px-3 py-2.5 rounded-2xl border border-slate-200 bg-white text-xs font-extrabold text-slate-700 hover:border-emerald-300 transition-colors"
                  >
                    <Clipboard size={14} />
                    Copy MD
                  </button>
                )}
                {synopsis?.yaml && (
                  <button
                    type="button"
                    onClick={() => copyToClipboard(synopsis.yaml)}
                    className="inline-flex items-center gap-2 px-3 py-2.5 rounded-2xl border border-slate-200 bg-white text-xs font-extrabold text-slate-700 hover:border-emerald-300 transition-colors"
                  >
                    <Clipboard size={14} />
                    Copy YAML
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => downloadMarkdown()}
                  className="inline-flex items-center gap-2 px-3 py-2.5 rounded-2xl border border-slate-200 bg-white text-xs font-extrabold text-slate-700 hover:border-emerald-300 transition-colors"
                >
                  MD
                </button>
                <button
                  type="button"
                  onClick={() => downloadYaml()}
                  className="inline-flex items-center gap-2 px-3 py-2.5 rounded-2xl border border-slate-200 bg-white text-xs font-extrabold text-slate-700 hover:border-emerald-300 transition-colors"
                >
                  YAML
                </button>
              </div>
            </div>

            {/* loading state */}
            {loading && (
              <div className="space-y-3">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-5/6" />
                <Skeleton className="h-14 w-4/6" />
              </div>
            )}

            {!loading && rightTab === "synopsis" && synopsis && (
              <div className="space-y-4">
                <SynopsisSection
                  title="Общие сведения"
                  sectionKey="meta"
                  icon={<Info size={16} className="text-emerald-700" />}
                  fields={[
                    { label: "Название протокола", value: synopsis.protocolTitle, key: "protocolTitle" },
                    { label: "Номер протокола", value: synopsis.protocolNumber, key: "protocolNumber" },
                  ]}
                  editSection={editSection}
                  setEditSection={setEditSection}
                  safeText={safeText}
                  updateSynopsisField={updateSynopsisField}
                  synopsisDraft={synopsisDraft}
                />

                <SynopsisSection
                  title="Цели"
                  sectionKey="obj"
                  icon={<Activity size={16} className="text-emerald-700" />}
                  fields={[
                    { label: "Objectives", value: synopsis.objectives, key: "objectives" },
                    { label: "Tasks (по одной в строке)", value: synopsis.tasks, key: "tasks", list: true },
                  ]}
                  editSection={editSection}
                  setEditSection={setEditSection}
                  safeText={safeText}
                  updateSynopsisField={updateSynopsisField}
                  synopsisDraft={synopsisDraft}
                />

                <SynopsisSection
                  title="Дизайн и методология"
                  sectionKey="design"
                  icon={<Sigma size={16} className="text-emerald-700" />}
                  fields={[
                    { label: "Design", value: synopsis.design, key: "design" },
                    { label: "Study periods", value: synopsis.studyPeriods, key: "studyPeriods" },
                    { label: "Methodology", value: synopsis.methodology, key: "methodology" },
                  ]}
                  editSection={editSection}
                  setEditSection={setEditSection}
                  safeText={safeText}
                  updateSynopsisField={updateSynopsisField}
                  synopsisDraft={synopsisDraft}
                />

                <SynopsisSection
                  title="Популяция"
                  sectionKey="pop"
                  icon={<ShieldCheck size={16} className="text-emerald-700" />}
                  fields={[
                    { label: "Population", value: synopsis.population, key: "population" },
                    { label: "Inclusion (по одной в строке)", value: synopsis.inclusionCriteria, key: "inclusionCriteria", list: true },
                    { label: "Exclusion (по одной в строке)", value: synopsis.exclusionCriteria, key: "exclusionCriteria", list: true },
                  ]}
                  editSection={editSection}
                  setEditSection={setEditSection}
                  safeText={safeText}
                  updateSynopsisField={updateSynopsisField}
                  synopsisDraft={synopsisDraft}
                />

                <SynopsisSection
                  title="Статистика"
                  sectionKey="stats"
                  icon={<Sigma size={16} className="text-emerald-700" />}
                  fields={[
                    { label: "PK parameters", value: synopsis.pkParameters, key: "pkParameters" },
                    { label: "BE criteria", value: synopsis.beCriteria, key: "beCriteria" },
                    { label: "Sample size calculation", value: synopsis.sampleSizeCalculation, key: "sampleSizeCalculation" },
                  ]}
                  editSection={editSection}
                  setEditSection={setEditSection}
                  safeText={safeText}
                  updateSynopsisField={updateSynopsisField}
                  synopsisDraft={synopsisDraft}
                />
              </div>
            )}

            {!loading && rightTab === "calc" && (
              <div className="space-y-4 text-sm text-slate-700">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="rounded-3xl border border-slate-200 bg-white p-4">
                    <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500">
                      Выборка
                    </div>
                    <div className="mt-3 h-40">
                      <Bar
                        data={{
                          labels: ["Completed", "Dropout adj", "Screening"],
                          datasets: [
                            {
                              label: "N",
                              data: [
                                stats?.n_required || 0,
                                stats?.n_dropout_adjusted || 0,
                                stats?.n_screening || 0,
                              ],
                              backgroundColor: ["#10b981", "#34d399", "#0ea5e9"],
                              borderRadius: 8,
                            },
                          ],
                        }}
                        options={{
                          responsive: true,
                          maintainAspectRatio: false,
                          plugins: { legend: { display: false } },
                          scales: {
                            x: { ticks: { font: { size: 10 } } },
                            y: { ticks: { font: { size: 10 } } },
                          },
                        }}
                      />
                    </div>
                  </div>

                  <div className="rounded-3xl border border-slate-200 bg-white p-4">
                    <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500">
                      Таймпоинты
                    </div>
                    <div className="mt-3 h-40">
                      <Line
                        data={{
                          labels: (timeline?.timepoints_h || []).map((_: number, i: number) => i + 1),
                          datasets: [
                            {
                              label: "Time (h)",
                              data: timeline?.timepoints_h || [],
                              borderColor: "#0ea5e9",
                              backgroundColor: "rgba(14,165,233,0.2)",
                              fill: true,
                              tension: 0.3,
                              pointRadius: 2,
                            },
                          ],
                        }}
                        options={{
                          responsive: true,
                          maintainAspectRatio: false,
                          plugins: { legend: { display: false } },
                          scales: {
                            x: { ticks: { font: { size: 10 } } },
                            y: { ticks: { font: { size: 10 } } },
                          },
                        }}
                      />
                    </div>
                  </div>
                </div>

                <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                  <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500">
                    Формулы
                  </div>
                  <div className="mt-3 space-y-2">
                    <div>1) s² = ln(1 + CV²)</div>
                    <div>2) n0 = 2 × (Zα + Zβ)² × s² / Δ², где Δ = ln(1.25)</div>
                    <div>3) Коррекция: drop-out и screen-fail</div>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="rounded-3xl border border-slate-200 p-5">
                    <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500">Допущения</div>
                    <div className="mt-3 space-y-1">
                      <div>CV: <span className="font-bold">{safeText(stats?.assumptions?.cv_intra)}</span></div>
                      <div>α: 0.05</div>
                      <div>Power: 80%</div>
                      <div>Drop-out: {dropOut}%</div>
                      <div>Screen-fail: {screenFail}%</div>
                    </div>
                  </div>

                  <div className="rounded-3xl border border-slate-200 p-5">
                    <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500">Результат</div>
                    <div className="mt-3 space-y-1">
                      <div>N завершивших: <span className="font-bold">{safeText(stats?.n_required)}</span></div>
                      <div>N screening: <span className="font-bold">{safeText(stats?.n_screening)}</span></div>
                      <div>Washout (days): <span className="font-bold">{safeText(decision?.washout_days)}</span></div>
                      <div>Horizon (h): <span className="font-bold">{safeText(timeline?.sampling_horizon_h)}</span></div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {!loading && rightTab === "sources" && (
              <div className="space-y-3">
                {Array.isArray(ragData?.search_queries) && ragData.search_queries.length > 0 && (
                  <div className="rounded-3xl border border-slate-200 bg-white p-4">
                    <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500 mb-2">
                      Поисковые запросы
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {ragData.search_queries.slice(0, 12).map((q: string, i: number) => (
                        <span
                          key={`${q}-${i}`}
                          className="px-3 py-1.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-extrabold"
                        >
                          {q}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {Array.isArray(ragData?.be?.dois) && ragData.be.dois.length > 0 && (
                  <div className="rounded-3xl border border-slate-200 bg-white p-4">
                    <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500 mb-2">
                      DOI (из источников)
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {ragData.be.dois.slice(0, 8).map((d: string, i: number) => (
                        <span
                          key={`${d}-${i}`}
                          className="px-3 py-1.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-extrabold"
                        >
                          {d}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {Array.isArray(synopsis?.bibliography) && synopsis!.bibliography.length > 0 ? (
                  synopsis!.bibliography.slice(0, 40).map((b: any, i: number) => (
                    <div
                      key={i}
                      className="rounded-2xl border border-slate-200 bg-slate-50 p-4 flex items-start justify-between gap-3"
                    >
                      <div>
                        <div className="text-sm font-extrabold text-slate-900">{b.title || "Источник"}</div>
                        <div className="text-xs text-slate-500 break-all">{b.uri}</div>
                        {(b.used_for || b.confidence) && (
                          <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
                            {b.used_for && <span className="px-2 py-1 rounded-full bg-white border border-slate-200">{b.used_for}</span>}
                            {b.confidence && <span className="px-2 py-1 rounded-full bg-white border border-slate-200">{b.confidence}</span>}
                          </div>
                        )}
                      </div>
                      <div className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-400">
                        ref
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-sm text-slate-500">Источники пока не найдены.</div>
                )}

                {ragData?.context_preview && (
                  <div className="rounded-3xl border border-slate-200 bg-white p-4">
                    <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500 mb-2">
                      Контекст (preview)
                    </div>
                    <pre className="text-xs text-slate-700 whitespace-pre-wrap">{String(ragData.context_preview)}</pre>
                  </div>
                )}
              </div>
            )}

            {!loading && rightTab === "grls" && (
              <div className="space-y-4">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="text-[11px] uppercase tracking-[0.22em] font-extrabold text-slate-500 mb-2">
                    Быстрый поиск по GRLS
                  </div>
                  <input
                    value={grlsQuery}
                    onChange={(e) => setGrlsQuery(e.target.value)}
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold outline-none focus:border-emerald-300 transition-colors"
                    placeholder="Введите МНН или торговое название"
                  />
                  <div className="mt-2 text-xs text-slate-500">
                    Фильтр дозы/формы берётся из текущих полей слева.
                  </div>
                </div>

                {grlsLoading && <div className="text-sm text-slate-500">Поиск…</div>}
                {grlsError && <div className="text-sm text-red-600">{grlsError}</div>}

                {!grlsLoading && !grlsError && grlsResults.length === 0 && grlsQuery.trim() && (
                  <div className="text-sm text-slate-500">Ничего не найдено.</div>
                )}

                <div className="space-y-2">
                  {grlsResults.map((r, i) => (
                    <div
                      key={`${r.trade_name}-${i}`}
                      className="rounded-2xl border border-slate-200 bg-white p-4"
                    >
                      <div className="text-sm font-extrabold text-slate-900">
                        {r.trade_name} <span className="text-xs text-slate-400">score {r.score}</span>
                      </div>
                      <div className="text-xs text-slate-500">{r.inn}</div>
                      <div className="text-xs text-slate-500">{r.forms}</div>
                      <div className="text-xs text-slate-400 mt-1">
                        {r.reg_no || "—"} • {r.reg_date || "—"}
                      </div>
                      <div className="mt-2">
                        <button
                          type="button"
                          onClick={() => {
                            setRefManual(false);
                            setRefTradeName(r.trade_name);
                            showToast("ok", "Референт выбран");
                          }}
                          className="px-3 py-1.5 rounded-2xl text-xs font-extrabold bg-emerald-600 text-white hover:bg-emerald-700"
                        >
                          Выбрать как референт
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </section>
      </main>

      {/* Floating chat */}
      <div className="fixed bottom-7 left-7 z-[80]">
        {!chatOpen ? (
          <button
            type="button"
            onClick={() => setChatOpen(true)}
            className="w-16 h-16 rounded-2xl bg-slate-900 text-white shadow-lift flex items-center justify-center hover:scale-[1.03] active:scale-[0.98] transition-transform"
            aria-label="open chat"
          >
            <MessageSquare size={28} />
          </button>
        ) : (
          <div className="w-[420px] h-[560px] rounded-[28px] border border-slate-200 bg-white shadow-lift overflow-hidden flex flex-col">
            <div className="bg-slate-900 text-white px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-emerald-600 flex items-center justify-center">
                  <Cpu size={18} />
                </div>
                <div>
                  <div className="text-sm font-black">Регуляторный ассистент</div>
                  <div className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-slate-300">
                    online
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setChatOpen(false)}
                className="w-9 h-9 rounded-2xl hover:bg-white/10 flex items-center justify-center"
                aria-label="close chat"
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 bg-slate-50 space-y-4">
              {messages.length === 0 && (
                <div className="mt-12 text-center text-slate-500">
                  <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-white border border-slate-200">
                    <Info size={18} className="text-emerald-700" />
                  </div>
                  <div className="mt-3 text-sm">
                    Спросите про RSABE, дизайн, выборку или требования Решения №85.
                  </div>
                </div>
              )}

              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm shadow-sm ${
                      m.role === "user"
                        ? "bg-emerald-600 text-white rounded-tr-none"
                        : "bg-white text-slate-800 border border-slate-200 rounded-tl-none"
                    }`}
                  >
                    {m.content}
                  </div>
                </div>
              ))}

              {chatLoading && (
                <div className="flex justify-start">
                  <div className="px-4 py-3 rounded-2xl bg-white border border-slate-200">
                    <Loader2 size={16} className="animate-spin text-emerald-700" />
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            <div className="p-4 border-t border-slate-200 bg-white">
              <div className="relative">
                <input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  placeholder="Ваш вопрос…"
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 pr-12 text-sm outline-none focus:bg-white focus:border-emerald-300 transition-colors"
                />
                <button
                  type="button"
                  onClick={handleSendMessage}
                  className="absolute right-2 top-2 w-9 h-9 rounded-2xl bg-emerald-600 text-white flex items-center justify-center hover:bg-emerald-700 transition-colors"
                  aria-label="send"
                >
                  <Send size={16} />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-7 right-7 z-[90]">
          <div
            className={`rounded-2xl px-4 py-3 shadow-lift border text-sm font-semibold ${
              toast.kind === "ok"
                ? "bg-emerald-600 text-white border-emerald-600"
                : "bg-red-600 text-white border-red-600"
            }`}
          >
            {toast.text}
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
