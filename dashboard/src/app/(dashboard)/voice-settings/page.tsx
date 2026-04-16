"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, postJSON, type WANumber, type VoiceConfig } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Loader2, Save, Volume2 } from "lucide-react";

const VOICE_LANGUAGES = [
  { value: "ms", label: "Malay (Bahasa Melayu)" },
  { value: "id", label: "Indonesian (Bahasa Indonesia)" },
  { value: "en", label: "English" },
];

const VOICE_MODES = [
  { value: "auto", label: "Auto" },
  { value: "voice_only", label: "Voice Only" },
  { value: "text_only", label: "Text Only" },
];

export default function VoiceSettingsPage() {
  const { data: waData } = useSWR<{ numbers: WANumber[] }>("/api/wa-numbers", fetcher);
  const [selectedSession, setSelectedSession] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const { data: voiceData, mutate: mutateVoice } = useSWR<VoiceConfig>(
    selectedSession ? `/api/voice-config/${selectedSession}` : null,
    fetcher,
    { refreshInterval: 0 }
  );

  const waNumbers = waData?.numbers ?? [];
  const currentConfig = voiceData ?? {
    voice_enabled: false,
    voice_reply_mode: "auto",
    voice_language: "ms",
  };

  async function saveVoiceConfig() {
    if (!selectedSession) return;
    setSaving(true);
    try {
      await postJSON(`/api/voice-config/${selectedSession}`, {
        voice_enabled: currentConfig.voice_enabled,
        voice_reply_mode: currentConfig.voice_reply_mode,
        voice_language: currentConfig.voice_language,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      console.error("Failed to save voice config:", e);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-2">
        <Volume2 className="h-6 w-6 text-orange-500" />
        <h1 className="text-2xl font-bold">Voice Settings</h1>
      </div>
      <p className="text-neutral-400">
        Configure voice reply settings for each WhatsApp number. When enabled, customers can send voice notes and receive AI responses as voice notes.
      </p>

      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader>
          <CardTitle>Select WhatsApp Number</CardTitle>
          <CardDescription>
            Choose which WA number to configure
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Select value={selectedSession} onValueChange={(v) => v && setSelectedSession(v)}>
            <SelectTrigger className="w-64 bg-neutral-800 border-neutral-700">
              <SelectValue placeholder="Select a WA number..." />
            </SelectTrigger>
            <SelectContent>
              {waNumbers.map((num) => (
                <SelectItem key={num.session_name} value={num.session_name}>
                  {num.label || num.session_name} ({num.phone})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {selectedSession && (
        <>
          <Card className="bg-neutral-900 border-neutral-800">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Volume2 className="h-4 w-4" />
                Voice Configuration
              </CardTitle>
              <CardDescription>
                Current: {waNumbers.find((n) => n.session_name === selectedSession)?.label || selectedSession}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <Label htmlFor="voice-enabled">Enable Voice Reply</Label>
                  <p className="text-sm text-neutral-500">
                    Allow customers to send voice notes and receive voice responses
                  </p>
                </div>
                <Switch
                  id="voice-enabled"
                  checked={currentConfig.voice_enabled}
                  onCheckedChange={(checked) =>
                    mutateVoice({ ...currentConfig, voice_enabled: checked }, false)
                  }
                />
              </div>

              <div className="space-y-3">
                <Label>Reply Mode</Label>
                <Select
                  value={currentConfig.voice_reply_mode}
                  onValueChange={(v) =>
                    v && mutateVoice({ ...currentConfig, voice_reply_mode: v }, false)
                  }
                >
                  <SelectTrigger className="w-48 bg-neutral-800 border-neutral-700">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VOICE_MODES.map((mode) => (
                      <SelectItem key={mode.value} value={mode.value}>
                        {mode.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-neutral-500">
                  Auto: Use voice when customer sends voice, text otherwise
                </p>
              </div>

              <div className="space-y-3">
                <Label>TTS Language</Label>
                <Select
                  value={currentConfig.voice_language}
                  onValueChange={(v) =>
                    v && mutateVoice({ ...currentConfig, voice_language: v }, false)
                  }
                >
                  <SelectTrigger className="w-48 bg-neutral-800 border-neutral-700">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VOICE_LANGUAGES.map((lang) => (
                      <SelectItem key={lang.value} value={lang.value}>
                        {lang.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-neutral-500">
                  Language for text-to-speech responses
                </p>
              </div>

              <Button
                onClick={saveVoiceConfig}
                disabled={saving}
                className="bg-orange-600 hover:bg-orange-700"
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : saved ? (
                  <Save className="h-4 w-4 mr-2" />
                ) : null}
                {saving ? "Saving..." : saved ? "Saved!" : "Save Configuration"}
              </Button>
            </CardContent>
          </Card>

          <Card className="bg-neutral-900 border-neutral-800">
            <CardHeader>
              <CardTitle>Status</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-4">
                <Badge variant={currentConfig.voice_enabled ? "default" : "secondary"}>
                  Voice: {currentConfig.voice_enabled ? "Enabled" : "Disabled"}
                </Badge>
                <Badge variant="outline">
                  Mode: {currentConfig.voice_reply_mode}
                </Badge>
                <Badge variant="outline">
                  Language: {currentConfig.voice_language}
                </Badge>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}