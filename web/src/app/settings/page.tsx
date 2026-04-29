"use client";

import { Card, CardTitle } from "@/components/ui/Card";
import { useAppStore } from "@/stores/app";

export default function SettingsPage() {
  const { theme, setTheme } = useAppStore();

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-display">⚙️ Settings</h1>

      <Card>
        <CardTitle>Appearance</CardTitle>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span>Theme</span>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value as "dark" | "light")}
              className="px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white"
            >
              <option value="dark">Dark</option>
              <option value="light">Light</option>
            </select>
          </div>
        </div>
      </Card>

      <Card>
        <CardTitle>Model Configuration</CardTitle>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-400">Model ID</label>
            <input
              type="text"
              value="NeoQuasar/Kronos-small"
              readOnly
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-gray-400 font-mono"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">Tokenizer ID</label>
            <input
              type="text"
              value="NeoQuasar/Kronos-Tokenizer-base"
              readOnly
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-gray-400 font-mono"
            />
          </div>
        </div>
      </Card>

      <Card>
        <CardTitle>API Info</CardTitle>
        <div className="text-sm text-gray-400 space-y-2">
          <p>Backend: http://localhost:8000</p>
          <p>Swagger Docs: <a href="http://localhost:8000/docs" className="text-primary-light hover:underline" target="_blank">/docs</a></p>
          <p>Version: 2.0.0</p>
        </div>
      </Card>
    </div>
  );
}
