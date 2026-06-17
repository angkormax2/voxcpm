"use client";

import { STUDIO_NAME } from "@configs/studioBranding";
import { useState, useEffect, useRef, useMemo } from "react";
import axios from "axios";
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Slider,
  Switch,
  FormControlLabel,
  Grid,
  CircularProgress,
  Divider,
  Alert,
  Autocomplete,
  Chip,
  IconButton,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tooltip,
  LinearProgress
} from "@mui/material";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";

const API_BASE = "http://127.0.0.1:8000/api";

const AUTO_VOICE = { id: "auto", name: "Auto — match saved voice by speaker", type: "auto", gender: null };
const NONE_VOICE = { id: "none", name: "None — use upload or style only", type: "none", gender: null };

const GENDER_LABELS: Record<string, string> = {
  male: "Male",
  female: "Female",
  child: "Child",
  neutral: "Neutral"
};

type VoiceOption = {
  id: string;
  name: string;
  type: string;
  gender?: string | null;
};

type GenderOption = { label: string; value: string };
type BatchStatus = "pending" | "processing" | "done" | "failed";
type BatchItem = {
  id: string;
  text: string;
  fileName: string;
  status: BatchStatus;
  error?: string;
};

type OutputFile = {
  name: string;
  size_bytes: number;
  modified_at: string;
};

