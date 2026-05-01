"use client";

import { Card, CardTitle } from "@/components/ui/Card";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-display">⚙️ 设置</h1>

      <Card>
        <CardTitle>模型配置</CardTitle>
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
        <CardTitle>API 信息</CardTitle>
        <div className="text-sm text-gray-400 space-y-2">
          <p>后端地址: http://localhost:8000</p>
          <p>API 文档: <a href="http://localhost:8000/docs" className="text-primary-light hover:underline" target="_blank">/docs</a></p>
          <p>版本: 2.0.0</p>
        </div>
      </Card>
    </div>
  );
}
