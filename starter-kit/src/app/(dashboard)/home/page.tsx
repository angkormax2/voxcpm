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
  Tooltip
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
  neutral: "Neutral",
  unknown: "Unknown"
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
  const [elapsedSec, setElapsedSec] = useState(0);
  const [etaSec, setEtaSec] = useState<number | null>(null);
  const [genStartedAt, setGenStartedAt] = useState<number | null>(null);
  const [avgSecPerChar, setAvgSecPerChar] = useState(0.08);
  const [stickyVoiceId, setStickyVoiceId] = useState("");
  const [batchInput, setBatchInput] = useState("");
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [deleteOutputsDialogOpen, setDeleteOutputsDialogOpen] = useState(false);

  const logBoxRef = useRef<HTMLDivElement>(null);
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
    fetchVoices();
    void fetchOutputStats();
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
    } catch (err) {
      console.error("Failed to fetch output stats", err);
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
          };
          if (msg.type === "log" && msg.line) {
            streamLogs.push(msg.line);
            if (collectLogs) setLogs(prev => [...prev, msg.line as string]);
          } else if (msg.type === "plan" && msg.plan) {
            setSynthesisPlan(String(msg.plan));
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
      voiceUsed: doneData.voice_used || ""
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
    setAudioUrl("");
    setLogs([]);
    setSynthesisPlan("");
    setLastMeta(null);
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
      const chars = Math.max(1, text.trim().length);
      const normalized = actualSec / chars / Math.max(0.5, timesteps / 10);
      setAvgSecPerChar(prev => prev * 0.7 + normalized * 0.3);

      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioUrl(URL.createObjectURL(blob));
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
                disabled={loading || batchRunning}
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
                    ? `Elapsed: ${elapsedSec}s${etaSec != null ? ` · ETA: ~${etaSec}s` : ""}`
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
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.25, fontSize: "0.72rem" }}>
                Saved files: {outputCount}{outputFolder ? ` · ${outputFolder}` : ""}
              </Typography>

              <Typography variant="subtitle2" sx={{ mb: 0.75, fontWeight: 700 }}>
                Process log
              </Typography>
              <Box
                ref={logBoxRef}
                sx={{
                  mb: 1.5,
                  maxHeight: 140,
                  overflowY: "auto",
                  overflowX: "hidden",
                  bgcolor: "background.default",
                  color: "text.primary",
                  borderRadius: 2,
                  p: 1.25,
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                  fontSize: "0.72rem",
                  lineHeight: 1.5,
                  border: "1px solid",
                  borderColor: "divider",
                  overscrollBehavior: "contain",
                }}
              >
                {logs.length === 0 && loading ? (
                  <Typography variant="caption" color="text.secondary">
                    Waiting for server…
                  </Typography>
                ) : logs.length === 0 ? (
                  <Typography variant="caption" color="text.secondary">
                    Logs appear here while synthesizing…
                  </Typography>
                ) : (
                  logs.map((line, i) => <Box key={i}>{line}</Box>)
                )}
              </Box>
              {synthesisPlan && (
                <Box
                  sx={{
                    mb: 1.25,
                    p: 1.25,
                    borderRadius: 2,
                    bgcolor: "action.hover",
                    border: "1px solid",
                    borderColor: "divider",
                    maxHeight: 170,
                    overflowY: "auto",
                    overflowX: "hidden"
                  }}
                >
                  <Typography variant="caption" sx={{ display: "block", mb: 0.5, fontWeight: 700 }}>
                    Synthesis plan
                  </Typography>
                  <Typography
                    variant="caption"
                    component="pre"
                    sx={{
                      m: 0,
                      whiteSpace: "pre-wrap",
                      display: "block",
                      color: "text.secondary",
                      fontFamily: "inherit",
                      lineHeight: 1.45
                    }}
                  >
                    {synthesisPlan}
                  </Typography>
                </Box>
              )}

              {lastMeta && (
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                  {lastMeta.duration != null && `${lastMeta.duration}s`}
                  {lastMeta.sampleRate && ` · ${lastMeta.sampleRate} Hz`}
                  {lastMeta.device && ` · ${lastMeta.device.toUpperCase()}`}
                </Typography>
              )}

              <Box
                sx={{
                  mb: 1.5,
                  bgcolor: "background.paper",
                  borderRadius: 2,
                  p: 1.5,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  border: "1px dashed",
                  borderColor: "divider",
                  minHeight: 78
                }}
              >
                {audioUrl ? (
                  <audio controls src={audioUrl} style={{ width: "100%" }} />
                ) : (
                  <Typography color="text.secondary" align="center" variant="body2">
                    Audio output will appear here
                  </Typography>
                )}
              </Box>

              {lastAudioFile && (
                <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  <Button variant="outlined" size="small" onClick={handleUseLastForNext}>
                    Use for next synthesis
                  </Button>
                  <Button
                    variant="outlined"
                    size="small"
                    color="secondary"
                    onClick={() => setShowSaveLast(v => !v)}
                  >
                    {showSaveLast ? "Cancel save" : "Save output to library"}
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
    </Box>
  );
}