function formatDuration(sec?: number | null): string {
  if (sec == null || Number.isNaN(sec)) return "";
  const total = Math.max(0, Math.round(sec));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function shortOutputName(name: string): string {
  if (name.length <= 32) return name;
  return `${name.slice(0, 14)}…${name.slice(-16)}`;
}

function formatSavedTime(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.replace("T", " ").slice(0, 16);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function historyRowTitle(file: OutputFile): string {
  return formatSavedTime(file.modified_at) || shortOutputName(file.name);
}

function outputFileUrl(name: string): string {
  return `${API_BASE}/outputs/file/${encodeURIComponent(name)}`;
}

function base64ToBlob(b64: string, mime: string): Blob {
  const bytes = atob(b64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

export default function VoxCPMStudio() {
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [genderOptions, setGenderOptions] = useState<GenderOption[]>([]);
  const [speakerOptions, setSpeakerOptions] = useState<GenderOption[]>([]);
  const [text, setText] = useState("");
  const [speakerGender, setSpeakerGender] = useState("female");
  const [voiceSelect, setVoiceSelect] = useState("auto");
  const [controlInstruction, setControlInstruction] = useState("");
  const [cfgValue, setCfgValue] = useState(2.0);
  const [normalize, setNormalize] = useState(true);
  const [denoise, setDenoise] = useState(false);
  const [timesteps, setTimesteps] = useState(10);

  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [promptText, setPromptText] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);

  const [saveName, setSaveName] = useState("");
  const [saveGender, setSaveGender] = useState("female");
  const [saveAudio, setSaveAudio] = useState<File | null>(null);
  const [savePrompt, setSavePrompt] = useState("");
  const [saving, setSaving] = useState(false);

  const [loading, setLoading] = useState(false);
  const [audioUrl, setAudioUrl] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [logs, setLogs] = useState<string[]>([]);
  const [synthesisPlan, setSynthesisPlan] = useState("");
  const [lastMeta, setLastMeta] = useState<{ duration?: number; device?: string; sampleRate?: number } | null>(null);
  const [lastAudioFile, setLastAudioFile] = useState<File | null>(null);
  const [saveLastName, setSaveLastName] = useState("");
  const [saveLastGender, setSaveLastGender] = useState("female");
  const [showSaveLast, setShowSaveLast] = useState(false);
  const [savingLast, setSavingLast] = useState(false);
  const [outputFolder, setOutputFolder] = useState("");
  const [outputCount, setOutputCount] = useState(0);
  const [outputFiles, setOutputFiles] = useState<OutputFile[]>([]);
  const [outputMeta, setOutputMeta] = useState<Record<string, { genSec: number; audioSec?: number }>>({});
  const [lastFinishInfo, setLastFinishInfo] = useState<{ genSec: number; audioSec?: number } | null>(null);
  const [activeOutputName, setActiveOutputName] = useState<string | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [etaSec, setEtaSec] = useState<number | null>(null);
  const [genStartedAt, setGenStartedAt] = useState<number | null>(null);
  const [avgSecPerChar, setAvgSecPerChar] = useState(0.08);
  const [stickyVoiceId, setStickyVoiceId] = useState("");
  const [batchInput, setBatchInput] = useState("");
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [deleteOutputsDialogOpen, setDeleteOutputsDialogOpen] = useState(false);
  const [deleteOneOutputName, setDeleteOneOutputName] = useState<string | null>(null);
  const [showOutputDetails, setShowOutputDetails] = useState(false);

  // --- License chunk limits ---
  const [licenseMaxChunks, setLicenseMaxChunks] = useState<number | null>(null);
  const [licenseWarningThreshold, setLicenseWarningThreshold] = useState<number | null>(null);
  const [licenseChunkChars, setLicenseChunkChars] = useState(260);
  const [showUpgradeDialog, setShowUpgradeDialog] = useState(false);

  const logBoxRef = useRef<HTMLDivElement>(null);
  const mainAudioRef = useRef<HTMLAudioElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const saveFileRef = useRef<HTMLInputElement>(null);

  const savedVoices = useMemo(() => voices.filter(v => v.type === "saved"), [voices]);
  const pickerOptions = useMemo(
    () => [AUTO_VOICE, NONE_VOICE, ...voices.filter(v => v.type !== "none")],
    [voices]
  );

  const matchedProfile = useMemo(() => {
    if (speakerGender === "unknown" || speakerGender === "auto") return null;
    const matches = savedVoices.filter(v => (v.gender || "unknown") === speakerGender);
    return matches.length ? matches[matches.length - 1] : null;
  }, [savedVoices, speakerGender]);

  useEffect(() => {
    if (loading) setShowOutputDetails(true);
  }, [loading]);

  useEffect(() => {
    fetchVoices();
    void fetchOutputStats();
    void fetchLicenseLimits();
  }, []);

  useEffect(() => {
    // Reset auto voice lock when speaker context changes.
    setStickyVoiceId("");
  }, [speakerGender, audioFile]);

  useEffect(() => {
    if (voiceSelect !== "auto") setStickyVoiceId("");
  }, [voiceSelect]);

  useEffect(() => {
    if (!loading || genStartedAt == null) return;
    const id = window.setInterval(() => {
      const sec = Math.max(0, Math.floor((Date.now() - genStartedAt) / 1000));
      setElapsedSec(sec);
      if (etaSec != null) setEtaSec(Math.max(0, etaSec - 1));
    }, 1000);
    return () => window.clearInterval(id);
  }, [loading, genStartedAt, etaSec]);

  const fetchVoices = async () => {
    try {
      const res = await axios.get(`${API_BASE}/voices`);
      setVoices(res.data.voices || []);
      setGenderOptions(res.data.gender_options || []);
      setSpeakerOptions(res.data.speaker_options || []);
    } catch (err) {
      console.error("Failed to fetch voices", err);
    }
  };

  const fetchOutputStats = async () => {
    try {
      const res = await axios.get(`${API_BASE}/outputs`);
      setOutputFolder(String(res.data.folder || ""));
      setOutputCount(Number(res.data.count || 0));
      setOutputFiles((res.data.files || []) as OutputFile[]);
    } catch (err) {
      console.error("Failed to fetch output stats", err);
    }
  };

  const fetchLicenseLimits = async () => {
    try {
      const res = await axios.get(`${API_BASE}/license-limits`);
      setLicenseMaxChunks(res.data.max_chunks ?? null);
      setLicenseWarningThreshold(res.data.warning_threshold ?? null);
      if (res.data.chunk_chars) setLicenseChunkChars(res.data.chunk_chars);
    } catch (err) {
      console.error("Failed to fetch license limits", err);
    }
  };

  // Real-time chunk estimation based on text length
  const estimatedChunks = useMemo(() => {
    const cleaned = text.replace(/\s+/g, " ").trim();
    if (!cleaned) return 0;
    return Math.max(1, Math.ceil(cleaned.length / licenseChunkChars));
  }, [text, licenseChunkChars]);

  const isOverLimit = licenseMaxChunks != null && estimatedChunks > licenseMaxChunks;
  const isOverWarning = !isOverLimit && licenseWarningThreshold != null && estimatedChunks > licenseWarningThreshold;

  const selectOutputFile = (fileName: string) => {
    setActiveOutputName(fileName);
    setAudioUrl(outputFileUrl(fileName));
    window.setTimeout(() => {
      mainAudioRef.current?.play().catch(() => {});
    }, 80);
  };

  const handleDeleteOneOutput = async (name: string) => {
    try {
      await axios.delete(`${API_BASE}/outputs/file/${encodeURIComponent(name)}`);
      setOutputFiles(prev => prev.filter(f => f.name !== name));
      setOutputMeta(prev => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
      setOutputCount(prev => Math.max(0, prev - 1));
      if (activeOutputName === name) {
        setActiveOutputName(null);
        setAudioUrl("");
      }
      setInfo(`Removed ${name} from history.`);
    } catch (err) {
      console.error(err);
      setError("Could not delete this audio file.");
    }
  };

  const handleOpenOutputFolder = async () => {
    try {
      await axios.post(`${API_BASE}/outputs/open-folder`);
      setInfo("Opened generated-audio folder.");
    } catch (err) {
      console.error(err);
      setError("Could not open output folder.");
    }
  };

  const handleDeleteAllOutputs = async () => {
    try {
      const res = await axios.delete(`${API_BASE}/outputs`);
      setInfo(`Deleted ${res.data.deleted || 0} generated audio file(s).`);
      setOutputCount(0);
      setOutputFiles([]);
      setOutputMeta({});
      setActiveOutputName(null);
      setAudioUrl("");
      setLastFinishInfo(null);
      setLastMeta(null);
      await fetchOutputStats();
    } catch (err) {
      console.error(err);
      setError("Could not delete generated audio files.");
    }
  };


  const handleAudioUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) setAudioFile(e.target.files[0]);
  };

  const handleSaveAudioUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) setSaveAudio(e.target.files[0]);
  };

  const handleDeleteVoice = async (voiceId: string) => {
    if (!voiceId.startsWith("saved:")) return;
    if (!window.confirm("Delete this saved voice profile?")) return;
    try {
      await axios.delete(`${API_BASE}/voices/${encodeURIComponent(voiceId)}`);
      setInfo("Voice profile deleted.");
      if (voiceSelect === voiceId) setVoiceSelect("auto");
      await fetchVoices();
    } catch (err) {
      console.error(err);
      setError("Could not delete voice profile.");
    }
  };

  useEffect(() => {
    const el = logBoxRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [logs]);

  const uploadVoiceToLibrary = async (
    name: string,
    gender: string,
    audio: File,
    prompt: string,
    selectAfterSave = true
  ) => {
    const formData = new FormData();
    formData.append("name", name.trim());
    formData.append("gender", gender);
    formData.append("prompt", prompt);
    formData.append("audio", audio);
    const res = await axios.post(`${API_BASE}/voices/save`, formData);
    if (selectAfterSave && res.data.id) setVoiceSelect(res.data.id);
    await fetchVoices();
    return res.data;
  };

  const handleSaveVoice = async () => {
    if (!saveName.trim()) {
      setError("Enter a name for the voice profile.");
      return;
    }
    if (!saveAudio) {
      setError("Upload reference audio before saving a voice profile.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const res = await uploadVoiceToLibrary(saveName, saveGender, saveAudio, savePrompt);
      setInfo(res.message || "Voice saved.");
      setSaveName("");
      setSavePrompt("");
      setSaveAudio(null);
      if (saveFileRef.current) saveFileRef.current.value = "";
    } catch (err) {
      console.error(err);
      setError("Failed to save voice profile.");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveLastToLibrary = async () => {
    if (!lastAudioFile) {
      setError("No synthesis output to save yet.");
      return;
    }
    if (!saveLastName.trim()) {
      setError("Enter a name for this voice profile.");
      return;
    }
    setSavingLast(true);
    setError("");
    try {
      const res = await uploadVoiceToLibrary(
        saveLastName,
        saveLastGender,
        lastAudioFile,
        text.trim(),
        true
      );
      setInfo(res.message || "Last output saved to library — reuse it anytime without cloning again.");
      setShowSaveLast(false);
      setSaveLastName("");
    } catch (err) {
      console.error(err);
      setError("Failed to save last output to library.");
    } finally {
      setSavingLast(false);
    }
  };

  const handleUseLastForNext = () => {
    if (!lastAudioFile) return;
    setAudioFile(lastAudioFile);
    setVoiceSelect("none");
    setInfo("Last synthesis is set as reference audio for the next run.");
  };

  const slugifyFileName = (value: string, index: number) => {
    const base = value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 36);
    return `${String(index + 1).padStart(3, "0")}_${base || "audio"}.wav`;
  };

  const buildBatchQueue = () => {
    const lines = batchInput
      .split(/\r?\n/)
      .map(v => v.trim())
      .filter(Boolean);

    if (!lines.length) {
      setError("Add at least one line in Batch & Queue.");
      return;
    }

    const items: BatchItem[] = lines.map((line, i) => ({
      id: `${Date.now()}-${i}`,
      text: line,
      fileName: slugifyFileName(line, i),
      status: "pending"
    }));
    setBatchItems(items);
    setInfo(`Queue created with ${items.length} item(s).`);
  };

  const updateBatchItem = (id: string, patch: Partial<BatchItem>) => {
    setBatchItems(prev => prev.map(item => (item.id === id ? { ...item, ...patch } : item)));
  };

  const runSynthesisRequest = async (targetText: string, collectLogs: boolean) => {
    const requestVoiceSelect = voiceSelect === "auto" && stickyVoiceId ? stickyVoiceId : voiceSelect;
    const formData = new FormData();
    formData.append("text", targetText);
    formData.append("voice_select", requestVoiceSelect);
    formData.append("speaker_gender", speakerGender);
    formData.append("control_instruction", controlInstruction);
    formData.append("cfg_value", cfgValue.toString());
    formData.append("normalize", normalize.toString());
    formData.append("denoise", denoise.toString());
    formData.append("timesteps", timesteps.toString());
    formData.append("prompt_text", promptText);
    if (audioFile) formData.append("reference_audio", audioFile);

    const res = await fetch(`${API_BASE}/generate`, { method: "POST", body: formData });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const errBody = await res.json();
        if (errBody.detail) detail = String(errBody.detail);
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    if (!res.body) throw new Error("No response body");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let doneData: {
      audio_base64?: string;
      plan?: string;
      duration_sec?: number;
      device?: string;
      sample_rate?: number;
      logs?: string[];
      voice_used?: string;
      saved_file?: string;
    } | null = null;
    const streamLogs: string[] = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        const raw = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (raw) {
          const msg = JSON.parse(raw) as {
            type: string;
            line?: string;
            message?: string;
            audio_base64?: string;
            plan?: string;
            duration_sec?: number;
            device?: string;
            sample_rate?: number;
            logs?: string[];
            voice_used?: string;
            saved_file?: string;
          };
          if (msg.type === "log" && msg.line) {
            streamLogs.push(msg.line);
            if (collectLogs) setLogs(prev => [...prev, msg.line as string]);
          } else if (msg.type === "plan" && msg.plan) {
            setSynthesisPlan(String(msg.plan));
          } else if (msg.type === "chunk_limit") {
            setShowUpgradeDialog(true);
            throw new Error(msg.message || "Chunk limit exceeded");
          } else if (msg.type === "chunk_warning" && msg.message) {
            if (collectLogs) setLogs(prev => [...prev, `⚠️ ${msg.message}`]);
          } else if (msg.type === "error") {
            throw new Error(msg.message || "Synthesis failed");
          } else if (msg.type === "done") {
            doneData = msg;
            if (msg.plan) setSynthesisPlan(String(msg.plan));
          }
        }
        newline = buffer.indexOf("\n");
      }
    }

    if (!doneData?.audio_base64) throw new Error("No audio returned from server");

    if (collectLogs && doneData.logs?.length) setLogs(doneData.logs);
    const blob = base64ToBlob(doneData.audio_base64, "audio/wav");
    return {
      blob,
      plan: doneData.plan || "",
      duration: doneData.duration_sec,
      device: doneData.device,
      sampleRate: doneData.sample_rate,
      logs: doneData.logs || streamLogs,
      voiceUsed: doneData.voice_used || "",
      savedFile: doneData.saved_file || ""
    };
  };

  const runBatchQueue = async () => {
    if (!batchItems.length) {
      setError("Create a queue first.");
      return;
    }
    if (batchRunning || loading) return;

    setBatchRunning(true);
    setError("");
    setInfo("");
    let completed = 0;

    try {
      for (const item of batchItems) {
        if (item.status === "done") continue;
        updateBatchItem(item.id, { status: "processing", error: "" });
        try {
          const result = await runSynthesisRequest(item.text, false);
          const url = URL.createObjectURL(result.blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = item.fileName;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
          updateBatchItem(item.id, { status: "done" });
          completed += 1;
        } catch (err: unknown) {
          updateBatchItem(item.id, {
            status: "failed",
            error: err instanceof Error ? err.message : "Generation failed"
          });
        }
      }
      await fetchOutputStats();
      setInfo(`Batch complete: ${completed}/${batchItems.length} generated.`);
    } finally {
      setBatchRunning(false);
    }
  };

  const resetBatchQueue = () => {
    if (batchRunning) return;
    setBatchItems([]);
    setBatchInput("");
  };

  const handleGenerate = async () => {
    if (!text.trim()) {
      setError("Please enter some text to synthesize.");
      return;
    }

    setLoading(true);
    setError("");
    setInfo("");
    setLogs([]);
    setSynthesisPlan("");
    setShowSaveLast(false);
    const startMs = Date.now();
    setGenStartedAt(startMs);
    setElapsedSec(0);
    const estimated = Math.max(4, Math.round(text.trim().length * avgSecPerChar * (timesteps / 10)));
    setEtaSec(estimated);
    let finishedOk = false;

    try {
      const result = await runSynthesisRequest(text.trim(), true);
      if (voiceSelect === "auto" && result.voiceUsed) {
        setStickyVoiceId(result.voiceUsed);
      }
      if (result.plan) setSynthesisPlan(result.plan);
      const blob = result.blob;
      const file = new File([blob], `synthesis_${Date.now()}.wav`, { type: "audio/wav" });
      setLastAudioFile(file);
      setSaveLastName(text.trim().slice(0, 40) || "My voice");
      setSaveLastGender(speakerGender);
      setLastMeta({
        duration: result.duration,
        device: result.device,
        sampleRate: result.sampleRate
      });
      const actualSec = Math.max(1, Math.round((Date.now() - startMs) / 1000));
      setLastFinishInfo({ genSec: actualSec, audioSec: result.duration });
      const chars = Math.max(1, text.trim().length);
      const normalized = actualSec / chars / Math.max(0.5, timesteps / 10);
      setAvgSecPerChar(prev => prev * 0.7 + normalized * 0.3);

      const savedName = result.savedFile || "";
      if (savedName) {
        setOutputMeta(prev => ({
          ...prev,
          [savedName]: { genSec: actualSec, audioSec: result.duration }
        }));
        setActiveOutputName(savedName);
        setAudioUrl(outputFileUrl(savedName));
      } else {
        if (audioUrl.startsWith("blob:")) URL.revokeObjectURL(audioUrl);
        setActiveOutputName(null);
        setAudioUrl(URL.createObjectURL(blob));
      }
      await fetchOutputStats();
      finishedOk = true;
    } catch (err: unknown) {
      console.error("Generation error:", err);
      const detail = err instanceof Error ? err.message : "request failed";
      setError(detail === "request failed" ? "Failed to generate audio. See log below." : detail);
      setLogs(prev => [...prev, `[…] Error: ${detail}`]);
    } finally {
      setLoading(false);
      setEtaSec(null);
      setGenStartedAt(null);
      if (finishedOk) {
        // Keep UI clean after successful completion.
        setLogs([]);
      }
    }
  };

  const selectedVoice = pickerOptions.find(v => v.id === voiceSelect) || AUTO_VOICE;
  const lockedVoiceLabel = pickerOptions.find(v => v.id === stickyVoiceId)?.name || stickyVoiceId;

  return (
    <Box sx={{ flexGrow: 1, p: { xs: 2, md: 3 } }}>
      <Typography
        variant="h4"
        sx={{
          mb: 3,
          fontWeight: 800,
          color: "text.primary",
          letterSpacing: 0.2
        }}
      >
        {STUDIO_NAME}
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError("")}>{error}</Alert>}
      {info && <Alert severity="info" sx={{ mb: 2 }} onClose={() => setInfo("")}>{info}</Alert>}

      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Card elevation={3} sx={{ mb: 3, borderRadius: 3 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2 }}>Target Text</Typography>
              <TextField
                fullWidth
                multiline
                minRows={4}
                maxRows={18}
                placeholder="Enter the text you want to synthesize..."
                value={text}
                onChange={e => setText(e.target.value)}
                InputProps={{
                  sx: {
                    '& textarea': {
                      resize: 'vertical',
                    },
                  },
                }}
              />

              {/* Chunk estimation and license limit warnings */}
              {text.trim() && licenseMaxChunks != null && (
                <Box sx={{ mt: 1, display: "flex", alignItems: "center", gap: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    Est. ~{estimatedChunks} chunk{estimatedChunks !== 1 ? "s" : ""} / {licenseMaxChunks} max
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(100, (estimatedChunks / licenseMaxChunks) * 100)}
                    sx={{
                      flex: 1,
                      height: 6,
                      borderRadius: 3,
                      bgcolor: "action.hover",
                      "& .MuiLinearProgress-bar": {
                        bgcolor: isOverLimit ? "error.main" : isOverWarning ? "warning.main" : "success.main"
                      }
                    }}
                  />
                </Box>
              )}
              {isOverWarning && (
                <Alert severity="warning" sx={{ mt: 1 }}>
                  ⚠️ Long text detected (est. ~{estimatedChunks} chunks). Processing may take several minutes and use significant GPU memory.
                </Alert>
              )}
              {isOverLimit && (
                <Alert severity="error" sx={{ mt: 1 }}>
                  🚫 Text exceeds your plan limit ({estimatedChunks} / {licenseMaxChunks} chunks). Please shorten the text or{" "}
                  <Box component="span" sx={{ cursor: "pointer", textDecoration: "underline", fontWeight: 700 }} onClick={() => setShowUpgradeDialog(true)}>
                    contact your administrator to upgrade
                  </Box>.
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card elevation={3} sx={{ mb: 3, borderRadius: 3 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2 }}>Who Is Speaking?</Typography>
              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth>
                    <InputLabel>Speaker</InputLabel>
                    <Select
                      label="Speaker"
                      value={speakerGender}
                      onChange={e => setSpeakerGender(e.target.value)}
                    >
                      {(speakerOptions.length
                        ? speakerOptions
                        : Object.entries(GENDER_LABELS)
                            .filter(([value]) => value !== "unknown")
                            .map(([value, label]) => ({ value, label }))
                      ).map(opt => (
                        <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Autocomplete
                    options={pickerOptions}
                    groupBy={opt =>
                      opt.type === "builtin" ? "Built-in Styles" : opt.type === "saved" ? "Your Cloned Voices" : "Smart Pick"
                    }
                    getOptionLabel={opt => opt.name}
                    value={selectedVoice}
                    onChange={(_, v) => setVoiceSelect(v?.id || "auto")}
                    renderOption={(props, opt) => (
                      <li {...props} key={opt.id}>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                          <span>{opt.name}</span>
                          {opt.gender && opt.gender !== "unknown" && (
                            <Chip size="small" label={GENDER_LABELS[opt.gender] || opt.gender} />
                          )}
                        </Box>
                      </li>
                    )}
                    renderInput={params => <TextField {...params} label="Voice Profile" />}
                  />
                </Grid>
              </Grid>

              {voiceSelect === "auto" && (
                <Alert severity={matchedProfile ? "success" : "info"} sx={{ mb: 2 }}>
                  {matchedProfile
                    ? `Will clone: ${matchedProfile.name} (${GENDER_LABELS[matchedProfile.gender || "unknown"]})`
                    : `No saved ${GENDER_LABELS[speakerGender] || speakerGender} clone — using voice design for a ${GENDER_LABELS[speakerGender] || speakerGender} speaker. Upload reference audio to clone a specific voice.`}
                </Alert>
              )}
              {voiceSelect === "auto" && stickyVoiceId && (
                <Alert severity="success" sx={{ mb: 2 }}>
                  Voice lock is active for consistency: {lockedVoiceLabel}
                </Alert>
              )}

              <TextField
                fullWidth
                label="Control Instruction / Speaking Style"
                placeholder="e.g. warm, expressive, news anchor pace..."
                value={controlInstruction}
                onChange={e => setControlInstruction(e.target.value)}
                sx={{ mb: 2 }}
              />

              <Divider sx={{ my: 2 }} />

              <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: "medium" }}>
                One-time Reference Audio (optional)
              </Typography>
              <Box sx={{ display: "flex", gap: 2, alignItems: "center", mb: 2 }}>
                <Button variant="outlined" component="label">
                  Upload WAV
                  <input type="file" hidden accept="audio/*" ref={fileInputRef} onChange={handleAudioUpload} />
                </Button>
                {audioFile && (
                  <Chip
                    size="small"
                    label={audioFile.name}
                    onDelete={() => setAudioFile(null)}
                    sx={{ mb: 1 }}
                  />
                )}
              </Box>

              <FormControlLabel
                control={<Switch checked={showPrompt} onChange={e => setShowPrompt(e.target.checked)} />}
                label="Enable Ultimate Cloning (Audio Continuation)"
              />
              {showPrompt && (
                <TextField
                  fullWidth
                  label="Transcript of Reference Audio"
                  value={promptText}
                  onChange={e => setPromptText(e.target.value)}
                  sx={{ mt: 2 }}
                />
              )}
            </CardContent>
          </Card>

          <Card elevation={3} sx={{ mb: 3, borderRadius: 3 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2 }}>Your Voice Library</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Save clones with Male / Female / Child tags. The speaker picker above will auto-use the right profile.
              </Typography>

              {savedVoices.length > 0 ? (
                <List dense sx={{ mb: 2, bgcolor: "action.hover", borderRadius: 2 }}>
                  {savedVoices.map(v => (
                    <ListItem key={v.id}>
                      <ListItemText
                        primary={v.name}
                        secondary={GENDER_LABELS[v.gender || "unknown"] || v.gender}
                      />
                      <ListItemSecondaryAction>
                        <Tooltip title="Delete profile">
                          <IconButton edge="end" color="error" onClick={() => handleDeleteVoice(v.id)} aria-label="delete">
                            ✕
                          </IconButton>
                        </Tooltip>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  No saved voices yet.
                </Typography>
              )}

              <Grid container spacing={2}>
                <Grid item xs={12} sm={5}>
                  <TextField
                    fullWidth
                    label="Profile name"
                    placeholder="e.g. Host Male"
                    value={saveName}
                    onChange={e => setSaveName(e.target.value)}
                  />
                </Grid>
                <Grid item xs={12} sm={3}>
                  <FormControl fullWidth>
                    <InputLabel>Voice type</InputLabel>
                    <Select label="Voice type" value={saveGender} onChange={e => setSaveGender(e.target.value)}>
                      {(genderOptions.length ? genderOptions : Object.entries(GENDER_LABELS).map(([value, label]) => ({ value, label }))).map(
                        opt => (
                          <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                        )
                      )}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Button variant="outlined" component="label" fullWidth sx={{ height: "56px" }}>
                    {saveAudio ? saveAudio.name : "Reference audio"}
                    <input type="file" hidden accept="audio/*" ref={saveFileRef} onChange={handleSaveAudioUpload} />
                  </Button>
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Transcript (optional)"
                    value={savePrompt}
                    onChange={e => setSavePrompt(e.target.value)}
                  />
                </Grid>
                <Grid item xs={12}>
                  <Button
                    variant="contained"
                    onClick={handleSaveVoice}
                    disabled={saving}
                  >
                    {saving ? <CircularProgress size={18} color="inherit" /> : "Save to Library"}
                  </Button>
                </Grid>
              </Grid>
            </CardContent>
          </Card>

          <Card elevation={3} sx={{ borderRadius: 3 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2 }}>Advanced Settings</Typography>
              <Grid container spacing={4}>
                <Grid item xs={12} sm={6}>
                  <Typography gutterBottom>CFG Scale: {cfgValue.toFixed(1)}</Typography>
                  <Slider value={cfgValue} min={1} max={5} step={0.1} onChange={(_, v) => setCfgValue(v as number)} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography gutterBottom>LocDiT Steps: {timesteps}</Typography>
                  <Slider value={timesteps} min={1} max={50} step={1} onChange={(_, v) => setTimesteps(v as number)} />
                </Grid>
              </Grid>
              <Box sx={{ display: "flex", gap: 3, mt: 2 }}>
                <FormControlLabel control={<Switch checked={normalize} onChange={e => setNormalize(e.target.checked)} />} label="Normalize Text" />
                <FormControlLabel control={<Switch checked={denoise} onChange={e => setDenoise(e.target.checked)} />} label="Denoise Prompt Audio" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card
            elevation={2}
            sx={{
              borderRadius: 3,
              border: theme => `1px solid ${theme.palette.divider}`,
              backgroundImage: "none"
            }}
          >
            <CardContent sx={{ p: { xs: 2, sm: 2.5 } }}>
              <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 700, lineHeight: 1.2 }}>Output</Typography>
              <Button
                variant="contained"
                size="large"
                fullWidth
                onClick={handleGenerate}
                disabled={loading || batchRunning || isOverLimit}
                sx={{
                  mb: 1.25,
                  py: 1.25,
                  fontWeight: 700,
                  fontSize: "1rem",
                  borderRadius: 2,
                  boxShadow: "none",
                  textTransform: "none",
                  "&:hover": {
                    boxShadow: "none"
                  }
                }}
              >
                {loading ? <CircularProgress size={26} color="inherit" /> : "Synthesize Audio"}
              </Button>
              <Box
                sx={{
                  mb: 1.25,
                  minHeight: 22,
                  display: "flex",
                  alignItems: "center",
                  gap: 0.75
                }}
              >
                <Box
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    bgcolor: loading ? "warning.main" : "success.main",
                    flexShrink: 0
                  }}
                />
                <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.2 }}>
                  {loading
                    ? `Generating… ${formatDuration(elapsedSec)}${etaSec != null ? ` · ETA ~${formatDuration(etaSec)}` : ""}`
                    : lastFinishInfo
                      ? `Done in ${formatDuration(lastFinishInfo.genSec)}${lastFinishInfo.audioSec != null ? ` · Audio ${formatDuration(lastFinishInfo.audioSec)}` : ""}`
                      : "Ready"}
                </Typography>
              </Box>
              <Box sx={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 1, mb: 1.25 }}>
                <Button
                  variant="contained"
                  size="small"
                  onClick={handleOpenOutputFolder}
                  sx={{
                    borderRadius: 1.5,
                    width: "100%",
                    minHeight: 32,
                    whiteSpace: "nowrap",
                    textTransform: "none",
                    fontWeight: 600
                  }}
                >
                  Open folder
                </Button>
                <Button
                  variant="outlined"
                  color="error"
                  size="small"
                  onClick={() => setDeleteOutputsDialogOpen(true)}
                  sx={{
                    borderRadius: 1.5,
                    width: "100%",
                    minHeight: 32,
                    whiteSpace: "nowrap",
                    textTransform: "none",
                    fontWeight: 600
                  }}
                >
                  Delete all
                </Button>
                <Button
                  variant="outlined"
                  color="secondary"
                  size="small"
                  onClick={() => void fetchOutputStats()}
                  sx={{
                    gridColumn: "1 / -1",
                    borderRadius: 1.5,
                    width: "100%",
                    minHeight: 32,
                    whiteSpace: "nowrap",
                    textTransform: "none",
                    fontWeight: 600
                  }}
                >
                  Refresh
                </Button>
              </Box>
              <Box
                sx={{
                  mb: 1.5,
                  borderRadius: 2.5,
                  overflow: "hidden",
                  border: "1px solid",
                  borderColor: "divider",
                  bgcolor: "background.default"
                }}
              >
                <Box
                  sx={{
                    px: 1.5,
                    py: 1.25,
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    bgcolor: theme =>
                      theme.palette.mode === "dark" ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)"
                  }}
                >
                  <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      Now playing
                    </Typography>
                    {outputCount > 0 && (
                      <Typography variant="caption" color="text.secondary">
                        {outputCount} saved
                      </Typography>
                    )}
                  </Box>
                  {(lastMeta || lastFinishInfo) && (
                    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 1 }}>
                      {lastFinishInfo && (
                        <Chip size="small" label={`Gen ${formatDuration(lastFinishInfo.genSec)}`} sx={{ height: 22, fontSize: "0.68rem" }} />
                      )}
                      {(lastFinishInfo?.audioSec != null || lastMeta?.duration != null) && (
                        <Chip
                          size="small"
                          color="primary"
                          variant="outlined"
                          label={formatDuration(lastFinishInfo?.audioSec ?? lastMeta?.duration)}
                          sx={{ height: 22, fontSize: "0.68rem" }}
                        />
                      )}
                    </Box>
                  )}
                  {audioUrl ? (
                    <Box
                      sx={{
                        borderRadius: 1.5,
                        p: 0.75,
                        bgcolor: "background.paper",
                        border: "1px solid",
                        borderColor: "primary.main"
                      }}
                    >
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5, px: 0.25 }} noWrap>
                        {activeOutputName ? historyRowTitle(outputFiles.find(f => f.name === activeOutputName) || { name: activeOutputName, size_bytes: 0, modified_at: "" }) : "Latest"}
                      </Typography>
                      <audio
                        ref={mainAudioRef}
                        controls
                        src={audioUrl}
                        style={{ width: "100%", height: 36, display: "block" }}
                      />
                    </Box>
                  ) : (
                    <Box sx={{ py: 1.5, textAlign: "center", borderRadius: 1.5, bgcolor: "action.hover" }}>
                      <Typography variant="caption" color="text.secondary">
                        Synthesize audio to play here
                      </Typography>
                    </Box>
                  )}
                </Box>

                <Box sx={{ px: 1.25, py: 1, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <Typography variant="caption" sx={{ fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.6, color: "text.secondary" }}>
                    History
                  </Typography>
                  {outputFiles.length > 0 && (
                    <Chip label={outputFiles.length} size="small" sx={{ height: 20, fontSize: "0.65rem" }} />
                  )}
                </Box>

                <Box
                  sx={{
                    maxHeight: 176,
                    overflowY: "auto",
                    "&::-webkit-scrollbar": { width: 5 },
                    "&::-webkit-scrollbar-thumb": { bgcolor: "divider", borderRadius: 3 }
                  }}
                >
                  {outputFiles.length === 0 ? (
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", px: 1.5, pb: 1.5 }}>
                      Previous outputs list here — tap to play above
                    </Typography>
                  ) : (
                    outputFiles.map(file => {
                      const meta = outputMeta[file.name];
                      const isActive = activeOutputName === file.name;
                      const durationLabel = meta?.audioSec != null ? formatDuration(meta.audioSec) : null;
                      return (
                        <Box
                          key={file.name}
                          onClick={() => selectOutputFile(file.name)}
                          sx={{
                            display: "flex",
                            alignItems: "center",
                            gap: 1,
                            px: 1.25,
                            py: 0.85,
                            cursor: "pointer",
                            bgcolor: isActive ? "action.selected" : "transparent",
                            borderLeft: "3px solid",
                            borderLeftColor: isActive ? "primary.main" : "transparent",
                            "&:hover": { bgcolor: "action.hover" }
                          }}
                        >
                          <Box
                            sx={{
                              width: 26,
                              height: 26,
                              borderRadius: "50%",
                              flexShrink: 0,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              bgcolor: isActive ? "primary.main" : "transparent",
                              color: isActive ? "primary.contrastText" : "text.secondary",
                              border: "1px solid",
                              borderColor: isActive ? "primary.main" : "divider"
                            }}
                          >
                            <i className="ri-play-fill" style={{ fontSize: 12, marginLeft: 1 }} />
                          </Box>
                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: isActive ? 700 : 500, fontSize: "0.8rem" }} noWrap>
                              {historyRowTitle(file)}
                            </Typography>
                            {meta?.genSec != null && (
                              <Typography variant="caption" color="text.secondary" noWrap>
                                Rendered in {formatDuration(meta.genSec)}
                              </Typography>
                            )}
                          </Box>
                          {durationLabel && (
                            <Chip label={durationLabel} size="small" variant="outlined" sx={{ height: 22, fontSize: "0.65rem", flexShrink: 0 }} />
                          )}
                          <IconButton
                            size="small"
                            aria-label="Remove"
                            onClick={e => {
                              e.stopPropagation();
                              setDeleteOneOutputName(file.name);
                            }}
                            sx={{ color: "text.disabled", "&:hover": { color: "error.main" } }}
                          >
                            <i className="ri-close-line" style={{ fontSize: 16 }} />
                          </IconButton>
                        </Box>
                      );
                    })
                  )}
                </Box>
              </Box>

              {lastAudioFile && (
                <Box sx={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 1 }}>
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={handleUseLastForNext}
                    startIcon={<i className="ri-repeat-line" />}
                    sx={{
                      borderRadius: 1.5,
                      minHeight: 36,
                      textTransform: "none",
                      fontWeight: 600,
                      fontSize: "0.8rem"
                    }}
                  >
                    Reuse voice
                  </Button>
                  <Button
                    variant="outlined"
                    size="small"
                    color="secondary"
                    onClick={() => setShowSaveLast(v => !v)}
                    startIcon={<i className="ri-save-3-line" />}
                    sx={{
                      borderRadius: 1.5,
                      minHeight: 36,
                      textTransform: "none",
                      fontWeight: 600,
                      fontSize: "0.8rem"
                    }}
                  >
                    {showSaveLast ? "Cancel" : "Save voice"}
                  </Button>
                  {showSaveLast && (
                    <Box sx={{ mt: 1, p: 2, bgcolor: "action.hover", borderRadius: 2 }}>
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                        Reuse this voice later without cloning again — pick it from Speaker + Auto or the voice list.
                      </Typography>
                      <TextField
                        fullWidth
                        size="small"
                        label="Profile name"
                        value={saveLastName}
                        onChange={e => setSaveLastName(e.target.value)}
                        sx={{ mb: 1 }}
                      />
                      <FormControl fullWidth size="small" sx={{ mb: 1 }}>
                        <InputLabel>Voice type</InputLabel>
                        <Select
                          label="Voice type"
                          value={saveLastGender}
                          onChange={e => setSaveLastGender(e.target.value)}
                        >
                          {(genderOptions.length
                            ? genderOptions
                            : Object.entries(GENDER_LABELS).map(([value, label]) => ({ value, label }))
                          ).map(opt => (
                            <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      <Button
                        variant="contained"
                        size="small"
                        fullWidth
                        disabled={savingLast}
                        onClick={handleSaveLastToLibrary}
                      >
                        {savingLast ? <CircularProgress size={16} color="inherit" /> : "Confirm save to library"}
                      </Button>
                    </Box>
                  )}
                </Box>
              )}

              <Button
                size="small"
                fullWidth
                onClick={() => setShowOutputDetails(v => !v)}
                endIcon={<i className={showOutputDetails ? "ri-arrow-up-s-line" : "ri-arrow-down-s-line"} />}
                sx={{ mb: 1, textTransform: "none", color: "text.secondary", fontWeight: 600 }}
              >
                {showOutputDetails ? "Hide" : "Show"} process log
              </Button>
              {showOutputDetails && (
                <>
                  <Box
                    ref={logBoxRef}
                    sx={{
                      mb: 1,
                      maxHeight: 120,
                      overflowY: "auto",
                      bgcolor: "background.default",
                      borderRadius: 2,
                      p: 1.25,
                      fontFamily: "ui-monospace, Menlo, Monaco, Consolas, monospace",
                      fontSize: "0.7rem",
                      border: "1px solid",
                      borderColor: "divider"
                    }}
                  >
                    {logs.length === 0 ? (
                      <Typography variant="caption" color="text.secondary">
                        {loading ? "Waiting for server…" : "No logs yet"}
                      </Typography>
                    ) : (
                      logs.map((line, i) => <Box key={i}>{line}</Box>)
                    )}
                  </Box>
                  {synthesisPlan && (
                    <Box sx={{ mb: 1, p: 1.25, borderRadius: 2, bgcolor: "action.hover", maxHeight: 120, overflowY: "auto" }}>
                      <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 0.5 }}>
                        Synthesis plan
                      </Typography>
                      <Typography variant="caption" component="pre" sx={{ m: 0, whiteSpace: "pre-wrap", color: "text.secondary" }}>
                        {synthesisPlan}
                      </Typography>
                    </Box>
                  )}
                </>
              )}

            </CardContent>
          </Card>
          <Card
            elevation={2}
            sx={{
              mt: 1.5,
              borderRadius: 3,
              border: theme => `1px solid ${theme.palette.divider}`,
              overflow: "hidden",
              // Hide injected writing-assistant overlays inside this card only.
              "& grammarly-desktop-integration, & grammarly-extension": { display: "none !important" },
              "& [class*='grammarly'], & [id*='grammarly']": { display: "none !important" },
              "& [class*='lt-'], & [id*='lt-'], & [data-lt-active='true']": { display: "none !important" }
            }}
          >
            <CardContent sx={{ p: { xs: 2, sm: 2.5 } }}>
              <Typography variant="h6" sx={{ mb: 1, fontWeight: 700 }}>
                Batch & Queue
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", mb: 0.75, lineHeight: 1.35, wordBreak: "break-word", fontSize: "0.72rem" }}
              >
                One line = one generation job.
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", mb: 1, lineHeight: 1.35, wordBreak: "break-word", fontSize: "0.72rem" }}
              >
                Paste lines, then click Build Queue and Run Queue.
              </Typography>
              <TextField
                fullWidth
                multiline
                minRows={4}
                maxRows={10}
                placeholder={"Line 1 text...\nLine 2 text...\nLine 3 text..."}
                value={batchInput}
                onChange={e => setBatchInput(e.target.value)}
                inputProps={{
                  spellCheck: false,
                  autoComplete: "off",
                  autoCorrect: "off",
                  autoCapitalize: "off",
                  "data-gramm": "false",
                  "data-gramm_editor": "false",
                  "data-enable-grammarly": "false",
                  "data-lt-active": "false",
                  "data-ms-editor": "false"
                }}
                sx={{
                  mb: 1,
                  "& .MuiInputBase-root": { overflow: "hidden" },
                  "& textarea": { position: "relative", zIndex: 2 }
                }}
              />
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                  gap: 1,
                  mb: 1
                }}
              >
                <Button
                  size="small"
                  variant="outlined"
                  onClick={buildBatchQueue}
                  disabled={batchRunning}
                  sx={{ minHeight: 32, textTransform: "none", fontWeight: 600 }}
                >
                  Build Queue
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  onClick={runBatchQueue}
                  disabled={batchRunning || loading || batchItems.length === 0}
                  sx={{ minHeight: 32, textTransform: "none", fontWeight: 600 }}
                >
                  {batchRunning ? "Processing..." : "Run Queue"}
                </Button>
                <Button
                  size="small"
                  variant="text"
                  color="inherit"
                  onClick={resetBatchQueue}
                  disabled={batchRunning}
                  sx={{ gridColumn: "1 / -1", minHeight: 30, textTransform: "none", fontWeight: 600 }}
                >
                  Clear
                </Button>
              </Box>
              {batchItems.length > 0 && (
                <Box sx={{ mb: 1.25 }}>
                  <LinearProgress
                    variant="determinate"
                    value={(batchItems.filter(i => i.status === "done").length / batchItems.length) * 100}
                    sx={{ mb: 0.75, height: 6, borderRadius: 3 }}
                  />
                  <Typography variant="caption" color="text.secondary">
                    {batchItems.filter(i => i.status === "done").length}/{batchItems.length} completed
                  </Typography>
                </Box>
              )}
              <Box sx={{ maxHeight: 180, overflowY: "auto", border: "1px solid", borderColor: "divider", borderRadius: 2, p: 1 }}>
                {batchItems.length === 0 ? (
                  <Typography variant="caption" color="text.secondary">
                    Queue items will appear here.
                  </Typography>
                ) : (
                  batchItems.map(item => (
                    <Box key={item.id} sx={{ py: 0.75, borderBottom: "1px solid", borderBottomColor: "divider", "&:last-child": { borderBottom: 0 } }}>
                      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1 }}>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: "text.primary" }}>
                          {item.fileName}
                        </Typography>
                        <Chip
                          size="small"
                          label={item.status}
                          color={
                            item.status === "done"
                              ? "success"
                              : item.status === "failed"
                                ? "error"
                                : item.status === "processing"
                                  ? "warning"
                                  : "default"
                          }
                        />
                      </Box>
                      <Typography variant="caption" color="text.secondary">
                        {item.text}
                      </Typography>
                      {item.error && (
                        <Typography variant="caption" color="error.main" sx={{ display: "block" }}>
                          {item.error}
                        </Typography>
                      )}
                    </Box>
                  ))
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      <Dialog
        open={Boolean(deleteOneOutputName)}
        onClose={() => setDeleteOneOutputName(null)}
        aria-labelledby="delete-one-output-title"
      >
        <DialogTitle id="delete-one-output-title">Remove this audio?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {deleteOneOutputName ? `Delete ${deleteOneOutputName} from history?` : ""}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOneOutputName(null)} color="inherit">
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={async () => {
              const name = deleteOneOutputName;
              setDeleteOneOutputName(null);
              if (name) await handleDeleteOneOutput(name);
            }}
          >
            Remove
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={deleteOutputsDialogOpen}
        onClose={() => setDeleteOutputsDialogOpen(false)}
        aria-labelledby="delete-generated-audio-title"
      >
        <DialogTitle id="delete-generated-audio-title">Delete all generated audio?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will permanently remove all generated `.wav` files in your output folder.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOutputsDialogOpen(false)} color="inherit">
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={async () => {
              setDeleteOutputsDialogOpen(false);
              await handleDeleteAllOutputs();
            }}
          >
            Delete all
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={showUpgradeDialog}
        onClose={() => setShowUpgradeDialog(false)}
        aria-labelledby="upgrade-dialog-title"
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle id="upgrade-dialog-title" sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Box component="span" sx={{ fontSize: "1.5rem" }}>🔒</Box>
          Chunk Limit Reached
        </DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            Your current license allows a maximum of <strong>{licenseMaxChunks}</strong> chunks per synthesis request,
            but your text requires approximately <strong>{estimatedChunks}</strong> chunks.
          </DialogContentText>
          <Alert severity="info" sx={{ mb: 2 }}>
            Each chunk is approximately {licenseChunkChars} characters. To process longer texts, you need a license with a higher chunk limit (up to 1,000).
          </Alert>
          <DialogContentText>
            <strong>What you can do:</strong>
          </DialogContentText>
          <Box component="ul" sx={{ mt: 1, pl: 3 }}>
            <li>
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                <strong>Shorten the text</strong> — remove content to bring it under {licenseMaxChunks} chunks
              </Typography>
            </li>
            <li>
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                <strong>Use Batch mode</strong> — split into separate requests in the Batch & Queue panel
              </Typography>
            </li>
            <li>
              <Typography variant="body2">
                <strong>Upgrade your license</strong> — contact your administrator for a higher chunk limit
              </Typography>
            </li>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowUpgradeDialog(false)} color="inherit">
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
