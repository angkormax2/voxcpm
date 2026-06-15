"use client";

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
  }, []);

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

    try {
      const formData = new FormData();
      formData.append("text", text);
      formData.append("voice_select", voiceSelect);
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
      let doneData: Record<string, unknown> | null = null;

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
            };
            if (msg.type === "log" && msg.line) {
              setLogs(prev => [...prev, msg.line as string]);
            } else if (msg.type === "error") {
              throw new Error(msg.message || "Synthesis failed");
            } else if (msg.type === "done") {
              doneData = msg;
              if (msg.logs?.length) setLogs(msg.logs);
              if (msg.plan) setSynthesisPlan(msg.plan);
            }
          }
          newline = buffer.indexOf("\n");
        }
      }

      if (!doneData?.audio_base64) {
        throw new Error("No audio returned from server");
      }

      const blob = base64ToBlob(doneData.audio_base64 as string, "audio/wav");
      const file = new File([blob], `synthesis_${Date.now()}.wav`, { type: "audio/wav" });
      setLastAudioFile(file);
      setSaveLastName(text.trim().slice(0, 40) || "My voice");
      setSaveLastGender(speakerGender);
      setLastMeta({
        duration: doneData.duration_sec as number | undefined,
        device: doneData.device as string | undefined,
        sampleRate: doneData.sample_rate as number | undefined
      });

      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioUrl(URL.createObjectURL(blob));
    } catch (err: unknown) {
      console.error("Generation error:", err);
      const detail = err instanceof Error ? err.message : "request failed";
      setError(detail === "request failed" ? "Failed to generate audio. See log below." : detail);
      setLogs(prev => [...prev, `[…] Error: ${detail}`]);
    } finally {
      setLoading(false);
    }
  };

  const selectedVoice = pickerOptions.find(v => v.id === voiceSelect) || AUTO_VOICE;

  return (
    <Box sx={{ flexGrow: 1, p: 3 }}>
      <Typography
        variant="h4"
        sx={{
          mb: 4,
          fontWeight: "bold",
          background: "-webkit-linear-gradient(45deg, #7C4DFF 30%, #448AFF 90%)",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent"
        }}
      >
        VoxCPM2 Studio
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
                rows={4}
                placeholder="Enter the text you want to synthesize..."
                value={text}
                onChange={e => setText(e.target.value)}
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
          <Card elevation={3} sx={{ borderRadius: 3, height: "100%", display: "flex", flexDirection: "column" }}>
            <CardContent sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
              <Typography variant="h6" sx={{ mb: 3 }}>Output</Typography>
              <Button
                variant="contained"
                size="large"
                fullWidth
                onClick={handleGenerate}
                disabled={loading}
                sx={{
                  mb: 2,
                  py: 1.5,
                  background: "linear-gradient(135deg, #7C4DFF 0%, #448AFF 100%)",
                  fontWeight: "bold",
                  fontSize: "1.1rem"
                }}
              >
                {loading ? <CircularProgress size={26} color="inherit" /> : "Synthesize Audio"}
              </Button>

              <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: "bold" }}>
                Process log
              </Typography>
              <Box
                ref={logBoxRef}
                sx={{
                  mb: 2,
                  maxHeight: 180,
                  overflowY: "auto",
                  overflowX: "hidden",
                  bgcolor: "#0d1117",
                  color: "#c9d1d9",
                  borderRadius: 2,
                  p: 1.5,
                  fontFamily: "monospace",
                  fontSize: "0.75rem",
                  lineHeight: 1.5,
                  border: "1px solid",
                  borderColor: "divider",
                  overscrollBehavior: "contain",
                }}
              >
                {logs.length === 0 && loading ? (
                  <Typography variant="caption" sx={{ color: "#8b949e" }}>
                    Waiting for server…
                  </Typography>
                ) : logs.length === 0 ? (
                  <Typography variant="caption" sx={{ color: "#8b949e" }}>
                    Logs appear here while synthesizing…
                  </Typography>
                ) : (
                  logs.map((line, i) => <Box key={i}>{line}</Box>)
                )}
              </Box>

              {lastMeta && (
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                  {lastMeta.duration != null && `${lastMeta.duration}s`}
                  {lastMeta.sampleRate && ` · ${lastMeta.sampleRate} Hz`}
                  {lastMeta.device && ` · ${lastMeta.device.toUpperCase()}`}
                </Typography>
              )}

              <Box
                sx={{
                  mb: 2,
                  bgcolor: "background.default",
                  borderRadius: 2,
                  p: 2,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  border: "1px dashed",
                  borderColor: "divider",
                  minHeight: 80
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

              {synthesisPlan && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="caption" color="text.secondary" fontWeight="bold">
                    Synthesis plan
                  </Typography>
                  <Typography
                    variant="caption"
                    component="pre"
                    sx={{ whiteSpace: "pre-wrap", mt: 0.5, display: "block", color: "text.secondary" }}
                  >
                    {synthesisPlan}
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
